"""India-only rolling news service for the intraday momentum scanner."""

from __future__ import annotations

import calendar
import logging
import os
import ssl
import threading
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import certifi
import feedparser

from sector_definitions import ALL_SYMBOLS, SECTOR_DEFINITIONS


IST = ZoneInfo("Asia/Kolkata")
log = logging.getLogger("market-news")

NEWS_SITES = [
    "moneycontrol.com",
    "economictimes.indiatimes.com",
    "livemint.com",
    "business-standard.com",
    "financialexpress.com",
    "cnbctv18.com",
    "zeebiz.com",
    "thehindubusinessline.com",
    "bqprime.com",
]

QUERY_MAP = {
    "M&M": "Mahindra & Mahindra",
    "LT": "Larsen & Toubro",
    "BAJAJ-AUTO": "Bajaj Auto",
    "LODHA": "Macrotech Developers Lodha",
    "ADANIENT": "Adani Enterprises",
    "JIOFIN": "Jio Financial Services",
    "BSE": "BSE Ltd",
    "MCX": "Multi Commodity Exchange of India",
    "ETERNAL": "Eternal stock India",
    "TMPV": "Tata Motors stock",
}

NEWS_WINDOW_HOURS = int(os.getenv("NEWS_WINDOW_HOURS", "24"))
NEWS_ITEMS_PER_SYMBOL = int(os.getenv("NEWS_ITEMS_PER_SYMBOL", "5"))
NEWS_POLL_SEC = int(os.getenv("NEWS_POLL_SEC", "60"))
NEWS_REQUEST_DELAY_SEC = float(os.getenv("NEWS_REQUEST_DELAY_SEC", "0.12"))
NEWS_WATCHLIST_MODE = os.getenv("NEWS_WATCHLIST_MODE", "ALL").upper()

SYMBOL_TO_SECTORS: dict[str, list[str]] = {}
for sector, symbols in SECTOR_DEFINITIONS.items():
    if sector == "NIFTY_50":
        continue
    for symbol in symbols:
        SYMBOL_TO_SECTORS.setdefault(symbol, []).append(sector)

SYMBOLS = SECTOR_DEFINITIONS["NIFTY_50"] if NEWS_WATCHLIST_MODE == "NIFTY_50" else ALL_SYMBOLS


class FinancialSentiment:
    """Lazy FinBERT classifier with a small no-model fallback."""

    POSITIVE = {"growth", "profit", "wins", "award", "order", "surge", "strong", "upgrade", "approval", "dividend", "record", "expands"}
    NEGATIVE = {"loss", "fraud", "probe", "decline", "weak", "downgrade", "lawsuit", "default", "cuts", "fall", "risk", "delay"}

    def __init__(self) -> None:
        self.model = None
        self.tokenizer = None
        self.status = "Starting"
        self.error = None
        self.lock = threading.Lock()

    def _load(self) -> None:
        if self.model is not None or self.status == "Offline fallback":
            return
        with self.lock:
            if self.model is not None or self.status == "Offline fallback":
                return
            try:
                from transformers import AutoModelForSequenceClassification, AutoTokenizer
                import torch

                self.status = "Loading FinBERT"
                self.tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
                self.model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
                self.model.eval()
                self.status = "FinBERT online"
                log.info("News sentiment model loaded")
            except Exception as exc:  # pragma: no cover - depends on local model/network
                self.error = str(exc)
                self.status = "Offline fallback"
                log.warning("FinBERT unavailable; using offline fallback: %s", exc)

    def _fallback(self, text: str) -> tuple[str, float]:
        words = {word.strip(".,:;!?()[]{}\"").lower() for word in text.split()}
        positive = len(words & self.POSITIVE)
        negative = len(words & self.NEGATIVE)
        if positive == negative:
            return "NEUTRAL", 0.0
        label = "POSITIVE" if positive > negative else "NEGATIVE"
        confidence = min(0.45 + abs(positive - negative) * 0.08, 0.82)
        return label, confidence if label == "POSITIVE" else -confidence

    def classify(self, text: str) -> tuple[str, float]:
        self._load()
        if self.model is None or self.tokenizer is None:
            return self._fallback(text)
        try:
            import torch

            inputs = self.tokenizer(text[:1200], return_tensors="pt", truncation=True, max_length=256)
            with torch.inference_mode():
                probabilities = torch.softmax(self.model(**inputs).logits[0], dim=-1)
            index = int(torch.argmax(probabilities).item())
            labels = self.model.config.id2label
            label = str(labels.get(index, labels.get(str(index), f"LABEL_{index}"))).upper()
            if label.startswith("LABEL_"):
                label = {0: "POSITIVE", 1: "NEGATIVE", 2: "NEUTRAL"}.get(index, "NEUTRAL")
            if "POS" in label:
                label = "POSITIVE"
            elif "NEG" in label:
                label = "NEGATIVE"
            else:
                label = "NEUTRAL"
            confidence = float(probabilities[index].item())
            return label, confidence if label == "POSITIVE" else -confidence if label == "NEGATIVE" else 0.0
        except Exception as exc:
            log.warning("FinBERT classification failed: %s", exc)
            return self._fallback(text)


