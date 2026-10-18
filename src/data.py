"""Load Yahoo open and close prices and turn them into return series.

Close-to-close returns are split into an overnight part (close to next open) and a
session part (open to close). The backtest decides at the close and trades at the
next open, so the overnight return belongs to the old position and the session
return to the new one.
"""
import numpy as np
import pandas as pd

from . import config as C


def ohlc(name):
    d = pd.read_parquet(C.RAW / f"{name}_ohlc.parquet")
    return d["Open"], d["Close"]


def etf_returns():
    """Close-to-close, open-to-close and close-to-open log returns for the ETF universe."""
    o, c = ohlc("etf")
    cc = np.log(c).diff()
    oc = np.log(c / o)
    return cc, oc, cc - oc
