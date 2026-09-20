from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from image2svg.analyze.external import run_bridge


def _default_script() -> Path:
    return Path(str(files("image2svg.ai.scripts").joinpath("starvector_generate.py")))


@dataclass(slots=True)
class StarVectorOptions:
    """Configuration for the StarVector bridge process."""

    python: str = "python"
    device: str = "cuda"
    max_length: int = 4000
    model: str | None = None
    timeout: float | None = 3600.0
    script: Path | None = None


class StarVectorGenerator:
    """Generate SVG code for icon-like crops via the StarVector bridge."""

    name = "starvector"

    def __init__(self, options: StarVectorOptions | None = None) -> None:
        self.options = options or StarVectorOptions()

    def generate_batch(self, crop_paths: list[Path], workdir: Path) -> dict[str, str]:
        """Generate SVGs for several crops in a single model session."""
        if not crop_paths:
            return {}
        script = self.options.script or _default_script()
        args = [
            "--device",
            self.options.device,
            "--max-length",
            str(self.options.max_length),
        ]
        for crop_path in crop_paths:
            args += ["--image", str(crop_path)]
        if self.options.model:
            args += ["--model", self.options.model]
        payload = run_bridge(
            self.options.python,
            script,
            args,
            Path(workdir) / "starvector.json",
            timeout=self.options.timeout,
        )
        return {
            str(Path(record["image"])): str(record.get("svg", ""))
            for record in payload.get("results", [])
        }

    def generate(self, crop_path: Path, workdir: Path) -> str:
        return self.generate_batch([Path(crop_path)], workdir).get(str(Path(crop_path)), "")

    __call__ = generate
