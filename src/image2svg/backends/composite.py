from __future__ import annotations

from pathlib import Path

from image2svg.backends.base import VectorBackend
from image2svg.core.models import VectorResult
from image2svg.core.scene import Scene, merge_scenes
from image2svg.reconstruct.arrows import connect_arrows
from image2svg.reconstruct.cleanup import (
    assign_z_order,
    deduplicate_scene,
    drop_baked_text,
    drop_duplicate_text,
    filter_artifact_text,
)


class CompositeBackend(VectorBackend):
    """Run several backends over the same image and merge their scenes."""

    name = "composite"

    def __init__(
        self,
        backends: list[VectorBackend],
        *,
        background: str | None = None,
        drop_baked_text: bool = True,
    ) -> None:
        if not backends:
            raise ValueError("CompositeBackend requires at least one backend")
        self.backends = list(backends)
        self.background = background
        self.drop_baked_text = drop_baked_text

    def reconstruct(self, image_path: Path) -> VectorResult:
        image_path = Path(image_path)
        scenes: list[Scene] = []
        parts: list[str] = []
        for backend in self.backends:
            result = backend.reconstruct(image_path)
            parts.append(backend.name)
            if result.scene is not None:
                scenes.append(result.scene)

        scene = merge_scenes(scenes, background=self.background)
        if self.drop_baked_text:
            drop_baked_text(scene)
        deduplicate_scene(scene)
        connect_arrows(scene)
        drop_duplicate_text(scene)
        filter_artifact_text(scene)
        assign_z_order(scene)
        return VectorResult(
            scene=scene,
            metadata={"backend": self.name, "parts": parts},
        )
