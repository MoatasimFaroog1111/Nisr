from __future__ import annotations

import argparse
import asyncio
import json

from infrastructure.composition_root import build_runtime


async def _run(args) -> None:
    container = build_runtime(approvals=list(args.approve or []))
    state = await container.orchestrator.run(
        args.objective,
        constraints=args.constraint or [],
        approvals=args.approve or [],
    )
    print(json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Nisr autonomous agent")
    parser.add_argument("objective")
    parser.add_argument("--constraint", action="append", default=[])
    parser.add_argument("--approve", action="append", default=[])
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
