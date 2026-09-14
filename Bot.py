import asyncio
import os
import logging
import aiohttp
from aiohttp import web
import pandas as pd
import pandas_ta as ta
from telegram import Bot

# Render Environment Variables se read karega
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOLS = ["BTCUSD", "ETHUSD", "SOLUSD", "XAUTUSD"]
TIMEFRAME = "15m"
COOLDOWN_MINUTES = 30
DELTA_REST_URL = "https://cdn.india.delta.exchange/v2/history/candles"

bot = Bot(token=TELEGRAM_BOT_TOKEN)
last_alert_time = {s: 0 for s in SYMBOLS}
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

async def send_telegram_alert(message: str):
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Telegram error: {e}")

async def fetch_candles(session, symbol: str, resolution: str = "15m"):
    params = {"symbol": symbol, "resolution": resolution}
    try:
        async with session.get(DELTA_REST_URL, params=params, timeout=10) as resp:
            data = await resp.json()
            if data.get("success") and "result" in data:
                df = pd.DataFrame(data["result"]).iloc[::-1].reset_index(drop=True)
                for col in ["close", "high", "low", "open", "volume"]:
                    df[col] = df[col].astype(float)
                return df
    except Exception as e:
        logging.error(f"Data fetch error for {symbol}: {e}")
    return None

def analyze_market(df: pd.DataFrame, symbol: str):
    if len(df) < 50:
        return None
    df["RSI"] = ta.rsi(df["close"], length=14)
    df["EMA_20"] = ta.ema(df["close"], length=20)
    df["EMA_50"] = ta.ema(df["close"], length=50)
    df["EMA_200"] = ta.ema(df["close"], length=200)
    df["ATR"] = ta.atr(df["high"], df["low"], df["close"], length=14)

    curr, prev = df.iloc[-1], df.iloc[-2]
    atr, price = curr["ATR"], curr["close"]

    # Strategy: EMA Cross in Trend Direction
    if (prev["EMA_20"] <= prev["EMA_50"]) and (curr["EMA_20"] > curr["EMA_50"]) and (curr["close"] > curr["EMA_200"]):
        return {
            "strategy": "EMA 20/50 Golden Cross + 200 Trend",
            "entry": f"${price:.2f}",
            "sl": f"${price - (1.5 * atr):.2f}",
            "tp1": f"${price + (2.0 * atr):.2f}",
            "tp2": f"${price + (3.5 * atr):.2f}",
            "tip": "Strong macro trend confirmed above 200 EMA."
        }
    return None

async def monitor_symbols():
    async with aiohttp.ClientSession() as session:
        while True:
            for symbol in SYMBOLS:
                df = await fetch_candles(session, symbol, resolution=TIMEFRAME)
                if df is not None:
                    signal = analyze_market(df, symbol)
                    if signal:
                        now_loop = asyncio.get_event_loop().time()
                        if (now_loop - last_alert_time[symbol]) > (COOLDOWN_MINUTES * 60):
                            msg = (
                                f"🔔 *[DELTA MENTOR ALERT] — {symbol}*\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"📊 *Setup:* {signal['strategy']}\n"
                                f"📍 *Entry:* `{signal['entry']}`\n"
                                f"🛑 *SL:* `{signal['sl']}`\n"
                                f"🎯 *TP1:* `{signal['tp1']}` | *TP2:* `{signal['tp2']}`\n"
                                f"💡 *Mentor Rule:* {signal['tip']}\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━"
                            )
                            await send_telegram_alert(msg)
                            last_alert_time[symbol] = now_loop
                await asyncio.sleep(2)
            await asyncio.sleep(60)

# Dummy Web Server (Render port binding ke liye zaroori hai)
async def handle_ping(request):
    return web.Response(text="Bot is running active 24/7!")

async def start_background_tasks(app):
    app['bot_task'] = asyncio.create_task(monitor_symbols())

async def cleanup_background_tasks(app):
    app['bot_task'].cancel()
    await app['bot_task']

def create_app():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    return app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    web.run_app(create_app(), host="0.0.0.0", port=port)
