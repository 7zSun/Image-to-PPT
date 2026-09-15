from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from image2svg.core.models import VectorResult


class VectorBackend(ABC):
    """Common interface implemented by every vectorization backend."""

    name = "base"

    @abstractmethod
    def reconstruct(self, image_path: Path) -> VectorResult:
        raise NotImplementedError
