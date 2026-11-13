import os, time, random, json, sys, requests, queue, threading, csv
import numpy as np, pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

try:
    from dhanhq import dhanhq, DhanContext
    try:
        from dhanhq import MarketFeed
        MARKETFEED_AVAILABLE = True
    except ImportError:
        MarketFeed = None
        MARKETFEED_AVAILABLE = False
    DHAN_AVAILABLE = True
except ImportError:
    DHAN_AVAILABLE = False
    MARKETFEED_AVAILABLE = False
    MarketFeed = None

print("=" * 48)
print("   QUANT TRADING BOT")
print("=" * 48)

CONFIG_FILE, CRED_FILE, LOCK_FILE = "config.json", "dhan_credentials.json", "bot.lock"

if os.path.exists(LOCK_FILE):
    try: os.remove(LOCK_FILE)
    except: pass
with open(LOCK_FILE, "w") as f: f.write(str(os.getpid()))

saved_config, use_saved = None, 'y'
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r") as f: saved_config = json.load(f)
        use_saved = input(f"\n📁 Found '{CONFIG_FILE}'. Use saved strategy config? (y/n) [default y]: ").strip().lower() or 'y'
    except: saved_config = None

if not saved_config or use_saved == 'n':
    print("\n[1] SELECT TRADING ASSET:\n  [1] Nifty 50 (Lot: 65)\n  [2] Sensex (Lot: 20)")
    asset_choice = input("Choice [1-2, def 1]: ").strip() or "1"
    if asset_choice == "2":
        ASSET_NAME, TICKER_SYMBOL, LOT_MULTIPLIER, DHAN_SECURITY_ID, DHAN_EXCHANGE = "SENSEX", "%5EBSESN", 20, "51", "IDX_I"
        DEF_RSI_P, DEF_RSI_OS, DEF_RSI_OB, DEF_HMA_P, DEF_TGT, DEF_TRIG, DEF_STP = 5, 60.0, 40.0, 4, 0.0, 5.0, 2.0
    else:
        ASSET_NAME, TICKER_SYMBOL, LOT_MULTIPLIER, DHAN_SECURITY_ID, DHAN_EXCHANGE = "NIFTY_50", "%5ENSEI", 65, "13", "IDX_I"
        DEF_RSI_P, DEF_RSI_OS, DEF_RSI_OB, DEF_HMA_P, DEF_TGT, DEF_TRIG, DEF_STP = 5, 60.0, 40.0, 4, 0.0, 5.0, 2.0

    print(f"👉 Selected: {ASSET_NAME.replace('_', ' ')}")
    TIMEFRAME_STR = "3sec"

    print("\n[3] CONFIGURE STRATEGY PARAMETERS & RISK CAPS:")
    try:
        RSI_PERIOD = int(input(f"  ➔ RSI Period [def {DEF_RSI_P}]: ") or DEF_RSI_P)
        RSI_OVERBOUGHT = float(input(f"  ➔ RSI Overbought / Upper Threshold [def {DEF_RSI_OB}]: ") or DEF_RSI_OB)
        RSI_OVERSOLD = float(input(f"  ➔ RSI Oversold / Lower Threshold [def {DEF_RSI_OS}]: ") or DEF_RSI_OS)
        HMA_PERIOD = int(input(f"  ➔ HMA Period [def {DEF_HMA_P}]: ") or DEF_HMA_P)
        USE_HMA = True
        INITIAL_TARGET_PTS = float(input(f"  ➔ Target Pts [def {DEF_TGT}]: ") or DEF_TGT)
        TSL_TRIGGER_PTS = float(input(f"  ➔ TSL Trigger [def {DEF_TRIG}]: ") or DEF_TRIG)
        TSL_STEP_PTS = float(input(f"  ➔ TSL Step [def {DEF_STP}]: ") or DEF_STP)
        MAX_LOSS_DAY = float(input("  ➔ Max Daily Loss Limit (₹) [def 3000]: ") or 3000.0)
        MAX_PROFIT_DAY = float(input("  ➔ Max Daily Profit Target (₹) [def 5000]: ") or 5000.0)
    except:
        RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT, HMA_PERIOD, USE_HMA = DEF_RSI_P, DEF_RSI_OS, DEF_RSI_OB, DEF_HMA_P, True
        INITIAL_TARGET_PTS, TSL_TRIGGER_PTS, TSL_STEP_PTS = DEF_TGT, DEF_TRIG, DEF_STP
        MAX_LOSS_DAY, MAX_PROFIT_DAY = 3000.0, 5000.0

    with open(CONFIG_FILE, "w") as f:
        json.dump({
            "ASSET_NAME": ASSET_NAME, "TICKER_SYMBOL": TICKER_SYMBOL, "LOT_MULTIPLIER": LOT_MULTIPLIER,
            "DHAN_SECURITY_ID": DHAN_SECURITY_ID, "DHAN_EXCHANGE": DHAN_EXCHANGE, "TIMEFRAME_STR": TIMEFRAME_STR,
            "RSI_PERIOD": RSI_PERIOD, "RSI_OVERSOLD": RSI_OVERSOLD, "RSI_OVERBOUGHT": RSI_OVERBOUGHT,
            "HMA_PERIOD": HMA_PERIOD, "USE_HMA": USE_HMA, "INITIAL_TARGET_PTS": INITIAL_TARGET_PTS,
            "TSL_TRIGGER_PTS": TSL_TRIGGER_PTS, "TSL_STEP_PTS": TSL_STEP_PTS,
            "MAX_LOSS_DAY": MAX_LOSS_DAY, "MAX_PROFIT_DAY": MAX_PROFIT_DAY
        }, f, indent=4)
    print(f"💾 Saved updated config to '{CONFIG_FILE}'.")
else:
    ASSET_NAME = saved_config.get("ASSET_NAME", "NIFTY_50")
    TICKER_SYMBOL = saved_config.get("TICKER_SYMBOL", "%5ENSEI")
    LOT_MULTIPLIER = saved_config.get("LOT_MULTIPLIER", 65)
    DHAN_SECURITY_ID = saved_config.get("DHAN_SECURITY_ID", "13")
    DHAN_EXCHANGE = saved_config.get("DHAN_EXCHANGE", "IDX_I")
    if ASSET_NAME == "SENSEX":
        DHAN_EXCHANGE = "IDX_I"
    TIMEFRAME_STR = "3sec"
    RSI_PERIOD = saved_config.get("RSI_PERIOD", 5)
    RSI_OVERSOLD = saved_config.get("RSI_OVERSOLD", 60.0)
    RSI_OVERBOUGHT = saved_config.get("RSI_OVERBOUGHT", 40.0)
    HMA_PERIOD = saved_config.get("HMA_PERIOD", 4)
    USE_HMA = True
    INITIAL_TARGET_PTS = saved_config.get("INITIAL_TARGET_PTS", 0.0)
    TSL_TRIGGER_PTS = saved_config.get("TSL_TRIGGER_PTS", 5.0)
    TSL_STEP_PTS = saved_config.get("TSL_STEP_PTS", 2.0)
    MAX_LOSS_DAY = saved_config.get("MAX_LOSS_DAY", 3000.0)
    MAX_PROFIT_DAY = saved_config.get("MAX_PROFIT_DAY", 5000.0)

print("\n[4] SELECT TRADING MODE:")
print("  [1] Yahoo Backtest")
print("  [2] Dhan Backtest")
print("  [3] Dhan Forward Trade (paper; live Dhan prices, no orders)")
print("  [4] Dhan Live Trade (real market orders)")
print("  [5] Dhan One-Minute Forward (Mode 2 logic; actual option prices; paper only)")
print("  [6] Dhan Event-Driven Forward (legacy tick mode)")
print("  [7] Dhan WebSocket Forward Paper (BEST DEFAULTS; single strategy)")
mode_choice = input("Choice [1-7, default 1]: ").strip() or "1"
if mode_choice not in ("1", "2", "3", "4", "5", "6", "7"):
    print("❌ Invalid choice."); exit(1)

historical_candles, cache_filename = [], f"{ASSET_NAME}_1min_cached.csv"
dhan_client = None
dhan_warmup_prices, last_dhan_candle_time = [], None
is_dhan_mode = mode_choice in ("2", "3", "4", "5", "6", "7")
is_live_mode = mode_choice in ("3", "4", "5", "6", "7")
is_live_trade = mode_choice == "4"
is_mode5 = mode_choice == "5"
is_mode6 = mode_choice == "6"
is_mode7 = mode_choice == "7"
EXECUTION_MODE = {
    "1": "YAHOO BACKTEST",
    "2": "DHAN BACKTEST (INDEX SIGNALS; OPTION PREMIUM SIMULATED)",
    "3": "DHAN FORWARD PAPER TRADE",
    "4": "DHAN LIVE TRADE - REAL ORDERS",
    "5": "DHAN ONE-MINUTE FORWARD (MODE 2 LOGIC; PAPER ONLY)",
    "6": "DHAN EVENT-DRIVEN FORWARD (TICK-BASED)",
    "7": "DHAN WEBSOCKET FORWARD PAPER (BEST DEFAULTS)"
}[mode_choice]
if mode_choice == "2":
    print("⚠️ Dhan backtest uses historical index candles. Historical option premiums are not fetched; option P&L is simulated.")
elif mode_choice == "1":
    print("ℹ️ Yahoo backtest uses index candles; option premiums/P&L are simulated.")

cid, tok = "", ""
if is_dhan_mode:
    if not DHAN_AVAILABLE:
        print("❌ dhanhq package is not installed."); exit(1)
    use_saved_cred = 'y'
    if os.path.exists(CRED_FILE):
        try:
            with open(CRED_FILE, "r") as f: dhan_creds = json.load(f)
            use_saved_cred = input(f"📁 Found '{CRED_FILE}'. Use saved Dhan credentials? (y/n) [default y]: ").strip().lower() or 'y'
            if use_saved_cred != 'n':
                cid, tok = dhan_creds.get("client_id", ""), dhan_creds.get("access_token", "")
        except: pass

    if not cid or not tok or use_saved_cred == 'n':
        cid, tok = input("Enter Dhan Client ID: ").strip(), input("Enter Dhan Access Token: ").strip()
        with open(CRED_FILE, "w") as f: json.dump({"client_id": cid, "access_token": tok}, f, indent=4)

    if not cid or not tok:
        print("❌ Dhan credentials are required."); exit(1)
    try:
        dhan_client = dhanhq(DhanContext(cid, tok))
        print("⏳ Connecting to Dhan API...")
        now_dt = datetime.now(IST).replace(tzinfo=None)
        resp = dhan_client.intraday_minute_data(
            security_id=DHAN_SECURITY_ID,
            exchange_segment=DHAN_EXCHANGE,
            instrument_type="INDEX",
            from_date=(now_dt - timedelta(days=5)).strftime("%Y-%m-%d"),
            to_date=now_dt.strftime("%Y-%m-%d")
        )
        if not resp or not resp.get("data") or not resp["data"].get("close"):
            print("❌ Empty Dhan historical candle response."); exit(1)
        data = resp["data"]
        completed = []
        current_minute = now_dt.replace(second=0, microsecond=0)
        for ts, close in zip(data.get("timestamp", []), data.get("close", [])):
            candle_dt = pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Kolkata").tz_localize(None) if isinstance(ts, (int, float, np.integer, np.floating)) else pd.to_datetime(ts)
            if candle_dt.tzinfo is not None:
                candle_dt = candle_dt.tz_convert("Asia/Kolkata").tz_localize(None)
            candle_dt = candle_dt.to_pydatetime()
            if candle_dt < current_minute:
                completed.append((candle_dt, float(close)))
        completed.sort(key=lambda item: item[0])
        if not completed:
            print("❌ No completed Dhan candles returned."); exit(1)

        if mode_choice == "2":
            historical_candles = [(dt.strftime("%Y-%m-%d %H:%M:%S"), close) for dt, close in completed]
            print(f"✅ Loaded {len(historical_candles)} historical Dhan index candles for backtest.")
        else:
            dhan_warmup_prices = [item[1] for item in completed[-120:]]
            last_dhan_candle_time = completed[-1][0]
    except Exception as e:
        print(f"❌ Dhan connection/data error: {e}")
        exit(1)
