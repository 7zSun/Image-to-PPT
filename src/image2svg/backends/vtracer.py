from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from image2svg.backends.base import VectorBackend
from image2svg.core.models import VectorResult


class VTracerBackend(VectorBackend):
    """Default deterministic tracing backend.

    Supports both the stable VTracer 0.6.x Python API and the newer 1.0
    pre-release API without leaking either API into the rest of the project.
    """

    name = "vtracer"

    def reconstruct(self, image_path: Path) -> VectorResult:
        try:
            import vtracer
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("VTracer is not installed. Run: pip install vtracer") from exc

        image_path = Path(image_path)
        if not image_path.is_file():
            raise FileNotFoundError(image_path)

        with TemporaryDirectory(prefix="image2svg-") as tmp:
            svg_path = Path(tmp) / "result.svg"

            if hasattr(vtracer, "convert_file"):
                vtracer.convert_file(str(image_path), str(svg_path))
            elif hasattr(vtracer, "convert_image_to_svg_py"):
                vtracer.convert_image_to_svg_py(str(image_path), str(svg_path))
            else:  # pragma: no cover - protects against an unknown future API
                raise RuntimeError("Unsupported VTracer Python API")

            svg = svg_path.read_text(encoding="utf-8")

        return VectorResult(svg=svg, metadata={"backend": self.name})
