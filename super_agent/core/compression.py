from __future__ import annotations

import json
from typing import Any


class ContextCompressor:
    def __init__(self, budget_chars: int = 50000, preserve_recent: int = 8):
        self.budget_chars = max(10000, budget_chars)
        self.preserve_recent = preserve_recent

    @staticmethod
    def _compact_result(item: dict[str, Any]) -> dict[str, Any]:
        output = item.get("output")
        if isinstance(output, str) and len(output) > 1800:
            output = output[:900] + "\n...[compressed]...\n" + output[-700:]
        elif isinstance(output, list) and len(output) > 20:
            output = output[:10] + [{"compressed": f"{len(output)-20} omitted items"}] + output[-10:]
        return {
            "tool": item.get("tool"),
            "ok": item.get("ok"),
            "error": item.get("error"),
            "output": output,
            "metadata": item.get("metadata", {}),
        }

    def compress_tool_results(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(results) <= self.preserve_recent:
            return results
        older = [self._compact_result(x) for x in results[:-self.preserve_recent]]
        recent = results[-self.preserve_recent:]
        return older + recent

    def compress_evidence(self, evidence: list[str]) -> list[str]:
        if len(evidence) <= 30:
            return evidence
        older = evidence[:-15]
        summary = " | ".join(x[:300] for x in older[-20:])
        return [f"COMPRESSED PRIOR EVIDENCE ({len(older)} items): {summary}"] + evidence[-15:]

    def fit(self, sections: list[tuple[str, Any]]) -> str:
        rendered = []
        for name, value in sections:
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str, indent=2)
            rendered.append(f"{name}:\n{text}")
        joined = "\n\n".join(rendered)
        if len(joined) <= self.budget_chars:
            return joined
        head = joined[: int(self.budget_chars * 0.65)]
        tail = joined[-int(self.budget_chars * 0.3):]
        return head + "\n\n...[context compressed to budget]...\n\n" + tail
