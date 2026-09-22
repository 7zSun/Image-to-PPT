from __future__ import annotations

from pathlib import Path


def render_svg(svg: str, output_path: Path, *, scale: float = 1.0) -> Path:
    """Render SVG to PNG using CairoSVG.

    CairoSVG is kept as an optional QA dependency so the core vectorization
    pipeline can still be imported in lightweight environments.
    """
    try:
        import cairosvg
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            'SVG rendering requires the QA extra: pip install -e ".[qa]"'
        ) from exc

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        write_to=str(output_path),
        scale=scale,
    )
    return output_path
