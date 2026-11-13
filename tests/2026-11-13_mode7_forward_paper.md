# Mode 7 Forward Paper Test Record

**Date:** 2026-11-13  
**Asset:** SENSEX  
**Mode:** Dhan WebSocket Forward Paper  
**Source revision:** `bots/latestbot_premium_tolerance.py`  
**Premium rule:** Base ceiling ₹200 with ₹5 tolerance; effective maximum ₹205  
**Execution:** Paper only; no live market orders

## Observed completed trades

| Time | Side / contract | Entry premium | Quantity | Exit | Points | Gross P&L | Brokerage | Net P&L |
|---|---|---:|---:|---|---:|---:|---:|---:|
| 13:40:33 | PE 80100 | ₹184.30 | 40 | 13:42:37, trailing giveback | +6.95 | ₹278 | ₹50 | **₹228** |
| 14:28:17 | CE 82700 | ₹197.80 | 40 | 14:31:11, trailing giveback | +9.25 | ₹370 | ₹50 | **₹320** |

**Combined observed net P&L: +₹548** across two completed paper trades.

## Premium-tolerance observations

- ₹210.00 was rejected as above ₹200 + ₹5 tolerance.
- ₹221.05 was rejected as above ₹200 + ₹5 tolerance.
- ₹197.80 was accepted and entered.
- Earlier run also showed ₹200.25 and ₹207.75 rejected under the original ₹200 ceiling before the tolerance revision.

## Other observed behaviour

- Dhan feed connected and two option contracts were subscribed.
- Supertrend direction changed from bearish to bullish during the run.
- CE entries were blocked while Supertrend was bearish.
- The CHOP filter was displayed as active, with the reported value below 61.8 at the successful CE entry.
- Trailing giveback closed both observed positions.
- The startup summary displayed RSI 3 / HMA 3, while Mode 7 printed and ran RSI 5 / thresholds 60/40 / HMA 4. This display/configuration mismatch remains to be corrected.

## Scope and limitations

This is a record of the values visible in the supplied screenshots, not a complete broker statement or independently reconciled execution report. These were paper trades. Two trades do not establish strategy profitability or live execution reliability. No claim is made about unshown signals, fills, slippage, or the remainder of the session.
