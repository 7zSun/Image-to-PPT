from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from image2svg.core.models import AuditResult


def build_conversion_report(
    *,
    input_path: Path,
    output_path: Path,
    backend: str,
    audit: AuditResult,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble the serializable conversion report dictionary."""
    return {
        "input": str(input_path),
        "output": str(output_path),
        "backend": backend,
        "svg_audit": asdict(audit),
        "editable_score": audit.editable_score,
        "warnings": list(warnings) if warnings else [],
    }


def write_conversion_report(report: dict[str, Any], output_path: Path) -> Path:
    """Write the conversion report as UTF-8 JSON and return its path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
