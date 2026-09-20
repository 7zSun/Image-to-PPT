from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from image2svg.analyze.ocr import OcrAnalyzer, OcrOptions
from image2svg.backends.base import VectorBackend
from image2svg.core.models import VectorResult
from image2svg.reconstruct.text import scene_from_ocr


class OcrBackend(VectorBackend):
    """Reconstruct a Scene IR of editable <text> elements via PaddleOCR.

    OCR only recovers text; combine it with another backend through
    :class:`~image2svg.backends.composite.CompositeBackend` for full images.
    """

    name = "ocr"

    def __init__(
        self,
        *,
        options: OcrOptions | None = None,
        background: str | None = None,
        color: str = "#000000",
    ) -> None:
        self.options = options or OcrOptions()
        self.background = background
        self.color = color

    def reconstruct(self, image_path: Path) -> VectorResult:
        image_path = Path(image_path)
        with TemporaryDirectory(prefix="image2svg-ocr-") as tmp:
            result = OcrAnalyzer(self.options).analyze(image_path, workdir=Path(tmp))
            scene = scene_from_ocr(result, background=self.background, color=self.color)
        return VectorResult(
            scene=scene,
            metadata={"backend": self.name, "regions": len(result.regions)},
        )
