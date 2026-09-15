from __future__ import annotations

import argparse
from pathlib import Path

from image2svg import __version__
from image2svg.pipeline import Image2SvgPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="image2svg",
        description="Convert raster images into editable SVG with optional QA.",
    )
    parser.add_argument("input", nargs="?", type=Path, help="Input PNG/JPG/WebP image")
    parser.add_argument("-o", "--output", type=Path, help="Output SVG path")
    parser.add_argument("--qa", action="store_true", help="Render and compare the generated SVG")
    parser.add_argument(
        "--vector-only",
        action="store_true",
        help="Reject generated SVGs containing raster or external image resources",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.input is None:
        parser.error("the following arguments are required: input")

    input_path: Path = args.input
    output_path = args.output or input_path.with_suffix(".svg")

    result = Image2SvgPipeline().run(
        input_path,
        output_path,
        qa=args.qa,
        vector_only=args.vector_only,
    )

    print(f"SVG: {result.svg_path}")
    print(
        "Audit: "
        f"nodes={result.audit.node_count}, paths={result.audit.path_count}, "
        f"embedded_raster={result.audit.embedded_raster_count}, "
        f"external_resources={result.audit.external_resource_count}"
    )
    if result.render_path:
        print(f"Render: {result.render_path}")
    if result.metrics_path:
        print(f"Metrics: {result.metrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
