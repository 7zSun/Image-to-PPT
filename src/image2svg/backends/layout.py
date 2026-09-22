from __future__ import annotations

import base64
import unicodedata
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from image2svg.analyze.layout import LayoutOptions, MineruLayoutAnalyzer
from image2svg.backends.base import VectorBackend
from image2svg.core.models import VectorResult
from image2svg.core.scene import Scene, SceneElement
from image2svg.reconstruct.text_metrics import fit_text_element
from image2svg.reconstruct.trace import traced_element

DEFAULT_FONT_FAMILY = "Arial, Helvetica, 'Segoe UI', sans-serif"
DEFAULT_CJK_FONT_FAMILY = "Microsoft YaHei, 'Segoe UI', Arial, sans-serif"
_FONT_SIZE_RATIO = 0.9
_BASELINE_RATIO = 0.82


def _data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _font_family(text: str) -> str:
    if any(unicodedata.east_asian_width(character) in {"W", "F"} for character in text):
        return DEFAULT_CJK_FONT_FAMILY
    return DEFAULT_FONT_FAMILY


def _text_units(text: str) -> float:
    units = 0.0
    for character in text:
        width = unicodedata.east_asian_width(character)
        if character.isspace():
            units += 0.32
        elif width in {"W", "F"}:
            units += 1.0
        elif character.isupper():
            units += 0.68
        else:
            units += 0.55
    return max(1.0, units)


def _contains(box: tuple[float, float, float, float], point: tuple[float, float]) -> bool:
    x0, y0, x1, y1 = box
    return x0 <= point[0] <= x1 and y0 <= point[1] <= y1


def _alignment(
    box: tuple[float, float, float, float],
    containers: list[tuple[float, float, float, float]],
    scene_width: float,
) -> str:
    x0, y0, x1, y1 = box
    center = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    matches = [candidate for candidate in containers if _contains(candidate, center)]
    if matches:
        container = min(matches, key=lambda candidate: (candidate[2] - candidate[0]) * (candidate[3] - candidate[1]))
        cx = (container[0] + container[2]) / 2.0
        if abs(center[0] - cx) <= max(8.0, (container[2] - container[0]) * 0.08):
            return "center"
    if x1 - x0 >= scene_width * 0.25 and abs(center[0] - scene_width / 2.0) <= scene_width * 0.06:
        return "center"
    return "left"


def _should_trace(path: Path, area_ratio: float) -> bool:
    if area_ratio > 0.025:
        return False
    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail((96, 96))
        quantized = image.quantize(colors=32)
        colors = quantized.getcolors(maxcolors=32) or []
    if not colors:
        return False
    dominant = max(count for count, _value in colors) / max(1, sum(count for count, _value in colors))
    return len(colors) <= 12 and dominant >= 0.35


class LayoutBackend(VectorBackend):
    """MinerU-driven reconstruction: real text boxes + real image regions.

    This is the anti-baking backend: text becomes editable <text> and only the
    genuine figure/chart regions are embedded as images.
    """

    name = "layout"

    def __init__(
        self,
        *,
        options: LayoutOptions | None = None,
        background: str | None = None,
        max_raster_area_ratio: float = 0.18,
        trace_small_graphics: bool = True,
        embed_raster: bool = True,
        include_text: bool = True,
    ) -> None:
        self.options = options or LayoutOptions()
        self.background = background
        self.max_raster_area_ratio = max_raster_area_ratio
        self.trace_small_graphics = trace_small_graphics
        self.embed_raster = embed_raster
        self.include_text = include_text

    def reconstruct(self, image_path: Path) -> VectorResult:
        image_path = Path(image_path)
        with TemporaryDirectory(prefix="image2svg-layout-") as tmp:
            result = MineruLayoutAnalyzer(self.options).analyze(
                image_path, workdir=Path(tmp)
            )
            elements: list[SceneElement] = []
            scene_area = max(1.0, float(result.width * result.height))
            containers = [block.box for block in result.blocks if block.type == "box"]

            for index, block in enumerate(result.blocks):
                x0, y0, x1, y1 = block.box
                bbox = (x0, y0, x1 - x0, y1 - y0)

                if block.type == "box":
                    style: dict[str, object] = {"rx": 8}
                    if block.color:
                        style["fill"] = block.color
                    if block.stroke and block.stroke != block.color:
                        style["stroke"] = block.stroke
                        style["stroke-width"] = 2
                    elements.append(
                        SceneElement(
                            id=f"layout_box_{index}",
                            type="rect",
                            bbox=bbox,
                            z_index=0,
                            style=style,
                        )
                    )
                    continue

                if block.crop_path is not None and Path(block.crop_path).exists():
                    area_ratio = max(0.0, bbox[2] * bbox[3]) / scene_area
                    if area_ratio > self.max_raster_area_ratio:
                        continue
                    crop_path = Path(block.crop_path)
                    if self.trace_small_graphics and _should_trace(crop_path, area_ratio):
                        try:
                            traced = traced_element(
                                crop_path,
                                bbox,
                                element_id=f"layout_trace_{index}",
                            )
                        except (KeyboardInterrupt, SystemExit):
                            raise
                        except (OSError, RuntimeError, ValueError):
                            traced = None
                        if traced is not None:
                            traced.style.update(
                                {"semantic": block.type, "source": "mineru"}
                            )
                            elements.append(traced)
                            continue
                    if not self.embed_raster:
                        continue
                    elements.append(
                        SceneElement(
                            id=f"layout_image_{index}",
                            type="image",
                            bbox=bbox,
                            z_index=0,
                            style={
                                "href": _data_uri(crop_path),
                                "semantic": block.type,
                                "source": "mineru",
                            },
                        )
                    )
                    continue

                if not block.text.strip():
                    continue
                if not self.include_text:
                    continue
                height = max(1.0, y1 - y0)
                width = max(1.0, x1 - x0)
                lines = [line for line in block.text.splitlines() if line.strip()] or [block.text]
                line_count = max(1, len(lines))
                line_height = height / line_count
                align = _alignment(block.box, containers, float(result.width))
                for line_index, line in enumerate(lines):
                    line_top = y0 + line_index * line_height
                    element = SceneElement(
                            id=f"layout_text_{index}_{line_index}",
                            type="text",
                            bbox=(x0, line_top, width, line_height),
                            z_index=1,
                            text=line,
                            style={
                                "font-family": _font_family(line),
                                "font-weight": block.weight,
                                "fill": block.color or "#333333",
                                "align": align,
                                "text-anchor": "middle" if align == "center" else "start",
                                "baseline-ratio": _BASELINE_RATIO,
                                "source": "mineru",
                                "fit-to-box": True,
                            },
                        )
                    elements.append(fit_text_element(element))

            scene = Scene(
                width=result.width,
                height=result.height,
                background=self.background,
                elements=elements,
            )
        return VectorResult(
            scene=scene,
            metadata={"backend": self.name, "blocks": len(result.blocks)},
        )