elif mode_choice == "1":
    try:
        resp = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{TICKER_SYMBOL}?interval=1m&range=7d", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"Yahoo Finance HTTP {resp.status_code}")
        res_json = resp.json()['chart']['result'][0]
        df_yf = pd.DataFrame({'Datetime': [datetime.fromtimestamp(ts) for ts in res_json['timestamp']], 'Close': res_json['indicators']['quote'][0]['close']}).dropna()
        df_yf.set_index('Datetime', inplace=True)
        resampled = df_yf.resample('1min').agg({'Close': 'last'}).dropna()
        resampled.reset_index(inplace=True)
        resampled.to_csv(cache_filename, index=False)
        historical_candles = [(str(row['Datetime']), float(row['Close'])) for _, row in resampled.iterrows()]
        if not historical_candles:
            raise RuntimeError("Yahoo returned no usable candles.")
    except Exception as e:
        print(f"❌ Yahoo Finance error: {e}"); exit(1)

print(f"\n" + "=" * 44 + f"\n • Asset: {ASSET_NAME} | Mode: {EXECUTION_MODE} | Lot: {LOT_MULTIPLIER} | Interval: 1m\n • RSI: P{RSI_PERIOD} OB/Upper {RSI_OVERBOUGHT} OS/Lower {RSI_OVERSOLD} | HMA SLOPE: {HMA_PERIOD}\n" + "=" * 44)
if input("\n🤖 Run engine? (y/n): ").strip().lower() != 'y':
    if os.path.exists(LOCK_FILE): os.remove(LOCK_FILE)
    exit(0)

GREEN, RED, CYAN, RESET = "\033[92m", "\033[91m", "\033[96m", "\033[0m"
active_position, strike_price, entry_premium, spot_peak_price = None, 0, 0, 0
entry_spot, spot_peak_points = 0.0, 0.0
locked_option_security_id, locked_option_segment = None, None
option_peak_gain, option_expiry = 0.0, None
active_order_quantity = 0
ORDER_WAIT_SECONDS = 12

class OrderSubmissionUncertain(RuntimeError):
    pass
last_option_chain_request_time = 0.0
price_history = list(dhan_warmup_prices) if is_live_mode else []
cumulative_rupees, cumulative_points, trade_counter, historical_index = 0.0, 0.0, 0, 0
current_day_str, day_counter, trades_today_counter, trade_records = "", 0, 0, []

print(f"\n🚀 Starting 1-Minute Signal Engine ({EXECUTION_MODE} MODE)...\n" + "-" * 52 + "\n")
sys.stdout.flush()

def compute_rsi(prices, period=RSI_PERIOD):
    if len(prices) < period + 1: return 50.0
    g = l = 0.0
    for i in range(1, period + 1):
        ch = prices[i] - prices[i-1]
        if ch > 0: g += ch
        else: l -= ch
    ag, al = g / period, l / period
    for i in range(period + 1, len(prices)):
        ch = prices[i] - prices[i-1]
        ag = ((ag * (period - 1)) + (ch if ch > 0 else 0.0)) / period
        al = ((al * (period - 1)) + (-ch if ch < 0 else 0.0)) / period
    if al == 0: return 100.0 if ag > 0 else 50.0
    if ag == 0: return 0.0
    return round(max(0.0, min(100.0, 100.0 - (100.0 / (1.0 + (ag / al))))), 1)

def compute_hma(prices, period=HMA_PERIOD):
    if len(prices) < period + int(np.sqrt(period)): return {"state": "FL", "rising": False, "falling": False}
    s = pd.Series(prices)
    wma = lambda ser, p: ser.rolling(p).apply(lambda x: np.dot(x, np.arange(1, p + 1)) / np.arange(1, p + 1).sum(), raw=True)
    h_ser = wma(2 * wma(s, int(period / 2)) - wma(s, period), int(np.sqrt(period)))
    if len(h_ser) < 2 or np.isnan(h_ser.iloc[-1]) or np.isnan(h_ser.iloc[-2]): return {"state": "FL", "rising": False, "falling": False}
    curr_h, prev_h = h_ser.iloc[-1], h_ser.iloc[-2]
    return {"state": "BU" if curr_h > prev_h else ("BE" if curr_h < prev_h else "FL"), "rising": curr_h > prev_h, "falling": curr_h < prev_h}


def dhan_api_post(endpoint, payload):
    headers = {
        "access-token": tok,
        "client-id": cid,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    response = requests.post(
        "https://api.dhan.co/v2" + endpoint,
        headers=headers,
        json=payload,
        timeout=15
    )
    response.raise_for_status()
    result = response.json()
    if result.get("status") not in ("success", "SUCCESS"):
        raise RuntimeError(f"Dhan {endpoint} response: {result}")
    return result


def dhan_order_request(method, endpoint, payload=None):
    headers = {
        "access-token": tok,
        "client-id": cid,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    response = requests.request(
        method,
        "https://api.dhan.co/v2" + endpoint,
        headers=headers,
        json=payload,
        timeout=15
    )
    try:
        result = response.json()
    except Exception:
        result = {"message": response.text}
    if response.status_code >= 400:
        raise RuntimeError(f"Dhan order API HTTP {response.status_code}: {result}")
    return result


def get_order_status(order_id):
    result = dhan_order_request("GET", f"/orders/{order_id}")
    if isinstance(result, list):
        result = result[0] if result else {}
    return result if isinstance(result, dict) else {}


def place_and_confirm_market_order(contract, transaction_type, quantity):
    payload = {
        "dhanClientId": cid,
        "transactionType": transaction_type,
        "exchangeSegment": contract["segment"],
        "productType": "INTRADAY",
        "orderType": "MARKET",
        "validity": "DAY",
        "securityId": str(contract["security_id"]),
        "quantity": int(quantity),
        "disclosedQuantity": 0,
        "price": 0,
        "triggerPrice": 0,
        "afterMarketOrder": False,
        "amoTime": "",
        "boProfitValue": 0,
        "boStopLossValue": 0
    }
    try:
        placed = dhan_order_request("POST", "/orders", payload)
    except requests.exceptions.RequestException as e:
        raise OrderSubmissionUncertain(f"Order submission outcome is unknown: {e}") from e
    order_id = placed.get("orderId")
    if not order_id:
        raise OrderSubmissionUncertain(f"Dhan response did not include an order ID: {placed}")

    deadline = time.time() + ORDER_WAIT_SECONDS
    latest = placed
    while time.time() < deadline:
        try:
            latest = get_order_status(order_id)
        except requests.exceptions.RequestException as e:
            raise OrderSubmissionUncertain(f"Could not confirm order {order_id}: {e}") from e
        status = str(latest.get("orderStatus", "")).upper()
        if status in ("TRADED", "REJECTED", "CANCELLED", "EXPIRED"):
            break
        time.sleep(1)

    status = str(latest.get("orderStatus", "")).upper()
    if status not in ("TRADED", "REJECTED", "CANCELLED", "EXPIRED"):
        try:
            dhan_order_request("DELETE", f"/orders/{order_id}")
            time.sleep(1)
            latest = get_order_status(order_id)
        except requests.exceptions.RequestException as e:
            raise OrderSubmissionUncertain(f"Could not confirm/cancel pending order {order_id}: {e}") from e
        status = str(latest.get("orderStatus", "")).upper()

    if status not in ("TRADED", "REJECTED", "CANCELLED", "EXPIRED"):
        raise OrderSubmissionUncertain(f"Order {order_id} remains in status {status}; refusing to scan or submit another order.")

    filled_qty = int(latest.get("filledQty") or 0)
    average_price = float(latest.get("averageTradedPrice") or 0.0)
    error = latest.get("omsErrorDescription") or latest.get("omsErrorCode") or ""
    return {
        "order_id": str(order_id),
        "status": status,
        "filled_qty": filled_qty,
        "average_price": average_price,
        "error": str(error),
        "requested_qty": int(quantity)
    }


last_marketfeed_request_time = 0.0
last_marketfeed_quote = {}

def get_live_option_ltp(security_id, segment):
    global last_marketfeed_request_time, last_marketfeed_quote

    cache_key = (str(segment), str(security_id))

    # Dhan Quote APIs are limited to 1 request per second.
    # Keep a small safety margin between all LTP snapshot requests.
    wait_time = 1.2 - (time.time() - last_marketfeed_request_time)
    if wait_time > 0:
        time.sleep(wait_time)

    # Retry rate-limit responses with backoff; do not hammer the endpoint.
    for attempt in range(3):
        try:
            last_marketfeed_request_time = time.time()
            result = dhan_api_post(
                "/marketfeed/ltp",
                {segment: [int(security_id)]}
            )
            quote = result.get("data", {}).get(segment, {}).get(str(security_id), {})
            price = quote.get("last_price")
            if price is not None and float(price) > 0:
                last_marketfeed_quote[cache_key] = (float(price), time.time())
                return float(price)
            return None
        except requests.exceptions.HTTPError as e:
            response = getattr(e, "response", None)
            if response is None or response.status_code != 429 or attempt == 2:
                raise
            backoff = 2.0 * (attempt + 1)
            print(f"⚠️ Dhan LTP rate limit (429). Waiting {backoff:.0f}s before retry.")
            sys.stdout.flush()
            time.sleep(backoff)

    return None


def get_locked_option_ltp():
    if not locked_option_security_id or not locked_option_segment:
        return None
    return get_live_option_ltp(locked_option_security_id, locked_option_segment)


def get_locked_option_ltp_for_contract(contract):
    return get_live_option_ltp(contract["security_id"], contract["segment"])


def select_atm_option(option_type, spot_price):
    global option_expiry, last_option_chain_request_time

    underlying_id = int(DHAN_SECURITY_ID)
    today = datetime.now(IST).replace(tzinfo=None).date()

    if not option_expiry or datetime.strptime(option_expiry, "%Y-%m-%d").date() < today:
        expiry_result = dhan_api_post(
            "/optionchain/expirylist",
            {"UnderlyingScrip": underlying_id, "UnderlyingSeg": DHAN_EXCHANGE}
        )
        last_option_chain_request_time = time.time()
        expiries = [
            value for value in expiry_result.get("data", [])
            if datetime.strptime(value, "%Y-%m-%d").date() >= today
        ]
        if not expiries:
            raise RuntimeError("Dhan returned no active option expiry.")
        option_expiry = min(expiries)

        # Dhan applies a 3-second limit to option-chain requests.
        wait_time = 3.1 - (time.time() - last_option_chain_request_time)
        if wait_time > 0:
            time.sleep(wait_time)

    wait_time = 3.1 - (time.time() - last_option_chain_request_time)
    if wait_time > 0:
        time.sleep(wait_time)

    chain_result = dhan_api_post(
        "/optionchain",
        {
            "UnderlyingScrip": underlying_id,
            "UnderlyingSeg": DHAN_EXCHANGE,
            "Expiry": option_expiry
        }
    )
    last_option_chain_request_time = time.time()

    option_chain = chain_result.get("data", {}).get("oc", {})
    if not option_chain:
        raise RuntimeError("Dhan returned an empty option chain.")

    strike_key = min(option_chain.keys(), key=lambda key: abs(float(key) - float(spot_price)))
    option_data = option_chain[strike_key].get(option_type.lower())
    if not option_data or not option_data.get("security_id"):
        raise RuntimeError(f"No {option_type} contract found at ATM strike {strike_key}.")

    option_segment = "BSE_FNO" if ASSET_NAME == "SENSEX" else "NSE_FNO"
    return {
        "security_id": str(option_data["security_id"]),
        "segment": option_segment,
        "strike": float(strike_key),
        "chain_ltp": float(option_data.get("last_price") or 0.0),
        "expiry": option_expiry
    }



def compute_supertrend(bars, period=10, multiplier=3.0):
    """Return (direction, atr, final_upper, final_lower) from completed OHLC bars.

    Direction is BULLISH or BEARISH. None means insufficient/invalid history.
    Uses Wilder ATR and the standard recursive Supertrend bands.
    """
    if len(bars) < period or period < 1:
        return None, None, None, None

    trs = []
    for i, bar in enumerate(bars):
        high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        if not all(np.isfinite(v) for v in (high, low, close)) or high < low:
            return None, None, None, None
        prev_close = float(bars[i - 1]["close"]) if i else close
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))

    atr = None
    final_upper = final_lower = None
    direction = None
    prev_close = None

    for i, bar in enumerate(bars):
        high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        if i == period - 1:
            atr = float(np.mean(trs[:period]))
        elif i >= period:
            atr = ((atr * (period - 1)) + trs[i]) / period
        if i < period - 1:
            prev_close = close
            continue

        basic_upper = (high + low) / 2.0 + multiplier * atr
        basic_lower = (high + low) / 2.0 - multiplier * atr

        if final_upper is None:
            final_upper, final_lower = basic_upper, basic_lower
            direction = "BULLISH" if close >= (high + low) / 2.0 else "BEARISH"
        else:
            old_upper, old_lower = final_upper, final_lower
            final_upper = (min(basic_upper, old_upper)
                           if prev_close <= old_upper else basic_upper)
            final_lower = (max(basic_lower, old_lower)
                           if prev_close >= old_lower else basic_lower)

            if direction == "BEARISH" and close > final_upper:
                direction = "BULLISH"
            elif direction == "BULLISH" and close < final_lower:
                direction = "BEARISH"

        prev_close = close

    return direction, float(atr), float(final_upper), float(final_lower)

