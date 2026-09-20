from __future__ import annotations

from image2svg.analyze.models import OcrResult
from image2svg.core.scene import Scene, SceneElement

DEFAULT_FONT_FAMILY = "Arial, Helvetica, 'Segoe UI', sans-serif"
#: OCR boxes bound ascender..descender; em size is slightly smaller than the box.
_FONT_SIZE_RATIO = 0.9
#: Fraction of the line box height where the baseline sits (above the descender).
_BASELINE_RATIO = 0.82


def scene_from_ocr(
    result: OcrResult,
    *,
    background: str | None = None,
    color: str = "#333333",
    font_family: str = DEFAULT_FONT_FAMILY,
    prefix: str = "text",
) -> Scene:
    """Build a Scene where each OCR region becomes an editable <text> element."""
    elements: list[SceneElement] = []
    for index, region in enumerate(result.regions):
        x0, y0, x1, y1 = region.box
        height = max(1.0, y1 - y0)
        width = max(1.0, x1 - x0)
        font_size = round(height * _FONT_SIZE_RATIO, 2)
        baseline = y0 + height * _BASELINE_RATIO
        elements.append(
            SceneElement(
                id=f"{prefix}_{index}",
                type="text",
                bbox=(x0, y0, width, baseline - y0),
                text=region.text,
                style={
                    "font-size": font_size,
                    "font-family": font_family,
                    "font-weight": region.weight,
                    "fill": region.color or color,
                },
            )
        )
    return Scene(
        width=result.width,
        height=result.height,
        background=background,
        elements=elements,
    )
