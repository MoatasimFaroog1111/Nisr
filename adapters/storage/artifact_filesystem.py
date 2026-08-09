from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class FileSystemArtifactAdapter:
    def __init__(self, root: Path):
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._manifest = self._root / "manifest.jsonl"

    def _safe(self, name: str) -> Path:
        clean = Path(name).name
        if not clean or clean in {".", ".."}:
            clean = f"artifact-{uuid4().hex}"
        return self._root / clean

    def write_text(self, name: str, content: str, *, kind: str = "text") -> dict:
        path = self._safe(name)
        path.write_text(content, encoding="utf-8")
        data = path.read_bytes()
        record = {
            "artifact_id": uuid4().hex,
            "name": path.name,
            "path": str(path),
            "kind": kind,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._manifest.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def list(self, limit: int = 100) -> list[dict]:
        if not self._manifest.exists():
            return []
        rows: list[dict] = []
        for line in self._manifest.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(rows))

    def read_text(self, name: str, max_chars: int = 100_000) -> str:
        return self._safe(name).read_text(encoding="utf-8")[:max_chars]
