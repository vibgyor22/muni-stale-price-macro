"""Download every input from Yahoo Finance. Free, no API keys.

    python -m src.fetch           # fetch what is missing
    python -m src.fetch --force   # refresh everything

MUB, VTEB   national muni bond ETFs (traded)
IEF         7-10 year Treasury ETF (hedge and main signal input)
SPY         S&P 500 ETF (equity catch-up input)
HYG, LQD, TLT, SHY   credit and Treasury ETFs used only in the factor regression
"""
import argparse

from . import config as C


def yahoo(force=False):
    import yfinance as yf
    for name, tickers in [("etf", C.ETF_TICKERS), ("factor", ["HYG", "LQD", "TLT", "SHY"])]:
        p = C.RAW / f"{name}_ohlc.parquet"
        if force or not p.exists():
            print("Yahoo", name)
            d = yf.download(tickers, start="2007-01-01", auto_adjust=True, progress=False)
            d[["Open", "Close", "Volume"]].to_parquet(p)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    yahoo(ap.parse_args().force)
