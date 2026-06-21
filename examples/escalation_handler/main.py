"""Customer Escalation Handler — collaborative realtime supervision demo.

Demonstrates RelayKit as a supervised realtime AI runtime through a multi-step
cascading outage investigation. The agent narrates evolving hypotheses, checks
infrastructure telemetry, correlates signals, and escalates when confidence is
insufficient — all observable and steerable by a connected supervisor.

Supervision capabilities shown:
- Continuous narration (agent exposes reasoning as it investigates)
- Supervisor injection (redirect investigation, add context mid-flight)
- Graduated autonomy (routine checks free, refunds/escalations gated)
- Interruption + recovery (cancel mid-investigation, agent acknowledges)
- Checkpoint-based collaboration (agent pauses at natural decision points)
- Ambient observability (every tool call, result, and reasoning step emitted)

Run:  uv run python examples/escalation_handler/main.py
Then: uv run python examples/escalation_handler/supervisor.py <session_id>
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections import deque

from livelink import LiveAgent, Runner, SessionConfig, WebSocketTransport

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared supervisor injection queue (per-session in production; module-level
# for this single-session demo). Supervisor pushes notes here via the
# WebSocket `inject` command; agent reads via check_supervisor_guidance tool.
# ---------------------------------------------------------------------------
_supervisor_notes: deque[str] = deque(maxlen=20)


def push_supervisor_note(text: str) -> None:
    _supervisor_notes.append(text)


def pop_supervisor_notes() -> list[str]:
    notes = list(_supervisor_notes)
    _supervisor_notes.clear()
    return notes


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions="""\
You are a senior support engineer at TechCorp, a B2B SaaS platform. You handle
complex customer escalations that involve multi-system investigation.

## How you work

You investigate methodically. Each investigation follows a pattern:
1. Identify the customer and understand their context
2. Check system status and recent incidents for correlation
3. Query telemetry and logs to build a causal picture
4. Form and test hypotheses, narrating your reasoning
5. Resolve or escalate based on evidence

## Narration style

Narrate your reasoning concisely as you investigate. This keeps your supervisor
informed without requiring them to ask. Examples of good narration:

- "Pulling up the account. Marcus is a 3-year Business Pro customer — that's
  high retention priority."
- "I found elevated error rates starting 14:02 UTC. Checking whether this
  correlates with the deploy at 13:58."
- "Conflicting signals: the customer says billing, but their errors predate
  the billing change. Let me dig deeper."
- "This looks like a cascading failure — the Salesforce connector timeout is
  causing dashboard requests to queue."

Do NOT dump chain-of-thought. Keep narration operationally useful.

## Supervisor collaboration

Your supervisor monitors this investigation in real time. Between major steps,
call check_supervisor_guidance to see if they've injected context or redirected
your investigation. If they have, acknowledge it and adapt your approach.

If supervisor says "summarize" — provide a brief status of what you know so far,
what you're investigating, and your current confidence level.

## Investigation status

After each significant discovery, call update_investigation_status with your
current hypothesis, confidence level, open questions, and evidence collected.
This keeps your supervisor's dashboard current without verbal narration for
every detail. Update when:
- You form or change a hypothesis
- Confidence shifts significantly
- You discover conflicting evidence
- You resolve or discard an open question

## Escalation rules

- Credits up to $25: issue directly (apply_account_credit)
- Refunds $25-$100: need supervisor approval (issue_refund)
- Refunds over $100: need supervisor approval + justification
- Engineering escalation: always needs supervisor approval
- P1 severity: explain blast radius and urgency clearly

## Tone

