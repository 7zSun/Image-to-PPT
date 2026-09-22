import json
import sys
from pathlib import Path

import pytest

from image2svg.ai.scripts.sam3_segment import _presentation_mask
from image2svg.analyze.external import ExternalToolError, run_bridge
from image2svg.analyze.models import (
    OcrResult,
    SegmentationResult,
    SegmentInstance,
    TextRegion,
)
from image2svg.analyze.ocr import OcrAnalyzer, OcrOptions
from image2svg.analyze.sam3 import Sam3Analyzer, Sam3Options
from image2svg.backends.base import VectorBackend
from image2svg.backends.composite import CompositeBackend
from image2svg.backends.layout import _font_family, _text_units
from image2svg.backends.ocr import OcrBackend
from image2svg.core.models import VectorResult
from image2svg.core.scene import Scene, SceneElement, merge_scenes
from image2svg.reconstruct.arrows import (
    FIXED_ARROW_COLOR,
    FIXED_ARROW_WIDTH,
    connect_arrows,
    render_arrow,
)
from image2svg.reconstruct.cleanup import (
    align_text_to_containers,
    deduplicate_scene,
    drop_baked_text,
    drop_duplicate_text,
    drop_text_backplates,
)
from image2svg.reconstruct.generate import generated_element
from image2svg.reconstruct.router import classify_instance
from image2svg.reconstruct.segments import element_from_instance, scene_from_segmentation
from image2svg.reconstruct.text import scene_from_ocr
from image2svg.svg.audit import audit_svg
from image2svg.svg.builder import build_svg


def _write_png(path: Path, size: tuple[int, int] = (40, 40)) -> None:
    from PIL import Image

    Image.new("RGBA", size, (255, 0, 0, 255)).save(path)


def test_run_bridge_reads_json_output(tmp_path: Path) -> None:
    script = tmp_path / "bridge.py"
    script.write_text(
        "import argparse, json\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--output')\n"
        "p.add_argument('--value')\n"
        "a = p.parse_args()\n"
        "json.dump({'value': a.value}, open(a.output, 'w'))\n",
        encoding="utf-8",
    )

    payload = run_bridge(
        sys.executable,
        script,
        ["--value", "42"],
        tmp_path / "out.json",
    )

    assert payload == {"value": "42"}


def test_run_bridge_raises_on_failure(tmp_path: Path) -> None:
    script = tmp_path / "boom.py"
    script.write_text("raise SystemExit(3)\n", encoding="utf-8")

    with pytest.raises(ExternalToolError):
        run_bridge(sys.executable, script, [], tmp_path / "out.json")


def _fake_bridge(monkeypatch, module: str, payload: dict) -> None:
    def fake(python, script, args, output_path, *, timeout=None, env=None):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr(f"{module}.run_bridge", fake)


def test_sam3_analyzer_parses_instances(tmp_path: Path, monkeypatch) -> None:
    payload = {
        "image": "demo.png",
        "width": 256,
        "height": 256,
        "prompts": ["circle"],
        "instances": [
            {
                "label": "circle",
                "score": 0.75,
                "box": [24.0, 140.0, 102.0, 218.0],
                "area": 3845,
                "color": "#EF4444",
                "crop_path": str(tmp_path / "crops" / "circle_000.png"),
            }
        ],
    }
    _fake_bridge(monkeypatch, "image2svg.analyze.sam3", payload)

    result = Sam3Analyzer(Sam3Options()).analyze(
        tmp_path / "demo.png", ["circle"], workdir=tmp_path
    )

    assert result.width == 256
    assert len(result.instances) == 1
    instance = result.instances[0]
    assert instance.label == "circle"
    assert instance.box == (24.0, 140.0, 102.0, 218.0)
    assert instance.color == "#EF4444"


def test_ocr_analyzer_parses_regions(tmp_path: Path, monkeypatch) -> None:
    payload = {
        "image": "demo.png",
        "width": 200,
        "height": 50,
        "regions": [{"text": "Hello", "score": 0.98, "box": [10.0, 5.0, 120.0, 40.0]}],
    }
    _fake_bridge(monkeypatch, "image2svg.analyze.ocr", payload)

    result = OcrAnalyzer(OcrOptions()).analyze(tmp_path / "demo.png", workdir=tmp_path)

    assert result.regions == [TextRegion("Hello", 0.98, (10.0, 5.0, 120.0, 40.0))]


