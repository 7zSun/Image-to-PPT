import json
from pathlib import Path

from image2svg.backends.base import VectorBackend
from image2svg.core.models import VectorResult
from image2svg.pipeline import Image2SvgPipeline
from image2svg.report.report import build_conversion_report, write_conversion_report
from image2svg.svg.audit import audit_svg

FULL_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<rect x="0" y="0" width="10" height="10"/>'
    '<circle cx="20" cy="20" r="5"/>'
    '<ellipse cx="40" cy="40" rx="5" ry="3"/>'
    '<polygon points="0,0 10,0 5,10"/>'
    '<text x="1" y="1">hi</text>'
    '<path d="M0 0 L10 10 Z"/>'
    "</svg>"
)


class FakeBackend(VectorBackend):
    name = "fake"

    def reconstruct(self, image_path: Path) -> VectorResult:
        return VectorResult(svg=FULL_SVG)


def test_audit_exposes_element_counts() -> None:
    result = audit_svg(FULL_SVG)

    assert result.element_counts == {
        "path": 1,
        "rect": 1,
        "circle": 1,
        "ellipse": 1,
        "polygon": 1,
        "text": 1,
    }
    assert result.path_count == 1
    assert result.has_viewbox is True


def test_editable_score_full_marks() -> None:
    assert audit_svg(FULL_SVG).editable_score == 100


def test_editable_score_penalizes_missing_viewbox_and_raster() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<image href="data:image/png;base64,AAAA" width="1" height="1"/>'
        "</svg>"
    )
    result = audit_svg(svg)

    assert result.has_viewbox is False
    assert result.embedded_raster_count == 1
    assert result.editable_score == 20


def test_editable_score_for_bare_svg() -> None:
    result = audit_svg('<svg xmlns="http://www.w3.org/2000/svg"></svg>')

    assert result.element_counts["path"] == 0
    assert result.editable_score == 40


def test_editable_score_zero_on_invalid_xml() -> None:
    result = audit_svg('<svg viewBox="0 0 10 10">')

    assert result.valid_xml is False
    assert result.editable_score == 0
    assert result.element_counts["path"] == 0


def test_build_conversion_report_contains_expected_fields() -> None:
    report = build_conversion_report(
        input_path=Path("in.png"),
        output_path=Path("out.svg"),
        backend="fake",
        audit=audit_svg(FULL_SVG),
    )

    assert report["input"] == "in.png"
    assert report["output"] == "out.svg"
    assert report["backend"] == "fake"
    assert report["editable_score"] == 100
    assert report["warnings"] == []
    assert report["svg_audit"]["element_counts"]["path"] == 1


def test_write_conversion_report_round_trips_json(tmp_path: Path) -> None:
    report = build_conversion_report(
        input_path=Path("in.png"),
        output_path=Path("out.svg"),
        backend="fake",
        audit=audit_svg(FULL_SVG),
        warnings=["Missing viewBox"],
    )

    report_path = write_conversion_report(report, tmp_path / "conversion_report.json")

    assert report_path.exists()
    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    assert loaded == report


def test_pipeline_generates_report_by_default(tmp_path: Path) -> None:
    source = tmp_path / "input.png"
    source.write_bytes(b"not-read-by-fake-backend")
    output = tmp_path / "output.svg"

    result = Image2SvgPipeline(FakeBackend()).run(source, output, qa=False)

    assert result.report_path is not None
    assert result.report_path == tmp_path / "conversion_report.json"
    assert result.report_path.exists()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["backend"] == "fake"
    assert report["editable_score"] == 100


def test_pipeline_can_disable_report(tmp_path: Path) -> None:
    source = tmp_path / "input.png"
    source.write_bytes(b"not-read-by-fake-backend")
    output = tmp_path / "output.svg"

    result = Image2SvgPipeline(FakeBackend()).run(
        source,
        output,
        qa=False,
        generate_report=False,
    )

    assert result.report_path is None
    assert not (tmp_path / "conversion_report.json").exists()
