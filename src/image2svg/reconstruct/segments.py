from __future__ import annotations

import base64
from pathlib import Path

from PIL import Image

from image2svg.analyze.models import SegmentationResult, SegmentInstance
from image2svg.core.scene import Scene, SceneElement
from image2svg.reconstruct.arrows import render_arrow
from image2svg.reconstruct.generate import SvgGenerator, generated_element
from image2svg.reconstruct.router import classify_instance
from image2svg.reconstruct.trace import traced_element

#: Maps open-vocabulary labels to editable SVG primitives.
_PRIMITIVE_LABELS: dict[str, str] = {
    "rectangle": "rect",
    "rect": "rect",
    "square": "rect",
    "box": "rect",
    "card": "rect",
    "circle": "circle",
    "dot": "circle",
    "ellipse": "ellipse",
    "oval": "ellipse",
    "triangle": "polygon",
    "line": "line",
}

#: Fitted geometry kinds that map cleanly onto primitives.
_CLEAN_GEOMETRY = ("rect", "rounded_rect", "ellipse")


def _data_uri(path: Path) -> str:
    data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _fill_style(instance: SegmentInstance) -> dict[str, object]:
    return {"fill": instance.color} if instance.color else {}


def _crop_bbox(instance: SegmentInstance) -> tuple[float, float, float, float]:
    if instance.crop_box:
        x0, y0, x1, y1 = instance.crop_box
    else:
        x0, y0, x1, y1 = instance.box
    return (x0, y0, x1 - x0, y1 - y0)


def _geometry_element(
    instance: SegmentInstance, index: int, prefix: str
) -> SceneElement | None:
    """Build an element from a fitted geometry produced by the AI bridge."""
    geometry = instance.geometry
    if not geometry:
        return None

    kind = geometry.get("kind")

    if kind == "arrow":
        start = geometry.get("start")
        end = geometry.get("end")
        if not start or not end:
            return None
        sx, sy = float(start[0]), float(start[1])
        ex, ey = float(end[0]), float(end[1])
        color = geometry.get("stroke") or instance.color or "#333333"
        width = float(geometry.get("stroke_width", 2.0))
        markup = render_arrow((sx, sy), (ex, ey), color, width)
        if not markup:
            return None
        pad = max(8.0, width * 3.2)
        return SceneElement(
            id=f"{prefix}_arrow_{index}",
            type="group",
            bbox=(
                min(sx, ex) - pad,
                min(sy, ey) - pad,
                abs(ex - sx) + 2 * pad,
                abs(ey - sy) + 2 * pad,
            ),
            z_index=2,
            raw_svg=markup,
            style={
                "transform": "translate(0,0)",
                "arrow_start": [sx, sy],
                "arrow_end": [ex, ey],
                "stroke": color,
                "stroke_width": width,
            },
        )

    box = geometry.get("bbox", instance.box)
    x0, y0, x1, y1 = (float(value) for value in box)
    bbox = (x0, y0, x1 - x0, y1 - y0)
    style = _fill_style(instance)

    if kind == "rect":
        return SceneElement(id=f"{prefix}_rect_{index}", type="rect", bbox=bbox, style=style)
    if kind == "rounded_rect":
        rounded_style: dict[str, object] = dict(style)
        rounded_style["rx"] = geometry.get("radius", 0)
        if geometry.get("stroke") and geometry.get("stroke") != instance.color:
            rounded_style["stroke"] = geometry["stroke"]
            rounded_style["stroke-width"] = geometry.get("stroke_width", 2.0)
        return SceneElement(
            id=f"{prefix}_rect_{index}", type="rect", bbox=bbox, style=rounded_style
        )
    if kind == "ellipse":
        return SceneElement(id=f"{prefix}_ellipse_{index}", type="ellipse", bbox=bbox, style=style)
    if kind == "polygon":
        points = [tuple(float(value) for value in point) for point in geometry.get("points", [])]
        if len(points) < 3:
            return None
        return SceneElement(
            id=f"{prefix}_polygon_{index}",
            type="polygon",
            bbox=bbox,
            points=points,
            style=style,
        )
    return None


