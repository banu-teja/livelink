"""Supervisor CLI: connect to a running agent session and control it.

Usage: uv run python examples/supervised_agent/supervisor.py <session_id>

Commands while connected: yes | no | inspect | cancel
Approvals are prompted automatically when tools requiring approval fire.
"""

import asyncio
import json
import sys


async def main(session_id: str) -> None:
    try:
        import websockets
    except ImportError:
        raise ImportError("Install websockets: pip install websockets") from None

    uri = f"ws://localhost:8000/supervise/{session_id}"
    print(f"Connecting to {uri} ...")

    async with websockets.connect(uri) as ws:
        connected = json.loads(await ws.recv())
        print(f"Connected: session={connected['session_id']} model={connected['model']}")
        for pa in connected.get("pending_approvals", []):
            print(f"  Pending: [{pa['request_id'][:8]}] {pa['question']}")

        await ws.send(json.dumps({"type": "subscribe", "cmd_id": "sub-1"}))
        ack = json.loads(await ws.recv())
        if ack.get("type") == "error":
            print(f"Error: {ack['message']}")
            return
        print("Subscribed. Streaming events...\n")

        async def listen() -> None:
            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "event":
                    et, payload = msg["event_type"], msg.get("payload", {})
                    if et == "ToolApprovalRequested":
                        print(
                            f"\n  APPROVAL NEEDED: {payload.get('tool_name')}({payload.get('arguments')})"
                        )
                        print("  Type 'yes' or 'no': ", end="", flush=True)
                    elif et == "ToolExecutionCompleted":
                        print(
                            f"  [done] {payload.get('tool_name')} -> {payload.get('result', '')[:60]}"
                        )
                    elif et == "SessionEnded":
                        print("\n  Session ended.")
                        return
                    else:
                        print(f"  [{et}] {payload}")
                elif msg["type"] == "ack" and msg.get("detail"):
                    print(f"  ack: {json.dumps(msg['detail'], indent=2)}")

        async def commands() -> None:
            loop = asyncio.get_running_loop()
            while True:
                line = (await loop.run_in_executor(None, sys.stdin.readline)).strip().lower()
                if not line:
                    continue
                if line == "inspect":
                    await ws.send(json.dumps({"type": "inspect", "cmd_id": "i-1"}))
                elif line == "cancel":
                    await ws.send(
                        json.dumps(
                            {"type": "cancel", "cmd_id": "c-1", "reason": "supervisor_cancelled"}
                        )
                    )
                elif line in ("yes", "y"):
                    await _resolve(ws, "Yes")
                elif line in ("no", "n"):
                    await _resolve(ws, "No")
                else:
                    print("  Commands: yes | no | inspect | cancel")

        await asyncio.gather(listen(), commands())


async def _resolve(ws, answer: str) -> None:
    """Resolve the most recent pending approval via inspect then resolve."""
    await ws.send(json.dumps({"type": "inspect", "cmd_id": "r-check"}))
    resp = json.loads(await ws.recv())
    pending = resp.get("detail", {}).get("pending_approvals", [])
    if not pending:
        print("  No pending approvals.")
        return
    rid = pending[0]["request_id"]
    await ws.send(
        json.dumps({"type": "resolve", "cmd_id": "r-1", "request_id": rid, "answer": answer})
    )
    print(f"  Resolved [{rid[:8]}] -> {answer}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python supervisor.py <session_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