def test_scene_from_segmentation_maps_primitives(tmp_path: Path) -> None:
    result = SegmentationResult(
        image_path=tmp_path / "demo.png",
        width=256,
        height=256,
        instances=[
            SegmentInstance("rectangle", 0.7, (20.0, 20.0, 237.0, 109.0), color="#2563EB"),
            SegmentInstance("circle", 0.75, (24.0, 140.0, 102.0, 218.0), color="#EF4444"),
            SegmentInstance("triangle", 0.88, (49.0, 141.0, 208.0, 221.0), color="#10B981"),
        ],
    )

    scene = scene_from_segmentation(result)
    svg = build_svg(scene)
    audit = audit_svg(svg)

    assert [element.type for element in scene.elements] == ["rect", "circle", "polygon"]
    assert audit.has_viewbox
    assert audit.element_counts["rect"] == 1
    assert audit.element_counts["circle"] == 1
    assert audit.element_counts["polygon"] == 1
    # No <path> element, so the "path_count > 0" rule keeps this at 80/100.
    assert audit.editable_score == 80


def test_scene_from_segmentation_falls_back_to_image(tmp_path: Path) -> None:
    crop = tmp_path / "crop.png"
    crop.write_bytes(b"\x89PNG\r\n\x1a\n fake")
    result = SegmentationResult(
        image_path=tmp_path / "demo.png",
        width=100,
        height=100,
        instances=[
            SegmentInstance("rocket", 0.6, (0.0, 0.0, 40.0, 40.0), crop_path=crop),
        ],
    )

    scene = scene_from_segmentation(result)

    assert scene.elements[0].type == "image"
    assert str(scene.elements[0].style["href"]).startswith("data:image/png;base64,")


def test_scene_from_segmentation_can_drop_unknown(tmp_path: Path) -> None:
    result = SegmentationResult(
        image_path=tmp_path / "demo.png",
        width=100,
        height=100,
        instances=[SegmentInstance("rocket", 0.6, (0.0, 0.0, 50.0, 50.0))],
    )

    scene = scene_from_segmentation(result, fallback="drop")

    assert scene.elements == []


def test_scene_from_segmentation_rejects_large_raster_fallback(tmp_path: Path) -> None:
    crop = tmp_path / "large.png"
    _write_png(crop)
    result = SegmentationResult(
        image_path=tmp_path / "demo.png",
        width=100,
        height=100,
        instances=[
            SegmentInstance(
                "photo",
                0.9,
                (0.0, 0.0, 80.0, 80.0),
                crop_path=crop,
                crop_box=(0.0, 0.0, 80.0, 80.0),
            )
        ],
    )

    scene = scene_from_segmentation(result, refine="vector")

    assert scene.elements == []


def test_geometry_fitting_takes_precedence(tmp_path: Path) -> None:
    result = SegmentationResult(
        image_path=tmp_path / "figure.png",
        width=200,
        height=200,
        instances=[
            SegmentInstance(
                "whatever",
                0.9,
                (0.0, 0.0, 10.0, 10.0),
                color="#2563EB",
                geometry={"kind": "rounded_rect", "bbox": [0.0, 0.0, 40.0, 20.0], "radius": 5},
            ),
            SegmentInstance(
                "whatever",
                0.9,
                (0.0, 0.0, 10.0, 10.0),
                geometry={"kind": "ellipse", "bbox": [0.0, 0.0, 20.0, 10.0]},
            ),
            SegmentInstance(
                "whatever",
                0.9,
                (0.0, 0.0, 10.0, 10.0),
                geometry={
                    "kind": "polygon",
                    "bbox": [0.0, 0.0, 30.0, 30.0],
                    "points": [[0.0, 0.0], [30.0, 0.0], [15.0, 30.0]],
                },
            ),
        ],
    )

    scene = scene_from_segmentation(result)

    assert [element.type for element in scene.elements] == ["rect", "ellipse", "polygon"]
    assert scene.elements[0].style["rx"] == 5
    assert scene.elements[2].points == [(0.0, 0.0), (30.0, 0.0), (15.0, 30.0)]


