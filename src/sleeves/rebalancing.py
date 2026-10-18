"""Sleeve R: month-end rebalancing flows (replication of Harvey, Mazzoleni & Melone 2025).

Roughly $20tn sits in fixed-weight stock/bond mandates (pensions, target-date and
balanced funds) that rebalance near month-end. When stocks have outrun bonds during
the month these funds must sell stocks and buy bonds, and vice versa. The required
trade is computable from public prices. We trade the opposite of the drift during
the last five business days (excluding the final one), long IEF / short SPY when
equities are overweight.
"""
import numpy as np
import pandas as pd

from ..data import etf_returns


def rebalancing(cost=1e-4):
    cc, _, _ = etf_returns()
    r = np.expm1(cc[["SPY", "IEF"]].dropna())
    idx = r.index
    last = pd.Series(idx.to_period("M"), index=idx)
    last = last != last.shift(-1)
    drift, w = [], 0.6
    for t, a, b in zip(idx, r.SPY.values, r.IEF.values):
        w = w * (1 + a) / (w * (1 + a) + (1 - w) * (1 + b))
        drift.append(w - 0.6)
        if last[t]:
            w = 0.6
    drift = pd.Series(drift, index=idx)
    g = pd.Series(1, index=idx).groupby([idx.year, idx.month])
    to_end = g.transform("size") - g.cumsum()
    sig = drift.where(to_end.between(1, 5), 0.0)
    z = sig / sig.rolling(500, min_periods=100).std()
    pos = -z.clip(-3, 3)
    pnl = pos.shift(1) * (r.SPY - r.IEF) - pos.diff().abs() * cost
    return pnl.rename("rebalancing")
