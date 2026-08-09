from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class ArtifactManager:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = self.root / "manifest.jsonl"

    def _safe(self, name: str) -> Path:
        clean = Path(name).name
        if not clean or clean in {".", ".."}:
            clean = f"artifact-{uuid4().hex}"
        return self.root / clean

    def write_text(self, name: str, content: str, *, kind: str = "text", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        path = self._safe(name)
        path.write_text(content, encoding="utf-8")
        return self.register(path, kind=kind, metadata=metadata)

    def copy_in(self, source: Path, name: str | None = None, *, kind: str = "file", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        dest = self._safe(name or source.name)
        shutil.copy2(source, dest)
        return self.register(dest, kind=kind, metadata=metadata)

    def register(self, path: Path, *, kind: str = "file", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        data = path.read_bytes()
        record = {
            "artifact_id": uuid4().hex,
            "name": path.name,
            "path": str(path),
            "kind": kind,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        with self.manifest.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return record

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.manifest.exists():
            return []
        rows = []
        for line in self.manifest.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return list(reversed(rows))

    def read_text(self, name: str, max_chars: int = 100000) -> str:
        return self._safe(name).read_text(encoding="utf-8")[:max_chars]
