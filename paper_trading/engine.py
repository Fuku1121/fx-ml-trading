"""Atomic paper accounts; no broker integration and no network calls."""
import copy
import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Callable

import pandas as pd

BAR_SECONDS = 900
DAY_SECONDS = 86400
CLOCK_BACKWARD_TOLERANCE_SECONDS = 10
FINALIZATION_GRACE_SECONDS = 5
USDJPY_PIP = 0.01


def market_closed(stamp: float) -> bool:
    timestamp = pd.Timestamp(stamp, unit='s', tz='UTC').tz_convert('America/New_York')
    return (
        timestamp.dayofweek == 5
        or (timestamp.dayofweek == 4 and timestamp.hour >= 17)
        or (timestamp.dayofweek == 6 and timestamp.hour < 17)
    )


def next_bar(stamp: int) -> int:
    stamp += BAR_SECONDS
    while market_closed(stamp):
        stamp += BAR_SECONDS
    return stamp


def crosses_rollover(start: float, end: float) -> bool:

    def day(timestamp):
        return (pd.Timestamp(
            timestamp,
            unit='s',
            tz='UTC'
        ).tz_convert('America/New_York') + pd.Timedelta(hours=7)).date()
    return day(start) != day(end)


def costs(config: dict[str, Any], entry: float) -> tuple[float, float]:
    pip = USDJPY_PIP
    usual = (
        config['commission_return_roundtrip']
        + (config['assumed_spread_pips'] + config['slippage_pips_roundtrip']) * pip / entry
    )
    stress = (
        config['commission_return_roundtrip']
        + (
            config['assumed_spread_pips'] * config['stress_spread_multiplier']
            + config['stress_slippage_pips_roundtrip']
        ) * pip / entry
    )
    return (usual, stress)


