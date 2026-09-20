from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from image2svg.core.scene import Scene


@dataclass(slots=True)
class VectorResult:
    svg: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    scene: Scene | None = None


@dataclass(slots=True)
class AuditResult:
    valid_xml: bool
    has_viewbox: bool
    embedded_raster_count: int
    external_resource_count: int
    node_count: int
    path_count: int
    errors: list[str] = field(default_factory=list)
    element_counts: dict[str, int] = field(default_factory=dict)
    editable_score: int = 0

    @property
    def ok(self) -> bool:
        return self.valid_xml and self.has_viewbox and not self.errors


@dataclass(slots=True)
class PipelineResult:
    input_path: Path
    svg_path: Path
    audit: AuditResult
    render_path: Path | None = None
    metrics_path: Path | None = None
    report_path: Path | None = None
    scene: Scene | None = None