def _trace_element(
    instance: SegmentInstance, index: int, prefix: str
) -> SceneElement | None:
    if instance.crop_path is None:
        return None
    crop_path = Path(instance.crop_path)
    if not crop_path.exists():
        return None

    try:
        with Image.open(crop_path) as image:
            image.verify()
    except Exception:  # noqa: BLE001 - not a usable image, skip tracing
        return None

    try:
        return traced_element(
            crop_path,
            _crop_bbox(instance),
            element_id=f"{prefix}_trace_{index}",
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:  # noqa: BLE001 - vtracer raises pyo3 PanicException
        return None


def _image_element(
    instance: SegmentInstance, index: int, prefix: str
) -> SceneElement | None:
    if instance.crop_path is None:
        return None
    crop_path = Path(instance.crop_path)
    if not crop_path.exists():
        return None
    style: dict[str, object] = dict(_fill_style(instance))
    style["href"] = _data_uri(crop_path)
    return SceneElement(
        id=f"{prefix}_image_{index}",
        type="image",
        bbox=_crop_bbox(instance) if instance.crop_box else (
            instance.box[0],
            instance.box[1],
            instance.box[2] - instance.box[0],
            instance.box[3] - instance.box[1],
        ),
        style=style,
    )


def _generate_element(
    instance: SegmentInstance,
    index: int,
    prefix: str,
    generator: SvgGenerator | None,
    workdir: Path | None,
) -> SceneElement | None:
    if generator is None or workdir is None or instance.crop_path is None:
        return None
    crop_path = Path(instance.crop_path)
    if not crop_path.exists():
        return None
    return generated_element(
        generator,
        crop_path,
        _crop_bbox(instance),
        element_id=f"{prefix}_gen_{index}",
        workdir=workdir,
    )


def element_from_instance(
    instance: SegmentInstance,
    index: int,
    *,
    prefix: str = "ai",
    fallback: str = "image",
    refine: str = "trace",
    image_area: float = 0.0,
    generator: SvgGenerator | None = None,
    workdir: Path | None = None,
) -> SceneElement | None:
    """Reconstruct one editable element from a segmentation instance.

    ``refine`` controls how non-primitive segments are handled:

    * ``"router"``: classify each segment (primitive / trace / generate).
    * ``"trace"`` (default): vectorize the masked crop with VTracer.
    * ``"generate"``: generate SVG with a generative backend, else trace.
    * ``"geometry"``: use the fitted polygon.
    * ``"image"``: embed the masked crop as a raster fallback.
    """
    geometry = instance.geometry
    kind = geometry.get("kind") if geometry else None

    if refine == "raster":
        # Only keep textured content (photos / renders); drop everything else.
        if classify_instance(instance, image_area) == "raster":
            return _image_element(instance, index, prefix)
        return None

    if refine == "vector":
        # Keep photos/renders as pixels, vectorize everything else.
        if classify_instance(instance, image_area) == "raster":
            return _image_element(instance, index, prefix)
        traced = _trace_element(instance, index, prefix)
        if traced is not None:
            return traced
        return None

    decision = classify_instance(instance, image_area) if refine == "router" else refine

    # Textured (raster) content keeps its original pixels, even if its outline
    # is rectangular.
    if decision in ("raster", "image"):
        image = _image_element(instance, index, prefix)
        if image is not None:
            return image

    if kind in _CLEAN_GEOMETRY:
        return _geometry_element(instance, index, prefix)

    if kind == "arrow":
        element = _geometry_element(instance, index, prefix)
        if element is not None:
            return element

    if decision == "generate":
        generated = _generate_element(instance, index, prefix, generator, workdir)
        if generated is not None:
            return generated
        generated = _trace_element(instance, index, prefix)
        if generated is not None:
            return generated
    else:  # "trace" or an unknown decision
        traced = _trace_element(instance, index, prefix)
        if traced is not None:
            return traced

    if geometry is not None:
        element = _geometry_element(instance, index, prefix)
        if element is not None:
            return element

    x0, y0, x1, y1 = instance.box
    bbox = (x0, y0, x1 - x0, y1 - y0)
    label = instance.label.strip().lower()
    style = _fill_style(instance)
    primitive = _PRIMITIVE_LABELS.get(label)

    if primitive == "rect":
        return SceneElement(id=f"{prefix}_rect_{index}", type="rect", bbox=bbox, style=style)
    if primitive == "circle":
        return SceneElement(id=f"{prefix}_circle_{index}", type="circle", bbox=bbox, style=style)
    if primitive == "ellipse":
        return SceneElement(id=f"{prefix}_ellipse_{index}", type="ellipse", bbox=bbox, style=style)
    if primitive == "polygon":
        points = [(x0, y1), (x1, y1), ((x0 + x1) / 2, y0)]
        return SceneElement(
            id=f"{prefix}_polygon_{index}",
            type="polygon",
            bbox=bbox,
            points=points,
            style=style,
        )
    if primitive == "line":
        middle = (y0 + y1) / 2
        line_style = {"stroke": instance.color or "#000000", "stroke-width": 2}
        return SceneElement(
            id=f"{prefix}_line_{index}",
            type="line",
            bbox=bbox,
            points=[(x0, middle), (x1, middle)],
            style=line_style,
        )

    if fallback == "image":
        return _image_element(instance, index, prefix)
    return None


def scene_from_segmentation(
    result: SegmentationResult,
    *,
    background: str | None = None,
    prefix: str = "ai",
    fallback: str = "image",
    refine: str = "trace",
    generator: SvgGenerator | None = None,
    workdir: Path | None = None,
) -> Scene:
    """Build a Scene from SAM3 instances, keeping primitives editable."""
    image_area = float(result.width) * float(result.height)
    elements: list[SceneElement] = []
    for index, instance in enumerate(result.instances):
        element = element_from_instance(
            instance,
            index,
            prefix=prefix,
            fallback=fallback,
            refine=refine,
            image_area=image_area,
            generator=generator,
            workdir=workdir,
        )
        if element is not None:
            elements.append(element)
    return Scene(
        width=result.width,
        height=result.height,
        background=background,
        elements=elements,
    )
