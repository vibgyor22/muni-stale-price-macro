"""The muni lag strategy.

Economics
    Municipal bonds trade rarely, are held by tax-motivated retail investors, and are
    marked by pricing vendors ("evaluated pricing") rather than by continuous trading.
    Muni ETF market makers anchor to those marks. So when Treasuries move, muni ETFs
    price in roughly 60-70% of the move that day and the rest over the next two to
    four days. The same slowness makes muni fund flows persistent (outflows beget
    outflows) and makes the start-of-month reinvestment of coupons and redemptions
    a predictable demand shock.

Signal (all inputs known at the close of day t; traded at the open of day t+1)
    catch-up   EWMA (half-life 1d) of IEF returns in vol units -> long munis after Treasury rallies
    risk       same for SPY, smaller weight (credit/risk sentiment also reaches munis late)
    calendar   +0.5 on the first five business days of each month
    flow       60-day momentum of the hedged muni residual
Position is on the muni ETF hedged with IEF at its rolling 1-year beta, so the
Treasury direction itself is not the bet. A no-trade band cuts turnover.
"""
import numpy as np
import pandas as pd

from . import config as C
from .data import etf_returns


def _band(target, width):
    out, cur = np.zeros(len(target)), 0.0
    for i, t in enumerate(target.values):
        if not np.isnan(t) and abs(t - cur) > width:
            cur = t
        out[i] = cur
    return pd.Series(out, index=target.index)


def _z_ewma(r, hl):
    z = r / r.rolling(60, min_periods=20).std().shift(1)
    return z.ewm(halflife=hl).mean() * np.sqrt(hl)


def run_one(etf, cost_mult=1.0, params=None, components=None, driver_shift=0):
    p = dict(C.MUNI_PARAMS, **(params or {}))
    cc, oc, co = etf_returns()
    rates, risk = C.MUNI_DRIVERS["rates"], C.MUNI_DRIVERS["risk"]
    x = cc[[etf, rates, risk]].dropna()
    idx = x.index
    beta = (x[etf].rolling(250, min_periods=60).cov(x[rates]) / x[rates].rolling(250, min_periods=60).var()).shift(1)
    res_cc = x[etf] - beta * x[rates]                                     # hedged muni return, close-close
    res_oc = oc[etf].reindex(idx) - beta * oc[rates].reindex(idx)        # open-close part
    res_co = res_cc - res_oc                                              # overnight part
    vol = res_cc.rolling(60, min_periods=20).std().shift(1)

    bd = pd.Series(1, index=idx).groupby([idx.year, idx.month]).cumsum()
    nxt_bd = bd.shift(-1)                                                 # the calendar is known in advance
    parts = {
        "catch_up": _z_ewma(x[rates].shift(driver_shift), p["halflife"]),   # driver_shift>0: placebo
        "risk": _z_ewma(x[risk].shift(driver_shift), p["halflife"]),
        "calendar": ((nxt_bd >= 1) & (nxt_bd <= 5)).astype(float),
        "flow": res_cc.rolling(60).sum() / vol / np.sqrt(60),
    }
    w = {"catch_up": p["w_rates"], "risk": p["w_risk"], "calendar": p["w_calendar"], "flow": p["w_flow"]}
    if components is not None:
        w = {k: (v if k in components else 0.0) for k, v in w.items()}
    target = sum(w[k] * parts[k] for k in parts).clip(-p["cap"], p["cap"])
    pos = _band(target, p["band"])

    new, old = pos.shift(1), pos.shift(2)          # decided at close t, traded at open t+1
    cost = (C.MUNI_COST + beta.abs() * C.HEDGE_COST) * cost_mult
    pnl = old * res_co + new * res_oc - (new - old).abs() * cost
    return pd.DataFrame({"pnl": pnl / vol, "pnl_raw": pnl, "pos": pos, "beta": beta, "vol": vol, **parts})


def run(cost_mult=1.0, params=None, components=None, driver_shift=0):
    """Daily P&L in risk units, equal-weighted across the muni ETFs."""
    legs = {e: run_one(e, cost_mult, params, components, driver_shift)["pnl"] for e in C.MUNI_ETFS}
    return pd.DataFrame(legs).mean(axis=1).rename("muni")


def same_day_vs_total_beta():
    """Evidence of slowness: muni beta to Treasuries over 1 day vs over 10 days."""
    cc, _, _ = etf_returns()
    rows = []
    for e in C.MUNI_ETFS:
        x = cc[[e, "IEF"]].dropna()
        b1 = x[e].cov(x.IEF) / x.IEF.var()
        x10 = x.rolling(10).sum().iloc[::10].dropna()
        b10 = x10[e].cov(x10.IEF) / x10.IEF.var()
        lead = pd.concat([x.IEF, (x[e] - b1 * x.IEF).shift(-1)], axis=1).corr().iloc[0, 1]
        rows.append(dict(etf=e, beta_1d=b1, beta_10d=b10, share_priced_same_day=b1 / b10,
                         corr_ief_today_vs_muni_resid_tomorrow=lead))
    return pd.DataFrame(rows).set_index("etf")


def impulse_response(horizon=10):
    """Average cumulative hedged muni return after a +1 sd daily Treasury (IEF) move."""
    cc, _, _ = etf_returns()
    out = {}
    for e in C.MUNI_ETFS:
        x = cc[[e, "IEF"]].dropna()
        z = x.IEF / x.IEF.rolling(60, min_periods=20).std().shift(1)
        raw = {}
        for k in range(0, horizon + 1):
            y = x[e].shift(-k)
            raw[k] = (y.cov(z) / z.var()) * 1e4             # bp of muni return per 1-sd IEF move
        b = pd.Series(raw).cumsum()
        out[e] = b
    return pd.DataFrame(out)