def test_scene_from_ocr_creates_text_elements() -> None:
    result = OcrResult(
        image_path=Path("demo.png"),
        width=200,
        height=50,
        regions=[TextRegion("Hello", 0.98, (10.0, 5.0, 120.0, 40.0))],
    )

    scene = scene_from_ocr(result)
    svg = build_svg(scene)
    audit = audit_svg(svg)

    assert scene.elements[0].type == "text"
    assert scene.elements[0].text == "Hello"
    assert audit.element_counts["text"] == 1
    assert ">Hello<" in svg


def test_merge_scenes_combines_elements() -> None:
    first = Scene(width=100, height=80, background="#FFFFFF")
    first.elements.append(SceneElement(id="a", type="rect", bbox=(0, 0, 10, 10)))
    second = Scene(width=120, height=90)
    second.elements.append(SceneElement(id="b", type="text", bbox=(0, 0, 10, 10), text="hi"))

    merged = merge_scenes([first, second])

    assert (merged.width, merged.height) == (120, 90)
    assert merged.background == "#FFFFFF"
    assert [element.id for element in merged.elements] == ["a", "b"]


def test_drop_baked_text_removes_text_inside_images() -> None:
    scene = Scene(width=200, height=200)
    scene.elements.append(
        SceneElement(id="img", type="image", bbox=(0, 0, 100, 100), style={"href": "data:,"})
    )
    scene.elements.append(
        SceneElement(id="baked", type="text", bbox=(40, 40, 20, 10), text="baked")
    )
    scene.elements.append(
        SceneElement(id="free", type="text", bbox=(150, 150, 20, 10), text="free")
    )

    drop_baked_text(scene)

    assert [element.id for element in scene.elements] == ["img", "free"]


def test_deduplicate_prefers_editable_rect_over_generic_image() -> None:
    scene = Scene(
        width=200,
        height=100,
        elements=[
            SceneElement(
                id="image",
                type="image",
                bbox=(10, 10, 100, 50),
                style={"href": "data:,", "semantic": "image"},
            ),
            SceneElement(
                id="rect",
                type="rect",
                bbox=(10, 10, 100, 50),
                style={"fill": "#FFFFFF", "semantic": "card"},
            ),
        ],
    )

    deduplicate_scene(scene)

    assert [element.id for element in scene.elements] == ["rect"]


def test_deduplicate_keeps_icon_nested_in_card() -> None:
    scene = Scene(
        width=200,
        height=100,
        elements=[
            SceneElement(id="card", type="rect", bbox=(0, 0, 100, 80)),
            SceneElement(id="icon", type="group", bbox=(20, 10, 40, 40), raw_svg="<path/>"),
        ],
    )

    deduplicate_scene(scene)

    assert [element.id for element in scene.elements] == ["card", "icon"]


def test_deduplicate_prefers_segmented_original_over_detector_rect() -> None:
    scene = Scene(
        width=200,
        height=100,
        elements=[
            SceneElement(
                id="panel",
                type="rect",
                bbox=(20, 10, 80, 60),
                style={"fill": "#FFFFFF", "source": "groundingdino"},
            ),
            SceneElement(
                id="segmented",
                type="image",
                bbox=(20, 10, 80, 60),
                style={"href": "data:,", "semantic": "icon", "source": "sam3"},
            ),
        ],
    )

    deduplicate_scene(scene)

    assert [element.id for element in scene.elements] == ["segmented"]


def test_drop_text_backplates_removes_tight_flat_regions() -> None:
    scene = Scene(
        width=300,
        height=100,
        elements=[
            SceneElement(id="artifact", type="rect", bbox=(10, 10, 120, 20)),
            SceneElement(id="card", type="rect", bbox=(0, 0, 280, 80)),
            SceneElement(id="text", type="text", bbox=(15, 11, 110, 18), text="Label"),
        ],
    )

    drop_text_backplates(scene)

    assert [element.id for element in scene.elements] == ["card", "text"]


def test_drop_duplicate_text_prefers_paddle_fragments_over_mineru_line() -> None:
    scene = Scene(
        width=400,
        height=100,
        elements=[
            SceneElement(
                id="layout",
                type="text",
                bbox=(10, 10, 360, 30),
                text="Reconstruction Agent collaborative system",
                style={"source": "mineru"},
            ),
            SceneElement(
                id="ocr-title",
                type="text",
                bbox=(12, 12, 150, 28),
                text="Reconstruction Agent",
                style={"source": "paddleocr"},
            ),
            SceneElement(
                id="ocr-subtitle",
                type="text",
                bbox=(170, 12, 195, 28),
                text="collaborative system",
                style={"source": "paddleocr"},
            ),
        ],
    )

    drop_duplicate_text(scene)

    assert [element.id for element in scene.elements] == ["ocr-title", "ocr-subtitle"]


