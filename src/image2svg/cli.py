from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from image2svg import __version__
from image2svg.analyze.detector import DEFAULT_LABELS, DetectorOptions
from image2svg.analyze.layout import LayoutOptions
from image2svg.analyze.ocr import OcrOptions
from image2svg.analyze.omnisvg import OmniSvgGenerator, OmniSvgOptions
from image2svg.analyze.regions import RegionOptions
from image2svg.analyze.sam3 import Sam3Options
from image2svg.analyze.starvector import StarVectorGenerator, StarVectorOptions
from image2svg.backends.base import VectorBackend
from image2svg.backends.composite import CompositeBackend
from image2svg.backends.detector import DetectorBackend
from image2svg.backends.layout import LayoutBackend
from image2svg.backends.ocr import OcrBackend
from image2svg.backends.panels import PanelBackend
from image2svg.backends.sam3 import Sam3Backend
from image2svg.export.html import export_html
from image2svg.export.pptx import export_pptx
from image2svg.pipeline import Image2SvgPipeline
from image2svg.presets import PRESET_NAMES, preset_defaults

DEFAULT_SAM_PROMPTS = ["icon", "photo", "building", "robot", "document"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="image2svg",
        description="Convert raster images into editable SVG with optional QA.",
    )
    parser.add_argument("input", nargs="?", type=Path, help="Input PNG/JPG/WebP image")
    parser.add_argument(
        "--preset",
        choices=PRESET_NAMES,
        default=None,
        help="Apply a balanced or paper/complex-figure reconstruction preset",
    )
    parser.add_argument("-o", "--output", type=Path, help="Output SVG path")
    parser.add_argument("--pptx", type=Path, help="Also export an editable PPTX")
    parser.add_argument("--html", type=Path, help="Also export an interactive review page")
    parser.add_argument("--qa", action="store_true", help="Render and compare the generated SVG")
    parser.add_argument(
        "--vector-only",
        action="store_true",
        help="Reject generated SVGs containing raster or external image resources",
    )
    parser.add_argument(
        "--sam3",
        action="store_true",
        help="Reconstruct editable elements with SAM3 open-vocabulary segmentation",
    )
    parser.add_argument(
        "--prompt",
        action="append",
        default=[],
        help="Text prompt for --sam3 (repeatable)",
    )
    parser.add_argument(
        "--ai-python",
        default=None,
        help="Python executable of the AI environment (default: $IMAGE2SVG_AI_PYTHON)",
    )
    parser.add_argument(
        "--model-root",
        type=Path,
        default=None,
        help="Directory containing local model folders (default: $IMAGE2SVG_MODEL_ROOT)",
    )
    parser.add_argument("--ai-device", default="cuda", help="Device for AI backends")
    parser.add_argument("--ai-confidence", type=float, default=0.5, help="Detection confidence")
    parser.add_argument(
        "--ai-background",
        default=None,
        help="Background color for AI-reconstructed scenes (e.g. #FFFFFF)",
    )
    parser.add_argument(
        "--ai-fallback",
        choices=["image", "drop"],
        default="image",
        help="How to handle segments that are not recognized primitives",
    )
    parser.add_argument(
        "--ai-refine",
        choices=["router", "trace", "generate", "geometry", "image", "raster", "vector"],
        default="trace",
        help=(
            "How to reconstruct non-primitives; vector preserves complex segmented "
            "graphics and traces flat ones"
        ),
    )
    parser.add_argument(
        "--starvector-python",
        default=None,
        help="Python executable of the StarVector env (default: $IMAGE2SVG_STARVECTOR_PYTHON)",
    )
    parser.add_argument(
        "--omnisvg-python",
        default=None,
        help="Python executable of the OmniSVG env (default: $IMAGE2SVG_OMNISVG_PYTHON)",
    )
    parser.add_argument(
        "--ai-generator",
        choices=["auto", "starvector", "omnisvg", "none"],
        default="auto",
        help="Generative backend for the router 'generate' class",
    )
    parser.add_argument(
        "--ai-panels",
        action="store_true",
        help="Add a deterministic panel/bar fallback when --detect is not enabled",
    )
    parser.add_argument(
        "--arrows",
        action="store_true",
        help="Enable experimental fixed-style connector reconstruction",
    )
    parser.add_argument(
        "--detect",
        action="store_true",
        help="Add a GroundingDINO structure layer (panels/cards as rects, icons traced)",
    )
    parser.add_argument(
        "--mineru",
        action="store_true",
        help="Use MinerU layout parsing: editable text + true image regions (anti-baking)",
    )
    parser.add_argument(
        "--mineru-ocr",
        action="store_true",
        help="Also OCR text inside image regions (makes icon/box labels editable)",
    )
    parser.add_argument(
        "--detect-label",
        action="append",
        default=[],
        help="Detection label for --detect (repeatable)",
    )
    parser.add_argument("--detect-threshold", type=float, default=0.3, help="DINO box threshold")
    parser.add_argument(
        "--detect-loose-arrows",
        action="store_true",
        help="Explicitly add an experimental low-threshold arrow detection pass",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Never embed raster crops; produce a purely vector SVG (best editability)",
    )
    parser.add_argument(
        "--keep-baked-text",
        action="store_true",
        help="Keep OCR text even inside preserved image regions (editable but duplicates)",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Reconstruct editable <text> elements via PaddleOCR",
    )
    parser.add_argument("--ocr-lang", default="ch", help="PaddleOCR language")
    parser.add_argument("--ocr-device", default="cpu", help="Device for PaddleOCR")
    parser.add_argument("--ocr-confidence", type=float, default=0.3, help="OCR confidence floor")
    parser.add_argument("--ocr-det-model-dir", default=None, help="Custom detection model dir")
    parser.add_argument("--ocr-rec-model-dir", default=None, help="Custom recognition model dir")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def parse_cli_args(
    parser: argparse.ArgumentParser, argv: list[str] | None = None
) -> argparse.Namespace:
    raw_argv = sys.argv[1:] if argv is None else argv
    preset_parser = argparse.ArgumentParser(add_help=False)
    preset_parser.add_argument("--preset", choices=PRESET_NAMES, default=None)
    selected, _ = preset_parser.parse_known_args(raw_argv)
    if selected.preset:
        parser.set_defaults(**preset_defaults(selected.preset))
    return parser.parse_args(raw_argv)


