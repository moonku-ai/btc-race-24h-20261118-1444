# btc-race-24h-20261118-1444 — momentum breakout bot

Entry for make.fun's "Race a BTC trading bot live for 24 hours"
(`btc-race-24h-20261118-1444`). One asset, CBBTC (Coinbase Wrapped BTC) vs
USDC, 1-minute bars, $1,000 paper capital, long only. The bot speaks
`agent-fun/bars-replay/v1` on stdin/stdout via the kit's Python SDK shim
(`vendor/makefun_bars.py`, copied byte-for-byte from the kit).

## Strategy

1-minute cbBTC returns show a small positive autocorrelation at lags 1-3, so
a sharp 2-minute jump tends to keep running for a few minutes. The bot rides
that continuation and gets out fast when it fails:

- **Entry** (flat only): the close rose >= 30 bps over the last two closes
  -> buy with 80% of cash (`max_slippage_bps` 300).
- **Exit**: sell half at +40 bps from the fill price; sell the rest at
  +80 bps, on a trailing stop of 55 bps below the highest close since entry,
  on a hard stop of -60 bps, or after 30 bars held.

Why these numbers: a full-size round trip pays ~30 bps in fees (4 bps),
slippage (2 bps) and pool impact (~10 bps a leg at this depth), so the bot
only trades on a strong (~3-sigma) 2-minute move and scales out to bank part
of the move while letting the rest run. Dip-buying and EMA-cross variants
were tested on the dev window and lost money in this falling market; the
momentum version was the only family that stayed positive.

## Results

Local backtest on the kit's frozen 24h dev window (exact integer fill model
from the kit harness; BTC fell -2.80% over the window, buy-and-hold -$31.63):

- Net PnL **+$5.74**, 11 trades, max drawdown 0.6%, fees $1.93.
- Robustness: on 100 return-stitched 1-hour block-bootstrap windows (fresh
  seed), mean +$8.52, median +$7.32, 100% of windows profitable, min +$0.77,
  average 12.8 trades (min 3) — so the >= 1-trade guardrail is safe.

## Files

- `main.py` — the bot (pure Python stdlib + the vendored shim).
- `vendor/makefun_bars.py` — the kit's Python SDK shim, unmodified.
- `LICENSE` — MIT.
