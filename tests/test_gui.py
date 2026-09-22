from pathlib import Path

from image2svg.gui import build_cli_arguments


def test_gui_arguments_enable_paper_preset_and_expected_outputs(tmp_path: Path) -> None:
    input_path = tmp_path / "paper.png"
    output_dir = tmp_path / "result"

    arguments = build_cli_arguments(
        input_path,
        output_dir,
        "paper",
        qa=True,
        review_html=True,
        arrows=False,
        ai_python="C:/ai/python.exe",
        model_root="C:/models",
    )

    assert arguments[0] == str(input_path)
    assert ["--preset", "paper"] == arguments[
        arguments.index("--preset") : arguments.index("--preset") + 2
    ]
    assert "--qa" in arguments
    assert "--arrows" not in arguments
    assert str(output_dir / "paper.svg") in arguments
    assert str(output_dir / "paper.pptx") in arguments
    assert str(output_dir / "paper.review.html") in arguments
    assert ["--model-root", "C:/models"] == arguments[
        arguments.index("--model-root") : arguments.index("--model-root") + 2
    ]
