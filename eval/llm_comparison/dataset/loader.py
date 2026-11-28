from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc.msg}") from exc
        if not isinstance(row, dict) or not row.get("id"):
            raise ValueError(f"Each dataset row needs an id ({path}:{line_number})")
        if row["id"] in seen:
            raise ValueError(f"Duplicate dataset id: {row['id']}")
        if row.get("synthetic") is not True:
            raise ValueError(f"Starter rows must be marked synthetic: {row['id']}")
        seen.add(row["id"])
        rows.append(row)
    return rows
