"""Simulated operational tools for incident response.

All responses are deterministic — no external services required.
Data tells a coherent story: a recent deploy introduced Redis caching
that doesn't handle evictions gracefully under memory pressure.
"""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def check_metrics(service: str, metric_type: str) -> str:
    """Check service metrics. metric_type: error_rate | latency | throughput | saturation.

    Args:
        service: Service name (e.g. checkout-service).
        metric_type: One of error_rate, latency, throughput, saturation.
    """
    if service == "checkout-service":
        if metric_type == "error_rate":
            return (
                "Service: checkout-service | Metric: error_rate\n"
                "Current: 12.4% (baseline: 0.3%)\n"
                "Trend: Spike started 14:32 UTC, rising\n"
                "  /api/checkout/submit: 23.1% (HTTP 500)\n"
                "  /api/checkout/validate: 2.1% (normal)\n"
                "  /api/checkout/confirm: 18.7% (HTTP 503)"
            )
        if metric_type == "latency":
            return (
                "Service: checkout-service | Metric: p99_latency\n"
                "Current: 2,800ms (baseline: 400ms)\n"
                "Percentiles: p50=620ms p90=1,900ms p99=2,800ms\n"
                "Trend: Correlated with error spike at 14:32 UTC\n"
                "Note: Redis connection timeouts inflating tail latency"
            )
        if metric_type == "throughput":
            return (
                "Service: checkout-service | Metric: throughput\n"
                "Current: 790 req/s (baseline: 1,200 req/s) — down 34%\n"
                "Trend: Drop since 14:32 UTC\n"
                "Note: Clients retrying failed requests, unique users down ~50%"
            )
        if metric_type == "saturation":
            return (
                "Service: checkout-service | Metric: saturation\n"
                "CPU: 61% (baseline 35%) | Memory: 72% (baseline 55%)\n"
                "Threads blocked on I/O: 47 (baseline: 3)\n"
                "Note: Blocked threads waiting on Redis connection pool"
            )
    return f"No metrics data for {service}/{metric_type}"


@tool
def query_logs(service: str, severity: str, time_range: str) -> str:
    """Query structured logs for a service.

    Args:
        service: Service name.
        severity: Log level — error, warn, or info.
        time_range: Time window (e.g. 15m, 1h).
    """
    if service == "checkout-service" and severity == "error":
        return (
            "Errors for checkout-service (last 15m): 1,847 total\n"
            "  1. RedisConnectionError: Connection pool exhausted (923x)\n"
            "     cache.session_hydrate() -> redis.get() -> ConnectionPool.get_connection()\n"
            "  2. HTTP 503 from payment-gateway (downstream timeout) (612x)\n"
            "     Gateway healthy — timeouts from checkout holding conns too long\n"
            "  3. CacheEvictionStorm: 847 keys evicted in 12s (312x)\n"
            "     New caching code has no eviction handler, raises on missing key"
        )
    if service == "checkout-service" and severity == "warn":
        return (
            "Warnings for checkout-service (last 15m): 3,201 total\n"
            "  1. Cache miss rate: 67% (normal: 3%) — 2,100 occurrences\n"
            "  2. Redis pool near capacity (847/1000) — 890 occurrences\n"
            "  3. Retry storm: avg 3.2 retries/req to Redis — 211 occurrences"
        )
    if service == "checkout-service" and severity == "info":
        return (
            "Info for checkout-service (last 15m): 12,400 entries\n"
            "  Session hydrated from cache: 4,100 (was 0 before v2.14.3)\n"
            "  Cache key written (no TTL): 3,800\n"
            "  Fallback to direct DB query: 2,300\n"
            "  Request completed normally: 2,200"
        )
    return f"No log data for {service}/{severity}/{time_range}"


@tool
def check_deployments(service: str, hours: int) -> str:
    """Check recent deployments for a service.

    Args:
        service: Service name.
        hours: How many hours back to look.
    """
    if service == "checkout-service":
        return (
            "Recent deployments for checkout-service:\n"
            "  1. v2.14.3 — deployed 13:45 UTC (47 min before error spike)\n"
            "     PR #1847 by @sarah.chen\n"
            "     Changelog: 'Added Redis caching layer for session hydration'\n"
            "     Diff: +342 lines (checkout/cache.py, checkout/handlers.py)\n"
            "     Feature flag: redis_session_cache (enabled at deploy)\n"
            "     Rollback target: v2.14.2\n"
            "  2. v2.14.2 — deployed 09:15 UTC (stable 4.5h before v2.14.3)\n"
            "     Changelog: 'Fix decimal rounding in tax calculation'\n"
            "  3. v2.14.1 — deployed 2 days ago\n"
            "     Changelog: 'Update payment-gateway SDK to v3.2'"
        )
    return f"No deployment data for {service} in last {hours}h"


@tool
def check_dependencies(service: str) -> str:
    """Check health of upstream and downstream dependencies for a service.

    Args:
        service: Service name to check dependencies for.
    """
    if service == "checkout-service":
        return (
            "Dependencies for checkout-service:\n"
            "  redis-cluster: DEGRADED\n"
            "    Memory: 14.2GB / 15GB (94.7%) | Eviction: 3x baseline\n"
            "    Connected clients: 891 (pool max/instance: 250)\n"
            "    Slowlog (>10ms): 34 entries in last 5 min\n"
            "  payment-gateway: HEALTHY (p99: 230ms, errors: 0.2%)\n"
            "    Note: 503s from checkout are client-side timeouts, not gateway\n"
            "  postgres-primary: HEALTHY (124/500 conns, lag: 0ms)\n"
            "    Query load: +18% from fallback queries on cache misses\n"
            "  user-service: HEALTHY (p99: 12ms)\n"
            "  inventory-service: HEALTHY (p99: 45ms)"
        )
    return f"No dependency data for {service}"