def test_align_text_snaps_overlapping_title_into_panel() -> None:
    scene = Scene(
        width=1000,
        height=500,
        elements=[
            SceneElement(
                id="panel",
                type="rect",
                bbox=(200, 60, 600, 100),
                style={"fill": "#1577DB"},
            ),
            SceneElement(
                id="title",
                type="text",
                bbox=(370, 20, 280, 65),
                text="Title",
                style={"fill": "#1F61D1"},
            ),
        ],
    )

    align_text_to_containers(scene)

    title = scene.elements[1]
    assert title.bbox == (360.0, 77.5, 280, 65)
    assert title.style["align"] == "center"
    assert title.style["fill"] == "#FFFFFF"


def test_align_text_clamps_centered_label_to_card_coordinates() -> None:
    scene = Scene(
        width=400,
        height=200,
        elements=[
            SceneElement(
                id="card",
                type="rect",
                bbox=(100, 40, 160, 100),
                style={"fill": "#FFFFFF"},
            ),
            SceneElement(
                id="label",
                type="text",
                bbox=(94, 90, 130, 24),
                text="Centered label",
                style={"fill": "#111111"},
            ),
        ],
    )

    align_text_to_containers(scene)

    label = scene.elements[1]
    assert label.bbox == (115.0, 90, 130, 24)
    assert label.style["align"] == "center"


def test_connect_arrows_snaps_and_records_relationships() -> None:
    arrow_style = {
        "arrow_start": [45.0, 50.0],
        "arrow_end": [155.0, 50.0],
        "stroke": "#000000",
        "stroke_width": 2.0,
    }
    scene = Scene(
        width=200,
        height=120,
        elements=[
            SceneElement(id="left", type="rect", bbox=(0, 30, 40, 40)),
            SceneElement(id="right", type="rect", bbox=(160, 30, 40, 40)),
            SceneElement(
                id="arrow",
                type="group",
                bbox=(45, 50, 110, 0),
                style=arrow_style,
                raw_svg=render_arrow((45, 50), (155, 50), "#000000", 2.0),
            ),
            SceneElement(
                id="noise",
                type="group",
                bbox=(70, 100, 30, 0),
                style={
                    "arrow_start": [70.0, 100.0],
                    "arrow_end": [100.0, 100.0],
                    "stroke": "#000000",
                    "stroke_width": 2.0,
                },
                raw_svg=render_arrow((70, 100), (100, 100), "#000000", 2.0),
            ),
        ],
    )

    connect_arrows(scene, max_snap=12.0)

    arrow = next(element for element in scene.elements if element.id == "arrow")
    assert arrow.style["arrow_start"] == [40, 50.0]
    assert arrow.style["arrow_end"] == [160, 50.0]
    assert arrow.style["connector_start"] == "left"
    assert arrow.style["connector_end"] == "right"
    assert all(element.id != "noise" for element in scene.elements)


def test_connect_arrows_infers_relationship_and_uses_fixed_style() -> None:
    scene = Scene(
        width=300,
        height=200,
        elements=[
            SceneElement(id="source", type="rect", bbox=(20, 20, 80, 50)),
            SceneElement(id="target", type="rect", bbox=(200, 130, 80, 50)),
            SceneElement(
                id="arrow",
                type="group",
                bbox=(145, 90, 10, 10),
                style={
                    "arrow_start": [155.0, 100.0],
                    "arrow_end": [145.0, 90.0],
                    "stroke": "#FF00FF",
                    "stroke_width": 9.0,
                },
            ),
        ],
    )

    connect_arrows(scene)

    arrow = next(element for element in scene.elements if element.id == "arrow")
    assert arrow.style["connector_start"] == "source"
    assert arrow.style["connector_end"] == "target"
    assert arrow.style["stroke"] == FIXED_ARROW_COLOR
    assert arrow.style["stroke_width"] == FIXED_ARROW_WIDTH
    assert arrow.style["arrowhead"] is True