Professional, efficient, empathetic when appropriate. Don't over-apologize.
Acknowledge customer frustration once, then focus on resolution. Be honest
about uncertainty — "I'm not yet sure" is better than guessing.
""",
    voice="Puck",
)


# ---------------------------------------------------------------------------
# Investigation tools — designed to reveal partial information, forcing the
# agent to correlate signals and update hypotheses across multiple calls.
# ---------------------------------------------------------------------------


@agent.tool
async def lookup_customer(email: str) -> str:
    """Look up customer account details, history, and health indicators.

    Args:
        email: Customer email address
    """
    await asyncio.sleep(0.8)
    customers = {
        "marcus@techcorp-customer.com": (
            "Customer: Marcus Chen | Acme Corp\n"
            "Plan: Business Pro ($299/mo) | Tenure: 3.2 years\n"
            "Health: AT-RISK (score: 34/100, declining 3 months)\n"
            "MRR: $299 | Expansion potential: $800/mo (Team plan)\n"
            "Open tickets: 4 (avg resolution: 6.2 days — above SLA)\n"
            "Last contact: 2 days ago — billing dispute, unresolved\n"
            "Account notes: Referenced Competitor X in last call. Champion\n"
            "  (VP Eng Sarah Liu) went silent 2 weeks ago. Risk factors:\n"
            "  slow ticket resolution + billing friction + champion disengagement."
        ),
        "ops@enterprise-client.io": (
            "Customer: Enterprise Client Inc (Jordan Park, SRE Lead)\n"
            "Plan: Enterprise ($2,400/mo) | Tenure: 14 months\n"
            "Health: STABLE (score: 72/100)\n"
            "MRR: $2,400 | 47 seats active | 3 integrations\n"
            "Open tickets: 1 (this one, opened 18 min ago)\n"
            "Last contact: Routine QBR 3 weeks ago — positive\n"
            "Account notes: Heavy Salesforce integration user. Their pipeline\n"
            "  depends on our connector for lead routing. Production-critical."
        ),
        "sarah@startup.co": (
            "Customer: Sarah Kim | CloudStart (startup)\n"
            "Plan: Starter ($29/mo) | Tenure: 6 weeks\n"
            "Health: NEW (no score yet)\n"
            "MRR: $29 | 3 seats | Signed up during Product Hunt launch\n"
            "Open tickets: 0\n"
            "Last contact: First contact ever\n"
            "Account notes: No usage data yet. Free trial convert."
        ),
    }
    return customers.get(
        email,
        f"No customer found for '{email}'. Ask for correct email or account ID.",
    )


@agent.tool
async def check_system_status() -> str:
    """Get current status of all TechCorp services with real-time metrics."""
    await asyncio.sleep(0.5)
    return (
        "SYSTEM STATUS (as of now):\n"
        "┌─────────────────┬────────────┬───────────────────────────────────┐\n"
        "│ Service         │ Status     │ Detail                            │\n"
        "├─────────────────┼────────────┼───────────────────────────────────┤\n"
        "│ API Gateway     │ ✓ OK       │ p99: 142ms (normal)               │\n"
        "│ Dashboard       │ ⚠ DEGRADED │ p99: 4.2s (10x normal)            │\n"
        "│ Billing Service │ ✓ OK       │ Processing normally               │\n"
        "│ Salesforce Conn │ ✗ PARTIAL  │ 34% failure rate (auth errors)    │\n"
        "│ Data Pipeline   │ ✓ OK       │ Lag: 2.1s (acceptable)            │\n"
        "│ Worker Pool     │ ⚠ STRESSED │ Queue depth: 12,400 (4x normal)   │\n"
        "└─────────────────┴────────────┴───────────────────────────────────┘\n"
        "Active incidents: 1 (INC-4471: Salesforce connector auth failures)\n"
        "Last deploy: 13:58 UTC today (worker-pool-v2.14.1)"
    )


@agent.tool
async def query_error_logs(service: str, minutes: int = 30) -> str:
    """Query error logs for a specific service over recent time window.

    Args:
        service: Service name (api, dashboard, salesforce, workers, billing)
        minutes: How many minutes back to search (default 30)
    """
    await asyncio.sleep(1.2)
    logs = {
        "dashboard": (
            f"Error logs for 'dashboard' (last {minutes}min):\n"
            "Total errors: 847 (baseline: ~20/30min)\n"
            "Top errors:\n"
            "  1. TimeoutError: upstream_salesforce_connector (612 occurrences)\n"
            "     └─ Correlation: requests waiting on SF connector response\n"
            "  2. 504 Gateway Timeout: /api/integrations/sync (189 occurrences)\n"
            "     └─ Correlation: SF sync endpoint backing up request queue\n"
            "  3. OOMKilled: dashboard-renderer-pod (46 occurrences)\n"
            "     └─ Correlation: memory pressure from queued requests\n"
            "Pattern: errors spike at 14:02 UTC, 4 min after deploy. Not direct\n"
            "  deploy failure — cascade from SF connector timeout propagation."
        ),
        "salesforce": (
            f"Error logs for 'salesforce' (last {minutes}min):\n"
            "Total errors: 2,341 (baseline: ~5/30min)\n"
            "Top errors:\n"
            "  1. AuthenticationError: invalid_grant (1,891 occurrences)\n"
            "     └─ OAuth token refresh failing for ~34% of connected accounts\n"
            "  2. RateLimitError: concurrent_api_limit (312 occurrences)\n"
            "     └─ Retry storms from failed auth causing rate limit hits\n"
            "  3. TimeoutError: connection_pool_exhausted (138 occurrences)\n"
            "     └─ Pool saturated by retrying failed connections\n"
            "Root signal: Salesforce rotated their OAuth signing key at 13:55 UTC.\n"
            "  Our token refresh uses cached key. ~34% of tokens expired since then."
        ),
        "workers": (
            f"Error logs for 'workers' (last {minutes}min):\n"
            "Total errors: 1,456 (baseline: ~30/30min)\n"
            "Queue depth: 12,400 jobs (normal: ~3,000)\n"
            "Top errors:\n"
            "  1. TaskTimeoutError: salesforce_sync_job (978 occurrences)\n"
            "     └─ Sync jobs timing out waiting for SF connector\n"
            "  2. RetryExhausted: integration_webhook (342 occurrences)\n"
            "     └─ Webhooks failing after 3 retries\n"
            "  3. MemoryPressure: worker-pod-group-B (136 occurrences)\n"
            "     └─ Jobs accumulating in memory, not draining\n"
            "Deploy v2.14.1 at 13:58 increased worker concurrency from 50→100.\n"
            "  Normally beneficial, but amplifying the SF failure cascade."
        ),
        "billing": (
            f"Error logs for 'billing' (last {minutes}min):\n"
            "Total errors: 3 (baseline: ~2/30min)\n"
            "No anomalies detected. Processing normally."
        ),
    }
    return logs.get(
        service,
        f"No logs found for '{service}'. Available: dashboard, salesforce, workers, billing",
    )


@agent.tool
async def query_deployment_history(hours: int = 4) -> str:
    """Check recent deployments and their rollback status.

    Args:
        hours: How far back to look (default 4 hours)
    """
    await asyncio.sleep(0.7)
    return (
        f"Deployments (last {hours}h):\n"
        "1. worker-pool-v2.14.1 @ 13:58 UTC (32 min ago)\n"
        "   Author: deploy-bot (merged by @alex.kumar)\n"
        "   Change: Increased worker concurrency 50→100 for queue throughput\n"
        "   Status: LIVE | Rollback: available (v2.14.0)\n"
        "   Health check: PASSING (but queue depth elevated)\n"
        "\n"
        "2. dashboard-v3.8.2 @ 11:30 UTC (3h ago)\n"
        "   Author: @priya.patel\n"
        "   Change: UI polish, no backend changes\n"
        "   Status: LIVE | Healthy\n"
        "\n"
        "3. salesforce-connector-v1.22.0 @ 09:15 UTC (5h ago)\n"
        "   Change: Added retry logic for auth failures\n"
        "   Status: LIVE | NOTE: retry logic may be amplifying current issue"
    )


@agent.tool
async def check_customer_impact(service: str) -> str:
    """Assess how many customers are affected by a service issue.

    Args:
        service: Service experiencing issues
    """
    await asyncio.sleep(0.9)
    impacts = {
        "salesforce": (
            "CUSTOMER IMPACT — Salesforce Connector:\n"
            "Affected accounts: 847 / 2,491 total (34%)\n"
            "Enterprise accounts affected: 12 / 89 (13%)\n"
            "Revenue at risk: ~$18,400/mo (affected enterprise MRR)\n"
            "Customer-reported tickets: 23 (opened in last 30 min)\n"
            "Regions: us-east-1 (primary), eu-west-1 (partial)\n"
            "Customer segments:\n"
            "  - Heavy SF users (>100 syncs/day): 100% affected\n"
            "  - Light SF users (<10 syncs/day): ~15% affected\n"
            "  - Non-SF users: not affected"
        ),
        "dashboard": (
            "CUSTOMER IMPACT — Dashboard:\n"
            "Affected: users loading pages with integration widgets\n"
            "Estimated: ~40% of active sessions experiencing slowness\n"
            "Severity: degraded (slow) not down (inaccessible)\n"
            "Workaround available: disable integration widgets temporarily"
        ),
    }
    return impacts.get(service, f"No impact data available for '{service}'.")


@agent.tool
async def check_supervisor_guidance() -> str:
    """Check if the supervisor has injected context or redirection.

    Call this between major investigation steps to see if your supervisor
    wants you to adjust your approach, investigate something specific, or
    has additional context to share.
    """
    notes = pop_supervisor_notes()
    if not notes:
        return "No supervisor guidance at this time. Continue investigation."
    return "SUPERVISOR GUIDANCE:\n" + "\n".join(f"• {note}" for note in notes)


@agent.tool
async def update_investigation_status(
    hypothesis: str,
    confidence: int,
    evidence: str,
    open_questions: str,
    priority: str = "investigating",
) -> str:
    """Publish your current investigation state for supervisor visibility.

    Call this after each significant discovery or hypothesis change.

    Args:
        hypothesis: Current leading theory (1-2 sentences)
        confidence: Confidence percentage (0-100)
        evidence: Key evidence collected so far (comma-separated)
        open_questions: Unresolved questions (comma-separated)
        priority: Current focus — investigating, mitigating, escalating, resolving
    """
    return (
        f"STATUS PUBLISHED:\n"
        f"  Hypothesis: {hypothesis}\n"
        f"  Confidence: {confidence}%\n"
        f"  Evidence: {evidence}\n"
        f"  Open questions: {open_questions}\n"
        f"  Priority: {priority}"
    )


@agent.tool
async def query_metrics_realtime(service: str) -> str:
    """Get real-time metrics for a service. May return stale or conflicting data.

    Args:
        service: Service to query (dashboard, salesforce, workers, api)
    """
    await asyncio.sleep(0.6)
    metrics = {
        "salesforce": (
            "REALTIME METRICS — Salesforce Connector:\n"
            "  Request rate: 847/min (normal: ~200/min)\n"
            "  Error rate: 34.2% (⚠ elevated)\n"
            "  p50 latency: 1.2s | p99 latency: 28.4s (⚠ 10x normal)\n"
            "  Connection pool: 98/100 active (⚠ near exhaustion)\n"
            "  Auth success rate: 66% (34% failing on token refresh)\n"
            "\n"
            "  ⚠ CONFLICTING SIGNAL: Error rate is 34% but customer-reported\n"
            "    impact suggests higher. Possible explanation: retry masking —\n"
            "    each failed request retries 3x, inflating request rate while\n"
            "    individual user success rate may be lower than 66%.\n"
            "\n"
            "  ⚠ DATA FRESHNESS: Metrics pipeline lagging 3min in us-east-1.\n"
            "    Real-time values may understate current severity."
        ),
        "workers": (
            "REALTIME METRICS — Worker Pool:\n"
            "  Queue depth: 14,200 (normal: ~3,000) — still rising\n"
            "  Processing rate: 89 jobs/min (normal: 210/min)\n"
            "  Worker utilization: 100% (all 100 workers busy)\n"
            "  Avg job duration: 12.4s (normal: 2.1s — 6x slower)\n"
            "  Memory pressure: 87% (⚠ approaching OOM threshold)\n"
            "\n"
            "  ⚠ CONFLICTING SIGNAL: New concurrency config (50→100 workers)\n"
            "    should increase throughput, but actual throughput DECREASED.\n"
            "    Hypothesis: more workers = more concurrent SF connector calls\n"
            "    = faster pool exhaustion = worse per-request latency."
        ),
        "dashboard": (
            "REALTIME METRICS — Dashboard:\n"
            "  Active sessions: 1,247\n"
            "  Error rate: 12% of page loads failing\n"
            "  p50 latency: 890ms | p99 latency: 4.2s\n"
            "  Integration widget load: 67% success (⚠ SF widgets failing)\n"
            "  Non-integration pages: 99.2% success (unaffected)\n"
            "\n"
            "  PATTERN: Failures isolated to pages with Salesforce widgets.\n"
            "    Dashboard itself is healthy. Issue is upstream dependency."
        ),
    }
    return metrics.get(service, f"No realtime metrics for '{service}'.")


@agent.tool
async def check_rollback_status(rollback_id: str) -> str:
    """Check the status of an in-progress rollback.

    Args:
        rollback_id: The rollback ID from initiate_rollback
    """
    await asyncio.sleep(1.0)
    return (
        f"ROLLBACK STATUS — {rollback_id}:\n"
        "  Region us-east-1: ✓ complete (45s ago)\n"
        "  Region us-west-2: ✓ complete (30s ago)\n"
        "  Region eu-west-1: ⚠ PARTIAL — 3/8 pods rolled back, 5 pending\n"
        "    Error: ImagePullBackoff on pods worker-eu-{4,5,6,7,8}\n"
        "    Root cause: EU registry mirror 4min behind. Retrying.\n"
        "\n"
        "  IMPACT: US regions draining queue normally. EU queue still growing.\n"
        "  Worker queue depth (global): 11,800 (was 14,200 — improving)\n"
        "  Estimated full rollback: ~3 more minutes for EU.\n"
        "\n"
        "  ⚠ NOTE: Even after full rollback, SF connector auth issue persists.\n"
        "    Rollback addresses the amplification, not the root cause."
    )


@agent.tool
async def correlate_timeline(events: str) -> str:
    """Correlate multiple events on a timeline to identify causation.

    Args:
        events: Comma-separated list of events/timestamps to correlate
    """
    await asyncio.sleep(0.8)
    return (
        "TIMELINE CORRELATION:\n"
        "13:55 UTC — Salesforce rotates OAuth signing key (EXTERNAL)\n"
        "13:56 UTC — First SF auth errors appear in our connector\n"
        "13:58 UTC — worker-pool-v2.14.1 deployed (concurrency 50→100)\n"
        "14:00 UTC — SF connector retry storms begin (amplified by new concurrency)\n"
        "14:02 UTC — Worker queue depth crosses 10,000 threshold\n"
        "14:02 UTC — Dashboard timeout errors begin (waiting on SF responses)\n"
        "14:04 UTC — OOMKilled events start on dashboard pods\n"
        "14:08 UTC — First customer tickets arrive\n"
        "\n"
        "ASSESSMENT: Two independent events compounded.\n"
        "  Root cause: SF key rotation broke auth for 34% of tokens.\n"
        "  Amplifier: Worker concurrency increase caused more parallel retries,\n"
        "    exhausting connection pools faster than with old concurrency.\n"
        "  Neither event alone would have caused visible customer impact."
    )


@agent.tool(requires_approval=True)
async def initiate_rollback(service: str, target_version: str, reason: str) -> str:
    """Initiate a service rollback to a previous version. Requires approval.

    Args:
        service: Service to roll back
        target_version: Version to roll back to
        reason: Justification for rollback
    """
    await asyncio.sleep(0.5)
    return (
        f"ROLLBACK INITIATED:\n"
        f"Service: {service}\n"
        f"From: current → {target_version}\n"
        f"Reason: {reason}\n"
        f"ETA: ~90 seconds for full propagation\n"
        f"Rollback ID: RB-{random.randint(1000, 9999)}\n"
        f"Monitor: Worker queue depth should start draining within 2 minutes."
    )


@agent.tool(requires_approval=True)
async def issue_refund(amount: float, reason: str, ticket_id: str) -> str:
    """Issue a monetary refund. Requires supervisor approval.

    Args:
        amount: Refund amount in dollars
        reason: Detailed justification
        ticket_id: Associated support ticket
    """
    await asyncio.sleep(0.3)
    return (
        f"Refund processed: ${amount:.2f}\n"
        f"Reason: {reason}\n"
        f"Ticket: {ticket_id}\n"
        f"Confirmation: REF-{random.randint(10000, 99999)}\n"
        f"Applied to next billing cycle."
    )


@agent.tool(requires_approval=True)
async def escalate_to_engineering(severity: str, description: str, blast_radius: str) -> str:
    """Create an engineering escalation ticket. Requires supervisor approval.

    Args:
        severity: P1 (page oncall), P2 (urgent), P3 (next sprint)
        description: Technical root cause analysis
        blast_radius: Customer/revenue impact summary
    """
    await asyncio.sleep(0.4)
    ticket = f"ENG-{random.randint(1000, 9999)}"
    sla = {"P1": "15min response, 1h mitigation", "P2": "1h response", "P3": "next sprint"}
    return (
        f"Engineering escalation created: {ticket}\n"
        f"Severity: {severity} — SLA: {sla.get(severity, '4h response')}\n"
        f"Description: {description}\n"
        f"Blast radius: {blast_radius}\n"
        f"Oncall paged: {'Yes' if severity == 'P1' else 'No'}"
    )


@agent.tool
async def apply_account_credit(amount: float, reason: str) -> str:
    """Apply a courtesy credit up to $25 (no approval needed).

    Args:
        amount: Credit amount (max $25)
        reason: Brief reason
    """
    if amount > 25:
        return "Credits over $25 require issue_refund with supervisor approval."
    await asyncio.sleep(0.3)
    return f"Credit applied: ${amount:.2f}. Reason: {reason}. Visible immediately."


@agent.tool
async def send_customer_update(message: str, channel: str = "email") -> str:
    """Send a status update to the customer about their issue.

    Args:
        message: The update message content
        channel: Delivery channel (email, sms, in_app)
    """
    await asyncio.sleep(0.3)
    return (
        f"Update sent via {channel}: '{message[:80]}...'"
        if len(message) > 80
        else f"Update sent via {channel}: '{message}'"
    )


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

config = SessionConfig(supervision=True, approval_timeout=12.0)


async def main() -> None:
    try:
        from websockets.asyncio.server import serve as ws_serve
        import websockets.http11
        import websockets.datastructures
    except ImportError:
        raise ImportError("Install websockets: pip install livelink[serve]") from None

    from livelink._ui import DEFAULT_HTML

    def process_request(connection, request):
        if request.path in ("/", ""):
            headers = websockets.datastructures.Headers(
                {"Content-Type": "text/html; charset=utf-8"}
            )
            return websockets.http11.Response(200, "OK", headers, DEFAULT_HTML.encode())
        if request.path in ("/ws",) or request.path.startswith("/supervise/"):
            return None
        return websockets.http11.Response(
            404, "Not Found", websockets.datastructures.Headers(), b""
        )

    async def handle_connection(connection) -> None:
        path = getattr(getattr(connection, "request", None), "path", "")

        if path.startswith("/supervise/"):
            session_id = path.removeprefix("/supervise/").strip("/")
            await _handle_supervision_with_inject(connection, session_id)
            return

        transport = WebSocketTransport(connection)

        def on_start(session) -> None:
            sid = session.session_id
            print(f"\n  {'━' * 50}")
            print(f"  Session: {sid}")
            print(f"  Supervisor: python examples/escalation_handler/supervisor.py {sid}")
            print(f"  {'━' * 50}\n")

        result = await Runner.run(
            agent,
            transport,
            config=config,
            on_session_start=on_start,
            on_tool_start=lambda name, args: logger.info("  ▶ %s(%s)", name, args),
        )
        logger.info(
            "  ○ Session ended: turns=%d reason=%s", result.turn_count, result.stopped_reason
        )

    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║     ESCALATION HANDLER — Collaborative Supervision      ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()
    print("  A senior support engineer investigates cascading outages,")
    print("  correlates signals, and resolves issues — supervised in realtime.")
    print()
    print("  1. Open http://localhost:8000 (voice call starts)")
    print("  2. Copy the session ID printed below")
    print("  3. In another terminal: python examples/escalation_handler/supervisor.py <id>")
    print()
    print("  ┌─────────────────────────────────────────────────────────┐")
    print("  │ Try these scenarios:                                     │")
    print("  │                                                          │")
    print("  │  'Hi, I'm Jordan from Enterprise Client. Our Salesforce  │")
    print("  │   integration has been failing for the last hour and     │")
    print("  │   our lead pipeline is completely blocked.'              │")
    print("  │                                                          │")
    print("  │  'This is Marcus Chen. My dashboard has been broken for  │")
    print("  │   a week and nobody is fixing it. I'm looking at other   │")
    print("  │   vendors.'                                              │")
    print("  │                                                          │")
    print("  │  'I was charged $299 during your outage yesterday and    │")
    print("  │   I want a full refund.'                                 │")
    print("  └─────────────────────────────────────────────────────────┘")
    print()

    async with ws_serve(handle_connection, "localhost", 8000, process_request=process_request):
        await asyncio.Future()


async def _handle_supervision_with_inject(ws, session_id: str) -> None:
    """Wrap handle_supervision to intercept 'inject' commands before passing through."""
    from livelink.supervise import (
        _parse,
        _send,
        get_session,
        _SUBSCRIBE_TIMEOUT,
        _event_to_wire,
        _get_pending_approvals,
    )

    session = get_session(session_id)
    if session is None:
        await ws.close(4404, "session_not_found")
        return

    event_bus = session.event_bus
    if event_bus is None:
        await ws.close(4404, "supervision_not_enabled")
        return

    input_manager = session.input_manager
    cancellation_token = session.cancellation_token

    pending = _get_pending_approvals(input_manager)
    await _send(
        ws,
        {
            "type": "connected",
            "session_id": session_id,
            "model": session.agent.model,
            "state": "ended" if not session.is_connected else "running",
            "pending_approvals": pending,
            "replay_from": None,
        },
    )

    try:
        subscribe_msg = await asyncio.wait_for(ws.recv(), timeout=_SUBSCRIBE_TIMEOUT)
    except (asyncio.TimeoutError, Exception):
        await ws.close(4408, "subscribe_timeout")
        return

    cmd = _parse(subscribe_msg)
    if cmd is None or cmd.get("type") != "subscribe":
        await _send(
            ws,
            {
                "type": "error",
                "cmd_id": "",
                "code": "invalid_command",
                "message": "First message must be subscribe",
            },
        )
        await ws.close(4408, "subscribe_timeout")
        return

    cmd_id = cmd.get("cmd_id", "")
    after_event_id = cmd.get("after_event_id")

    if after_event_id:
        history = event_bus.history(limit=1000)
        found_idx = None
        for i, ev in enumerate(history):
            if ev.event_id == after_event_id:
                found_idx = i
                break
        if found_idx is None:
            await _send(
                ws,
                {
                    "type": "error",
                    "cmd_id": cmd_id,
                    "code": "replay_gap",
                    "message": "Event not in history buffer",
                },
            )
            return
        for ev in history[found_idx + 1 :]:
            await _send(ws, _event_to_wire(ev))

    await _send(ws, {"type": "ack", "cmd_id": cmd_id, "detail": {}})

    send_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1000)

    async def _event_handler(event) -> None:
        try:
            send_queue.put_nowait(_event_to_wire(event))
        except asyncio.QueueFull:
            pass

    sub_id = event_bus.subscribe_all(_event_handler)
    try:
        sender_task = asyncio.create_task(_sender(ws, send_queue))
        receiver_task = asyncio.create_task(
            _receiver_with_inject(ws, send_queue, session, input_manager, cancellation_token)
        )
        done, pending_tasks = await asyncio.wait(
            [sender_task, receiver_task], return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending_tasks:
            t.cancel()
        await asyncio.gather(*pending_tasks, return_exceptions=True)
    finally:
        event_bus.unsubscribe(sub_id)


async def _sender(ws, queue: asyncio.Queue) -> None:
    import json

    while True:
        msg = await queue.get()
        await ws.send(json.dumps(msg))


async def _receiver_with_inject(ws, send_queue, session, input_manager, cancellation_token) -> None:
    """Process commands including the 'inject' extension for supervisor guidance."""
    from livelink.supervise import _parse
    from livelink.supervision.hitl import InputStatus

    async for raw in ws:
        cmd = _parse(raw)
        if cmd is None:
            send_queue.put_nowait(
                {
                    "type": "error",
                    "cmd_id": "",
                    "code": "invalid_command",
                    "message": "Malformed JSON",
                }
            )
            continue

        cmd_type = cmd.get("type", "")
        cmd_id = cmd.get("cmd_id", "")

        if cmd_type == "inject":
            text = cmd.get("text", "").strip()
            if text:
                push_supervisor_note(text)
                send_queue.put_nowait(
                    {"type": "ack", "cmd_id": cmd_id, "detail": {"injected": text[:60]}}
                )
                logger.info("  ◆ Supervisor injected: %s", text[:80])
            else:
                send_queue.put_nowait(
                    {
                        "type": "error",
                        "cmd_id": cmd_id,
                        "code": "invalid_command",
                        "message": "inject requires 'text' field",
                    }
                )

        elif cmd_type == "resolve":
            request_id = cmd.get("request_id", "")
            answer = cmd.get("answer", "")
            if not input_manager:
                send_queue.put_nowait(
                    {
                        "type": "error",
                        "cmd_id": cmd_id,
                        "code": "session_ended",
                        "message": "No input manager",
                    }
                )
                continue
            try:
                status = input_manager.get_status(request_id)
            except KeyError:
                send_queue.put_nowait(
                    {
                        "type": "error",
                        "cmd_id": cmd_id,
                        "code": "unknown_request",
                        "message": f"No pending request: {request_id}",
                    }
                )
                continue
            if status == InputStatus.ANSWERED:
                send_queue.put_nowait(
                    {"type": "ack", "cmd_id": cmd_id, "detail": {"already_resolved": True}}
                )
                continue
            try:
                input_manager.resolve(request_id, answer, source="supervisor")
            except KeyError:
                send_queue.put_nowait(
                    {"type": "ack", "cmd_id": cmd_id, "detail": {"already_resolved": True}}
                )
                continue
            send_queue.put_nowait({"type": "ack", "cmd_id": cmd_id, "detail": {}})

        elif cmd_type == "cancel":
            reason = cmd.get("reason", "supervisor_cancelled")
            if cancellation_token is None:
                send_queue.put_nowait(
                    {
                        "type": "error",
                        "cmd_id": cmd_id,
                        "code": "session_ended",
                        "message": "No cancellation token",
                    }
                )
                continue
            if cancellation_token.is_cancelled:
                send_queue.put_nowait(
                    {"type": "ack", "cmd_id": cmd_id, "detail": {"already_cancelled": True}}
                )
                continue
            cancellation_token.cancel(reason=reason)
            send_queue.put_nowait({"type": "ack", "cmd_id": cmd_id, "detail": {}})

        elif cmd_type == "inspect":
            from livelink.supervise import _get_pending_approvals

            detail = {
                "session_id": session.session_id,
                "model": session.agent.model,
                "turn_count": session.turn_count,
                "state": "running" if session.is_connected else "ended",
                "is_cancelled": cancellation_token.is_cancelled if cancellation_token else False,
                "pending_approvals": _get_pending_approvals(input_manager),
            }
            send_queue.put_nowait({"type": "ack", "cmd_id": cmd_id, "detail": detail})

        else:
            send_queue.put_nowait(
                {
                    "type": "error",
                    "cmd_id": cmd_id,
                    "code": "invalid_command",
                    "message": f"Unknown: {cmd_type}",
                }
            )


if __name__ == "__main__":
    asyncio.run(main())
