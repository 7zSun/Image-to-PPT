from __future__ import annotations

import base64
from pathlib import Path
from tempfile import TemporaryDirectory

from image2svg.analyze.layout import LayoutOptions, MineruLayoutAnalyzer
from image2svg.backends.base import VectorBackend
from image2svg.core.models import VectorResult
from image2svg.core.scene import Scene, SceneElement

DEFAULT_FONT_FAMILY = "Arial, Helvetica, 'Segoe UI', sans-serif"
_FONT_SIZE_RATIO = 0.9
_BASELINE_RATIO = 0.82


def _data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


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
    ) -> None:
        self.options = options or LayoutOptions()
        self.background = background

    def reconstruct(self, image_path: Path) -> VectorResult:
        image_path = Path(image_path)
        with TemporaryDirectory(prefix="image2svg-layout-") as tmp:
            result = MineruLayoutAnalyzer(self.options).analyze(
                image_path, workdir=Path(tmp)
            )
            elements: list[SceneElement] = []
            text_blocks = [b for b in result.blocks if b.text.strip() and not b.crop_path]
            heights = sorted(max(1.0, b.box[3] - b.box[1]) for b in text_blocks)
            single_line = heights[len(heights) // 4] if heights else 24.0

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
                    elements.append(
                        SceneElement(
                            id=f"layout_image_{index}",
                            type="image",
                            bbox=bbox,
                            z_index=0,
                            style={"href": _data_uri(Path(block.crop_path))},
                        )
                    )
                    continue

                if not block.text.strip():
                    continue
                height = max(1.0, y1 - y0)
                width = max(1.0, x1 - x0)
                line_count = max(1, round(height / single_line))
                line_height = height / line_count
                font_size = round(line_height * _FONT_SIZE_RATIO, 2)
                lines = [line for line in block.text.splitlines() if line.strip()] or [block.text]
                for line_index, line in enumerate(lines):
                    # Shrink the font so a long single line fits the block width.
                    fit = width / (max(1, len(line)) * 0.55)
                    line_font = max(8.0, min(font_size, fit))
                    line_top = y0 + line_index * line_height
                    baseline = line_top + line_height * _BASELINE_RATIO
                    elements.append(
                        SceneElement(
                            id=f"layout_text_{index}_{line_index}",
                            type="text",
                            bbox=(x0, line_top, width, baseline - line_top),
                            z_index=1,
                            text=line,
                            style={
                                "font-size": round(line_font, 2),
                                "font-family": DEFAULT_FONT_FAMILY,
                                "font-weight": block.weight,
                                "fill": block.color or "#333333",
                            },
                        )
                    )

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