def test_sam_arrow_outline_becomes_fixed_connector() -> None:
    instance = SegmentInstance(
        label="arrow",
        score=0.9,
        box=(10, 10, 20, 50),
        geometry={
            "kind": "polygon",
            "bbox": [10, 10, 20, 50],
            "points": [[14, 10], [16, 10], [16, 42], [20, 42], [15, 50], [10, 42]],
        },
    )

    element = element_from_instance(instance, 0, refine="vector")

    assert element is not None
    assert element.type == "group"
    assert element.style["arrow_start"] == [15.0, 10.0]
    assert element.style["arrow_end"] == [15.0, 50.0]
    assert element.style["stroke"] == FIXED_ARROW_COLOR


def test_presentation_mask_dilates_icons_and_regularizes_rectangles() -> None:
    from PIL import Image, ImageDraw

    icon = Image.new("L", (30, 30), 0)
    ImageDraw.Draw(icon).ellipse((8, 8, 21, 21), fill=255)
    smoothed, mode = _presentation_mask(
        icon, "logo", {"kind": "polygon", "bbox": [8, 8, 22, 22]}
    )
    assert mode == "dilated"
    assert smoothed.getbbox()[0] < icon.getbbox()[0]

    rectangle = Image.new("L", (30, 30), 0)
    ImageDraw.Draw(rectangle).rectangle((6, 8, 23, 21), fill=255)
    regularized, mode = _presentation_mask(
        rectangle, "document", {"kind": "rect", "bbox": [6, 8, 24, 22]}
    )
    assert mode == "rectangle"
    assert regularized.getbbox()[0] < rectangle.getbbox()[0]


def test_text_metrics_handle_cjk() -> None:
    assert _font_family("分析智能体").startswith("Microsoft YaHei")
    assert _text_units("分析") > _text_units("AB")


def test_ocr_backend_reconstructs_text(tmp_path: Path, monkeypatch) -> None:
    payload = {
        "image": "demo.png",
        "width": 200,
        "height": 60,
        "regions": [{"text": "Hi", "score": 0.9, "box": [5.0, 5.0, 80.0, 45.0]}],
    }
    _fake_bridge(monkeypatch, "image2svg.analyze.ocr", payload)

    result = OcrBackend(options=OcrOptions(), background="#FFFFFF").reconstruct(
        tmp_path / "demo.png"
    )

    assert result.scene is not None
    assert result.scene.elements[0].type == "text"
    assert result.scene.background == "#FFFFFF"


def test_composite_backend_merges_two_scenes(tmp_path: Path) -> None:
    class RectBackend(VectorBackend):
        name = "rect"

        def reconstruct(self, image_path: Path) -> VectorResult:
            scene = Scene(width=50, height=50)
            scene.elements.append(SceneElement(id="r", type="rect", bbox=(0, 0, 5, 5)))
            return VectorResult(scene=scene)

    class TextBackend(VectorBackend):
        name = "text"

        def reconstruct(self, image_path: Path) -> VectorResult:
            scene = Scene(width=50, height=50)
            scene.elements.append(
                SceneElement(id="t", type="text", bbox=(0, 0, 5, 5), text="hi")
            )
            return VectorResult(scene=scene)

    result = CompositeBackend([RectBackend(), TextBackend()]).reconstruct(tmp_path / "i.png")

    assert result.scene is not None
    assert [element.id for element in result.scene.elements] == ["r", "t"]
    assert result.metadata["parts"] == ["rect", "text"]


def test_builder_emits_raw_svg_group() -> None:
    element = SceneElement(
        id="g",
        type="group",
        bbox=(10, 20, 30, 40),
        raw_svg='<path d="M0 0 L1 1 Z"/>',
    )

    svg = build_svg(Scene(width=100, height=100, elements=[element]))

    assert '<g id="g" transform="translate(10,20)">' in svg
    assert '<path d="M0 0 L1 1 Z"/>' in svg


def test_local_trace_produces_editable_paths(tmp_path: Path) -> None:
    from PIL import Image, ImageDraw

    from image2svg.reconstruct.trace import trace_svg, traced_element

    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((4, 4, 28, 28), fill=(37, 99, 235, 255))
    crop = tmp_path / "crop.png"
    image.save(crop)

    assert "<path" in trace_svg(crop)

    element = traced_element(crop, (0, 0, 32, 32), element_id="t")
    assert element is not None and element.raw_svg
    audit = audit_svg(build_svg(Scene(width=32, height=32, elements=[element])))
    assert audit.element_counts["path"] >= 1


