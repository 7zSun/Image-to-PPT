from __future__ import annotations

import json
import subprocess
from pathlib import Path


class ExternalToolError(RuntimeError):
    """Raised when a bridge script fails to produce a usable result."""


def run_bridge(
    python: str,
    script: Path,
    args: list[str],
    output_path: Path,
    *,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
) -> dict:
    """Run an AI bridge script in its own interpreter and load its JSON output."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [python, str(script), *args, "--output", str(output_path)]

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout or "").strip()
        raise ExternalToolError(
            f"Bridge script {script.name} failed with exit code {completed.returncode}:\n"
            f"{stderr[-2000:]}"
        )
    if not output_path.exists():
        raise ExternalToolError(f"Bridge script {script.name} did not write {output_path}")

    return json.loads(output_path.read_text(encoding="utf-8"))
