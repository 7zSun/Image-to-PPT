from pathlib import Path

import pytest

from image2svg.backends.base import VectorBackend
from image2svg.core.models import VectorResult
from image2svg.core.scene import Scene, SceneElement
from image2svg.pipeline import Image2SvgPipeline
from image2svg.svg.audit import audit_svg
from image2svg.svg.builder import build_svg


def _scene() -> Scene:
    return Scene(
        width=100,
        height=80,
        background="#FFFFFF",
        elements=[
            SceneElement(
                id="shape_2",
                type="rect",
                bbox=(0, 0, 10, 10),
                style={"fill": "#2563EB"},
                z_index=5,
            ),
            SceneElement(
                id="shape_1",
                type="path",
                bbox=(0, 0, 10, 10),
                path_d="M0 0 L10 10 Z",
                style={"fill": "#000000"},
                z_index=1,
            ),
            SceneElement(id="dot", type="circle", bbox=(10, 10, 20, 20), style={"fill": "#EF4444"}),
            SceneElement(
                id="oval", type="ellipse", bbox=(40, 10, 20, 10), style={"fill": "#10B981"}
            ),
            SceneElement(
                id="tri",
                type="polygon",
                bbox=(0, 40, 40, 40),
                points=[(0, 80), (40, 80), (20, 40)],
                style={"fill": "#F59E0B"},
            ),
            SceneElement(
                id="label",
                type="text",
                bbox=(5, 60, 60, 15),
                text="Demo <SVG>",
                style={"font-size": 12, "fill": "#111827"},
            ),
        ],
    )


def test_build_svg_has_viewbox_and_dimensions() -> None:
    svg = build_svg(_scene())

    assert 'viewBox="0 0 100 80"' in svg
    assert 'width="100"' in svg
    assert 'height="80"' in svg
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")


def test_build_svg_respects_z_order() -> None:
    svg = build_svg(_scene())

    assert svg.index('id="shape_1"') < svg.index('id="shape_2"')


def test_build_svg_emits_supported_elements() -> None:
    svg = build_svg(_scene())

    assert "<rect" in svg
    assert "<circle" in svg
    assert "<ellipse" in svg
    assert "<polygon" in svg
    assert "<path" in svg
    assert "<text" in svg


def test_build_svg_escapes_text_content() -> None:
    svg = build_svg(_scene())

    assert "Demo &lt;SVG&gt;" in svg


def test_built_svg_is_editable_with_full_score() -> None:
    audit = audit_svg(build_svg(_scene()))

    assert audit.valid_xml
    assert audit.has_viewbox
    assert audit.element_counts == {
        "path": 1,
        "rect": 2,
        "circle": 1,
        "ellipse": 1,
        "polygon": 1,
        "text": 1,
    }
    assert audit.editable_score == 100


def test_build_svg_rejects_unknown_element_type() -> None:
    scene = Scene(
        width=10,
        height=10,
        elements=[SceneElement(id="x", type="hexagon", bbox=(0, 0, 1, 1))],
    )

    with pytest.raises(ValueError):
        build_svg(scene)


def test_group_element_wraps_children() -> None:
    child = SceneElement(id="child", type="rect", bbox=(0, 0, 5, 5), style={"fill": "#000"})
    group = SceneElement(id="g1", type="group", bbox=(0, 0, 5, 5), children=[child])

    svg = build_svg(Scene(width=10, height=10, elements=[group]))

    assert '<g id="g1">' in svg
    assert 'id="child"' in svg


class FakeSceneBackend(VectorBackend):
    name = "fake-scene"

    def reconstruct(self, image_path: Path) -> VectorResult:
        return VectorResult(scene=_scene())


def test_pipeline_builds_svg_from_scene(tmp_path: Path) -> None:
    source = tmp_path / "input.png"
    source.write_bytes(b"not-read-by-fake-backend")
    output = tmp_path / "output.svg"

    result = Image2SvgPipeline(FakeSceneBackend()).run(source, output, qa=False)

    written = output.read_text(encoding="utf-8")
    assert "viewBox" in written
    assert result.audit.has_viewbox
    assert result.audit.editable_score == 100