class Engine:

    def __init__(
        self,
        root: str | Path,
        config: dict[str, Any],
        bundle: str,
        created: float | None = None,
        clock: Callable[[], float] | None = None
    ):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.clock = clock
        self.db = sqlite3.connect(self.root / 'comparison.sqlite3')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript(
            """
          CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS decisions(model TEXT,bar INTEGER,data TEXT NOT NULL,PRIMARY KEY(model,bar));
          CREATE TABLE IF NOT EXISTS trades(account TEXT,bar INTEGER,data TEXT NOT NULL,PRIMARY KEY(account,bar));
          CREATE TABLE IF NOT EXISTS equity(at REAL,account TEXT,data TEXT NOT NULL,PRIMARY KEY(at,account));
          CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at REAL,kind TEXT,detail TEXT);
        """
        )
        row = self.db.execute('SELECT data FROM state WHERE id=1').fetchone()
        if row:
            self.state = json.loads(row[0])
            if self.state['bundle'] != bundle:
                self.db.close()
                raise RuntimeError('Bundle changed; existing experiment cannot resume')
        else:
            if created is None:
                raise ValueError('New experiment needs an explicit creation time')
            accounts = {}
            for name in ('base_fixed', 'candidate_fixed', 'base_legacy'):
                accounts[name] = {
                    'equity': config['initial_equity'],
                    'stress_equity': config['initial_equity'],
                    'position': None,
                    'pending': None,
                    'trades': 0,
                    'mtm_peak': config['initial_equity'],
                    'mtm_max_drawdown': 0.0
                }
            self.state = {
                'bundle': bundle,
                'created': created,
                'updated_at': created,
                'initial_equity': config['initial_equity'],
                'phase': 'WARMUP',
                'start': None,
                'end': None,
                'last_bar': None,
                'tick_id': 0,
                'last_tick': None,
                'accounts': accounts,
                'reason': 'Waiting for four eligible histories',
                'histories': {symbol: {
                    'anchor': None,
                    'last': None,
                    'count': 0,
                    'cursor': None
                } for symbol in config['symbols']}
            }
            with self.db:
                self.save()

    def save(self) -> None:
        """Use the caller's transaction so decisions, trades and state commit together."""
        self.db.execute(
            'INSERT OR REPLACE INTO state VALUES(1,?)',
            (json.dumps(self.state, allow_nan=False),)
        )

    def event(self, at: float, kind: str, detail: str) -> None:
        self.db.execute('INSERT INTO events(at,kind,detail) VALUES(?,?,?)', (at, kind, detail))

    def halt(self, at: float, reason: str) -> None:
        self.state.update(phase='HALTED', reason=reason, updated_at=at)
        for account in self.state['accounts'].values():
            account['pending'] = None
        self.event(at, 'HALTED', reason)

    def disconnected(self, at: float) -> None:
        with self.db:
            for account in self.state['accounts'].values():
                account['pending'] = None
            self.event(at, 'DISCONNECTED', 'Pending entries cancelled; positions retained')
            self.save()

    def atomic_step(
        self,
        ticks,
        bar,
        frames,
        quality,
        ready,
        predict,
        at,
        histories=None,
        revoked=False
    ):
        # SQLite rolls back persisted rows; restore in-memory state on the same failure.
        before = copy.deepcopy(self.state)
        try:
            with self.db:
                if histories is not None:
                    self.state['histories'] = histories
                if revoked and any((account['position'] for account in self.state['accounts'].values())):
                    self.halt(at, 'Historical quality revoked while holding; review required')
                else:
                    self._step(ticks, bar, frames, quality, ready, predict, at)
                if before['phase'] not in ('HALTED', 'COMPLETED'):
                    self.state['updated_at'] = at
                self.save()
        except BaseException:
            self.state = before
            raise

    def _step(self, ticks, bar, frames, quality, ready, predict, at):
        state = self.state
        if state['phase'] in ('HALTED', 'COMPLETED'):
            return
        if (
            at < state['created'] - CLOCK_BACKWARD_TOLERANCE_SECONDS
            or (
                state['last_tick'] is not None
                and at < state['last_tick'] - CLOCK_BACKWARD_TOLERANCE_SECONDS
            )
        ):
            self.halt(at, 'Clock moved backwards')
            return
        if not self._process_ticks(ticks, at):
            return
        if self._check_deadlines(at):
            return
        self._process_bar(bar, frames, quality, ready, predict, at)

    def _process_ticks(self, ticks, at: float) -> bool:
        """Keep input order: consumed IDs must stay consumed even for rejected ticks."""
        state = self.state
        config = self.config
        for tick_id, event_ms, received, price in ticks:
            if tick_id <= state['tick_id']:
                continue
            state['tick_id'] = tick_id
            stamp = event_ms / 1000
            # A future-dated observation must never fill an order.
            if stamp > at:
                continue
            if state['last_tick'] is not None and stamp < state['last_tick']:
                continue
            holding = any((account['position'] for account in state['accounts'].values()))
            if (
                holding
                and state['last_tick'] is not None
                and (stamp - state['last_tick'] > config['max_observation_gap_seconds'])
            ):
                self.halt(at, 'USDJPY observation gap while holding; PnL unresolved')
                return False
            state['last_tick'] = stamp
            fresh = (
                0 <= at - stamp <= config['max_tick_age_seconds']
                and 0 <= at - received <= config['max_tick_age_seconds']
            )
            for name, account in state['accounts'].items():
                # An exit precedes an entry on the same observation, as in the saved contract.
                if not self._close_due_position(name, account, stamp, received, price, fresh, at):
                    return False
                self._fill_pending_order(name, account, stamp, received, price, fresh, at)
                if fresh:
                    self._mark_to_market(name, account, price)
        return True

    def _close_due_position(self, name, account, stamp, received, price, fresh, at) -> bool:
        config = self.config
        position = account['position']
        if position and stamp >= position['due']:
            if not fresh or stamp - position['due'] > config['max_observation_gap_seconds']:
                self.halt(at, 'Exit observation unavailable on time; position retained')
                return False
            normal, stress = costs(config, position['entry_price'])
            if name == 'base_legacy':
                normal = stress = config['legacy_cost_return']
            gross = position['side'] * (price / position['entry_price'] - 1)
            net = position['size'] * (gross - normal)
            stress_net = position['size'] * (gross - stress)
            account['equity'] *= 1 + net
            account['stress_equity'] *= 1 + stress_net
            account['trades'] += 1
            record = {
                **position,
                'exit_time': stamp,
                'exit_received': received,
                'exit_price': price,
                'gross_return': gross,
                'net_return': net,
                'stress_net_return': stress_net,
                'equity_after': account['equity'],
                'stress_equity_after': account['stress_equity'],
                'cost_return': normal,
                'stress_cost_return': stress,
                'fill_model': 'received_observation_not_bid_ask'
            }
            self.db.execute(
                'INSERT INTO trades VALUES(?,?,?)',
                (name, position['bar'], json.dumps(record))
            )
            account['position'] = None
            self.event(at, 'EXIT', name)
        return True

    def _fill_pending_order(self, name, account, stamp, received, price, fresh, at) -> None:
        pending = account['pending']
        if pending:
            if at > pending['expires']:
                account['pending'] = None
                self.event(at, 'ENTRY_EXPIRED', name)
            elif (
                fresh
                and received > pending['decision_at']
                and (stamp >= pending['decision_at'])
                and (not market_closed(stamp))
            ):
                account['position'] = {
                    **pending,
                    'entry_time': stamp,
                    'entry_received': received,
                    'entry_price': price,
                    'due': stamp + pending['hold']
                }
                account['pending'] = None
                self.event(at, 'ENTRY', name)

    def _mark_to_market(self, name, account, price: float) -> None:
        config = self.config
        position = account['position']
        mtm = account['equity']
        if position:
            normal, _ = costs(config, position['entry_price'])
            if name == 'base_legacy':
                normal = config['legacy_cost_return']
            mtm *= 1 + position['size'] * (position['side'] * (price / position['entry_price'] - 1) - normal)
        account['mtm_peak'] = max(account['mtm_peak'], mtm)
        account['mtm_max_drawdown'] = min(
            account['mtm_max_drawdown'],
            mtm / account['mtm_peak'] - 1
        )
        account['last_observed_mtm'] = mtm

    def _check_deadlines(self, at: float) -> bool:
        """Apply timeouts even when no new price or decision bar has arrived."""
        state = self.state
        config = self.config
        for name, account in state['accounts'].items():
            if (
                account['position']
                and at - (state['last_tick'] or at) > config['max_observation_gap_seconds']
            ):
                self.halt(at, 'No USDJPY observations for 120 seconds while holding')
                return True
            if account['pending'] and at > account['pending']['expires']:
                account['pending'] = None
                self.event(at, 'ENTRY_EXPIRED', name)
        if state['end'] is not None and at >= state['end']:
            if any((account['position'] for account in state['accounts'].values())):
                self.halt(at, 'End reached with unresolved position')
            else:
                for account in state['accounts'].values():
                    account['pending'] = None
                state.update(phase='COMPLETED', reason='Common 30-day comparison completed')
            return True
        if state['start'] is None and at - state['created'] >= config['warmup_max_days'] * DAY_SECONDS:
            self.halt(at, 'Warmup exceeded configured limit; check all four subscriptions')
            return True
        return False

    def _process_bar(self, bar, frames, quality, ready, predict, at: float) -> None:
        state = self.state
        config = self.config
        if bar is None or (state['last_bar'] is not None and bar <= state['last_bar']):
            return
        if not bar + BAR_SECONDS <= at <= bar + BAR_SECONDS + config['entry_window_seconds']:
            return
        if market_closed(bar):
            return
        if not ready:
            # Let collectors finalize before consuming this bar with a no-trade record.
            if at < bar + BAR_SECONDS + config['entry_window_seconds'] - FINALIZATION_GRACE_SECONDS:
                return
            if state['start'] is not None:
                for model in ('base', 'candidate'):
                    self.decision(
                        model,
                        bar,
                        {
                            'action': 'NO_TRADE',
                            'reason': 'SHARED_DATA_QUALITY',
                            'quality': quality,
                            'at': at
                        }
                    )
                state['last_bar'] = bar
            state['reason'] = 'Waiting for four aligned clean decision bars and eligible histories'
            return
        predictions = predict(frames, at)
        decision_at = self.clock() if self.clock is not None else at
        for prediction in predictions.values():
            if not math.isfinite(prediction['confidence']) or not 0 <= prediction['confidence'] <= 1:
                raise ValueError('Invalid model probability')
        if state['start'] is None:
            if decision_at > bar + BAR_SECONDS + config['entry_window_seconds']:
                return
            state.update(
                phase='RUNNING',
                start=decision_at,
                end=decision_at + config['comparison_days'] * DAY_SECONDS
            )
            self.event(at, 'COMPARISON_STARTED', 'Both predictors ready; one common deadline')
        for model, prediction in predictions.items():
            self._record_prediction(model, prediction, bar, quality, decision_at)
        state['last_bar'] = bar
        state['reason'] = 'Comparison running'

    def _record_prediction(self, model, prediction, bar, quality, decision_at: float) -> None:
        # Guard order determines the recorded reason when several conditions fail.
        state = self.state
        config = self.config
        account = 'base_fixed' if model == 'base' else 'candidate_fixed'
        targets = [account, 'base_legacy'] if model == 'base' else [account]
        hold = config['base_hold_seconds'] if model == 'base' else config['candidate_hold_seconds']
        reason = prediction.get('reason', 'LOW_CONFIDENCE')
        allowed = bool(prediction['allowed'])
        if decision_at > bar + BAR_SECONDS + config['entry_window_seconds']:
            allowed = False
            reason = 'INFERENCE_TOO_LATE'
        if (
            any(
                state['accounts'][account_name]['position']
                or state['accounts'][account_name]['pending']
                for account_name in targets
            )
        ):
            allowed = False
            reason = 'POSITION_OPEN'
        if (
            decision_at + config['entry_window_seconds'] + hold
            + config['max_observation_gap_seconds'] >= state['end']
        ):
            allowed = False
            reason = 'END_WINDOW'
        if crosses_rollover(decision_at, decision_at + config['entry_window_seconds'] + hold):
            allowed = False
            reason = 'ROLLOVER_WINDOW'
        self.decision(
            model,
            bar,
            {
                **prediction,
                'action': 'SIGNAL' if allowed else 'NO_TRADE',
                'reason': 'SIGNAL' if allowed else reason,
                'quality': quality,
                'at': decision_at
            }
        )
        if allowed:
            for name in targets:
                size = prediction.get('legacy_size', 1.0) if name == 'base_legacy' else 1.0
                if not math.isfinite(size) or size <= 0:
                    raise ValueError('Invalid size')
                state['accounts'][name]['pending'] = {
                    'bar': bar,
                    'side': prediction['side'],
                    'size': size,
                    'hold': hold,
                    'decision_at': decision_at,
                    'expires': bar + BAR_SECONDS + config['entry_window_seconds'],
                    'confidence': prediction['confidence'],
                    'quality': quality
                }

    def decision(self, model, bar, data):
        self.db.execute(
            'INSERT INTO decisions VALUES(?,?,?)',
            (model, bar, json.dumps(data, allow_nan=False))
        )

    def sample_equity(self, at: float) -> None:
        with self.db:
            for name, account in self.state['accounts'].items():
                self.db.execute(
                    'INSERT OR REPLACE INTO equity VALUES(?,?,?)',
                    (int(at), name, json.dumps(account))
                )

    def close(self) -> None:
        self.db.close()
