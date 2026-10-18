"""Turn raw GHCN station files into economically meaningful weather variables.

Everything is in physical units a gas or grain trader would recognise:
heating/cooling degree days (deg F), wind speed (m/s), freeze-off degree days,
and agronomic 'extreme degree days' above 29C (Schlenker & Roberts 2009).
"""
import numpy as np
import pandas as pd

from . import config as C

_COLS = ["ID", "DATE", "ELEMENT", "DATA_VALUE", "M_FLAG", "Q_FLAG", "S_FLAG", "OBS_TIME"]


def stations(start="1995-01-01"):
    """Daily table: DATE x ID with TMAX/TMIN (deg C), PRCP (mm), AWND (m/s). Cached."""
    cache = C.PROC / "ghcn_daily.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    out = []
    for s in C.ALL_STATIONS:
        d = pd.read_csv(C.RAW / "ghcn" / f"{s}.csv.gz", header=None, names=_COLS, dtype=str)
        d = d[d.ELEMENT.isin(["TMAX", "TMIN", "PRCP", "AWND"]) & d.Q_FLAG.isna()]
        d = d[d.DATE >= start.replace("-", "")]
        d["v"] = d.DATA_VALUE.astype(float) / 10.0          # GHCN stores tenths
        p = d.pivot_table(index="DATE", columns="ELEMENT", values="v", aggfunc="first")
        p["ID"] = s
        out.append(p.reset_index())
    g = pd.concat(out, ignore_index=True)
    g["DATE"] = pd.to_datetime(g.DATE)
    g.to_parquet(cache)
    return g


def _wide(g, col):
    return g.pivot_table(index="DATE", columns="ID", values=col)


def tavg_f(g):
    return ((_wide(g, "TMAX") + _wide(g, "TMIN")) / 2) * 9 / 5 + 32


def gas_weather_daily(g=None):
    """Regional HDD/CDD (EIA storage regions), wind-belt wind speed, basin freeze-offs."""
    g = stations() if g is None else g
    T = tavg_f(g)
    out = {}
    for reg, st in C.GAS_REGIONS.items():
        t = T[st].mean(axis=1)
        out[f"{reg}_hdd"] = (65 - t).clip(lower=0)
        out[f"{reg}_cdd"] = (t - 65).clip(lower=0)
    out["wind"] = _wide(g, "AWND")[C.WIND_STATIONS].mean(axis=1)
    tmin_f = _wide(g, "TMIN")[C.PROD_STATIONS] * 9 / 5 + 32
    out["freeze"] = (25 - tmin_f).clip(lower=0).mean(axis=1)     # deg F below 25F at wellheads
    return pd.DataFrame(out)


def degree_days(tmax, tmin, base):
    """Degree days above `base` assuming a sine-shaped daily temperature cycle."""
    h = np.sin(np.linspace(0, 2 * np.pi, 48, endpoint=False))[:, None]
    tmax, tmin = np.asarray(tmax, float), np.asarray(tmin, float)
    T = (tmax + tmin) / 2 + (tmax - tmin) / 2 * h
    return np.clip(T - base, 0, None).mean(axis=0)


def corn_belt_daily(g=None):
    """Production-weighted Corn Belt EDD (>29C), GDD (10-29C) and precipitation."""
    g = stations() if g is None else g
    tx, tn, pr = _wide(g, "TMAX"), _wide(g, "TMIN"), _wide(g, "PRCP")
    w = pd.Series(C.CORN_STATIONS, dtype=float)
    res = {}
    for name, fn in {
        "edd": lambda s: degree_days(tx[s], tn[s], 29),
        "gdd": lambda s: degree_days(tx[s], tn[s], 10) - degree_days(tx[s], tn[s], 29),
        "prcp": lambda s: pr[s].values,
    }.items():
        m = pd.DataFrame({s: fn(s) for s in w.index}, index=tx.index)
        res[name] = (m * w).sum(axis=1, min_count=6) / (m.notna() * w).sum(axis=1)
    return pd.DataFrame(res)


def seasonal_anomaly(x, ref_end):
    """x minus its day-of-year climatology estimated only on data up to `ref_end`."""
    h = x[x.index <= ref_end]
    clim = h.groupby(h.index.dayofyear).mean()
    clim = pd.concat([clim.iloc[-15:], clim, clim.iloc[:15]]).rolling(31, center=True).mean().iloc[15:-15]
    return x - clim.reindex(x.index.dayofyear).values