def test_refine_geometry_keeps_polygon(tmp_path: Path) -> None:
    instance = SegmentInstance(
        "icon",
        0.8,
        (0.0, 0.0, 10.0, 10.0),
        geometry={
            "kind": "polygon",
            "bbox": [0.0, 0.0, 30.0, 30.0],
            "points": [[0.0, 0.0], [30.0, 0.0], [15.0, 30.0]],
        },
    )

    element = element_from_instance(instance, 0, refine="geometry")

    assert element is not None and element.type == "polygon"


def test_router_classifies_segments() -> None:
    clean = SegmentInstance(
        "card", 0.9, (0.0, 0.0, 400.0, 200.0), geometry={"kind": "rounded_rect"}
    )
    icon = SegmentInstance(
        "icon",
        0.8,
        (0.0, 0.0, 40.0, 40.0),
        stats={"colors": 5, "vertices": 30, "solidity": 0.6},
    )
    flat = SegmentInstance(
        "shape",
        0.8,
        (0.0, 0.0, 300.0, 300.0),
        stats={"colors": 1, "vertices": 4, "solidity": 0.99},
    )

    image_area = 1000.0 * 1000.0
    assert classify_instance(clean, image_area) == "primitive"
    assert classify_instance(icon, image_area) == "generate"
    assert classify_instance(flat, image_area) == "trace"


def test_router_marks_textured_regions_as_raster() -> None:
    photo = SegmentInstance(
        "photo",
        0.9,
        (0.0, 0.0, 500.0, 400.0),
        geometry={"kind": "rect", "bbox": [0.0, 0.0, 500.0, 400.0]},
        stats={"colors": 40, "vertices": 12, "solidity": 0.8},
    )

    assert classify_instance(photo, 1000.0 * 1000.0) == "raster"


def test_router_preserves_multicolor_segmented_icon() -> None:
    icon = SegmentInstance(
        "icon",
        0.9,
        (0.0, 0.0, 120.0, 100.0),
        geometry={"kind": "polygon"},
        stats={"colors": 80, "vertices": 12, "solidity": 0.9},
    )

    assert classify_instance(icon, 1000.0 * 1000.0) == "raster"


def test_generated_element_scales_to_bbox(tmp_path: Path) -> None:
    class FakeGenerator:
        def generate(self, crop_path: Path, workdir: Path) -> str:
            return (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">'
                '<path d="M0 0 L100 50 L0 50 Z" fill="#000000"/></svg>'
            )

    element = generated_element(
        FakeGenerator(),
        tmp_path / "crop.png",
        (10.0, 20.0, 200.0, 100.0),
        element_id="gen",
        workdir=tmp_path,
    )

    assert element is not None and element.raw_svg
    assert 'width="200"' in element.raw_svg
    assert 'height="100"' in element.raw_svg
    assert 'viewBox="0 0 100 50"' in element.raw_svg
    svg = build_svg(Scene(width=300, height=300, elements=[element]))
    assert 'transform="translate(10,20)"' in svg
    assert audit_svg(svg).element_counts["path"] == 1


def test_router_uses_generator_for_icons(tmp_path: Path) -> None:
    crop = tmp_path / "crop.png"
    _write_png(crop)
    result = SegmentationResult(
        image_path=tmp_path / "figure.png",
        width=1000,
        height=1000,
        instances=[
            SegmentInstance(
                "icon",
                0.8,
                (0.0, 0.0, 40.0, 40.0),
                crop_path=crop,
                crop_box=(0.0, 0.0, 40.0, 40.0),
                stats={"colors": 5, "vertices": 30, "solidity": 0.6},
            )
        ],
    )

    class FakeGenerator:
        def generate(self, crop_path: Path, workdir: Path) -> str:
            return (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">'
                '<path d="M0 0 L40 40 Z" fill="#123456"/></svg>'
            )

    scene = scene_from_segmentation(
        result, refine="router", generator=FakeGenerator(), workdir=tmp_path
    )

    assert len(scene.elements) == 1
    element = scene.elements[0]
    assert element.type == "group"
    assert element.raw_svg is not None
    assert "L40 40" in element.raw_svg