def compute_choppiness(bars, period=14):
    """Classic Choppiness Index over completed OHLC bars; lower values imply trend."""
    if len(bars) < period or period < 2:
        return None
    window = bars[-period:]
    tr_sum = 0.0
    highs, lows = [], []
    for i, bar in enumerate(window):
        high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        prev_close = float(window[i - 1]["close"]) if i else float(bars[-period - 1]["close"]) if len(bars) > period else close
        tr_sum += max(high - low, abs(high - prev_close), abs(low - prev_close))
        highs.append(high); lows.append(low)
    price_range = max(highs) - min(lows)
    if price_range <= 0 or tr_sum <= 0:
        return 100.0
    return float(100.0 * np.log10(tr_sum / price_range) / np.log10(period))

def select_atm_option(option_type, spot_price, max_premium=None, min_premium=None):
    global option_expiry, last_option_chain_request_time

    underlying_id = int(DHAN_SECURITY_ID)
    today = datetime.now(IST).replace(tzinfo=None).date()

    if not option_expiry or datetime.strptime(option_expiry, "%Y-%m-%d").date() < today:
        expiry_result = dhan_api_post(
            "/optionchain/expirylist",
            {"UnderlyingScrip": underlying_id, "UnderlyingSeg": DHAN_EXCHANGE}
        )
        last_option_chain_request_time = time.time()
        expiries = [
            value for value in expiry_result.get("data", [])
            if datetime.strptime(value, "%Y-%m-%d").date() >= today
        ]
        if not expiries:
            raise RuntimeError("Dhan returned no active option expiry.")
        option_expiry = min(expiries)

        # Dhan applies a 3-second limit to option-chain requests.
        wait_time = 3.1 - (time.time() - last_option_chain_request_time)
        if wait_time > 0:
            time.sleep(wait_time)

    wait_time = 3.1 - (time.time() - last_option_chain_request_time)
    if wait_time > 0:
        time.sleep(wait_time)

    chain_result = dhan_api_post(
        "/optionchain",
        {
            "UnderlyingScrip": underlying_id,
            "UnderlyingSeg": DHAN_EXCHANGE,
            "Expiry": option_expiry
        }
    )
    last_option_chain_request_time = time.time()

    option_chain = chain_result.get("data", {}).get("oc", {})
    if not option_chain:
        raise RuntimeError("Dhan returned an empty option chain.")

    eligible_contracts = []
    for strike, strike_data in option_chain.items():
        option_data = strike_data.get(option_type.lower())
        if not option_data or not option_data.get("security_id"):
            continue
        chain_premium = float(option_data.get("last_price") or 0.0)
        if chain_premium <= 0:
            continue
        if max_premium is not None and chain_premium > max_premium:
            continue
        if min_premium is not None and chain_premium <= min_premium:
            continue
        eligible_contracts.append((abs(float(strike) - float(spot_price)), float(strike), option_data))

    if not eligible_contracts:
        limit_text = f" with premium at or below ₹{max_premium:.0f}" if max_premium is not None else ""
        raise RuntimeError(f"No {option_type} contract found{limit_text}; skipping this signal.")

    eligible_contracts.sort(key=lambda item: item[0])
    option_segment = "BSE_FNO" if ASSET_NAME == "SENSEX" else "NSE_FNO"

    # Verify candidates in nearest-to-spot order using live option quotes.
    # Do not rely on possibly stale option-chain LTP.
    if max_premium is not None:
        quote_errors = []
        for _, strike_value, option_data in eligible_contracts[:5]:
            live_premium = get_live_option_ltp(str(option_data["security_id"]), option_segment)
            if (live_premium is not None and 0 < live_premium <= max_premium
                    and (min_premium is None or live_premium > min_premium)):
                return {
                    "security_id": str(option_data["security_id"]),
                    "segment": option_segment,
                    "strike": float(strike_value),
                    "chain_ltp": float(option_data.get("last_price") or 0.0),
                    "live_ltp": float(live_premium),
                    "expiry": option_expiry
                }
            quote_errors.append(f"{strike_value:g}: {live_premium if live_premium is not None else 'no quote'}")

        raise RuntimeError(
            f"No verified {option_type} contract at or below ₹{max_premium:.0f} "
            f"among the 5 nearest chain-eligible strikes. Checked: {', '.join(quote_errors)}"
        )

    _, strike_value, option_data = eligible_contracts[0]
    return {
        "security_id": str(option_data["security_id"]),
        "segment": option_segment,
        "strike": float(strike_value),
        "chain_ltp": float(option_data.get("last_price") or 0.0),
        "expiry": option_expiry
    }


def refresh_dhan_index_warmup():
    global price_history, last_dhan_candle_time, dhan_warmup_prices
    now_dt = datetime.now(IST).replace(tzinfo=None)
    result = dhan_client.intraday_minute_data(
        security_id=DHAN_SECURITY_ID,
        exchange_segment=DHAN_EXCHANGE,
        instrument_type="INDEX",
        from_date=(now_dt - timedelta(days=5)).strftime("%Y-%m-%d"),
        to_date=now_dt.strftime("%Y-%m-%d")
    )
    data = result.get("data", {}) if result else {}
    completed = []
    current_minute = now_dt.replace(second=0, microsecond=0)
    for ts, close in zip(data.get("timestamp", []), data.get("close", [])):
        candle_dt = pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Kolkata").tz_localize(None) if isinstance(ts, (int, float, np.integer, np.floating)) else pd.to_datetime(ts)
        if candle_dt.tzinfo is not None:
            candle_dt = candle_dt.tz_convert("Asia/Kolkata").tz_localize(None)
        candle_dt = candle_dt.to_pydatetime()
        if candle_dt < current_minute:
            completed.append((candle_dt, float(close)))
    completed.sort(key=lambda item: item[0])
    if completed:
        price_history = [item[1] for item in completed[-120:]]
        dhan_warmup_prices = list(price_history)
        last_dhan_candle_time = completed[-1][0]

last_dhan_status_log = 0.0



