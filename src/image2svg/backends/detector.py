from __future__ import annotations

import base64
from pathlib import Path
from tempfile import TemporaryDirectory

from image2svg.analyze.detector import DetectorOptions, GroundingDinoAnalyzer
from image2svg.backends.base import VectorBackend
from image2svg.core.models import VectorResult
from image2svg.core.scene import Scene, SceneElement
from image2svg.reconstruct.arrows import render_arrow
from image2svg.reconstruct.trace import traced_element

#: Detection labels rendered as clean rectangles when the region is flat.
PANEL_LABELS = {
    "panel",
    "card",
    "section",
    "banner",
    "box",
    "container",
    "table",
    "frame",
    "border",
    "stage",
    "rounded rectangle",
    "rectangle",
    "button",
}
#: Above this many distinct colors the region keeps its original pixels.
RASTER_COLORS = 12


def _data_uri(path: Path) -> str:
    data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _arrow_element(instance, index: int, bbox) -> SceneElement | None:
    geometry = instance.geometry or {}
    start = geometry.get("start")
    end = geometry.get("end")
    if not start or not end:
        return None
    x0, y0 = bbox[0], bbox[1]
    sx, sy = x0 + float(start[0]), y0 + float(start[1])
    ex, ey = x0 + float(end[0]), y0 + float(end[1])
    color = geometry.get("stroke") or instance.color or "#333333"
    width = float(geometry.get("stroke_width", 2.0))
    markup = render_arrow((sx, sy), (ex, ey), color, width)
    if not markup:
        return None
    return SceneElement(
        id=f"detect_arrow_{index}",
        type="group",
        bbox=(min(sx, ex), min(sy, ey), abs(ex - sx), abs(ey - sy)),
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


class DetectorBackend(VectorBackend):
    """Structure + content layer from GroundingDINO.

    Flat panel/card regions become clean rectangles; textured regions
    (photos / renders / charts) keep their original pixels as embedded crops;
    small flat icons are traced.
    """

    name = "detector"

    def __init__(
        self,
        *,
        options: DetectorOptions | None = None,
        background: str | None = None,
        radius: float = 12.0,
        embed_raster: bool = True,
        structure_only: bool = False,
        arrows_only: bool = False,
    ) -> None:
        self.options = options or DetectorOptions()
        self.background = background
        self.radius = radius
        self.embed_raster = embed_raster
        self.structure_only = structure_only
        self.arrows_only = arrows_only

    def reconstruct(self, image_path: Path) -> VectorResult:
        image_path = Path(image_path)
        with TemporaryDirectory(prefix="image2svg-detect-") as tmp:
            result = GroundingDinoAnalyzer(self.options).analyze(
                image_path, workdir=Path(tmp)
            )
            elements: list[SceneElement] = []
            for index, instance in enumerate(result.instances):
                label = instance.label.strip().lower()
                x0, y0, x1, y1 = (float(value) for value in instance.box)
                bbox = (x0, y0, x1 - x0, y1 - y0)
                crop_path = instance.crop_path
                crop_bbox = bbox
                if instance.crop_box:
                    cx0, cy0, cx1, cy1 = instance.crop_box
                    crop_bbox = (cx0, cy0, cx1 - cx0, cy1 - cy0)

                colors = int((instance.stats or {}).get("colors", 1))

                if self.arrows_only:
                    if (instance.geometry or {}).get("kind") == "arrow":
                        arrow = _arrow_element(instance, index, bbox)
                        if arrow is not None:
                            elements.append(arrow)
                    continue

                if (instance.geometry or {}).get("kind") == "arrow":
                    arrow = _arrow_element(instance, index, bbox)
                    if arrow is not None:
                        elements.append(arrow)
                    continue

                # Panels/cards stay editable rectangles (never whole-card raster).
                if label in PANEL_LABELS:
                    style: dict[str, object] = {"rx": self.radius}
                    if instance.color:
                        style["fill"] = instance.color
                    stroke = (instance.geometry or {}).get("stroke")
                    if stroke and stroke != instance.color:
                        style["stroke"] = stroke
                        style["stroke-width"] = 2
                    elements.append(
                        SceneElement(
                            id=f"detect_rect_{index}",
                            type="rect",
                            bbox=bbox,
                            style=style,
                        )
                    )
                    continue

                if self.structure_only:
                    # When MinerU provides the content, only draw structure.
                    continue

                # Non-panel textured objects (photos, 3D renders, charts) keep
                # their original pixels.
                if (
                    self.embed_raster
                    and colors >= RASTER_COLORS
                    and crop_path
                    and Path(crop_path).exists()
                ):
                    elements.append(
                        SceneElement(
                            id=f"detect_image_{index}",
                            type="image",
                            bbox=crop_bbox,
                            style={"href": _data_uri(Path(crop_path))},
                        )
                    )
                    continue

                if crop_path is None or not Path(crop_path).exists():
                    continue
                element = traced_element(
                    Path(crop_path),
                    crop_bbox,
                    element_id=f"detect_trace_{index}",
                )
                if element is not None:
                    elements.append(element)

            scene = Scene(
                width=result.width,
                height=result.height,
                background=self.background,
                elements=elements,
            )
        return VectorResult(
            scene=scene,
            metadata={"backend": self.name, "detections": len(result.instances)},
        )

