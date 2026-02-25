"""
Interactive failover demo for Zephyr Smart Routing Engine.

Walk through the full lifecycle — normal operation, processor outage,
automatic failover, and recovery — with pauses between each step so you
can narrate and observe the dashboard at http://localhost:8000/dashboard.

Usage:
    1. Start the server:  python3 -m uvicorn app.main:app --reload
    2. Open the dashboard: http://localhost:8000/dashboard
    3. Run this script:    python3 demo.py
"""

import httpx
import time
import sys

BASE = "http://localhost:8000"

# ── Helpers ──────────────────────────────────────────────────────────

def wait(prompt: str = "Press Enter to continue..."):
    print(f"\n  \033[90m{prompt}\033[0m", end="")
    input()

def section(title: str):
    width = 62
    print(f"\n\033[1m{'━' * width}\033[0m")
    print(f"\033[1m  {title}\033[0m")
    print(f"\033[1m{'━' * width}\033[0m")

def step(msg: str):
    print(f"\n  \033[96m▸\033[0m {msg}")

def send_transactions(client: httpx.Client, count: int, delay: float = 0.03):
    """Send transactions one-by-one with a small delay so the dashboard updates visibly."""
    stats: dict[str, dict] = {}
    for i in range(count):
        currency = ["COP", "PEN", "CLP"][i % 3]
        amount = round(15000 + i * 250.50, 2)
        resp = client.post(
            f"{BASE}/transactions",
            json={"amount": amount, "currency": currency},
        )
        data = resp.json()
        pid = data["processor_id"]
        if pid not in stats:
            stats[pid] = {"name": data["processor_name"], "approved": 0, "declined": 0}
        if data["status"] == "approved":
            stats[pid]["approved"] += 1
        else:
            stats[pid]["declined"] += 1

        done = i + 1
        bar_len = 30
        filled = int(bar_len * done / count)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r  Sending: {bar} {done}/{count}", end="", flush=True)
        time.sleep(delay)

    print()
    return stats


def print_traffic_table(stats: dict[str, dict]):
    total = sum(s["approved"] + s["declined"] for s in stats.values())
    if total == 0:
        return

    print()
    print(f"  {'Processor':<20s} {'Txns':>5s} {'Share':>7s} {'Approved':>9s} {'Declined':>9s} {'Rate':>7s}")
    print(f"  {'─' * 20} {'─' * 5} {'─' * 7} {'─' * 9} {'─' * 9} {'─' * 7}")

    for pid in sorted(stats):
        s = stats[pid]
        count = s["approved"] + s["declined"]
        share = count / total * 100
        rate = s["approved"] / count * 100 if count else 0

        rate_color = "\033[92m" if rate >= 70 else ("\033[93m" if rate >= 40 else "\033[91m")
        print(
            f"  {s['name']:<20s} {count:>5d} {share:>6.1f}% {s['approved']:>9d} {s['declined']:>9d} "
            f"{rate_color}{rate:>6.1f}%\033[0m"
        )

    total_ok = sum(s["approved"] for s in stats.values())
    overall = total_ok / total * 100
    print(f"  {'─' * 20} {'─' * 5} {'─' * 7} {'─' * 9} {'─' * 9} {'─' * 7}")
    print(f"  {'TOTAL':<20s} {total:>5d} {'100.0%':>7s} {total_ok:>9d} {total - total_ok:>9d} {overall:>6.1f}%")


def print_health(client: httpx.Client):
    resp = client.get(f"{BASE}/health")
    data = resp.json()

    print(f"\n  \033[1mProcessor Health Panel\033[0m  (threshold: {data['health_threshold'] * 100:.0f}%)\n")
    for p in data["processors"]:
        rate = p["success_rate"] * 100
        if p["is_routing_enabled"]:
            icon = "\033[92m●\033[0m"
            routing_label = "\033[92mrouting\033[0m"
        else:
            icon = "\033[91m●\033[0m"
            routing_label = "\033[91mexcluded\033[0m"

        print(
            f"  {icon} {p['processor_name']:<15s}  "
            f"rate={rate:5.1f}%  "
            f"status={p['status']:<9s}  "
            f"attempts={p['total_attempts']:<4d}  "
            f"{routing_label}"
        )


# ── Main demo ────────────────────────────────────────────────────────

def main():
    client = httpx.Client(timeout=10)

    try:
        client.get(f"{BASE}/health")
    except httpx.ConnectError:
        print("\n  \033[91mError: Cannot connect to the server at http://localhost:8000\033[0m")
        print("  Start it first with:  python3 -m uvicorn app.main:app --reload\n")
        sys.exit(1)

    section("ZEPHYR SMART ROUTING ENGINE — LIVE DEMO")
    print("\n  Dashboard: \033[4mhttp://localhost:8000/dashboard\033[0m")
    print("  Open it in a browser to watch health metrics update in real time.")

    # Reset everything
    client.post(f"{BASE}/simulate/reset")
    step("State reset — all processors healthy, no history.")

    # ── PHASE 1 ──────────────────────────────────────────────────────

    wait("Press Enter to start Phase 1 (normal operation)...")

    section("PHASE 1 — Normal Operation")
    step("Sending 100 transactions with all processors healthy.")
    step("Expect: traffic goes to QuickCharge (cheapest fee at 2.7%).")
    print()

    stats = send_transactions(client, 100)
    print_traffic_table(stats)
    print_health(client)

    # ── PHASE 2 ──────────────────────────────────────────────────────

    wait("Press Enter to trigger an outage on QuickCharge...")

    section("PHASE 2 — Processor Outage")
    step("Simulating outage on processor_c (QuickCharge) — dropping success rate to 10%.")
    resp = client.post(f"{BASE}/simulate/outage/processor_c")
    print(f"  Server response: {resp.json()['message']}")

    step("Sending 100 transactions while QuickCharge is degraded.")
    step("Expect: circuit breaker detects failures, traffic shifts to PayFlow Pro (2.9% fee).")
    print()

    stats = send_transactions(client, 100)
    print_traffic_table(stats)
    print_health(client)

    # ── PHASE 3 ──────────────────────────────────────────────────────

    wait("Press Enter to recover QuickCharge and observe auto-healing...")

    section("PHASE 3 — Recovery & Auto-Healing")
    step("Restoring processor_c (QuickCharge) to its original 80% success rate.")
    resp = client.post(f"{BASE}/simulate/recover/processor_c")
    print(f"  Server response: {resp.json()['message']}")

    step("Sending 100 more transactions.")
    step("Expect: probe mechanism tests QuickCharge every ~10 txns.")
    step("As probes succeed, its sliding window improves until it crosses 60% and re-enters routing.")
    print()

    stats = send_transactions(client, 100)
    print_traffic_table(stats)
    print_health(client)

    # ── DONE ─────────────────────────────────────────────────────────

    section("DEMO COMPLETE")
    print("\n  Summary:")
    print("    Phase 1 → All healthy, routed to cheapest processor (QuickCharge)")
    print("    Phase 2 → QuickCharge went down, circuit breaker kicked in, traffic shifted")
    print("    Phase 3 → QuickCharge recovered, probe mechanism detected it, traffic resumed")
    print(f"\n  Total transactions sent: 300")
    print(f"  Dashboard: \033[4mhttp://localhost:8000/dashboard\033[0m\n")

    client.close()


if __name__ == "__main__":
    main()
