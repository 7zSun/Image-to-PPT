from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from image2svg.analyze.external import run_bridge
from image2svg.analyze.models import SegmentationResult, SegmentInstance


def _default_script() -> Path:
    return Path(str(files("image2svg.ai.scripts").joinpath("flat_regions.py")))


@dataclass(slots=True)
class RegionOptions:
    """Configuration for the deterministic flat-region detector."""

    python: str = "python"
    min_area_ratio: float = 0.0025
    max_regions: int = 120
    timeout: float | None = 1800.0
    script: Path | None = None


class FlatRegionAnalyzer:
    """Detect large flat panels / bars as editable rectangles."""

    name = "panels"

    def __init__(self, options: RegionOptions | None = None) -> None:
        self.options = options or RegionOptions()

    def analyze(self, image_path: Path, *, workdir: Path) -> SegmentationResult:
        image_path = Path(image_path)
        workdir = Path(workdir)
        script = self.options.script or _default_script()
        args = [
            "--image",
            str(image_path),
            "--min-area-ratio",
            str(self.options.min_area_ratio),
            "--max-regions",
            str(self.options.max_regions),
        ]
        payload: dict[str, Any] = run_bridge(
            self.options.python,
            script,
            args,
            workdir / "regions.json",
            timeout=self.options.timeout,
        )
        instances = [
            SegmentInstance(
                label=str(record.get("label", "panel")),
                score=float(record.get("score", 1.0)),
                box=tuple(float(value) for value in record["box"]),  # type: ignore[arg-type]
                area=int(record.get("area", 0)),
                color=record.get("color"),
                geometry=record.get("geometry"),
                stats=record.get("stats"),
            )
            for record in payload.get("instances", [])
        ]
        return SegmentationResult(
            image_path=image_path,
            width=int(payload.get("width", 0)),
            height=int(payload.get("height", 0)),
            instances=instances,
        )
