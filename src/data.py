"""Loaders that turn raw files into clean return series.

Two data-cleaning problems matter more than any model choice here:

1. Yahoo continuous futures (CL=F ...) splice contracts with no adjustment, so roll
   days show the calendar spread as a fake return. Fix: split each day into
   overnight (close->open) and session (open->close) parts. The session part is
   always one contract. The overnight part is kept unless it is an outlier
   (> 6x its typical size), which is what a contract switch looks like.
2. EIA publishes NYMEX contracts 1-4 by position, not by contract. When the front
   expires, "contract 2" becomes "contract 1". We detect each expiry with the
   exchange's calendar rule, confirm it in the data, and stitch the returns of
   the actual contract held.
"""
import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

from . import config as C


# ---------------------------------------------------------------- Yahoo
def ohlc(name):
    d = pd.read_parquet(C.RAW / f"{name}_ohlc.parquet")
    return d["Open"], d["Close"]


def etf_returns():
    """Close-to-close, open-to-close and close-to-open log returns for the ETF universe."""
    o, c = ohlc("etf")
    cc = np.log(c).diff()
    oc = np.log(c / o)
    return cc, oc, cc - oc


def fut_hybrid():
    o, c = ohlc("fut")
    session = np.log(c / o).where((o > 0) & (c > 0))
    gap = np.log(o / c.shift(1)).where((o > 0) & (c.shift(1) > 0))
    typical = gap.abs().rolling(250, min_periods=50).median().shift(1)
    r = session + gap.where(gap.abs() <= 6 * typical, 0.0)
    return r.where(r.abs() < 0.3)


# ---------------------------------------------------------------- EIA
def _xls(series):
    d = pd.read_excel(C.RAW / "eia" / f"{series}.xls", sheet_name="Data 1", header=2).iloc[:, :2]
    d.columns = ["d", "v"]
    return d.set_index("d").v


def eia_weekly(series):
    return _xls(series)


def _last_trade(k, m):
    """Last trading day of the contract delivering in month m (approximate exchange rules)."""
    if k == "NG":                                    # 3 business days before the 1st
        return m - BDay(3)
    if k == "CL":                                    # 3 business days before the 25th of prior month
        d = (m - pd.DateOffset(months=1)).replace(day=25)
        if d.weekday() >= 5:
            d = d - BDay(1)
        return d - BDay(3)
    d = m - pd.DateOffset(days=1)                    # HO, RB: last business day of prior month
    return d if d.weekday() < 5 else d - BDay(1)


def eia_curves():
    """Per commodity: prices of contracts 1-4, roll-clean daily returns, roll-day flags."""
    cache = C.PROC / "eia_curves.pkl"
    if cache.exists():
        return pd.read_pickle(cache)
    P = {k: pd.concat([_xls(s) for s in v], axis=1, keys=[1, 2, 3, 4], sort=True).where(lambda x: x > 0)
         for k, v in C.EIA_CURVES.items()}
    old = P.pop("RB_OLD")
    P["RB"] = pd.concat([old[old.index < P["RB"].dropna().index[0]], P["RB"]])
    out = {}
    for k, p in P.items():
        p = p.dropna()
        lr = np.log(p)
        idx = p.index
        same = lr.diff()                                              # same position, yesterday vs today
        shifted = pd.DataFrame({j: lr[j - 1] - lr[j].shift(1) for j in [2, 3, 4]})   # contract moved up one slot
        score = same[[2, 3, 4]].abs().sum(axis=1) - shifted.abs().sum(axis=1)
        roll = pd.Series(False, index=idx)
        for m in pd.date_range(idx[0], idx[-1] + pd.DateOffset(months=2), freq="MS"):
            j = idx.searchsorted(_last_trade(k, m), side="right")
            cand = [i for i in range(j - 1, j + 3) if 0 < i < len(idx)]
            if cand:
                roll.iloc[max(cand, key=lambda i: score.iloc[i])] = True
        ret = same.copy()
        for j in [2, 3, 4]:
            ret.loc[roll, j] = shifted.loc[roll, j]
        ret.loc[roll, 1] = np.nan                                     # expired contract: no clean return
        out[k] = dict(px=p, ret=ret, roll=roll)
    pd.to_pickle(out, cache)
    return out


# ---------------------------------------------------------------- helpers
def weekly_vol_normalised(daily):
    """Friday-to-Friday returns divided by trailing daily vol x sqrt(5): next-week return in vol units."""
    vol = daily.rolling(60, min_periods=20).std().shift(1)
    W = daily.fillna(0).cumsum().resample("W-FRI").last()
    wv = vol.resample("W-FRI").last()
    nxt = ((W.shift(-1) - W) / wv / np.sqrt(5)).clip(-5, 5)
    return nxt, wv
