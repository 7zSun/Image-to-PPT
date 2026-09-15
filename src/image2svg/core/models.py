from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class VectorResult:
    svg: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AuditResult:
    valid_xml: bool
    has_viewbox: bool
    embedded_raster_count: int
    external_resource_count: int
    node_count: int
    path_count: int
    errors: list[str] = field(default_factory=list)

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
