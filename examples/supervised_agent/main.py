"""Supervised voice agent with human-in-the-loop approval.

Run:  uv run python examples/supervised_agent/main.py
Then: uv run python examples/supervised_agent/supervisor.py <session_id>

The agent has tools that require supervisor approval before execution.
Connect the supervisor CLI to approve/reject tool calls in real time.
"""

import asyncio
import logging

from relaykit import LiveAgent, Runner, SessionConfig, WebSocketTransport
from relaykit.supervise import handle_supervision

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions=(
        "You are a banking assistant. You can check balances freely, but transfers "
        "and account deletions require supervisor approval. Be conversational and brief."
    ),
    voice="Puck",
)


@agent.tool
async def check_balance(account_id: str) -> str:
    """Check the balance of a bank account.

    Args:
        account_id: The account identifier
    """
    balances = {"checking": "$4,821.50", "savings": "$12,340.00", "business": "$89,100.25"}
    return f"Balance for {account_id}: {balances.get(account_id, '$0.00')}"


@agent.tool(requires_approval=True)
async def transfer_money(from_account: str, to_account: str, amount: str) -> str:
    """Transfer money between accounts. Requires supervisor approval.

    Args:
        from_account: Source account
        to_account: Destination account
        amount: Dollar amount to transfer
    """
    return f"Transferred {amount} from {from_account} to {to_account}. Confirmation: TXN-7291."


@agent.tool(requires_approval=True)
async def delete_account(account_id: str, reason: str) -> str:
    """Permanently delete a bank account. Requires supervisor approval.

    Args:
        account_id: Account to delete
        reason: Reason for deletion
    """
    return f"Account {account_id} deleted. Reason: {reason}"


config = SessionConfig(supervision=True, approval_timeout=120.0)


async def main() -> None:
    try:
        from websockets.asyncio.server import serve as ws_serve
    except ImportError:
        raise ImportError("Install websockets: pip install relaykit[serve]") from None

    async def handle_connection(connection) -> None:
        path = getattr(getattr(connection, "request", None), "path", "")

        if path.startswith("/supervise/"):
            session_id = path.removeprefix("/supervise/").strip("/")
            await handle_supervision(connection, session_id)
            return

        transport = WebSocketTransport(connection)
        result = await Runner.run(
            agent,
            transport,
            config=config,
            on_session_start=lambda s: print(f"\n  Session started: {s.session_id}"),
            on_tool_start=lambda name, args: logger.info("[tool] %s(%s)", name, args),
        )
        logger.info("[done] turns=%d reason=%s", result.turn_count, result.stopped_reason)

    print("Supervised agent -> http://localhost:8000")
    print(
        "Connect supervisor: uv run python examples/supervised_agent/supervisor.py <session_id>\n"
    )

    async with ws_serve(handle_connection, "localhost", 8000):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
