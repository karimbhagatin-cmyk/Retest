# Retest

Trading-bot source repository.

## Current baseline

- File: `bots/latestbot.py`
- Uploaded source filename: `latestbot.py`
- Baseline captured: 2026-11-13
- GitHub commit: `e8475860980e9ee959dac67856d0497ed2ff924c`

The uploaded source is committed unchanged as the current baseline. Do not overwrite this baseline when developing fixes; create a separate version or branch and preserve the original for rollback.

## Operating note

Mode 7 is labelled “Dhan WebSocket Forward Paper”. Its configuration in the uploaded source sets RSI 5, thresholds 60/40, HMA 4, 5-second signal candles, 2 lots, premium ceiling ₹200, no hard stop or target, trailing activation 5 points with 2-point giveback, ₹50 brokerage per trade, and 3 confirmation ticks. The mode uses Dhan market data and records paper trades; it is not the live-order mode.

The feed-error handling and experiment-stop behaviour have not been changed or certified by this baseline commit. Review and test those separately before relying on a forward run.
