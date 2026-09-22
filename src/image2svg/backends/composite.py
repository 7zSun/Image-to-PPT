from __future__ import annotations

from pathlib import Path

from image2svg.backends.base import VectorBackend
from image2svg.core.models import VectorResult
from image2svg.core.scene import Scene, merge_scenes
from image2svg.reconstruct.arrows import connect_arrows
from image2svg.reconstruct.cleanup import (
    align_text_to_containers,
    assign_z_order,
    deduplicate_scene,
    drop_baked_text,
    drop_duplicate_text,
    drop_text_backplates,
    filter_artifact_text,
)
from image2svg.reconstruct.text_metrics import avoid_text_graphics, fit_text_to_boxes


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
        deduplicate_scene(scene)
        if self.drop_baked_text:
            drop_baked_text(scene)
        connect_arrows(scene)
        drop_duplicate_text(scene)
        filter_artifact_text(scene)
        drop_text_backplates(scene)
        align_text_to_containers(scene)
        avoid_text_graphics(scene)
        fit_text_to_boxes(scene)
        assign_z_order(scene)
        return VectorResult(
            scene=scene,
            metadata={"backend": self.name, "parts": parts},
        )
