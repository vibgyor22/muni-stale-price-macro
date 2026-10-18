"""Download every input. All free, no API keys.

    python -m src.fetch           # fetch what is missing
    python -m src.fetch --force   # refresh everything

Yahoo Finance   ETF and futures open/close (muni, Treasury, equity, energy)
EIA             NYMEX futures contracts 1-4 for WTI, NG, heating oil, gasoline (daily, 1985/1994-2024)
EIA             weekly US crude oil stocks; weekly Lower-48 natural gas storage
NOAA GHCN       daily station weather for the natural gas storage model
"""
import argparse
import time
import urllib.request

import pandas as pd

from . import config as C

UA = {"User-Agent": "Mozilla/5.0 (research; muni-stale-price-macro)"}


def _get(url, timeout=180):
    for attempt in range(4):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
        except Exception as e:
            if attempt == 3:
                raise
            print(f"  retry {attempt + 1}: {e}")
            time.sleep(5 * (attempt + 1))


def yahoo(force=False):
    import yfinance as yf
    for name, tickers, start in [("etf", C.ETF_TICKERS, "2007-01-01"), ("fut", C.FUT_TICKERS, "2000-01-01")]:
        p = C.RAW / f"{name}_ohlc.parquet"
        if force or not p.exists():
            print("Yahoo", name)
            d = yf.download(tickers, start=start, auto_adjust=True, progress=False)
            d[["Open", "Close", "Volume"]].to_parquet(p)


def eia(force=False):
    for series in [s for v in C.EIA_CURVES.values() for s in v]:
        p = C.RAW / "eia" / f"{series}.xls"
        if force or not p.exists():
            book = "ng" if series.startswith("RNGC") else "pet"
            print("EIA", series)
            p.write_bytes(_get(f"https://www.eia.gov/dnav/{book}/hist_xls/{series}d.xls"))
    weekly = {"eia_WCESTUS1.xls": "https://www.eia.gov/dnav/pet/hist_xls/WCESTUS1w.xls"}
    for f, u in weekly.items():
        p = C.RAW / "eia" / f
        if force or not p.exists():
            print("EIA", f)
            p.write_bytes(_get(u))
    p = C.RAW / "ng_storage.xls"
    if force or not p.exists():
        p.write_bytes(_get("https://www.eia.gov/dnav/ng/hist_xls/NW2_EPG0_SWO_R48_BCFw.xls"))


def ghcn(force=False):
    from .natgas import ALL_STATIONS
    for s in ALL_STATIONS:
        p = C.RAW / "ghcn" / f"{s}.csv.gz"
        if force or not p.exists():
            print("GHCN", s)
            p.write_bytes(_get(f"https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_station/{s}.csv.gz"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    f = ap.parse_args().force
    yahoo(f)
    eia(f)
    ghcn(f)
