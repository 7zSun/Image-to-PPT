from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Protocol

from image2svg.core.scene import SceneElement

_OPEN_SVG = re.compile(r"<svg\b([^>]*)>", re.IGNORECASE)
_ATTR = re.compile(r'\s(?:width|height|x|y)\s*=\s*"[^"]*"', re.IGNORECASE)


class SvgGenerator(Protocol):
    def generate(self, crop_path: Path, workdir: Path) -> str: ...


class CachedGenerator:
    """Serve generated SVGs from a batch result, keyed by crop path."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping

    def generate(self, crop_path: Path, workdir: Path) -> str:
        return self.mapping.get(str(Path(crop_path)), "")


def _fmt(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def _embed_svg(markup: str, width: float, height: float) -> str | None:
    """Resize a generated <svg> to the target box, keeping its own viewBox."""
    match = _OPEN_SVG.search(markup)
    if match is None:
        return None
    attrs = match.group(1)

    source_w = re.search(r'\bwidth\s*=\s*"([0-9.]+)', attrs, re.IGNORECASE)
    source_h = re.search(r'\bheight\s*=\s*"([0-9.]+)', attrs, re.IGNORECASE)

    cleaned = _ATTR.sub("", attrs)
    if "viewBox" not in cleaned and source_w and source_h:
        cleaned += f' viewBox="0 0 {source_w.group(1)} {source_h.group(1)}"'

    body = markup[match.end() :]
    end = body.rfind("</svg>")
    if end == -1:
        return None

    candidate = f'<svg{cleaned} width="{_fmt(width)}" height="{_fmt(height)}">{body[:end]}</svg>'
    try:
        ET.fromstring(candidate)
    except ET.ParseError:
        return None
    return candidate


def generated_element(
    generator: SvgGenerator,
    crop_path: Path,
    bbox: tuple[float, float, float, float],
    *,
    element_id: str,
    workdir: Path,
) -> SceneElement | None:
    """Generate SVG for a crop and place it (scaled) at ``bbox``."""
    try:
        markup = generator.generate(Path(crop_path), Path(workdir))
    except Exception:  # noqa: BLE001 - generation is best-effort
        return None
    if not markup or "<svg" not in markup.lower():
        return None
    if "<image" in markup.lower():  # model fell back to embedding a raster
        return None

    width, height = bbox[2], bbox[3]
    embedded = _embed_svg(markup, width, height)
    if embedded is None:
        return None

    return SceneElement(
        id=element_id,
        type="group",
        bbox=bbox,
        raw_svg=embedded,
    )
