from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from image2svg.analyze.external import run_bridge
from image2svg.analyze.models import SegmentationResult, SegmentInstance


def _default_script() -> Path:
    return Path(str(files("image2svg.ai.scripts").joinpath("sam3_segment.py")))


@dataclass(slots=True)
class Sam3Options:
    """Configuration for the SAM3 bridge process."""

    python: str = "python"
    device: str = "cuda"
    confidence: float = 0.5
    resolution: int = 1008
    checkpoint: str | None = None
    timeout: float | None = 3600.0
    script: Path | None = None


class Sam3Analyzer:
    """Open-vocabulary segmentation via the SAM3 bridge script."""

    name = "sam3"

    def __init__(self, options: Sam3Options | None = None) -> None:
        self.options = options or Sam3Options()

    def analyze(
        self,
        image_path: Path,
        prompts: list[str],
        *,
        workdir: Path,
        export_crops: bool = True,
    ) -> SegmentationResult:
        image_path = Path(image_path)
        workdir = Path(workdir)
        script = self.options.script or _default_script()

        output_path = workdir / "sam3.json"
        args: list[str] = [
            "--image",
            str(image_path),
            "--device",
            self.options.device,
            "--confidence",
            str(self.options.confidence),
            "--resolution",
            str(self.options.resolution),
        ]
        for prompt in prompts:
            args += ["--prompt", prompt]
        if self.options.checkpoint:
            args += ["--checkpoint", self.options.checkpoint]
        if export_crops:
            args += ["--crop-dir", str(workdir / "crops")]

        payload: dict[str, Any] = run_bridge(
            self.options.python,
            script,
            args,
            output_path,
            timeout=self.options.timeout,
        )

        instances = [
            SegmentInstance(
                label=str(record["label"]),
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
                geometry=record.get("geometry"),
                stats=record.get("stats"),
            )
            for record in payload.get("instances", [])
        ]
        return SegmentationResult(
            image_path=image_path,
            width=int(payload.get("width", 0)),
            height=int(payload.get("height", 0)),
            prompts=list(payload.get("prompts", prompts)),
            instances=instances,
            background=payload.get("background"),
        )
