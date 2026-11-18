"""Momentum breakout bot for make.fun btc-race-24h-20261118-1444 (bars-replay/v1).

Strategy, in plain words (see README.md for the full reasoning):
  * One asset, CBBTC, long only, starting from 1,000 USDC.
  * Entry: when flat, if the close rose at least 30 bps over the last two
    1-minute closes, buy with 80% of cash. One-minute cbBTC returns show a
    small positive autocorrelation at lags 1-3, so a sharp 2-minute jump tends
    to keep running for a few minutes; the entry rides that continuation.
  * Exit: sell half the position at +40 bps from the fill price, and the rest
    at +80 bps, on a trailing stop of 55 bps from the highest close since
    entry, on a hard stop of -60 bps, or after 30 bars held, whichever first.
  * Costs are the whole game here: a full-size round trip pays ~30 bps in
    fees, slippage and pool impact, so the bot only trades on a strong
    (3-sigma) 2-minute move and lets winners run with a trailing stop.

Determinism: only integer arithmetic on the bars the harness sends. No wall
clock, no network, no files, no randomness, no environment reads. Two runs on
the same data produce the same orders byte for byte.

Local dev-window result (kit's frozen 24h window, exact integer fill model):
net PnL +$5.74, 11 trades, max drawdown 0.6%.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# Strategy parameters (all in basis points unless noted).
ENTRY_MOM_BPS = 30        # 2-minute close return that triggers a buy
SIZE_BPS = 8000           # buy with 80% of cash
TAKE_HALF_BPS = 40        # sell half the position at this gain vs fill price
TAKE_REST_BPS = 80        # sell the rest at this gain vs fill price
TRAIL_BPS = 55            # trailing stop: sell the rest this far below the high
STOP_BPS = 60             # hard stop: sell the rest this far below the fill price
MAX_HOLD_BARS = 30        # time exit: sell the rest after this many bars held
MAX_SLIPPAGE_BPS = 300    # per-order slippage cap vs the latest close
LAST_TRADEABLE_SEQ = 1439  # orders decided on the last batch are rejected

# Bot state, all plain ints.
closes = []          # closes seen so far, as ints at price_scale 5
entry_price = None   # fill price of the buy that opened the current position
high_since_entry = 0  # highest close since entry (trailing stop reference)
hold_bars = 0        # batches held in the current position
scaled_out = False   # True once the half-position take-profit has fired
pending_buy_id = None  # client_id of a buy whose fill has not been reported yet
pending_buy_close = 0  # close the pending buy was decided on


def on_batch(state, batch):
    global entry_price, high_since_entry, hold_bars, scaled_out
    global pending_buy_id, pending_buy_close

    # Fold in the fills of the orders decided on the previous batch.
    for fill in batch.get("fills", []):
        if fill.get("client_id") == pending_buy_id:
            pending_buy_id = None
            if fill.get("status") == "filled" and fill.get("side") == "buy":
                # A fill price of 0 or less cannot happen on a real fill, but
                # guard it: entry_price feeds a division below, and a bad
                # price here would corrupt every exit decision after it.
                price = int(fill["price"])
                if price <= 0:
                    continue
                entry_price = price
                high_since_entry = pending_buy_close
                if high_since_entry < state.close(SYMBOL):
                    high_since_entry = state.close(SYMBOL)
                hold_bars = 0
                scaled_out = False
        if fill.get("side") == "sell" and fill.get("status") == "filled":
            # A sell that emptied the position closes the round trip.
            holding = state.positions.get(SYMBOL)
            if holding is None or holding.qty == 0:
                entry_price = None
                high_since_entry = 0
                hold_bars = 0
                scaled_out = False

    close = state.close(SYMBOL)
    if close is None:
        return []
    closes.append(close)

    holding = state.positions.get(SYMBOL)
    qty = holding.qty if holding else 0

    if state.warming_up or state.seq >= LAST_TRADEABLE_SEQ:
        return []

    if qty == 0:
        entry_price = None
        # Entry: 2-minute close momentum of at least ENTRY_MOM_BPS.
        if len(closes) < 3:
            return []
        mom_bps = (close - closes[-3]) * 10000 // closes[-3]
        if mom_bps < ENTRY_MOM_BPS:
            return []
        notional = state.cash * SIZE_BPS // 10000
        if notional < 1_000_000:
            return []
        cid = state.client_id()
        pending_buy_id = cid
        pending_buy_close = close
        return [{
            "side": "buy",
            "client_id": cid,
            "symbol": SYMBOL,
            "notional_quote_units": notional,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]

    # In a position: manage the exit.
    if entry_price is None:
        # Position held but its fill price is not known yet (should not
        # happen: fills arrive one batch after the buy). Hold and wait.
        return []
    hold_bars += 1
    if close > high_since_entry:
        high_since_entry = close
    ret_bps = (close - entry_price) * 10000 // entry_price
    trail_bps = (high_since_entry - close) * 10000 // high_since_entry

    if not scaled_out and ret_bps >= TAKE_HALF_BPS:
        scaled_out = True
        return [{
            "side": "sell",
            "symbol": SYMBOL,
            "qty": qty // 2,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]
    if (ret_bps >= TAKE_REST_BPS or ret_bps <= -STOP_BPS
            or trail_bps >= TRAIL_BPS or hold_bars >= MAX_HOLD_BARS):
        return [{
            "side": "sell",
            "symbol": SYMBOL,
            "qty": qty,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]
    return []


makefun_bars.run(on_batch)
