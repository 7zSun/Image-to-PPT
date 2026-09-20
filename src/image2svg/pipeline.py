from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from image2svg.backends.base import VectorBackend
from image2svg.backends.vtracer import VTracerBackend
from image2svg.core.models import PipelineResult
from image2svg.qa.compare import compare_images
from image2svg.report.report import build_conversion_report, write_conversion_report
from image2svg.svg.audit import audit_svg
from image2svg.svg.builder import build_svg
from image2svg.svg.render import render_svg


class Image2SvgPipeline:
    def __init__(self, backend: VectorBackend | None = None) -> None:
        self.backend = backend or VTracerBackend()

    def run(
        self,
        input_path: Path,
        output_path: Path,
        *,
        qa: bool = False,
        vector_only: bool = False,
        generate_report: bool = True,
    ) -> PipelineResult:
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        vector = self.backend.reconstruct(input_path)
        scene = vector.scene
        svg = build_svg(scene) if scene is not None else vector.svg
        audit = audit_svg(svg)

        if not audit.valid_xml:
            raise RuntimeError("Generated SVG is invalid XML")
        if vector_only and (audit.embedded_raster_count or audit.external_resource_count):
            raise RuntimeError("--vector-only rejected raster/external resources in generated SVG")

        output_path.write_text(svg, encoding="utf-8")

        report_path: Path | None = None
        if generate_report:
            report = build_conversion_report(
                input_path=input_path,
                output_path=output_path,
                backend=self.backend.name,
                audit=audit,
                warnings=list(audit.errors),
            )
            report_path = write_conversion_report(
                report,
                output_path.parent / "conversion_report.json",
            )

        render_path: Path | None = None
        metrics_path: Path | None = None
        if qa:
            qa_dir = output_path.parent / f"{output_path.stem}.qa"
            qa_dir.mkdir(parents=True, exist_ok=True)

            audit_path = qa_dir / "audit.json"
            audit_path.write_text(
                json.dumps(asdict(audit), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            render_path = render_svg(svg, qa_dir / "render.png")
            metrics = compare_images(
                input_path,
                render_path,
                difference_path=qa_dir / "comparison.png",
            )
            metrics["backend"] = self.backend.name
            metrics_path = qa_dir / "metrics.json"
            metrics_path.write_text(
                json.dumps(metrics, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return PipelineResult(
            input_path=input_path,
            svg_path=output_path,
            audit=audit,
            render_path=render_path,
            metrics_path=metrics_path,
            report_path=report_path,
            scene=scene,
        )
