from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from image2svg.core.scene import SceneElement


def trace_svg(image_path: Path) -> str:
    """Vectorize an image crop and return only its inner SVG markup."""
    import vtracer

    image_path = Path(image_path)
    with TemporaryDirectory(prefix="image2svg-trace-") as tmp:
        output = Path(tmp) / "trace.svg"
        if hasattr(vtracer, "convert_file"):
            vtracer.convert_file(str(image_path), str(output))
        elif hasattr(vtracer, "convert_image_to_svg_py"):
            vtracer.convert_image_to_svg_py(str(image_path), str(output))
        else:  # pragma: no cover - protects against an unknown future API
            raise RuntimeError("Unsupported VTracer Python API")
        svg = output.read_text(encoding="utf-8")

    start = svg.find(">", svg.find("<svg"))
    end = svg.rfind("</svg>")
    if start == -1 or end == -1:
        return ""
    return svg[start + 1 : end].strip()


def traced_element(
    crop_path: Path,
    bbox: tuple[float, float, float, float],
    *,
    element_id: str,
) -> SceneElement | None:
    """Trace a masked crop and wrap the resulting paths as a positioned group."""
    markup = trace_svg(crop_path)
    if "<path" not in markup:
        return None
    return SceneElement(
        id=element_id,
        type="group",
        bbox=bbox,
        raw_svg=markup,
    )
