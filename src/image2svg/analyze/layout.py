from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

from image2svg.analyze.external import run_bridge
from image2svg.analyze.models import Box


def _default_script() -> Path:
    return Path(str(files("image2svg.ai.scripts").joinpath("mineru_parse.py")))


@dataclass(slots=True)
class LayoutBlock:
    type: str
    box: Box
    text: str = ""
    color: str | None = None
    stroke: str | None = None
    weight: str = "normal"
    crop_path: Path | None = None


@dataclass(slots=True)
class LayoutResult:
    image_path: Path
    width: int
    height: int
    blocks: list[LayoutBlock] = field(default_factory=list)


@dataclass(slots=True)
class LayoutOptions:
    """Configuration for the MinerU layout bridge."""

    python: str = "python"
    model: str | None = None
    max_edge: int = 1600
    ocr_text: bool = False
    timeout: float | None = 1800.0
    script: Path | None = None


class MineruLayoutAnalyzer:
    """Document layout parsing (text vs image separation) with MinerU2.5."""

    name = "mineru"

    def __init__(self, options: LayoutOptions | None = None) -> None:
        self.options = options or LayoutOptions()

    def analyze(
        self,
        image_path: Path,
        *,
        workdir: Path,
        export_crops: bool = True,
    ) -> LayoutResult:
        image_path = Path(image_path)
        workdir = Path(workdir)
        script = self.options.script or _default_script()
        args: list[str] = ["--image", str(image_path), "--max-edge", str(self.options.max_edge)]
        if self.options.model:
            args += ["--model", self.options.model]
        if self.options.ocr_text:
            args += ["--ocr-text"]
        if export_crops:
            args += ["--crop-dir", str(workdir / "layout_crops")]

        payload: dict[str, Any] = run_bridge(
            self.options.python,
            script,
            args,
            workdir / "layout.json",
            timeout=self.options.timeout,
        )
        blocks = [
            LayoutBlock(
                type=str(record.get("type", "unknown")),
                box=tuple(float(value) for value in record["bbox"]),  # type: ignore[arg-type]
                text=str(record.get("text", "")),
                color=record.get("color"),
                stroke=record.get("stroke"),
                weight=str(record.get("weight", "normal")),
                crop_path=Path(record["crop_path"]) if record.get("crop_path") else None,
            )
            for record in payload.get("blocks", [])
        ]
        return LayoutResult(
            image_path=image_path,
            width=int(payload.get("width", 0)),
            height=int(payload.get("height", 0)),
            blocks=blocks,
        )