def _timestamp(entry: Any) -> int:
    if getattr(entry, "published_parsed", None):
        return int(calendar.timegm(entry.published_parsed))
    return int(time.time())


def _source(entry: Any, title: str) -> str:
    source = ""
    try:
        source = entry.get("source", {}).get("title", "")
    except AttributeError:
        pass
    return source or (title.rsplit(" - ", 1)[-1].strip() if " - " in title else "Indian business media")


def _request_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 Indian market research dashboard"})
    context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(request, timeout=15, context=context) as response:
        return response.read()


class NewsService:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.sentiment = FinancialSentiment()
        self.media: list[dict[str, Any]] = []
        self.seen_media: set[str] = set()
        self.started = False
        self.status = "starting"
        self.last_poll = None
        self.last_error = None
        self.last_new_media = 0

    def start(self) -> None:
        with self.lock:
            if self.started:
                return
            self.started = True
        threading.Thread(target=self._loop, name="news-poller", daemon=True).start()

    def _feed(self, symbol: str):
        name = QUERY_MAP.get(symbol, symbol)
        sites = " OR ".join(f"site:{site}" for site in NEWS_SITES)
        query = f'("{name}") (India OR Indian OR NSE OR BSE OR Nifty) (stock OR share OR results OR order OR contract) ({sites}) when:1d'
        url = "https://news.google.com/rss/search?q=" + quote(query) + "&hl=en-IN&gl=IN&ceid=IN:en"
        return feedparser.parse(_request_bytes(url))

    def _prune(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cutoff = int(time.time()) - NEWS_WINDOW_HOURS * 60 * 60
        return [item for item in items if int(item.get("ts", 0)) >= cutoff]

    def _publish_progress(self, media: list[dict[str, Any]], seen: set[str]) -> None:
        with self.lock:
            self.media = sorted(self._prune(media), key=lambda item: item["ts"], reverse=True)
            self.seen_media = set(seen)
            self.last_poll = datetime.now(IST).isoformat()
            self.status = "scanning"

    def _poll_once(self) -> None:
        with self.lock:
            media = list(self.media)
            seen_media = set(self.seen_media)
        new_media = 0
        for position, symbol in enumerate(SYMBOLS, start=1):
            try:
                for entry in self._feed(symbol).entries[:NEWS_ITEMS_PER_SYMBOL]:
                    link = entry.get("link")
                    title = str(entry.get("title") or "").strip()
                    if not link or not title or link in seen_media:
                        continue
                    label, score = self.sentiment.classify(title)
                    seen_media.add(link)
                    media.append({
                        "id": link,
                        "ts": _timestamp(entry),
                        "symbol": symbol,
                        "sector": ",".join(SYMBOL_TO_SECTORS.get(symbol, [])),
                        "title": title,
                        "link": link,
                        "source": _source(entry, title),
                        "sentiment": label,
                        "sent_score": score,
                        "kind": "MEDIA",
                    })
                    new_media += 1
            except Exception as exc:
                log.debug("News fetch failed for %s: %s", symbol, exc)
            time.sleep(NEWS_REQUEST_DELAY_SEC)
            if position % 5 == 0:
                self._publish_progress(media, seen_media)

        with self.lock:
            self.media = sorted(self._prune(media), key=lambda item: item["ts"], reverse=True)[:1200]
            self.seen_media = seen_media
            self.last_poll = datetime.now(IST).isoformat()
            self.last_error = None
            self.last_new_media = new_media
            self.status = "live"
        log.info("News poll complete: +%s media", new_media)

    def _loop(self) -> None:
        while True:
            try:
                self._poll_once()
            except Exception:
                self.status = "error"
                log.exception("News poll failed")
            time.sleep(max(NEWS_POLL_SEC, 30))

    def snapshot(self, sector: str = "ALL", symbol: str = "", limit: int = 300) -> dict[str, Any]:
        with self.lock:
            items = sorted(self._prune(self.media), key=lambda item: item["ts"], reverse=True)
            metadata = {"status": self.status, "last_poll": self.last_poll, "last_error": self.last_error, "model": self.sentiment.status, "new_media": self.last_new_media, "source": "MEDIA"}
        if sector and sector != "ALL":
            items = [item for item in items if sector in str(item.get("sector", "")).split(",")]
        if symbol:
            items = [item for item in items if item.get("symbol") == symbol]
        return {"items": items[:max(1, min(limit, 600))], "meta": {**metadata, "watchlist": NEWS_WATCHLIST_MODE, "symbols": len(SYMBOLS), "window_hours": NEWS_WINDOW_HOURS, "poll_interval": NEWS_POLL_SEC}}

    def health(self) -> dict[str, Any]:
        with self.lock:
            return {"status": self.status, "last_poll": self.last_poll, "model": self.sentiment.status, "items": len(self.media)}


NEWS_SERVICE = NewsService()
