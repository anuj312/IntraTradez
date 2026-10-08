"""Embed the premium stylesheet into the scanner's single served HTML.

Usage: python scripts/sync_premium_css.py

The Flask app serves a standalone HTML document without a public static route,
so CSS is intentionally embedded to work with the original deployment.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "intraday-momentum-scanner.html"
CSS = ROOT / "premium-terminal.css"
START = '<style id="pulse-spectra-premium">'
END = "</style>"


def main():
    text = HTML.read_text(encoding="utf-8")
    pos = text.index(START)
    finish = text.index(END, pos) + len(END)
    result = text[:pos] + START + "\n" + CSS.read_text(encoding="utf-8").rstrip() + "\n" + END + text[finish:]
    HTML.write_text(result, encoding="utf-8")
    print("Premium styles embedded in intraday-momentum-scanner.html")


if __name__ == "__main__":
    main()
