from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from image2svg.analyze.sam3 import Sam3Analyzer, Sam3Options
from image2svg.backends.base import VectorBackend
from image2svg.core.models import VectorResult
from image2svg.reconstruct.generate import CachedGenerator
from image2svg.reconstruct.router import classify_instance
from image2svg.reconstruct.segments import scene_from_segmentation


class Sam3Backend(VectorBackend):
    """Reconstruct an editable Scene IR from SAM3 open-vocabulary segmentation.

    The heavy SAM3 runtime is invoked through a bridge subprocess, so this
    backend stays importable in the lightweight pipeline environment.
    """

    name = "sam3"

    def __init__(
        self,
        prompts: list[str],
        *,
        options: Sam3Options | None = None,
        fallback: str = "image",
        refine: str = "trace",
        generator: Any = None,
        background: str | None = None,
    ) -> None:
        if not prompts:
            raise ValueError("Sam3Backend requires at least one text prompt")
        self.prompts = list(prompts)
        self.options = options or Sam3Options()
        self.fallback = fallback
        self.refine = refine
        self.generator = generator
        self.background = background

    def reconstruct(self, image_path: Path) -> VectorResult:
        image_path = Path(image_path)
        with TemporaryDirectory(prefix="image2svg-sam3-") as tmp:
            result = Sam3Analyzer(self.options).analyze(
                image_path,
                self.prompts,
                workdir=Path(tmp),
            )
            generator = self._batch_generator(result, Path(tmp))
            scene = scene_from_segmentation(
                result,
                background=self.background or result.background,
                fallback=self.fallback,
                refine=self.refine,
                generator=generator,
                workdir=Path(tmp),
            )
        return VectorResult(
            scene=scene,
            metadata={
                "backend": self.name,
                "prompts": self.prompts,
                "instances": len(result.instances),
                "refine": self.refine,
            },
        )

    def _batch_generator(self, result: Any, workdir: Path) -> Any:
        """Batch-generate all icon crops once, then serve them from cache."""
        if self.generator is None or self.refine not in ("router", "generate"):
            return self.generator
        if not hasattr(self.generator, "generate_batch"):
            return self.generator

        image_area = float(result.width) * float(result.height)
        crops: list[Path] = []
        seen: set[str] = set()
        for instance in result.instances:
            decision = (
                classify_instance(instance, image_area)
                if self.refine == "router"
                else "generate"
            )
            if decision != "generate" or instance.crop_path is None:
                continue
            crop = Path(instance.crop_path)
            if crop.exists() and str(crop) not in seen:
                seen.add(str(crop))
                crops.append(crop)

        if not crops:
            return self.generator
        mapping = self.generator.generate_batch(crops, workdir)
        return CachedGenerator(mapping)
