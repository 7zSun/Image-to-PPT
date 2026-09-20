from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from image2svg.analyze.external import run_bridge


def _default_script() -> Path:
    return Path(str(files("image2svg.ai.scripts").joinpath("omnisvg_generate.py")))


@dataclass(slots=True)
class OmniSvgOptions:
    """Configuration for the OmniSVG bridge process."""

    python: str = "python"
    model_size: str = "4B"
    max_length: int = 1024
    num_candidates: int = 1
    repo: str | None = None
    weights: str | None = None
    timeout: float | None = 3600.0
    script: Path | None = None


class OmniSvgGenerator:
    """Generate SVG code for icon/illustration crops via OmniSVG."""

    name = "omnisvg"

    def __init__(self, options: OmniSvgOptions | None = None) -> None:
        self.options = options or OmniSvgOptions()

    def generate_batch(self, crop_paths: list[Path], workdir: Path) -> dict[str, str]:
        if not crop_paths:
            return {}
        script = self.options.script or _default_script()
        args = [
            "--model-size",
            self.options.model_size,
            "--max-length",
            str(self.options.max_length),
            "--num-candidates",
            str(self.options.num_candidates),
        ]
        if self.options.repo:
            args += ["--repo", self.options.repo]
        if self.options.weights:
            args += ["--weights", self.options.weights]
        for crop_path in crop_paths:
            args += ["--image", str(crop_path)]
        payload = run_bridge(
            self.options.python,
            script,
            args,
            Path(workdir) / "omnisvg.json",
            timeout=self.options.timeout,
        )
        return {
            str(Path(record["image"])): str(record.get("svg", ""))
            for record in payload.get("results", [])
        }

    def generate(self, crop_path: Path, workdir: Path) -> str:
        return self.generate_batch([Path(crop_path)], workdir).get(str(Path(crop_path)), "")

    __call__ = generate
