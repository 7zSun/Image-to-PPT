from image2svg.analyze.detector import DEFAULT_LABELS
from image2svg.backends.panels import PanelBackend
from image2svg.backends.sam3 import Sam3Backend
from image2svg.cli import DEFAULT_SAM_PROMPTS, _build_backend, build_parser, parse_cli_args
from image2svg.presets import PAPER_PROMPTS


def test_cli_parser_defaults() -> None:
    parser = build_parser()
    assert parser.prog == "image2svg"

    args = parser.parse_args([])
    assert args.input is None
    assert args.qa is False
    assert args.vector_only is False
    assert args.arrows is False


def test_arrows_are_disabled_in_default_ai_configuration() -> None:
    assert "arrow" not in DEFAULT_LABELS
    assert "arrow" not in DEFAULT_SAM_PROMPTS

    parser = build_parser()
    panels = _build_backend(parser, parser.parse_args(["input.png", "--ai-panels"]))
    assert isinstance(panels, PanelBackend)
    assert panels.include_arrows is False

    sam3 = _build_backend(parser, parser.parse_args(["input.png", "--sam3"]))
    assert isinstance(sam3, Sam3Backend)
    assert "arrow" not in sam3.prompts


def test_arrows_can_be_enabled_explicitly() -> None:
    parser = build_parser()
    panels = _build_backend(
        parser, parser.parse_args(["input.png", "--ai-panels", "--arrows"])
    )
    assert isinstance(panels, PanelBackend)
    assert panels.include_arrows is True

    sam3 = _build_backend(
        parser, parser.parse_args(["input.png", "--sam3", "--arrows"])
    )
    assert isinstance(sam3, Sam3Backend)
    assert "arrow" in sam3.prompts


def test_paper_preset_enables_complex_visual_preservation() -> None:
    parser = build_parser()
    args = parse_cli_args(parser, ["input.png", "--preset", "paper"])

    assert args.detect is True
    assert args.mineru is True
    assert args.ocr is True
    assert args.sam3 is True
    assert args.ai_refine == "image"
    assert args.ai_fallback == "image"
    assert args.prompt == PAPER_PROMPTS
    assert args.arrows is False


def test_explicit_option_overrides_preset_default() -> None:
    parser = build_parser()
    args = parse_cli_args(
        parser,
        ["input.png", "--preset", "paper", "--ai-refine", "trace"],
    )

    assert args.ai_refine == "trace"
