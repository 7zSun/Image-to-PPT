from __future__ import annotations

from typing import Any

PAPER_PROMPTS = ["photo", "image", "diagram", "chart", "point cloud", "tactile"]

PRESET_NAMES = ("balanced", "paper")


def preset_defaults(name: str | None) -> dict[str, Any]:
    if name == "balanced":
        return {
            "detect": True,
            "mineru": True,
            "ocr": True,
            "ai_background": "#FFFFFF",
        }
    if name == "paper":
        return {
            "detect": True,
            "mineru": True,
            "ocr": True,
            "sam3": True,
            "prompt": list(PAPER_PROMPTS),
            "ai_refine": "image",
            "ai_fallback": "image",
            "ai_background": "#FFFFFF",
        }
    return {}