def run_single_strategy_event_forward(cfg):
    """Run independent RSI/HMA paper strategies with a shared 1m Supertrend direction filter."""
    if not MARKETFEED_AVAILABLE:
        raise RuntimeError("Dhan MarketFeed unavailable in this dhanhq installation.")
    active_cfgs = [dict(cfg, name="BEST")] if cfg.get("enabled", True) else []
    configs = active_cfgs[:]
    if not active_cfgs:
        raise RuntimeError("The single strategy is disabled.")

    # Shared one-minute Supertrend filter; only completed index candles are used.
    ST_PERIOD, ST_MULTIPLIER = 10, 3.0
    trend_bars, trend_direction, trend_last_completed_at = [], None, None
    trend_chop, trend_bucket, trend_ohlc = None, None, None
    CHOP_PERIOD, CHOP_TREND_MAX, CHOP_TRANSITION_MAX = 14, 38.2, 61.8
    chop_blocked = {"TRANSITION": 0, "SIDEWAYS": 0, "UNAVAILABLE": 0}
    trend_blocked = {"BULLISH_BLOCKED_PE": 0, "BEARISH_BLOCKED_CE": 0,
                     "UNINITIALISED": 0, "STALE": 0}
    try:
        now_naive = datetime.now(IST).replace(tzinfo=None)
        hist_resp = dhan_client.intraday_minute_data(
            security_id=DHAN_SECURITY_ID, exchange_segment=DHAN_EXCHANGE,
            instrument_type="INDEX",
            from_date=(now_naive - timedelta(days=5)).strftime("%Y-%m-%d"),
            to_date=now_naive.strftime("%Y-%m-%d"))
        hist_data = hist_resp.get("data", {}) if isinstance(hist_resp, dict) else {}
        arrays = [hist_data.get(k, []) or [] for k in ("timestamp", "open", "high", "low", "close")]
        n = min((len(a) for a in arrays), default=0)
        warm = []
        current_minute = now_naive.replace(second=0, microsecond=0)
        for i in range(n):
            raw_ts = arrays[0][i]
            dt = (pd.to_datetime(raw_ts, unit="s", utc=True)
                  if isinstance(raw_ts, (int, float, np.integer, np.floating))
                  else pd.to_datetime(raw_ts))
            if dt.tzinfo is not None:
                dt = dt.tz_convert("Asia/Kolkata").tz_localize(None)
            dt = dt.to_pydatetime()
            if dt < current_minute:
                bar = {"timestamp": dt, "open": float(arrays[1][i]),
                       "high": float(arrays[2][i]), "low": float(arrays[3][i]),
                       "close": float(arrays[4][i])}
                if all(np.isfinite(bar[k]) for k in ("open", "high", "low", "close")) and bar["high"] >= bar["low"]:
                    warm.append(bar)
        warm.sort(key=lambda b: b["timestamp"])
        trend_bars = warm[-300:]
        trend_direction, _, _, _ = compute_supertrend(trend_bars, ST_PERIOD, ST_MULTIPLIER)
        trend_chop = compute_choppiness(trend_bars, CHOP_PERIOD)
        if trend_direction:
            trend_last_completed_at = trend_bars[-1]["timestamp"].replace(tzinfo=IST)
            print(f"TREND WARM-UP | {len(trend_bars)} completed 1m bars | SUPERTREND {trend_direction} | CHOP {trend_chop if trend_chop is not None else 'WAITING'}")
        else:
            print("SUPERTREND WARM-UP | unavailable/insufficient OHLC; waiting for live bars")
    except Exception as exc:
        print(f"SUPERTREND WARM-UP WARNING | {exc} | waiting for live bars")
    q = queue.Queue(maxsize=60000)
    errors = queue.Queue()
    tracked = {str(DHAN_SECURITY_ID): ("INDEX", None, None)}
    contracts, quotes, quote_ts, positions = {}, {}, {}, {}
    states, ledgers, stats = {}, {}, {}
    all_events = 0
    option_exchange = MarketFeed.BSE_FNO if ASSET_NAME == "SENSEX" else MarketFeed.NSE_FNO

    def on_message(feed, message):
        if not isinstance(message, dict): return
        sid = str(message.get("security_id", ""))
        mapping = tracked.get(sid)
        if mapping is None: return
        try:
            px = float(message.get("LTP", 0))
            if px <= 0: return
            stamp = datetime.now(IST)
            events = ([{"ts": stamp, "role": "INDEX", "name": None, "side": None, "sid": sid, "ltp": px}]
                      if mapping[0] == "INDEX" else
                      [{"ts": stamp, "role": "OPTION", "name": name, "side": side, "sid": sid, "ltp": px}
                       for name, side in list(mapping)])
            for event in events:
                q.put_nowait(event)
        except (TypeError, ValueError, queue.Full):
            try: errors.put_nowait("Market tick queue full or invalid tick")
            except queue.Full: pass

    def on_error(feed, error):
        try: errors.put_nowait(error)
        except queue.Full: pass

    feed = MarketFeed(DhanContext(cid, tok),
        [(MarketFeed.IDX, str(DHAN_SECURITY_ID), MarketFeed.Ticker)], version="v2",
        on_message=on_message, on_error=on_error)

    # Per-strategy data and accounting are completely isolated.
    for cfg in active_cfgs:
        name = cfg["name"]
        contracts[name] = {"CE": None, "PE": None}
        positions[name] = None
        quotes[name] = {"CE": None, "PE": None}
        quote_ts[name] = {"CE": None, "PE": None}
        states[name] = {"bucket": None, "ohlc": None, "closes": [], "prev_rsi": None,
                        "day_net": 0.0, "halt_day": False, "last_status": None, "candidate_side": None, "candidate_count": 0, "last_index_tick": None}
        ledgers[name] = []
        stats[name] = {"gross_profit": 0.0, "gross_loss": 0.0, "cost": 0.0,
                       "net": 0.0, "equity_peak": 0.0, "max_drawdown": 0.0, "equity": 0.0}

    tick_path = f"mode7_best_ticks_{datetime.now(IST).strftime('%Y%m%d_%H%M%S')}.csv"
    tick_file = open(tick_path, "w", newline="", encoding="utf-8")
    tick_writer = csv.DictWriter(tick_file, fieldnames=["timestamp", "event", "strategy", "side", "security_id", "ltp", "index_ltp"])
    tick_writer.writeheader()
    last_index = None
    last_summary = time.time()
    manual = queue.Queue()
    started = datetime.now(IST)

    def record_trade(name, pos, exit_px, stamp, reason):
        cfg = next(c for c in active_cfgs if c["name"] == name)
        st = stats[name]
        points = float(exit_px) - pos["entry"]
        gross = points * pos["quantity"]
        cost = float(cfg["brokerage_per_trade"])
        net = gross - cost
        st["gross_profit"] += max(gross, 0.0)
        st["gross_loss"] += abs(min(gross, 0.0))
        st["cost"] += cost
        st["net"] += net
        st["equity"] += net
        st["equity_peak"] = max(st["equity_peak"], st["equity"])
        st["max_drawdown"] = max(st["max_drawdown"], st["equity_peak"] - st["equity"])
        st["day_net"] = st.get("day_net", 0.0) + net
        st["halt_day"] = ((float(cfg["max_daily_loss"]) > 0 and st["day_net"] <= -float(cfg["max_daily_loss"])) or
                           (float(cfg["max_daily_profit"]) > 0 and st["day_net"] >= float(cfg["max_daily_profit"])))
        states[name]["halt_day"] = st["halt_day"]
        rec = {"strategy": name, "entry_time": pos["entry_time"], "exit_time": stamp.isoformat(),
               "asset": ASSET_NAME, "side": pos["side"], "strike": pos["contract"]["strike"],
               "security_id": pos["contract"]["security_id"], "expiry": pos["contract"].get("expiry"),
               "entry_spot": pos["spot"], "entry_premium": pos["entry"], "exit_premium": float(exit_px),
               "points": points, "quantity": pos["quantity"], "lots": cfg["lots"],
               "gross_pnl": gross, "cost": cost, "net_pnl": net,
               "peak_points": pos["peak"], "adverse_ticks_at_exit": pos["adverse"],
               "supertrend_direction": pos.get("trend_direction", "UNKNOWN"),
               "hard_stop_threshold": pos.get("hard_stop_threshold"),
               "hard_stop_trigger_time": pos.get("hard_stop_trigger_time"),
               "hard_stop_trigger_price": pos.get("hard_stop_trigger_price"),
               "hard_stop_observed_exit_price": float(exit_px) if reason == "HARD_STOP" else None,
               "hard_stop_observed_overshoot_points": (
                   max(0.0, float(pos["hard_stop_threshold"]) - float(exit_px))
                   if reason == "HARD_STOP" and pos.get("hard_stop_threshold") is not None else None
               ),
               "exit_reason": reason}
        ledgers[name].append(rec)
        # Append a consolidated ledger after every trade so a stopped run retains its data.
        combined = [r for rows in ledgers.values() for r in rows]
        pd.DataFrame(combined).to_csv("mode7_best_trades.csv", index=False)
        print(f"{stamp.strftime('%H:%M:%S')} | {name} {reason} {pos['side']} {pos['contract']['strike']:g} "
              f"| {points:+.2f} pt | NET ₹{net:+,.0f}")
        positions[name] = None

    def exit_position(name, stamp, reason):
        pos = positions[name]
        if not pos: return
        side = pos["side"]
        px = quotes[name].get(side)
        ts = quote_ts[name].get(side)
        if px is not None and ts is not None and (stamp - ts).total_seconds() <= 3:
            record_trade(name, pos, px, ts, reason)
        else:
            print(f"{stamp.strftime('%H:%M:%S')} | {name} EXIT NOT BOOKED: latest option quote is stale")

    def process_candle(name, stamp, candle):
        cfg = next(c for c in active_cfgs if c["name"] == name)
        state = states[name]
        state["closes"].append(float(candle["close"]))
        state["closes"] = state["closes"][-500:]
        closes = state["closes"]
        rsi = compute_rsi(closes, int(cfg["rsi_period"]))
        hma = compute_hma(closes, int(cfg["hma_period"]))
        prev = state["prev_rsi"]
        if prev is not None and stamp.strftime("%H:%M") < "15:25" and not state["halt_day"] and positions[name] is None:
            ce_cross = prev <= float(cfg["rsi_oversold"]) and rsi > float(cfg["rsi_oversold"])
            pe_cross = prev >= float(cfg["rsi_overbought"]) and rsi < float(cfg["rsi_overbought"])
            if ce_cross and (hma["rising"] if cfg["use_hma"] else True):
                state["candidate_side"], state["candidate_count"] = "CE", 0
                print(f"{stamp.strftime('%H:%M:%S')} | {name} CE CANDIDATE | RSI {rsi:.1f} HMA {hma['state']} | awaiting 3 qualifying ticks")
            elif pe_cross and (hma["falling"] if cfg["use_hma"] else True):
                state["candidate_side"], state["candidate_count"] = "PE", 0
                print(f"{stamp.strftime('%H:%M:%S')} | {name} PE CANDIDATE | RSI {rsi:.1f} HMA {hma['state']} | awaiting 3 qualifying ticks")
            elif state["candidate_side"] is not None:
                state["candidate_side"], state["candidate_count"] = None, 0
        state["prev_rsi"] = rsi

    def confirm_index_tick(name, px, stamp):
        cfg = next(c for c in active_cfgs if c["name"] == name)
        state = states[name]
        side = state["candidate_side"]
        previous_tick = state.get("last_index_tick")
        state["last_index_tick"] = float(px)
        if side is None or positions[name] is not None or state["halt_day"]:
            return
        if previous_tick is None or float(px) == previous_tick:
            return
        tick_up, tick_down = float(px) > previous_tick, float(px) < previous_tick
        closes = state["closes"] + [float(px)]
        rsi = compute_rsi(closes, int(cfg["rsi_period"]))
        hma = compute_hma(closes, int(cfg["hma_period"]))
        valid = ((side == "CE" and rsi > float(cfg["rsi_oversold"]) and hma["rising"] and tick_up) or
                 (side == "PE" and rsi < float(cfg["rsi_overbought"]) and hma["falling"] and tick_down))
        if not valid:
            state["candidate_side"], state["candidate_count"] = None, 0
            return
        state["candidate_count"] += 1
        if state["candidate_count"] < int(cfg.get("confirmation_ticks", 3)):
            return

        age = ((stamp - trend_last_completed_at).total_seconds()
               if trend_last_completed_at is not None else None)
        if trend_direction is None:
            trend_blocked["UNINITIALISED"] += 1
            print(f"{stamp.strftime('%H:%M:%S')} | {name} BLOCK {side} | SUPERTREND NOT INITIALISED")
        elif age is None or age > 120:
            trend_blocked["STALE"] += 1
            print(f"{stamp.strftime('%H:%M:%S')} | {name} BLOCK {side} | SUPERTREND STALE")
        elif side == "CE" and trend_direction != "BULLISH":
            trend_blocked["BEARISH_BLOCKED_CE"] += 1
            print(f"{stamp.strftime('%H:%M:%S')} | {name} BLOCK CE | SUPERTREND {trend_direction}")
        elif side == "PE" and trend_direction != "BEARISH":
            trend_blocked["BULLISH_BLOCKED_PE"] += 1
            print(f"{stamp.strftime('%H:%M:%S')} | {name} BLOCK PE | SUPERTREND {trend_direction}")
        elif trend_chop is None:
            chop_blocked["UNAVAILABLE"] += 1
            print(f"{stamp.strftime('%H:%M:%S')} | {name} BLOCK {side} | CHOP NOT READY")
        elif trend_chop >= CHOP_TRANSITION_MAX:
            chop_blocked["SIDEWAYS"] += 1
            print(f"{stamp.strftime('%H:%M:%S')} | {name} BLOCK {side} | CHOP {trend_chop:.1f} >= 61.8")
        else:
            contract = contracts[name][side]
            option_px, quote_time = quotes[name][side], quote_ts[name][side]
            if contract and option_px is not None and quote_time is not None and (stamp - quote_time).total_seconds() <= 3:
                premium_min, premium_max = float(cfg["premium_min"]), float(cfg["premium_max"])
                premium_tolerance = float(cfg.get("premium_tolerance", 0.0))
                effective_premium_max = premium_max + premium_tolerance if premium_max > 0 else 0.0
                if (premium_min > 0 and option_px <= premium_min) or (effective_premium_max > 0 and option_px > effective_premium_max):
                    limit_text = f"₹{premium_max:.0f} + ₹{premium_tolerance:.0f} tolerance" if premium_max > 0 else "no maximum"
                    print(f"{stamp.strftime('%H:%M:%S')} | {name} SKIP {side} | PREMIUM ₹{option_px:.2f} ABOVE {limit_text}")
                else:
                    qty = int(cfg["lot_multiplier"]) * int(cfg["lots"])
                    positions[name] = {"side": side, "contract": contract, "entry": option_px,
                        "entry_time": stamp.isoformat(), "spot": float(px), "quantity": qty,
                        "last": option_px, "peak": 0.0, "adverse": 0,
                        "trend_direction": trend_direction}
                    print(f"{stamp.strftime('%H:%M:%S')} | {name} PAPER BUY {side} {contract['strike']:g} @₹{option_px:.2f} "
                          f"| RSI {rsi:.1f} HMA {hma['state']} | ST {trend_direction} CHOP {trend_chop:.1f} | {qty} qty")
            else:
                print(f"{stamp.strftime('%H:%M:%S')} | {name} SKIP {side} | OPTION QUOTE NOT FRESH")
        state["candidate_side"], state["candidate_count"] = None, 0

    def listener():
        while True:
            try: cmd = input().strip().upper()
            except (EOFError, OSError): return
            if cmd in ("X", "EXIT", "Q", "QUIT"): manual.put(cmd)

    print("\\nMODE 7 | SINGLE-STRATEGY WEBSOCKET FORWARD PAPER")
    print(f"Asset: {ASSET_NAME} | Active strategy: {len(active_cfgs)} | Shared Dhan feed")
    print("DIRECTION: SUPERTREND | 1m | ATR 10 | MULTIPLIER 3")
    print("REGIME FILTER: CHOP(14) | <61.8 ENTRIES ALLOWED | >=61.8 SIDEWAYS BLOCKED")
    print(f"SIGNALS: 5-second candles | CONFIRMATION: {int(active_cfgs[0].get('confirmation_ticks', 3))} qualifying index ticks")
    print("EXITS: no hard stop/target | trailing activation 5 pts, giveback 2 pts | option WebSocket ticks")
    print("CE only in bullish trend | PE only in bearish trend | uninitialised/stale trend blocks entries")
    print("Trade lines are printed immediately; one-minute summaries show cumulative net P&L.")
    print("X = close all positions and continue | Q = close all positions and stop")
    for cfg in active_cfgs:
        print(f"{cfg['name']}: RSI {cfg['rsi_period']} ({cfg['rsi_oversold']}/{cfg['rsi_overbought']}) "
              f"HMA {cfg['hma_period']} | {cfg['timeframe_seconds']}s | lots {cfg['lots']} | "
              f"premium ₹{cfg['premium_min']}-{cfg['premium_max'] or 'ATM'}"
              f" (+₹{cfg.get('premium_tolerance', 0):g} tolerance)")

    feed.start()
    threading.Thread(target=listener, daemon=True, name="mode7-command-listener").start()
    contracts_ready = False
    try:
        while True:
            try: ev = q.get(timeout=0.5)
            except queue.Empty: ev = None
            now = datetime.now(IST)
            if ev:
                all_events += 1
                role, px, ts = ev["role"], ev["ltp"], ev["ts"]
                if role == "INDEX":
                    last_index = px

                    # Aggregate live index ticks into completed one-minute OHLC bars.
                    minute_bucket = int(ts.timestamp()) // 60 * 60
                    if trend_bucket is None:
                        trend_bucket = minute_bucket
                        trend_ohlc = {"open": px, "high": px, "low": px, "close": px}
                    elif minute_bucket == trend_bucket:
                        trend_ohlc["high"] = max(trend_ohlc["high"], px)
                        trend_ohlc["low"] = min(trend_ohlc["low"], px)
                        trend_ohlc["close"] = px
                    else:
                        completed_stamp = datetime.fromtimestamp(trend_bucket, IST)
                        trend_bars.append({"timestamp": completed_stamp,
                            "open": trend_ohlc["open"], "high": trend_ohlc["high"],
                            "low": trend_ohlc["low"], "close": trend_ohlc["close"]})
                        trend_bars = trend_bars[-300:]
                        new_direction, _, _, _ = compute_supertrend(
                            trend_bars, ST_PERIOD, ST_MULTIPLIER)
                        trend_chop = compute_choppiness(trend_bars, CHOP_PERIOD)
                        if new_direction is not None:
                            if new_direction != trend_direction:
                                print(f"{completed_stamp.strftime('%H:%M:%S')} | SUPERTREND {trend_direction or 'INITIALISING'} -> {new_direction}")
                            trend_direction = new_direction
                            trend_last_completed_at = completed_stamp
                        trend_bucket = minute_bucket
                        trend_ohlc = {"open": px, "high": px, "low": px, "close": px}

                    if not contracts_ready:
                        print(f"Selecting option contracts for {len(active_cfgs)} strategies | IDX {px:.2f}")
                        subs, seen = [], set()
                        # All five RSI variants compare the same two option contracts.
                        # Select each side once to reduce option-chain calls and rate-limit risk.
                        reference_cfg = active_cfgs[0]
                        base_pmax = float(reference_cfg["premium_max"])
                        tolerance = float(reference_cfg.get("premium_tolerance", 0.0))
                        pmax = (base_pmax + tolerance) if base_pmax > 0 else (1000000.0 if float(reference_cfg["premium_min"]) > 0 else None)
                        pmin = float(reference_cfg["premium_min"]) or None
                        shared_contracts = {
                            side: select_atm_option(side, px, max_premium=pmax, min_premium=pmin)
                            for side in ("CE", "PE")
                        }
                        for cfg in active_cfgs:
                            name = cfg["name"]
                            for side, con in shared_contracts.items():
                                contracts[name][side] = con
                                sid = str(con["security_id"])
                                tracked.setdefault(sid, [])
                                tracked[sid].append((name, side))
                                if sid not in seen:
                                    subs.append((option_exchange, sid, MarketFeed.Ticker)); seen.add(sid)
                        feed.subscribe_symbols(subs)
                        contracts_ready = True
                        print(f"Subscribed to {len(subs)} unique option contracts. Experiment running.")
                    for cfg in active_cfgs:
                        name = cfg["name"]
                        sec = int(cfg["timeframe_seconds"])
                        state = states[name]
                        bucket = int(ts.timestamp()) // sec * sec
                        if state["bucket"] is None:
                            state["bucket"] = bucket
                            state["ohlc"] = {"open": px, "high": px, "low": px, "close": px}
                        elif bucket == state["bucket"]:
                            c = state["ohlc"]; c["high"] = max(c["high"], px); c["low"] = min(c["low"], px); c["close"] = px
                        else:
                            process_candle(name, datetime.fromtimestamp(state["bucket"], IST), state["ohlc"])
                            state["bucket"] = bucket
                            state["ohlc"] = {"open": px, "high": px, "low": px, "close": px}
                        confirm_index_tick(name, px, ts)
                else:
                    name, side = ev["name"], ev["side"]
                    quotes[name][side] = px; quote_ts[name][side] = ts
                    pos = positions[name]
                    if pos and side == pos["side"] and ev["sid"] == str(pos["contract"]["security_id"]):
                        points = px - pos["entry"]
                        pos["peak"] = max(pos["peak"], points)
                        pos["adverse"] = pos["adverse"] + 1 if px < pos["last"] else 0
                        pos["last"] = px
                        cfg = next(c for c in active_cfgs if c["name"] == name)
                        reason = None
                        if float(cfg["hard_stop_points"]) > 0 and points <= -float(cfg["hard_stop_points"]):
                            reason = "HARD_STOP"
                            pos["hard_stop_threshold"] = float(pos["entry"]) - float(cfg["hard_stop_points"])
                            pos["hard_stop_trigger_time"] = ts.isoformat(timespec="milliseconds")
                            pos["hard_stop_trigger_price"] = float(px)
                        elif float(cfg["target_points"]) > 0 and points >= float(cfg["target_points"]): reason = "TARGET"
                        elif int(cfg["adverse_ticks"]) > 0 and pos["adverse"] >= int(cfg["adverse_ticks"]): reason = f"{cfg['adverse_ticks']}_ADVERSE_TICKS"
                        elif float(cfg["trailing_trigger_points"]) > 0 and pos["peak"] >= float(cfg["trailing_trigger_points"]):
                            giveback = max(float(cfg["trailing_step_points"]), 0.01)
                            if pos["peak"] - points >= giveback: reason = "TRAILING_GIVEBACK"
                        if reason: record_trade(name, pos, px, ts, reason)
                tick_writer.writerow({"timestamp": ts.isoformat(timespec="milliseconds"), "event": role,
                    "strategy": ev.get("name") or "", "side": ev.get("side") or "",
                    "security_id": ev["sid"], "ltp": px, "index_ltp": last_index})
                tick_file.flush()

            while not manual.empty():
                cmd = manual.get_nowait()
                for cfg in active_cfgs: exit_position(cfg["name"], now, "MANUAL_EXIT")
                if cmd in ("Q", "QUIT"):
                    raise KeyboardInterrupt

            if not errors.empty():
                print(f"FEED ERROR: {errors.get()}"); raise RuntimeError("Dhan feed error; stopping experiment")
            if now.strftime("%H:%M") >= "15:35":
                for cfg in active_cfgs: exit_position(cfg["name"], now, "SESSION_CUTOFF_15_35")
                print("Session cutoff reached: 15:35 IST")
                break
            if time.time() - last_summary >= 60:
                parts = []
                for cfg in active_cfgs:
                    name = cfg["name"]; pos = positions[name]
                    unreal = 0.0
                    if pos:
                        latest = quotes[name].get(pos["side"])
                        if latest is not None: unreal = (latest - pos["entry"]) * pos["quantity"]
                    parts.append(f"{name} ₹{stats[name]['net'] + unreal:+.0f}")
                print(f"{now.strftime('%H:%M')} SUMMARY | " + " | ".join(parts))
                last_summary = time.time()
    except KeyboardInterrupt:
        print("\\nExperiment stopped by user.")
        for cfg in active_cfgs: exit_position(cfg["name"], datetime.now(IST), "MANUAL_STOP")
    finally:
        try: feed.close_connection()
        except Exception: pass
        tick_file.close()
        ended = datetime.now(IST)
        print("\\n" + "=" * 88 + "\\nMODE 7 SINGLE-STRATEGY PAPER REPORT\\n" + "=" * 88)
        print(f"Asset: {ASSET_NAME} | Started: {started.isoformat(timespec='seconds')} | Ended: {ended.isoformat(timespec='seconds')}")
        print(f"Events processed: {all_events} | Tick log: {tick_path} | Trade ledger: mode7_best_trades.csv")
        print(f"Supertrend: 1m ATR {ST_PERIOD}, multiplier {ST_MULTIPLIER} | Final direction: {trend_direction or 'UNINITIALISED'}")
        print(f"Choppiness: 1m CHOP({CHOP_PERIOD}) | Final: {trend_chop if trend_chop is not None else 'UNAVAILABLE'} | Entries allowed below {CHOP_TRANSITION_MAX}")
        print("Supertrend blocks: " + " | ".join(f"{k}={v}" for k, v in trend_blocked.items()))
        print("Choppiness blocks: " + " | ".join(f"{k}={v}" for k, v in chop_blocked.items()))
        print("\\nRESULTS")
        print(f"{'Strategy':<12}{'Trades':>8}{'Profit':>13}{'Loss':>13}{'Drawdown':>13}{'Cost':>11}{'Net':>13}")
        for cfg in configs:
            name = cfg["name"]
            if name not in stats:
                print(f"{name:<12}{'DISABLED':>8}"); continue
            st = stats[name]
            print(f"{name:<12}{len(ledgers[name]):>8}{st['gross_profit']:>13.2f}{st['gross_loss']:>13.2f}"
                  f"{st['max_drawdown']:>13.2f}{st['cost']:>11.2f}{st['net']:>13.2f}")
        print("\\nCONFIGURATION USED")
        for cfg in configs:
            print(f"\\n{cfg['name']} | {'ENABLED' if cfg.get('enabled') else 'DISABLED'}")
            for key in ("asset_name", "lot_multiplier", "rsi_period", "rsi_oversold", "rsi_overbought", "hma_period",
                        "use_hma", "timeframe_seconds", "lots", "premium_min", "premium_max", "premium_tolerance", "hard_stop_points",
                        "target_points", "adverse_ticks", "trailing_trigger_points", "trailing_step_points",
                        "brokerage_per_trade", "max_daily_loss", "max_daily_profit"):
                print(f"  {key}: {cfg.get(key)}")
        report_path = f"mode7_best_report_{started.strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"MODE 7 SINGLE-STRATEGY PAPER REPORT\\nAsset: {ASSET_NAME}\\nStarted: {started.isoformat()}\\nEnded: {ended.isoformat()}\\n")
            f.write(f"Events: {all_events}\\nTick log: {tick_path}\\nTrade ledger: mode7_best_trades.csv\\n")
            f.write(f"Supertrend: 1m ATR {ST_PERIOD}, multiplier {ST_MULTIPLIER}; final direction {trend_direction or 'UNINITIALISED'}\\n")
            f.write("Signals blocked: " + json.dumps(trend_blocked) + "\\n\\nRESULTS\\n")
            f.write("Strategy,Trades,GrossProfit,GrossLoss,MaxDrawdown,Costs,Net\\n")
            for cfg in configs:
                name=cfg["name"]
                if name in stats:
                    st=stats[name]; f.write(f"{name},{len(ledgers[name])},{st['gross_profit']:.2f},{st['gross_loss']:.2f},{st['max_drawdown']:.2f},{st['cost']:.2f},{st['net']:.2f}\\n")
                else: f.write(f"{name},DISABLED\\n")
            f.write("\\nCONFIGURATIONS\\n" + json.dumps(configs, indent=2))
        print(f"\\nFull report saved: {report_path}")
        sys.stdout.flush()

