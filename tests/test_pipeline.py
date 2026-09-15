from pathlib import Path

from image2svg.backends.base import VectorBackend
from image2svg.core.models import VectorResult
from image2svg.pipeline import Image2SvgPipeline


class FakeBackend(VectorBackend):
    name = "fake"

    def reconstruct(self, image_path: Path) -> VectorResult:
        return VectorResult(
            svg=(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
                '<rect width="10" height="10" fill="#000"/>'
                '</svg>'
            )
        )


def test_pipeline_writes_svg_without_qa(tmp_path: Path) -> None:
    source = tmp_path / "input.png"
    source.write_bytes(b"not-read-by-fake-backend")
    output = tmp_path / "output.svg"

    result = Image2SvgPipeline(FakeBackend()).run(source, output, qa=False)

    assert output.exists()
    assert result.audit.valid_xml
    assert result.audit.path_count == 0
