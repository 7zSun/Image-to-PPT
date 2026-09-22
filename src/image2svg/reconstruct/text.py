from __future__ import annotations

import unicodedata

from image2svg.analyze.models import OcrResult
from image2svg.core.scene import Scene, SceneElement
from image2svg.reconstruct.text_metrics import fit_text_element

DEFAULT_FONT_FAMILY = "Arial, Helvetica, 'Segoe UI', sans-serif"
DEFAULT_CJK_FONT_FAMILY = "Microsoft YaHei, 'Segoe UI', Arial, sans-serif"
#: OCR boxes bound ascender..descender; em size is slightly smaller than the box.
_FONT_SIZE_RATIO = 0.9
#: Fraction of the line box height where the baseline sits (above the descender).
_BASELINE_RATIO = 0.82


def _font_family(text: str, fallback: str) -> str:
    if any(unicodedata.east_asian_width(character) in {"W", "F"} for character in text):
        return DEFAULT_CJK_FONT_FAMILY
    return fallback


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
        element = SceneElement(
                id=f"{prefix}_{index}",
                type="text",
                bbox=(x0, y0, width, height),
                text=region.text,
                style={
                    "font-family": _font_family(region.text, font_family),
                    "font-weight": region.weight,
                    "fill": region.color or color,
                    "baseline-ratio": _BASELINE_RATIO,
                    "source": "paddleocr",
                    "confidence": region.score,
                    "fit-to-box": True,
                },
            )
        elements.append(fit_text_element(element))
    return Scene(
        width=result.width,
        height=result.height,
        background=background,
        elements=elements,
    )