def run_event_driven_mode6():
    """
    Mode 6: tick-driven RSI/HMA signal engine.
    Default execution is paper with bot-managed exits.
    Live Super Order requires a separate explicit LIVE confirmation.
    """
    if not MARKETFEED_AVAILABLE:
        raise RuntimeError(
            "Dhan MarketFeed is unavailable in this dhanhq installation. "
            "Upgrade/install the official DhanHQ Python package before using Mode 6."
        )

    print("\n[MODE 6] EVENT-DRIVEN FORWARD")
    print("  Signal source : Dhan Market Feed WebSocket (tick-by-tick)")
    print("  RSI / HMA     : recalculated on each distinct index-price tick")
    print("  Confirmation  : 3 consecutive qualifying ticks")
    print("  Entry default : PAPER")
    print("  Exit default  : BOT-MANAGED")
    print("  Session exit  : 15:35 IST")
    print("-" * 52)

    exit_choice = input("Exit management [1] Bot-managed paper (default) [2] Dhan Super Order LIVE: ").strip() or "1"
    use_super_order = exit_choice == "2"
    super_target_points = 0.0
    super_sl_points = 0.0
    super_trailing_jump = 0.0

    if use_super_order:
        print("\n⚠️ SUPER ORDER MODE PLACES REAL ORDERS.")
        print("Dhan Super Order requires explicit target and initial stop-loss prices.")
        super_target_points = float(input("Option target distance in points: ").strip())
        super_sl_points = float(input("Initial option stop-loss distance in points: ").strip())
        super_trailing_jump = float(input("Dhan trailing jump in points [0 for none]: ").strip() or "0")
        if super_target_points <= 0 or super_sl_points <= 0 or super_trailing_jump < 0:
            raise ValueError("Super Order target and initial stop-loss must be positive.")
        confirm = input("Type LIVE to enable real Super Order placement: ").strip()
        if confirm != "LIVE":
            print("Live Super Order not confirmed. Returning without placing orders.")
            return

    confirmation_ticks = 3
    try:
        confirmation_ticks = int(input("Crossover confirmation ticks [default 3]: ").strip() or "3")
    except ValueError:
        confirmation_ticks = 3
    if confirmation_ticks < 1:
        raise ValueError("Confirmation ticks must be at least 1.")

    if not price_history:
        raise RuntimeError("No Dhan warm-up history is available for RSI/HMA calculations.")

    tick_queue = queue.Queue(maxsize=10000)
    feed_errors = queue.Queue()

    def on_feed_message(feed, message):
        if not isinstance(message, dict):
            return
        if str(message.get("security_id")) != str(DHAN_SECURITY_ID):
            return
        try:
            price = float(message.get("LTP", 0))
            if price > 0:
                item = (price, time.time(), message.get("LTT", ""))
                try:
                    tick_queue.put_nowait(item)
                except queue.Full:
                    # Preserve the newest price when the consumer briefly falls behind.
                    try:
                        tick_queue.get_nowait()
                    except queue.Empty:
                        pass
                    tick_queue.put_nowait(item)
        except (TypeError, ValueError):
            return

    def on_feed_error(feed, error):
        try:
            feed_errors.put_nowait(error)
        except queue.Full:
            pass

    index_instrument = [(MarketFeed.IDX, str(DHAN_SECURITY_ID), MarketFeed.Ticker)]
    market_feed = MarketFeed(
        DhanContext(cid, tok),
        index_instrument,
        version="v2",
        on_message=on_feed_message,
        on_error=on_feed_error
    )
    feed_thread = market_feed.start()
    print("⏳ Connecting to Dhan tick feed...")
    sys.stdout.flush()

    local_prices = list(price_history[-120:])
    previous_rsi = compute_rsi(local_prices)
    previous_hma = compute_hma(local_prices)
    candidate_side = None
    candidate_count = 0
    last_tick_price = None
    active = None
    peak_gain = 0.0
    super_order_id = None
    event_trade_count = 0
    event_pnl_rupees = 0.0
    event_pnl_points = 0.0
    last_status_time = 0.0
    feed_ready = False

    def submit_super_order(contract, quantity, premium):
        target_price = round(premium + super_target_points, 2)
        stop_price = round(premium - super_sl_points, 2)
        if stop_price <= 0 or target_price <= premium:
            raise ValueError("Calculated Super Order prices are invalid.")
        payload = {
            "dhanClientId": cid,
            "correlationId": f"M6{int(time.time())}"[-30:],
            "transactionType": "BUY",
            "exchangeSegment": contract["segment"],
            "productType": "INTRADAY",
            "orderType": "MARKET",
            "securityId": str(contract["security_id"]),
            "quantity": int(quantity),
            "price": 0,
            "targetPrice": target_price,
            "stopLossPrice": stop_price,
            "trailingJump": super_trailing_jump
        }
        response = requests.post(
            "https://api.dhan.co/v2/super/orders",
            headers={
                "access-token": tok,
                "client-id": cid,
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            json=payload,
            timeout=15
        )
        response.raise_for_status()
        result = response.json()
        order_id = result.get("orderId")
        if not order_id:
            raise RuntimeError(f"Super Order response has no orderId: {result}")
        return str(order_id), result

    try:
        while True:
            now_dt = datetime.now(IST).replace(tzinfo=None)
            now_text = now_dt.strftime("%H:%M:%S")

            if not active and now_text >= "15:35:00":
                print(f"{RED}{now_text} SESSION END — no new entries after 15:35.{RESET}")
                break

            try:
                price, received_at, exchange_time = tick_queue.get(timeout=1.0)
                feed_ready = True
            except queue.Empty:
                if not feed_ready and time.time() - last_status_time >= 10:
                    print(f"⏳ {now_text} Waiting for Dhan index ticks...")
                    sys.stdout.flush()
                    last_status_time = time.time()
                try:
                    err = feed_errors.get_nowait()
                    print(f"⚠️ Dhan feed: {err}")
                except queue.Empty:
                    pass
                # Bot-managed open positions use actual option LTP; poll no faster
                # than the REST quote allowance when not using a Super Order.
                if active and not use_super_order:
                    option_ltp = get_live_option_ltp(active["security_id"], active["segment"])
                    if option_ltp:
                        gain = option_ltp - active["entry"]
                        peak_gain = max(peak_gain, gain)
                        should_exit = (
                            peak_gain >= TSL_TRIGGER_PTS and
                            gain <= peak_gain - TSL_STEP_PTS
                        ) or now_text >= "15:35:00"
                        if should_exit:
                            realized = gain
                            event_pnl_points += realized
                            event_pnl_rupees += realized * active["quantity"]
                            event_trade_count += 1
                            print(f"{GREEN}{now_text} {active['side']} {active['strike']:g} {active['hma']} R:{active['rsi']:.1f} {active['entry']:4.0f} {option_ltp:4.0f} {realized:+3.0f} {realized*active['quantity']:+5.0f} {event_pnl_rupees:+6.0f} [{event_trade_count}]{RESET}")
                            active = None
                            peak_gain = 0.0
                        else:
                            print(f"{now_text} {active['side']} {active['strike']:g} {active['hma']} R:{active['rsi']:.1f} {active['entry']:4.0f} {option_ltp:4.0f} {gain:+2.0f}")
                continue

            # Ignore duplicate LTP updates: confirmation counts distinct price changes.
            if last_tick_price is not None and price == last_tick_price:
                continue
            last_tick_price = price
            local_prices.append(price)
            if len(local_prices) > 240:
                local_prices.pop(0)

            rsi = compute_rsi(local_prices)
            hma = compute_hma(local_prices)
            hma_label = hma["state"]
            tick_up = len(local_prices) >= 2 and local_prices[-1] > local_prices[-2]
            tick_down = len(local_prices) >= 2 and local_prices[-1] < local_prices[-2]

            if active:
                if use_super_order:
                    # Dhan owns the target/SL legs. Track only for display/status.
                    if now_text >= "15:35:00":
                        print(f"⚠️ {now_text} 15:35 reached; check Dhan Super Order book and close/cancel any open leg manually if still active.")
                        break
                    print(f"{now_text} HOLD {active['side']} {active['strike']:g} {hma_label} R:{rsi:.1f} Entry:{active['entry']:.2f} Super:{super_order_id}")
                else:
                    option_ltp = get_live_option_ltp(active["security_id"], active["segment"])
                    if option_ltp is not None:
                        gain = option_ltp - active["entry"]
                        peak_gain = max(peak_gain, gain)
                        should_exit = (
                            peak_gain >= TSL_TRIGGER_PTS and
                            gain <= peak_gain - TSL_STEP_PTS
                        ) or now_text >= "15:35:00"
                        if should_exit:
                            realized = gain
                            event_pnl_points += realized
                            event_pnl_rupees += realized * active["quantity"]
                            event_trade_count += 1
                            print(f"{GREEN}{now_text} {active['side']} {active['strike']:g} {hma_label} R:{rsi:.1f} {active['entry']:4.0f} {option_ltp:4.0f} {realized:+3.0f} {realized*active['quantity']:+5.0f} {event_pnl_rupees:+6.0f} [{event_trade_count}]{RESET}")
                            active = None
                            peak_gain = 0.0
                        else:
                            print(f"{now_text} {active['side']} {active['strike']:g} {hma_label} R:{rsi:.1f} {active['entry']:4.0f} {option_ltp:4.0f} {gain:+2.0f}")
                previous_rsi, previous_hma = rsi, hma
                continue

            # A candidate begins on the actual threshold crossing.
            if candidate_side is None:
                if previous_rsi <= RSI_OVERSOLD and rsi > RSI_OVERSOLD:
                    candidate_side = "CE"
                    candidate_count = 1
                elif previous_rsi >= RSI_OVERBOUGHT and rsi < RSI_OVERBOUGHT:
                    candidate_side = "PE"
                    candidate_count = 1
            else:
                valid = (
                    candidate_side == "CE" and rsi > RSI_OVERSOLD and
                    hma["rising"] and tick_up
                ) or (
                    candidate_side == "PE" and rsi < RSI_OVERBOUGHT and
                    hma["falling"] and tick_down
                )
                if valid:
                    candidate_count += 1
                else:
                    print(f"{now_text} SIGNAL RESET {candidate_side} R:{rsi:.1f} HMA:{hma_label}")
                    candidate_side = None
                    candidate_count = 0

            # On first crossover tick, HMA and price direction must already agree.
            if candidate_side and candidate_count == 1:
                first_valid = (
                    candidate_side == "CE" and hma["rising"] and tick_up
                ) or (
                    candidate_side == "PE" and hma["falling"] and tick_down
                )
                if not first_valid:
                    candidate_side = None
                    candidate_count = 0

            if candidate_side and candidate_count >= confirmation_ticks:
                side = candidate_side
                print(f"{RED}{now_text} CONFIRMED {side} {price:.2f} HMA:{hma_label} RSI:{rsi:.1f} Ticks:{candidate_count}{RESET}")
                try:
                    contract = select_atm_option(side, price)
                    live_entry_premium = get_locked_option_ltp_for_contract(contract)
                    if live_entry_premium is None or live_entry_premium <= 0:
                        raise RuntimeError("No valid option LTP for selected ATM contract.")

                    if use_super_order:
                        order_id, order_response = submit_super_order(contract, LOT_MULTIPLIER, live_entry_premium)
                        super_order_id = order_id
                        print(f"{RED}{now_text} LIVE SUPER ORDER {side} Strike:{contract['strike']:g} ID:{contract['security_id']} Qty:{LOT_MULTIPLIER} Premium:{live_entry_premium:.2f} Order:{order_id}{RESET}")
                    else:
                        print(f"{RED}{now_text} PAPER BUY {side} Strike:{contract['strike']:g} Exp:{contract['expiry']} ID:{contract['security_id']} Qty:{LOT_MULTIPLIER} Avg:{live_entry_premium:.2f} Spot:{price:.2f} HMA:{hma_label} RSI:{rsi:.1f}{RESET}")

                    active = {
                        "side": side,
                        "security_id": contract["security_id"],
                        "segment": contract["segment"],
                        "strike": contract["strike"],
                        "entry": live_entry_premium,
                        "quantity": LOT_MULTIPLIER,
                        "hma": hma_label,
                        "rsi": rsi
                    }
                    peak_gain = 0.0
                except Exception as e:
                    print(f"⚠️ {now_text} {side} signal, entry failed: {e}")
                candidate_side = None
                candidate_count = 0

            print(f"{now_text} sc {price:.2f} {hma_label} R:{rsi:.1f} C:{candidate_count}/{confirmation_ticks}")
            previous_rsi, previous_hma = rsi, hma
            sys.stdout.flush()

    finally:
        try:
            market_feed.close_connection()
        except Exception:
            pass

    print("\n" + "=" * 40 + "\n     MODE 6 PERFORMANCE SUMMARY     \n" + "=" * 40)
    print(f"• Completed cycles : {event_trade_count}")
    print(f"• Net points        : {event_pnl_points:+.2f}")
    print(f"• Net paper P&L     : ₹{event_pnl_rupees:+,.0f}")
    print("=" * 40)
    sys.stdout.flush()


try:
    while True:
        if is_mode7:
            best_cfg = {
                "asset_name": ASSET_NAME, "lot_multiplier": int(LOT_MULTIPLIER),
                "rsi_period": 5, "rsi_oversold": 60.0, "rsi_overbought": 40.0,
                "hma_period": 4, "use_hma": True, "timeframe_seconds": 5,
                "lots": 2, "premium_min": 0.0, "premium_max": 200.0, "premium_tolerance": 5.0,
                "hard_stop_points": 0.0, "target_points": 0.0, "adverse_ticks": 0,
                "trailing_trigger_points": 5.0, "trailing_step_points": 2.0,
                "brokerage_per_trade": 50.0, "max_daily_loss": 0.0,
                "max_daily_profit": 0.0, "confirmation_ticks": 3, "enabled": True
            }
            run_single_strategy_event_forward(best_cfg)
            break
        if is_mode6:
            run_event_driven_mode6()
            break
        if active_position is None and cumulative_rupees <= -MAX_LOSS_DAY: break
        if active_position is None and cumulative_rupees >= MAX_PROFIT_DAY: break

        # While a Dhan option is locked, monitor only that contract.
        if is_live_mode and active_position is not None:
            now_text = datetime.now(IST).replace(tzinfo=None).strftime("%H:%M")
            try:
                option_ltp = get_locked_option_ltp()
            except Exception as e:
                print(f"⚠️ Option quote error for locked contract {locked_option_security_id}: {e}")
                option_ltp = None

            if option_ltp is not None:
                current_option_gain = option_ltp - entry_premium
                if is_mode5:
                    # Match Mode 2 backtest exit calculations, using actual Dhan option LTP.
                    current_pnl_pts = int(round(current_option_gain))
                    if current_pnl_pts > spot_peak_price:
                        spot_peak_price = current_pnl_pts
                    max_gain = spot_peak_price
                    exit_triggered = (
                        max_gain >= TSL_TRIGGER_PTS
                        and current_pnl_pts <= max_gain - TSL_STEP_PTS
                    ) or now_text >= "15:35"
                else:
                    option_peak_gain = max(option_peak_gain, current_option_gain)
                    exit_triggered = (
                        option_peak_gain >= TSL_TRIGGER_PTS
                        and current_option_gain <= option_peak_gain - TSL_STEP_PTS
                    ) or now_text >= "15:35"

                if exit_triggered:
                    exit_contract = {"security_id": locked_option_security_id, "segment": locked_option_segment}
                    try:
                        if is_live_trade:
                            exit_result = place_and_confirm_market_order(exit_contract, "SELL", active_order_quantity)
                            if exit_result["filled_qty"] > 0:
                                active_order_quantity -= exit_result["filled_qty"]
                                realized_points = exit_result["average_price"] - entry_premium
                                cumulative_rupees += realized_points * exit_result["filled_qty"]
                                cumulative_points += realized_points
                                print(f"{GREEN}{now_text} SELL {exit_result['status']} Filled:{exit_result['filled_qty']} Remaining:{active_order_quantity} Avg:{exit_result['average_price']:.2f} Order:{exit_result['order_id']} Realized:₹{realized_points * exit_result['filled_qty']:+.2f}{RESET}")
                        else:
                            realized_points = option_ltp - entry_premium
                            cumulative_rupees += realized_points * active_order_quantity
                            cumulative_points += realized_points
                            active_order_quantity = 0
                            if not is_mode5:
                                print(f"{GREEN}{now_text} PAPER SELL Filled:{LOT_MULTIPLIER} Avg:{option_ltp:.2f} Realized:₹{realized_points * LOT_MULTIPLIER:+.2f}{RESET}")
                        if active_order_quantity <= 0:
                            trade_counter += 1
                            if is_mode5:
                                pnl_rs = realized_points * LOT_MULTIPLIER
                                print(f"{GREEN}{now_text} {active_position} {strike_price:g} {hma_label} R:{int(rsi)} {entry_premium:4.0f} {option_ltp:4.0f} {realized_points:+3.0f} {pnl_rs:+5.0f} {cumulative_rupees:+6.0f} [{trade_counter}]{RESET}")
                            else:
                                print(f"{GREEN}{now_text} EXIT COMPLETE {active_position} {strike_price} Premium:{option_ltp:.2f} Entry:{entry_premium:.2f} Pts:{current_option_gain:+.2f} Peak:{option_peak_gain:.2f} [{trade_counter}]{RESET}")
                            active_position = None
                            locked_option_security_id, locked_option_segment = None, None
                            entry_premium, option_peak_gain = 0.0, 0.0
                            strike_price = 0
                            active_order_quantity = 0
                            try:
                                refresh_dhan_index_warmup()
                                print("↻ Index candle history refreshed. Scanning for the next entry.")
                            except Exception as e:
                                print(f"⚠️ Index warm-up refresh failed: {e}")
                        else:
                            print(f"⚠️ Exit incomplete; retaining position tracking for {active_order_quantity} units. {exit_result['error']}")
                    except OrderSubmissionUncertain as e:
                        print(f"🛑 {e} Bot halted to prevent a duplicate or opposite order.")
                        break
                    except Exception as e:
                        print(f"⚠️ SELL order failed; position remains locked and will be monitored: {e}")
                else:
                    if is_mode5:
                        pk_str = "Pk" if current_pnl_pts == max_gain else ""
                        print(f"{now_text} {active_position} {strike_price:g} {hma_label} R:{int(rsi)} {entry_premium:4.0f} {option_ltp:4.0f} {current_pnl_pts:+2d} {pk_str}")
                    else:
                        print(f"{now_text} HOLD {active_position} {strike_price} Premium:{option_ltp:.2f} Entry:{entry_premium:.2f} Pts:{current_option_gain:+.2f} Peak:{option_peak_gain:.2f}")
            elif now_text >= "15:35":
                print(f"{RED}{now_text} SESSION END — quote unavailable; open position remains unresolved. No new entry will be scanned.{RESET}")

            sys.stdout.flush()
            time.sleep(5.0)
            continue

        ltp = 0.0
        if historical_index < len(historical_candles):
            full_dt_str, ltp = historical_candles[historical_index]
            historical_index += 1
        elif is_live_mode and dhan_client:
            try:
                now_dt = datetime.now(IST).replace(tzinfo=None)
                resp = dhan_client.intraday_minute_data(
                    security_id=DHAN_SECURITY_ID,
                    exchange_segment=DHAN_EXCHANGE,
                    instrument_type="INDEX",
                    from_date=now_dt.strftime("%Y-%m-%d"),
                    to_date=now_dt.strftime("%Y-%m-%d")
                )
                if not resp or not resp.get("data") or not resp["data"].get("close"):
                    if time.time() - last_dhan_status_log >= 15:
                        detail = (resp.get("remarks") or resp.get("message") or resp.get("status") or "No candle data in Dhan response") if isinstance(resp, dict) else repr(resp)
                        print(f"⏳ {now_dt:%H:%M:%S} Waiting for Dhan index candles: {detail}")
                        sys.stdout.flush()
                        last_dhan_status_log = time.time()
                    time.sleep(5.0)
                    continue

                data = resp["data"]
                timestamps = data.get("timestamp", [])
                closes = data.get("close", [])
                current_minute = now_dt.replace(second=0, microsecond=0)
                new_candles = []
                for ts, close in zip(timestamps, closes):
                    candle_dt = pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Kolkata").tz_localize(None) if isinstance(ts, (int, float, np.integer, np.floating)) else pd.to_datetime(ts)
                    if candle_dt.tzinfo is not None:
                        candle_dt = candle_dt.tz_convert("Asia/Kolkata").tz_localize(None)
                    candle_dt = candle_dt.to_pydatetime()
                    if candle_dt < current_minute and (last_dhan_candle_time is None or candle_dt > last_dhan_candle_time):
                        new_candles.append((candle_dt, float(close)))

                if not new_candles:
                    if time.time() - last_dhan_status_log >= 15:
                        latest_returned = None
                        if timestamps:
                            try:
                                raw_ts = timestamps[-1]
                                latest_dt = pd.to_datetime(raw_ts, unit="s", utc=True).tz_convert("Asia/Kolkata").tz_localize(None) if isinstance(raw_ts, (int, float, np.integer, np.floating)) else pd.to_datetime(raw_ts)
                                if latest_dt.tzinfo is not None:
                                    latest_dt = latest_dt.tz_convert("Asia/Kolkata").tz_localize(None)
                                latest_returned = latest_dt.strftime("%H:%M:%S")
                            except Exception:
                                latest_returned = str(timestamps[-1])
                        last_done = last_dhan_candle_time.strftime("%H:%M:%S") if last_dhan_candle_time else "none"
                        print(f"⏳ {now_dt:%H:%M:%S} No new completed candle. Dhan latest:{latest_returned or 'unavailable'} | Last processed:{last_done}")
                        sys.stdout.flush()
                        last_dhan_status_log = time.time()
                    time.sleep(5.0)
                    continue

                new_candles.sort(key=lambda item: item[0])
                candle_dt, ltp = new_candles[-1]
                last_dhan_candle_time = candle_dt
                full_dt_str = candle_dt.strftime("%Y-%m-%d %H:%M:%S")
                if not is_mode5:
                    print(f"📈 Dhan candle accepted: {full_dt_str} | Index close:{ltp:.2f}")
                    sys.stdout.flush()
                last_dhan_status_log = time.time()
                time.sleep(5.0)
            except Exception as e:
                print(f"⚠️ Dhan live candle request/processing error at {datetime.now(IST).replace(tzinfo=None):%H:%M:%S}: {type(e).__name__}: {e}")
                sys.stdout.flush()
                time.sleep(5.0)
                continue
        else:
            break

        date_str, time_str = full_dt_str.split(' ')[0], full_dt_str.split(' ')[1][:5] if ' ' in full_dt_str else "09:15"
        if date_str != current_day_str: current_day_str, day_counter, trades_today_counter = date_str, day_counter + 1, 0

        price_history.append(ltp)
        if len(price_history) > 120: price_history.pop(0)

        prev_rsi = compute_rsi(price_history[:-1]) if len(price_history) > 1 else 50.0
        rsi = compute_rsi(price_history)
        hma_res = compute_hma(price_history)
        hma_label = hma_res["state"]

        if active_position is not None:
            delta_spot = (ltp - strike_price) if active_position == "CE" else (strike_price - ltp)
            current_prem = max(10, int(round(entry_premium + abs(delta_spot * 0.15) + (random.random() * 2 - 1))))
            current_pnl_pts = int(round(current_prem - entry_premium))
            
            is_peak = False
            if current_pnl_pts > spot_peak_price:
                spot_peak_price = current_pnl_pts
                is_peak = True
            max_gain = spot_peak_price

            exit_triggered, locked_pts = False, 0
            if max_gain >= TSL_TRIGGER_PTS and current_pnl_pts <= max_gain - TSL_STEP_PTS:
                exit_triggered, locked_pts = True, int(max_gain - TSL_STEP_PTS)
            elif time_str >= "15:25": exit_triggered, locked_pts = True, current_pnl_pts

            if exit_triggered:
                trade_counter, trades_today_counter = trade_counter + 1, trades_today_counter + 1
                pnl_rs = locked_pts * LOT_MULTIPLIER
                cumulative_rupees += pnl_rs
                cumulative_points += locked_pts

                trade_records.append({"date": date_str, "month": date_str[:7], "investment": entry_premium * LOT_MULTIPLIER, "pnl_rs": pnl_rs, "locked_pts": locked_pts})
                c_col = GREEN if cumulative_rupees >= 0 else RED
                # Exit line highlighted in GREEN
                print(f"{GREEN}{time_str} {active_position} {strike_price} {hma_label} R:{int(rsi)} {entry_premium:4d} {current_prem:4d} {locked_pts:+3d} {pnl_rs:+5.0f} {cumulative_rupees:+6.0f} [{day_counter}/{trades_today_counter}/{trade_counter}]{RESET}")
                sys.stdout.flush()
                active_position = None
            else:
                pk_str = "Pk" if is_peak else ""
                print(f"{time_str} {active_position} {strike_price} {hma_label} R:{int(rsi)} {entry_premium:4d} {current_prem:4d} {current_pnl_pts:+2d} {pk_str}")
                sys.stdout.flush()
        else:
            if time_str < "15:25":
                rsi_ce_signal = (prev_rsi <= RSI_OVERSOLD and rsi > RSI_OVERSOLD)
                rsi_pe_signal = (prev_rsi >= RSI_OVERBOUGHT and rsi < RSI_OVERBOUGHT)
                ce_signal = rsi_ce_signal and hma_res["rising"]
                pe_signal = rsi_pe_signal and hma_res["falling"]

                if ce_signal or pe_signal:
                    signal_side = "CE" if ce_signal else "PE"
                    if is_live_mode:
                        try:
                            contract = select_atm_option(signal_side, ltp)
                            live_entry_premium = get_locked_option_ltp_for_contract(contract)
                            if live_entry_premium is None:
                                raise RuntimeError("No live LTP returned for the selected option contract.")

                            if is_live_trade:
                                entry_result = place_and_confirm_market_order(contract, "BUY", LOT_MULTIPLIER)
                                if entry_result["filled_qty"] <= 0 or entry_result["average_price"] <= 0:
                                    print(f"⚠️ {time_str} BUY not filled ({entry_result['status']}). {entry_result['error']} Returning to scan.")
                                    continue
                                active_order_quantity = entry_result["filled_qty"]
                                entry_premium = entry_result["average_price"]
                                order_note = f"Order:{entry_result['order_id']}"
                                if active_order_quantity < LOT_MULTIPLIER:
                                    print(f"⚠️ Partial entry fill: managing only {active_order_quantity} filled units.")
                            else:
                                active_order_quantity = LOT_MULTIPLIER
                                entry_premium = live_entry_premium
                                order_note = "PAPER - no order sent"

                            locked_option_security_id = contract["security_id"]
                            locked_option_segment = contract["segment"]
                            strike_price = contract["strike"]
                            active_position = signal_side
                            option_peak_gain = 0.0
                            if is_mode5:
                                spot_peak_price = 0
                            if is_mode5:
                                print(f"{RED}{time_str} {active_position} {strike_price:g} {hma_label} R:{int(rsi)} {entry_premium:4.0f} {entry_premium:4.0f} {0:+2d} [{hma_label}]{RESET}")
                            else:
                                trade_label = "LIVE BUY FILLED" if is_live_trade else "FORWARD PAPER BUY"
                                print(f"{RED}{time_str} {trade_label} {active_position} Strike:{strike_price:g} Exp:{contract['expiry']} ID:{locked_option_security_id} Qty:{active_order_quantity} Avg:{entry_premium:.2f} {order_note} Spot:{ltp:.2f} HMA:{hma_label} RSI:{rsi:.1f}{RESET}")
                        except OrderSubmissionUncertain as e:
                            print(f"🛑 {e} Bot halted; check Dhan orderbook before restarting.")
                            break
                        except Exception as e:
                            active_position = None
                            locked_option_security_id, locked_option_segment = None, None
                            active_order_quantity = 0
                            print(f"⚠️ {time_str} {signal_side} signal, but entry failed: {e}. Returning to scan.")
                        sys.stdout.flush()
                        continue
                    active_position = signal_side
                    strike_price = (int(round(ltp, -2)) - 100) if ce_signal else (int(round(ltp, -2)) + 100)
                    entry_premium = int(round(250.0 + random.random() * 30))
                    spot_peak_price = 0

                    dummy_out = int(round(entry_premium + (random.random() * 6 - 3)))
                    # Entry/Signal line highlighted in RED
                    print(f"{RED}{time_str} {active_position} {strike_price} {hma_label} R:{int(rsi)} {entry_premium:4d} {dummy_out:4d} [{hma_label}]{RESET}")
                    sys.stdout.flush()
                else: 
                    dummy_in = int(round(250.0 + random.random() * 10))
                    dummy_out = int(round(dummy_in + (random.random() * 6 - 3)))
                    print(f"{time_str} sc {int(ltp)} {hma_label} R:{int(rsi)} {dummy_in:4d} {dummy_out:4d}")
                sys.stdout.flush()
            else: print(f"{time_str} CLOSED"); sys.stdout.flush()
except KeyboardInterrupt:
    print("\n🛑 Bot stopped manually.")
finally:
    if os.path.exists(LOCK_FILE):
        try: os.remove(LOCK_FILE)
        except: pass

print(f"\n" + "=" * 40 + f"\n     PERFORMANCE SUMMARY     \n" + "=" * 40)
if is_live_mode:
    print(f"• Completed signal cycles : {trade_counter}")
    print(f"• Net index points        : {cumulative_points:+.2f}")
    if active_position is not None:
        print(f"• Still tracking          : {active_position} from {entry_spot:.2f}")
elif len(trade_records) > 0:
    investments = [t["investment"] for t in trade_records]
    opening_inv = investments[0]
    overall_return_pct = (cumulative_rupees / opening_inv) * 100 if opening_inv > 0 else 0.0
    print(f"• Earnings : ₹{cumulative_rupees:+,.0f} ({overall_return_pct:+.1f}%) | {cumulative_points:+,.1f} Pts")
    print(f"• Trades   : {len(trade_records)}")
else: print(" ⚠️ No trades recorded.")
print("=" * 40)
sys.stdout.flush()