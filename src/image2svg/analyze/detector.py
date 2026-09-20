from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

from image2svg.analyze.external import run_bridge
from image2svg.analyze.models import SegmentationResult, SegmentInstance

DEFAULT_LABELS = [
    "panel",
    "card",
    "section",
    "frame",
    "border",
    "stage",
    "container",
    "banner",
    "diagram",
    "chart",
    "rounded rectangle",
    "rectangle",
    "button",
    "box",
    "icon",
    "arrow",
    "arrows",
    "line",
    "connector",
    "link",
    "logo",
    "symbol",
    "photo",
    "render",
]


def _default_script() -> Path:
    return Path(str(files("image2svg.ai.scripts").joinpath("groundingdino_detect.py")))


@dataclass(slots=True)
class DetectorOptions:
    """Configuration for the GroundingDINO detection bridge."""

    python: str = "python"
    labels: list[str] = field(default_factory=lambda: list(DEFAULT_LABELS))
    box_threshold: float = 0.3
    text_threshold: float = 0.25
    model: str | None = None
    timeout: float | None = 1800.0
    script: Path | None = None


class GroundingDinoAnalyzer:
    """Open-vocabulary object/panel detection with GroundingDINO."""

    name = "groundingdino"

    def __init__(self, options: DetectorOptions | None = None) -> None:
        self.options = options or DetectorOptions()

    def analyze(
        self,
        image_path: Path,
        *,
        workdir: Path,
        export_crops: bool = True,
    ) -> SegmentationResult:
        image_path = Path(image_path)
        workdir = Path(workdir)
        script = self.options.script or _default_script()
        args: list[str] = [
            "--image",
            str(image_path),
            "--box-threshold",
            str(self.options.box_threshold),
            "--text-threshold",
            str(self.options.text_threshold),
        ]
        for label in self.options.labels:
            args += ["--label", label]
        if self.options.model:
            args += ["--model", self.options.model]
        if export_crops:
            args += ["--crop-dir", str(workdir / "detector_crops")]

        payload: dict[str, Any] = run_bridge(
            self.options.python,
            script,
            args,
            workdir / "detector.json",
            timeout=self.options.timeout,
        )
        instances = [
            SegmentInstance(
                label=str(record.get("label", "")),
                score=float(record.get("score", 0.0)),
                box=tuple(float(value) for value in record["box"]),  # type: ignore[arg-type]
                area=int(record.get("area", 0)),
                color=record.get("color"),
                crop_path=Path(record["crop_path"]) if record.get("crop_path") else None,
                crop_box=(
                    tuple(float(value) for value in record["crop_box"])
                    if record.get("crop_box")
                    else None
                ),
                geometry=record.get("geometry")
                or {
                    "kind": "rect",
                    "stroke": record.get("stroke"),
                },
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
