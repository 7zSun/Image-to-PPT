from image2svg.cli import build_parser


def test_cli_parser_defaults() -> None:
    parser = build_parser()
    assert parser.prog == "image2svg"

    args = parser.parse_args([])
    assert args.input is None
    assert args.qa is False
    assert args.vector_only is False
