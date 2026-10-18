"""Combine sleeves into one book and compute statistics."""
import numpy as np
import pandas as pd

from . import config as C


def stats(x, freq):
    x = x.dropna()
    if len(x) < 20:
        return dict(sharpe=np.nan, t_stat=np.nan, years=0, hit=np.nan, skew=np.nan)
    sr = x.mean() / x.std() * np.sqrt(freq)
    yrs = len(x) / freq
    return dict(sharpe=sr, t_stat=sr * np.sqrt(yrs), years=yrs, hit=(x > 0).mean(), skew=x.skew())


def max_drawdown(x, freq, vol=C.VOL_TARGET):
    x = x.dropna()
    eq = (x / x.std() * vol / np.sqrt(freq)).cumsum()
    return (eq - eq.cummax()).min()


def split_table(series_dict, freq, splits):
    rows = {}
    for name, s in series_dict.items():
        row = {}
        for lab, a, b in splits:
            row[f"sharpe {lab}"] = stats(s.loc[a:b], freq)["sharpe"]
        full = stats(s, freq)
        row.update({"sharpe full": full["sharpe"], "t full": full["t_stat"], "years": full["years"],
                    "max DD @10% vol": max_drawdown(s, freq)})
        rows[name] = row
    return pd.DataFrame(rows).T


def combine(weekly, weights):
    """Risk-normalise each weekly sleeve by its trailing 2-year vol, then weight."""
    Z = (weekly / weekly.rolling(104, min_periods=26).std().shift(1)).clip(-6, 6)
    w = pd.Series(weights)
    num = (Z[w.index] * w).sum(axis=1, min_count=1)
    den = (Z[w.index].notna() * w).sum(axis=1)
    return (num / den).rename("book"), Z
