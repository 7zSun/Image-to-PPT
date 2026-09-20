from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from image2svg.analyze.regions import FlatRegionAnalyzer, RegionOptions
from image2svg.backends.base import VectorBackend
from image2svg.core.models import VectorResult
from image2svg.reconstruct.segments import scene_from_segmentation


class PanelBackend(VectorBackend):
    """Deterministic structural skeleton: large flat panels and bars as rects."""

    name = "panels"

    def __init__(
        self,
        *,
        options: RegionOptions | None = None,
        background: str | None = None,
    ) -> None:
        self.options = options or RegionOptions()
        self.background = background

    def reconstruct(self, image_path: Path) -> VectorResult:
        image_path = Path(image_path)
        with TemporaryDirectory(prefix="image2svg-panels-") as tmp:
            result = FlatRegionAnalyzer(self.options).analyze(image_path, workdir=Path(tmp))
            scene = scene_from_segmentation(
                result,
                background=self.background,
                refine="geometry",
                fallback="drop",
                prefix="panel",
            )
        return VectorResult(
            scene=scene,
            metadata={"backend": self.name, "regions": len(result.instances)},
        )
