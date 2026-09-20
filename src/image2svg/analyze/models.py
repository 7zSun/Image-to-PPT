"""Data models shared by the optional AI analyzers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

Box = tuple[float, float, float, float]  # (x0, y0, x1, y1)


@dataclass(slots=True)
class SegmentInstance:
    label: str
    score: float
    box: Box
    area: int = 0
    color: str | None = None
    crop_path: Path | None = None
    crop_box: Box | None = None
    geometry: dict | None = None
    stats: dict | None = None


@dataclass(slots=True)
class SegmentationResult:
    image_path: Path
    width: int
    height: int
    prompts: list[str] = field(default_factory=list)
    instances: list[SegmentInstance] = field(default_factory=list)
    background: str | None = None


@dataclass(slots=True)
class TextRegion:
    text: str
    score: float
    box: Box
    color: str | None = None
    weight: str = "normal"


@dataclass(slots=True)
class OcrResult:
    image_path: Path
    width: int
    height: int
    regions: list[TextRegion] = field(default_factory=list)