def _ai_python(args: argparse.Namespace) -> str:
    return args.ai_python or os.environ.get("IMAGE2SVG_AI_PYTHON", "python")


def _build_generator(args: argparse.Namespace) -> object | None:
    starvector_python = args.starvector_python or os.environ.get("IMAGE2SVG_STARVECTOR_PYTHON")
    omnisvg_python = args.omnisvg_python or os.environ.get("IMAGE2SVG_OMNISVG_PYTHON")

    choice = args.ai_generator
    if choice == "auto":
        choice = "omnisvg" if omnisvg_python else "starvector" if starvector_python else "none"

    if choice == "omnisvg":
        return OmniSvgGenerator(OmniSvgOptions(python=omnisvg_python)) if omnisvg_python else None
    if choice == "starvector":
        return (
            StarVectorGenerator(StarVectorOptions(python=starvector_python, device=args.ai_device))
            if starvector_python
            else None
        )
    return None


def _build_backend(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> VectorBackend | None:
    backends: list[VectorBackend] = []

    if args.ai_panels and not args.detect:
        backends.append(
            PanelBackend(
                options=RegionOptions(python=_ai_python(args)),
                background=args.ai_background,
                include_arrows=args.arrows and not args.sam3,
            )
        )

    if args.detect:
        detector_labels = list(args.detect_label or DEFAULT_LABELS)
        if args.arrows and not any("arrow" in label.lower() for label in detector_labels):
            detector_labels.append("arrow")
        backends.append(
            DetectorBackend(
                options=DetectorOptions(
                    python=_ai_python(args),
                    labels=detector_labels,
                    box_threshold=args.detect_threshold,
                ),
                background=args.ai_background,
                embed_raster=not args.no_images,
                structure_only=False,
            )
        )
        if args.detect_loose_arrows:
            backends.append(
                DetectorBackend(
                    options=DetectorOptions(
                        python=_ai_python(args),
                        labels=["arrow", "line", "connector"],
                        box_threshold=min(args.detect_threshold, 0.2),
                    ),
                    background=args.ai_background,
                    embed_raster=False,
                    arrows_only=True,
                )
            )

    if args.mineru:
        backends.append(
            LayoutBackend(
                options=LayoutOptions(
                    python=_ai_python(args),
                    ocr_text=args.mineru_ocr,
                ),
                background=args.ai_background,
                embed_raster=not args.no_images,
                include_text=not args.ocr,
            )
        )

    if args.sam3:
        refine = args.ai_refine
        if args.no_images and refine in ("raster", "vector", "router"):
            refine = "trace"
        generator = None
        if refine in ("router", "generate"):
            generator = _build_generator(args)
        sam_prompts = list(args.prompt or DEFAULT_SAM_PROMPTS)
        if args.arrows and not any("arrow" in prompt.lower() for prompt in sam_prompts):
            sam_prompts.append("arrow")
        backends.append(
            Sam3Backend(
                sam_prompts,
                options=Sam3Options(
                    python=_ai_python(args),
                    device=args.ai_device,
                    confidence=args.ai_confidence,
                ),
                fallback=args.ai_fallback,
                refine=refine,
                generator=generator,
                background=args.ai_background,
            )
        )

    if args.ocr:
        backends.append(
            OcrBackend(
                options=OcrOptions(
                    python=_ai_python(args),
                    device=args.ocr_device,
                    lang=args.ocr_lang,
                    confidence=args.ocr_confidence,
                    det_model_dir=args.ocr_det_model_dir,
                    rec_model_dir=args.ocr_rec_model_dir,
                ),
                background=args.ai_background,
            )
        )

    if not backends:
        return None
    if len(backends) == 1:
        return backends[0]
    return CompositeBackend(
        backends,
        background=args.ai_background,
        drop_baked_text=not args.keep_baked_text and not args.mineru_ocr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parse_cli_args(parser, argv)
    if args.input is None:
        parser.error("the following arguments are required: input")

    input_path: Path = args.input
    output_path = args.output or input_path.with_suffix(".svg")
    if args.model_root:
        os.environ["IMAGE2SVG_MODEL_ROOT"] = str(args.model_root)

    result = Image2SvgPipeline(_build_backend(parser, args)).run(
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
        f"external_resources={result.audit.external_resource_count}, "
        f"editable_score={result.audit.editable_score}"
    )
    if result.report_path:
        print(f"Report: {result.report_path}")
    if args.pptx and result.scene is not None:
        export_pptx(result.scene, args.pptx)
        print(f"PPTX: {args.pptx}")
    if args.html and result.scene is not None and result.render_path is not None:
        export_html(result.scene, input_path, result.render_path, args.html)
        print(f"HTML: {args.html}")
    if result.render_path:
        print(f"Render: {result.render_path}")
    if result.metrics_path:
        print(f"Metrics: {result.metrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