@tool
def run_query(query: str) -> str:
    """Run an ad-hoc observability query against metrics, traces, or logs.

    Args:
        query: Free-form query (e.g. 'redis connections', 'cache hit rate', 'error breakdown').
    """
    q = query.lower()
    if "redis" in q and "connection" in q:
        return (
            "Redis connections (checkout-service pods):\n"
            "  pod-a1: 248/250 | pod-a2: 250/250 (saturated)\n"
            "  pod-b1: 201/250 | pod-b2: 192/250\n"
            "  Total: 891/1000 | Acquire wait p99: 4,200ms (normal <5ms)\n"
            "  New conns since v2.14.3: +340 (session hydration cache)"
        )
    if "cache" in q and "hit" in q:
        return (
            "Cache stats (checkout-service, 30m):\n"
            "  Hit: 33% | Miss: 67% (caching didn't exist pre-v2.14.3)\n"
            "  Evicted keys accessed: 412 (return None -> crash in deserialize)\n"
            "  Keys without TTL: 18,400 (all from v2.14.3)\n"
            "  No TTL = removed only via eviction under memory pressure"
        )
    if "error" in q and "breakdown" in q:
        return (
            "Error breakdown (checkout-service, 30m):\n"
            "  RedisConnectionError: 48.2%\n"
            "  HTTP 503 (upstream timeout): 33.1%\n"
            "  ValueError (NoneType deserialize): 16.9%\n"
            "  Other: 1.8%\n"
            "  Chain: pool exhaustion -> timeout -> 503 cascade (all spike at 14:32)"
        )
    if "evict" in q or "memory" in q:
        return (
            "Redis eviction analysis:\n"
            "  Policy: allkeys-lru | Memory: 14.2/15GB\n"
            "  New keys (1h): 18,400 from v2.14.3 | Evicted (1h): 12,300\n"
            "  Burst: 847 keys/12s (3 events in 30m)\n"
            "  Pattern: checkout:session:* (no TTL)\n"
            "  Pre-existing keys: TTL=300s | v2.14.3 keys: no TTL"
        )
    if "deploy" in q or "version" in q or "canary" in q:
        return (
            "Deployment correlation:\n"
            "  v2.14.3 deployed 13:45 | First errors 14:32 (47 min lag)\n"
            "  Lag cause: Redis memory filled as cache keys accumulated\n"
            "  Canary: 5 min @ 10% — too short for memory pressure\n"
            "  Full rollout 13:50 — all pods writing keys without TTL"
        )
    return f"No results for query: {query}"


@tool
def scale_service(service: str, replicas: int) -> str:
    """Scale a service horizontally by adjusting replica count.

    Args:
        service: Service name to scale.
        replicas: Target number of replicas.
    """
    return (
        f"Scaling {service}: 4 -> {replicas} replicas\n"
        f"  ETA healthy: ~90s\n"
        f"  Warning: Each new pod opens 250 Redis connections.\n"
        f"  Adding replicas will INCREASE Redis connection pressure."
    )


@tool
def rollback_deployment(service: str, target_version: str) -> str:
    """Rollback a service to a previous deployment version.

    Args:
        service: Service name to roll back.
        target_version: Version to roll back to (e.g. v2.14.2).
    """
    return (
        f"Rolling back {service} to {target_version}...\n"
        f"  Strategy: rolling update (zero-downtime) | ETA: ~60s\n"
        f"  Effect: Redis caching layer removed, direct DB path restored\n"
        f"  Note: Existing cache keys remain until evicted (no TTL)"
    )


@tool
def toggle_feature_flag(flag_name: str, enabled: bool) -> str:
    """Toggle a feature flag on or off.

    Args:
        flag_name: Feature flag name (e.g. redis_session_cache).
        enabled: True to enable, False to disable.
    """
    state = "ENABLED" if enabled else "DISABLED"
    if flag_name == "redis_session_cache":
        effect = "Bypass Redis cache, use direct DB path" if not enabled else "Active"
        return (
            f"Flag '{flag_name}' -> {state} (propagation: ~5s)\n"
            f"  Effect: {effect}\n"
            f"  Note: Faster than rollback — code stays deployed but inactive"
        )
    return f"Flag '{flag_name}' -> {state} (propagation: ~5s)"


@tool
def page_oncall(team: str, severity: str, message: str) -> str:
    """Page the on-call engineer for a team.

    Args:
        team: Team name (e.g. checkout-team, platform-infra).
        severity: Incident severity — P1, P2, P3, or P4.
        message: Brief description for the page.
    """
    return (
        f"Paging {team} on-call ({severity})...\n"
        f"  Message: {message}\n"
        f"  Route: PagerDuty -> Slack #incidents -> phone\n"
        f"  Ack: @mike.torres in 38s | Bridge: https://meet.internal/inc-2847"
    )
