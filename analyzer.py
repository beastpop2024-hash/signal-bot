import aiohttp
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

FOREX_ONLY = ["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD"]

SYSTEM_PROMPT = """تو یک تحلیلگر حرفه‌ای بازارهای مالی با تخصص SMC/ICT هستی.
روش تحلیل: BOS، CHoCH، FVG، Order Block، Liquidity Sweep، Premium/Discount Zone.
استراتژی‌های مجاز:
- CHoCH + FVG Reversal
- BOS + Order Block Retest
- Liquidity Sweep + Rejection
- FVG Fill Continuation
- Premium/Discount Reversal
- OB + Liquidity Grab
- Breaker Block Continuation
- Weekly Bias + Daily Confirmation
قوانین:
۱. فقط وقتی ساختار کاملاً واضح است سیگنال بده
۲. امتیاز ۰ تا ۱۰۰ بده
۳. اگر بازار رنج یا مبهم است: signal = "NO_TRADE"
۴. RR باید حداقل 1:1.5 باشد وگرنه NO_TRADE
خروجی فقط JSON خالص بدون هیچ توضیح:
{
  "signal": "BUY" یا "SELL" یا "NO_TRADE",
  "score": عدد صحیح ۰ تا ۱۰۰,
  "entry": عدد اعشاری,
  "sl": عدد اعشاری,
  "tp1": عدد اعشاری,
  "tp2": عدد اعشاری,
  "timeframe": "مثلاً Daily + 4H",
  "strategy": "نام استراتژی",
  "rr": "مثلاً 1:2.1",
  "reasons": "دلایل فارسی یک جمله",
  "narrative": "تحلیل عمیق فارسی ۲ تا ۳ جمله",
  "advice": "توصیه عملی فارسی یک جمله"
}"""

class MarketAnalyzer:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-1.5-flash:generateContent?key={api_key}"
        )
        self.binance = "https://api.binance.com/api/v3"
        self.fxrate = "https://open.er-api.com/v6/latest"

    async def _klines(self, symbol: str, interval: str, limit: int = 100) -> Optional[list]:
        url = f"{self.binance}/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=12)) as r:
                    if r.status == 200:
                        return await r.json()
                    return None
        except Exception as e:
            logger.error(f"Binance error {symbol}: {e}")
            return None

    async def _forex_price(self, symbol: str) -> Optional[float]:
        base = symbol[:3]
        quote = symbol[3:]
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{self.fxrate}/{base}", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data.get("rates", {}).get(quote)
        except Exception as e:
            logger.error(f"Forex error {symbol}: {e}")
        return None

    def _summarize(self, klines: list, label: str) -> str:
        if not klines or len(klines) < 10:
            return ""
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        cur = closes[-1]
        ema20 = sum(closes[-20:]) / min(20, len(closes))
        ema50 = sum(closes[-50:]) / min(50, len(closes))
        trend = "BULLISH" if ema20 > ema50 else "BEARISH"
        last20 = klines[-20:]
        rows = "\n".join(
            f"O:{float(k[1]):.5f} H:{float(k[2]):.5f} L:{float(k[3]):.5f} C:{float(k[4]):.5f}"
            for k in last20
        )
        return (
            f"=== {label} ===\n"
            f"قیمت فعلی: {cur:.5f}\n"
            f"روند EMA20/EMA50: {trend}\n"
            f"سقف ۱۰ کندل اخیر: {max(highs[-10:]):.5f}\n"
            f"کف ۱۰ کندل اخیر: {min(lows[-10:]):.5f}\n"
            f"سقف ۳۰-۱۰ کندل: {max(highs[-30:-10]):.5f}\n"
            f"کف ۳۰-۱۰ کندل: {min(lows[-30:-10]):.5f}\n"
            f"آخرین ۲۰ کندل OHLC:\n{rows}\n"
        )

    async def _ask_gemini(self, market_data: str, symbol: str) -> Optional[dict]:
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": f"داده‌های بازار برای {symbol}:\n\n{market_data}\n\nتحلیل کامل SMC/ICT انجام بده. فقط JSON خروجی بده."}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800, "responseMimeType": "application/json"}
        }
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(self.gemini_url, json=payload, timeout=aiohttp.ClientTimeout(total=35)) as r:
                    if r.status != 200:
                        err = await r.text()
                        logger.error(f"Gemini error {r.status}: {err[:200]}")
                        return None
                    data = await r.json()
                    raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if raw.startswith("```"):
                        raw = raw.split("```")[1]
                        if raw.startswith("json"):
                            raw = raw[4:]
                    return json.loads(raw.strip())
        except Exception as e:
            logger.error(f"Gemini call error {symbol}: {e}")
        return None

    async def analyze(self, symbol: str) -> Optional[dict]:
        if symbol == "XAUUSD":
            k4h = await self._klines("XAUUSDT", "4h", 100)
            k1d = await self._klines("XAUUSDT", "1d", 50)
            if not k4h:
                return None
            data = self._summarize(k4h, "XAUUSD 4H") + "\n" + self._summarize(k1d or [], "XAUUSD Daily")
            return await self._ask_gemini(data, symbol)
        if symbol in FOREX_ONLY:
            price = await self._forex_price(symbol)
            if not price:
                return None
            data = f"نماد: {symbol}\nقیمت لحظه‌ای: {price:.5f}\nاگر تحلیل کافی نیست signal=NO_TRADE برگردان.\n"
            return await self._ask_gemini(data, symbol)
        k4h = await self._klines(symbol, "4h", 100)
        k1d = await self._klines(symbol, "1d", 50)
        if not k4h:
            return None
        data = self._summarize(k4h, f"{symbol} 4H") + "\n" + self._summarize(k1d or [], f"{symbol} Daily")
        return await self._ask_gemini(data, symbol)
