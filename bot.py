import os
import asyncio
import logging
from telegram import Bot
from telegram.constants import ParseMode
from analyzer import MarketAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHANNEL_ID     = os.environ.get("CHANNEL_ID", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SCAN_INTERVAL  = int(os.environ.get("SCAN_INTERVAL", "1800"))
LBANK_URL      = os.environ.get("LBANK_URL", "https://www.lbank.com")
DELTAFX_URL    = os.environ.get("DELTAFX_URL", "https://deltafx.com")

FOREX_SYMBOLS  = ["XAUUSD","EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD"]
CRYPTO_SYMBOLS = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","TRXUSDT","DOTUSDT","MATICUSDT","AVAXUSDT","LINKUSDT","ATOMUSDT","LTCUSDT","TONUSDT","SHIBUSDT","UNIUSDT","XLMUSDT","NEARUSDT","BCHUSDT"]

def format_signal(data: dict, symbol: str) -> str:
    arrow = "🟢" if data["signal"] == "BUY" else "🔴"
    return (
        f"📊 <b>{symbol}</b> — {arrow} <b>{data['signal']}</b>\n"
        f"⭐ <b>{data['score']}/100</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 ورود:     <code>{data['entry']}</code>\n"
        f"🛑 حد ضرر:  <code>{data['sl']}</code>\n"
        f"✅ TP1:      <code>{data['tp1']}</code>\n"
        f"🏆 TP2:      <code>{data['tp2']}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ {data['timeframe']}  |  📐 {data['strategy']}  |  ⚖️ RR {data['rr']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>دلایل:</b> {data['reasons']}\n\n"
        f"<blockquote>{data['narrative']}</blockquote>\n\n"
        f"💡 <b>توصیه:</b> {data['advice']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f'🏦 <a href="{LBANK_URL}">ثبت‌نام LBank — کپی‌تریدینگ + بونوس</a>\n'
        f'💰 <a href="{DELTAFX_URL}">ثبت‌نام DeltaFX — بونوس ۱۰۰٪ دیپازیت</a>'
    )

async def run_scan(bot: Bot, analyzer: MarketAnalyzer):
    logger.info("=== Starting market scan ===")
    signals_sent = 0
    for symbol in FOREX_SYMBOLS + CRYPTO_SYMBOLS:
        try:
            logger.info(f"Analyzing {symbol} ...")
            result = await analyzer.analyze(symbol)
            if result and result.get("signal") not in (None, "NO_TRADE") and result.get("score", 0) >= 70:
                msg = format_signal(result, symbol)
                await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode=ParseMode.HTML)
                signals_sent += 1
                logger.info(f"  ✅ Signal sent for {symbol} score={result['score']}")
                await asyncio.sleep(4)
            else:
                logger.info(f"  ⏭  {symbol} skipped")
        except Exception as e:
            logger.error(f"  ❌ {symbol}: {e}")
    if signals_sent == 0:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text="📡 <b>اسکن بازار انجام شد</b>\n━━━━━━━━━━━━━━━━━━━━━\n🔍 هیچ ستاپ با کیفیتی یافت نشد.\n⏳ اسکن بعدی ۳۰ دقیقه دیگر.\n━━━━━━━━━━━━━━━━━━━━━",
            parse_mode=ParseMode.HTML
        )
    logger.info(f"=== Scan complete — {signals_sent} signals sent ===")

async def main():
    if not all([TELEGRAM_TOKEN, CHANNEL_ID, GEMINI_API_KEY]):
        logger.error("MISSING ENV VARS!")
        return
    bot = Bot(token=TELEGRAM_TOKEN)
    analyzer = MarketAnalyzer(api_key=GEMINI_API_KEY)
    logger.info("🚀 Signal Bot started")
    while True:
        try:
            await run_scan(bot, analyzer)
        except Exception as e:
            logger.error(f"Scan loop error: {e}")
        logger.info(f"⏳ Sleeping {SCAN_INTERVAL}s ...")
        await asyncio.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
