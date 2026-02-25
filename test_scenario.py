"""
End-to-end failover demo for Zephyr Smart Routing Engine.

Recreates the real-world incident where Zephyr's primary processor went down,
causing payment success rates to plummet. This script proves that the smart
routing engine detects the failure, redirects traffic, and recovers automatically.

The demo runs in 3 phases against the live API:

  Phase 1 - Normal Operation (baseline):
    All processors are healthy. The cost-aware router sends traffic to QuickCharge
    (cheapest fee at 2.7%). Establishes that routing and health tracking work.

  Phase 2 - Outage (failover):
    QuickCharge's success rate is dropped to 10% via /simulate/outage.
    As transactions fail, the sliding window detects degradation, the circuit
    breaker marks QuickCharge as unhealthy (<60% success), and traffic
    automatically shifts to PayFlow Pro (next cheapest healthy processor).

  Phase 3 - Recovery (auto-healing):
    QuickCharge is restored via /simulate/recover. The probe mechanism
    periodically sends test transactions to unhealthy processors. As probes
    succeed, QuickCharge's sliding window improves and it becomes eligible
    for routing again.

Each phase prints traffic distribution and health status so a reviewer can
visually confirm the failover and recovery behavior.

Usage:
    1. Start the server:  python3 -m uvicorn app.main:app --reload
    2. Run this script:   python3 test_scenario.py
"""

import httpx
import time

BASE = "http://localhost:8000"
BATCH_SIZE = 80


def send_batch(client: httpx.Client, count: int) -> dict[str, dict]:
    """Send a batch of transactions and return per-processor stats."""
    stats: dict[str, dict] = {}
    for i in range(count):
        currency = ["COP", "PEN", "CLP"][i % 3]
        resp = client.post(
            f"{BASE}/transactions",
            json={"amount": 10000 + i * 100, "currency": currency},
        )
        data = resp.json()
        pid = data["processor_id"]
        if pid not in stats:
            stats[pid] = {"name": data["processor_name"], "approved": 0, "declined": 0}
        if data["status"] == "approved":
            stats[pid]["approved"] += 1
        else:
            stats[pid]["declined"] += 1
    return stats


def print_stats(phase: str, stats: dict[str, dict]):
    print(f"\n{'='*60}")
    print(f"  {phase}")
    print(f"{'='*60}")
    total = sum(s["approved"] + s["declined"] for s in stats.values())
    for pid, s in sorted(stats.items()):
        count = s["approved"] + s["declined"]
        pct = count / total * 100 if total else 0
        rate = s["approved"] / count * 100 if count else 0
        print(f"  {s['name']:15s} ({pid}): {count:3d} txns ({pct:5.1f}%)  "
              f"approved={s['approved']}, declined={s['declined']}, rate={rate:.0f}%")
    total_approved = sum(s["approved"] for s in stats.values())
    print(f"  {'':15s} Total: {total} txns, {total_approved} approved ({total_approved/total*100:.0f}%)")


def print_health(client: httpx.Client):
    resp = client.get(f"{BASE}/health")
    data = resp.json()
    print(f"\n  Processor Health:")
    for p in data["processors"]:
        icon = "OK" if p["is_routing_enabled"] else "XX"
        print(f"    [{icon}] {p['processor_name']:15s}  "
              f"rate={p['success_rate']*100:5.1f}%  "
              f"status={p['status']:9s}  "
              f"attempts={p['total_attempts']}")


def main():
    client = httpx.Client()

    print("\n" + "#" * 60)
    print("  ZEPHYR SMART ROUTING ENGINE - FAILOVER DEMO")
    print("#" * 60)

    # Clean slate: reset all processor success rates and health data
    client.post(f"{BASE}/simulate/reset")

    # --- Phase 1: Baseline ---
    # All processors healthy. Cost-aware router picks QuickCharge (cheapest).
    # Expected: ~100% traffic to QuickCharge, ~80% approval rate.
    print("\n>> Phase 1: Sending 80 transactions (all processors healthy)")
    stats = send_batch(client, BATCH_SIZE)
    print_stats("Phase 1 - Normal Operation", stats)
    print_health(client)

    # --- Phase 2: Outage simulation ---
    # Drop QuickCharge to 10% success rate (simulates processor downtime).
    # The circuit breaker should detect the degradation within ~20-30 txns
    # and shift traffic to PayFlow Pro (next cheapest healthy processor).
    # Expected: QuickCharge marked [XX] unhealthy, majority traffic on PayFlow Pro.
    print("\n>> Triggering OUTAGE on processor_c (QuickCharge)...")
    resp = client.post(f"{BASE}/simulate/outage/processor_c")
    print(f"   {resp.json()['message']}")
    time.sleep(0.5)

    print(f"\n>> Phase 2: Sending 80 transactions (processor_c degraded)")
    stats = send_batch(client, BATCH_SIZE)
    print_stats("Phase 2 - During Outage (QuickCharge down)", stats)
    print_health(client)

    # --- Phase 3: Recovery ---
    # Restore QuickCharge to original success rate. The probe mechanism sends
    # 1 in every 10 transactions to unhealthy processors. As probes succeed,
    # QuickCharge's sliding window improves. Once it crosses 60%, it becomes
    # eligible for routing again (auto-recovery).
    # Expected: QuickCharge receives probe traffic and gradually recovers.
    print("\n>> RECOVERING processor_c (QuickCharge)...")
    resp = client.post(f"{BASE}/simulate/recover/processor_c")
    print(f"   {resp.json()['message']}")
    time.sleep(0.5)

    print(f"\n>> Phase 3: Sending 80 transactions (processor_c recovered)")
    stats = send_batch(client, BATCH_SIZE)
    print_stats("Phase 3 - After Recovery", stats)
    print_health(client)

    print(f"\n{'#'*60}")
    print("  DEMO COMPLETE")
    print(f"{'#'*60}\n")

    client.close()


if __name__ == "__main__":
    main()
