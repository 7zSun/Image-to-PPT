from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from image2svg.analyze.external import run_bridge
from image2svg.analyze.models import OcrResult, TextRegion


def _default_script() -> Path:
    return Path(str(files("image2svg.ai.scripts").joinpath("ocr_recognize.py")))


@dataclass(slots=True)
class OcrOptions:
    """Configuration for the PaddleOCR bridge process."""

    python: str = "python"
    device: str = "cpu"
    lang: str = "en"
    det_model_dir: str | None = None
    rec_model_dir: str | None = None
    rec_char_dict: str | None = None
    confidence: float = 0.3
    timeout: float | None = 3600.0
    script: Path | None = None


class OcrAnalyzer:
    """Text detection + recognition via the PaddleOCR bridge script."""

    name = "paddleocr"

    def __init__(self, options: OcrOptions | None = None) -> None:
        self.options = options or OcrOptions()

    def analyze(self, image_path: Path, *, workdir: Path) -> OcrResult:
        image_path = Path(image_path)
        workdir = Path(workdir)
        script = self.options.script or _default_script()

        args: list[str] = [
            "--image",
            str(image_path),
            "--device",
            self.options.device,
            "--lang",
            self.options.lang,
            "--confidence",
            str(self.options.confidence),
        ]
        if self.options.det_model_dir:
            args += ["--det-model-dir", self.options.det_model_dir]
        if self.options.rec_model_dir:
            args += ["--rec-model-dir", self.options.rec_model_dir]
        if self.options.rec_char_dict:
            args += ["--rec-char-dict", self.options.rec_char_dict]

        payload: dict[str, Any] = run_bridge(
            self.options.python,
            script,
            args,
            workdir / "ocr.json",
            timeout=self.options.timeout,
        )

        regions = [
            TextRegion(
                text=str(record["text"]),
                score=float(record.get("score", 0.0)),
                box=tuple(float(value) for value in record["box"]),  # type: ignore[arg-type]
                color=record.get("color"),
                weight=str(record.get("weight", "normal")),
            )
            for record in payload.get("regions", [])
        ]
        return OcrResult(
            image_path=image_path,
            width=int(payload.get("width", 0)),
            height=int(payload.get("height", 0)),
            regions=regions,
        )
