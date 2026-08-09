from __future__ import annotations
import argparse, asyncio, json
from pathlib import Path
from super_agent.runtime import build_runtime

async def _run(args):
    approvals=list(args.approve or []); runtime=build_runtime(approvals=approvals)
    state=await runtime.run(args.objective,args.constraint or [],approvals)
    payload=json.dumps(state.model_dump(mode="json"),ensure_ascii=False,indent=2)
    if args.json_out:Path(args.json_out).write_text(payload,encoding="utf-8")
    print(state.final_result or payload)

def main():
    p=argparse.ArgumentParser(description="Run Super Agent"); p.add_argument("objective"); p.add_argument("--constraint",action="append",default=[]); p.add_argument("--approve",action="append",default=[]); p.add_argument("--json-out")
    args=p.parse_args(); asyncio.run(_run(args))
if __name__=="__main__":main()
