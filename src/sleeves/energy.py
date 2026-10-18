"""Energy sleeves built on the physical storage cycle.

E1  Seasonal storage premia in calendar spreads (EIA NYMEX contracts 1-4, 1994-2024)
    Storage builds and draws on a calendar (heating season, driving season, refinery
    maintenance). Hedgers' demand for front vs deferred contracts follows that calendar,
    so spread returns carry a seasonal risk premium. Estimated with a past-only
    seasonal t-statistic (same week +/-2 weeks in all prior years, >= 8 years).
    Days within 2 sessions of an expiry are excluded so contract-switch noise cannot
    masquerade as seasonality.

E2  Crude inventory under-reaction
    The weekly EIA crude build, measured against the same week in the prior 5 years,
    is summed over 4 weeks. Markets react on Wednesday but keep drifting for weeks:
    sustained surprise builds are bearish for the whole petroleum complex.
"""
import numpy as np
import pandas as pd

from .. import config as C
from ..data import eia_curves, eia_weekly, fut_hybrid, weekly_vol_normalised


def _seasonal_t(x, bw=2, min_years=8):
    woy = np.minimum(x.index.isocalendar().week.values.astype(int), 52)
    vals, out = x.values, np.full(len(x), np.nan)
    for i in range(len(x)):
        nb = [(int(woy[i]) + d - 1) % 52 + 1 for d in range(-bw, bw + 1)]
        past = vals[: i - 1][np.isin(woy[: i - 1], nb)]       # i-1: the latest fully realised week
        past = past[~np.isnan(past)]
        if len(past) >= min_years * (2 * bw + 1):
            out[i] = past.mean() / (past.std() / np.sqrt(len(past)))
    return pd.Series(out, index=x.index)


def spread_returns(mask_rolls=True):
    curves = eia_curves()
    cols = {}
    for k in C.ENERGY:
        r, roll = curves[k]["ret"], curves[k]["roll"]
        near = roll.copy()
        for s in (-2, -1, 1, 2):
            near |= roll.shift(s, fill_value=False)
        for a, b in [(1, 2), (2, 3), (3, 4)]:
            s = r[a] - r[b]                                     # long nearer, short further contract
            cols[f"{k}_s{a}{b}"] = s.mask(near, 0.0) if mask_rolls else s
    return pd.DataFrame(cols).loc["1990":]


def seasonal_spreads():
    S = spread_returns()
    nxt, wv = weekly_vol_normalised(S)
    pnl = {}
    for c in S.columns:
        t = _seasonal_t(nxt[c])
        pos = (t / 2).clip(-1, 1).ewm(halflife=2).mean()
        k = c.split("_")[0]
        tc = pos.diff().abs() * C.TICK[k] / (wv[c] * np.sqrt(5))      # one tick per spread trade, in vol units
        pnl[c] = pos * nxt[c] - tc
    P = pd.DataFrame(pnl)
    return P.mean(axis=1).rename("energy_seasonal"), P


def crude_inventory():
    x = eia_weekly("eia_WCESTUS1").diff().resample("W-FRI").last()
    woy = x.index.isocalendar().week.values
    normal = x.groupby(woy).transform(lambda v: v.shift(1).rolling(5, min_periods=3).mean())
    a = x - normal
    z = (a / a.rolling(156, min_periods=52).std().shift(1)).shift(1)   # week ending Fri t-1 is public by Fri t
    sig = -(z.rolling(4).sum() / 2 / 1.5).clip(-1, 1)
    R = fut_hybrid()[["CL=F", "BZ=F", "HO=F", "RB=F"]].loc["2000":]
    nxt, wv = weekly_vol_normalised(R)
    s = sig.reindex(nxt.index)
    gross = nxt.mul(s, axis=0).mean(axis=1)
    tc = s.diff().abs() * C.FUT_COST / (wv.mean(axis=1) * np.sqrt(5))
    return (gross - tc).rename("crude_inventory")
