"""Demonstrate the paper engine with synthetic prices and fixed dummy signals.

No network, API key, fitted estimator, or live state is used. Output describes
software behaviour, not model accuracy or investment performance.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from engine import Engine


def demo_signals(_frames, _at):
    """Create deliberately opposite signals to make account separation visible."""
    return {
        "base": {
            "confidence": 0.6,
            "p_up": 0.6,
            "side": 1,
            "allowed": True,
            "legacy_size": 1.5,
        },
        "candidate": {
            "confidence": 0.6,
            "p_up": 0.4,
            "side": -1,
            "allowed": True,
        },
    }


def run_demo():
    """Fill on the next observation, resume, and close all three accounts."""
    config = json.loads(Path(__file__).with_name("protocol.json").read_text())
    start = int(pd.Timestamp("2026-09-21 10:00:00Z").timestamp())
    bundle_id = "synthetic-review-demo-v1"

    with TemporaryDirectory(prefix="fx-paper-demo-") as directory:
        root = Path(directory)
        engine = Engine(root, config, bundle_id, created=start - 1000)
        try:
            engine.atomic_step(
                [], start, {}, {}, True, demo_signals, start + 905
            )
            entry_time = start + 906
            first_tick = (1, entry_time * 1000, entry_time, 150.0)
            engine.atomic_step(
                [first_tick], None, {}, {}, True, demo_signals, entry_time
            )
            original_deadline = engine.state["end"]
        finally:
            engine.close()

        engine = Engine(root, config, bundle_id)
        try:
            # Replaying an already-seen observation must not create another order.
            engine.atomic_step(
                [first_tick], start, {}, {}, True, demo_signals, entry_time
            )
            for tick_id, elapsed in enumerate(range(60, 7201, 60), start=2):
                at = entry_time + elapsed
                tick = (tick_id, at * 1000, at, 150.1)
                engine.atomic_step(
                    [tick], None, {}, {}, True, demo_signals, at
                )

            entries = engine.db.execute(
                "SELECT COUNT(*) FROM events WHERE kind = 'ENTRY'"
            ).fetchone()[0]
            accounts = engine.state["accounts"]
            assert entries == 3, "Restart duplicated a paper entry"
            assert engine.state["end"] == original_deadline
            assert all(account["trades"] == 1 for account in accounts.values())
            assert all(account["position"] is None for account in accounts.values())
            assert all(
                account["stress_equity"] <= account["equity"] + 1e-8
                for account in accounts.values()
            )
            return {
                "mode": "SYNTHETIC_DEMO_NOT_RESEARCH_RESULTS",
                "real_orders": False,
                "network_used": False,
                "model_used": False,
                "restart_preserved_deadline": True,
                "duplicate_entries_after_restart": entries - 3,
                "accounts": {
                    name: {
                        "closed_trades": account["trades"],
                        "open_position": account["position"],
                        "synthetic_pnl_jpy": round(
                            account["equity"] - config["initial_equity"], 4
                        ),
                    }
                    for name, account in accounts.items()
                },
                "limitations": "Fixed dummy signals and artificial prices; not ML performance.",
            }
        finally:
            engine.close()


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2, allow_nan=False))
