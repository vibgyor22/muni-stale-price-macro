"""Sleeve G: weather-stripped natural gas storage.

Weekly gas storage changes are ~80% weather. A point-in-time regression on regional
heating/cooling degree days (EIA's five storage regions), wind-belt wind speed (wind
displaces gas burn) and wellhead freeze-offs removes the weather part. The 13-week
sum of what is left is a structural tightness signal the market under-reacts to.
"""
import numpy as np
import pandas as pd

from . import config as C
from .data import fut_hybrid, weekly_vol_normalised

REGIONS = {
    "east": ["USW00094728", "USW00014739", "USW00013739", "USW00013743", "USW00094823",
             "USW00013874", "USW00013881", "USW00012839", "USW00014821"],
    "midwest": ["USW00094846", "USW00094847", "USW00014922", "USW00014933", "USW00093819",
                "USW00013994", "USW00014837", "USW00013897", "USW00093817"],
    "mountain": ["USW00003017", "USW00024127", "USW00023183", "USW00024011", "USW00014942"],
    "pacific": ["USW00023174", "USW00023234", "USW00024233", "USW00024229"],
    "southcentral": ["USW00012960", "USW00003927", "USW00013967", "USW00013957", "USW00012916",
                     "USW00013985", "USW00023047", "USW00023042", "USW00023023", "USW00013962"],
}
WIND = ["USW00023047", "USW00023042", "USW00013967", "USW00013985", "USW00023023", "USW00014933", "USW00013962"]
PROD = ["USW00094823", "USW00023023", "USW00013957"]
ALL_STATIONS = sorted({s for v in REGIONS.values() for s in v} | set(WIND) | set(PROD))
_COLS = ["ID", "DATE", "ELEMENT", "DATA_VALUE", "M_FLAG", "Q_FLAG", "S_FLAG", "OBS_TIME"]


def stations():
    cache = C.PROC / "ghcn_daily.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    out = []
    for s in ALL_STATIONS:
        d = pd.read_csv(C.RAW / "ghcn" / f"{s}.csv.gz", header=None, names=_COLS, dtype=str)
        d = d[d.ELEMENT.isin(["TMAX", "TMIN", "AWND"]) & d.Q_FLAG.isna() & (d.DATE >= "19950101")]
        d["v"] = d.DATA_VALUE.astype(float) / 10.0
        p = d.pivot_table(index="DATE", columns="ELEMENT", values="v", aggfunc="first")
        p["ID"] = s
        out.append(p.reset_index())
    g = pd.concat(out, ignore_index=True)
    g["DATE"] = pd.to_datetime(g.DATE)
    g.to_parquet(cache)
    return g


def weekly_table():
    g = stations()
    w = lambda col: g.pivot_table(index="DATE", columns="ID", values=col)
    T = ((w("TMAX") + w("TMIN")) / 2) * 9 / 5 + 32
    feat = {}
    for reg, st in REGIONS.items():
        t = T[st].mean(axis=1)
        feat[f"{reg}_hdd"], feat[f"{reg}_cdd"] = (65 - t).clip(lower=0), (t - 65).clip(lower=0)
    feat["freeze"] = (25 - (w("TMIN")[PROD] * 9 / 5 + 32)).clip(lower=0).mean(axis=1)
    D = pd.DataFrame(feat)
    wk = D.resample("W-FRI").sum(min_count=6)
    wk["wind"] = w("AWND")[WIND].mean(axis=1).resample("W-FRI").mean()
    s = pd.read_excel(C.RAW / "ng_storage.xls", sheet_name="Data 1", header=2).iloc[:, :2]
    s.columns = ["d", "bcf"]
    df = wk.join(s.set_index("d").bcf.diff().rename("ds"), how="inner").dropna(subset=["ds"])
    woy = df.index.isocalendar().week.values
    for c in [c for c in df.columns]:
        df[c + "_a"] = df[c] - df.groupby(woy)[c].transform(lambda x: x.shift(1).expanding(3).mean())
    return df.dropna()


def structural_residual(min_weeks=104):
    df = weekly_table()
    F = [c for c in df.columns if c.endswith("_a") and c != "ds_a"]
    X = np.column_stack([np.ones(len(df)), df[F].values])
    y = df["ds_a"].values
    pred = np.full(len(df), np.nan)
    for i in range(min_weeks, len(df)):
        b = np.linalg.lstsq(X[:i], y[:i], rcond=None)[0]       # refit every week on past weeks only
        pred[i] = X[i] @ b
    df["weather_part"] = pred
    df["structural"] = df["ds_a"] - pred
    ok = ~np.isnan(pred)
    r2 = 1 - np.sum((y[ok] - pred[ok]) ** 2) / np.sum((y[ok] - y[ok].mean()) ** 2)
    return df, r2


def ng_weather():
    df, r2 = structural_residual()
    st = df.structural.rolling(13).sum()
    z = (st / st.rolling(104, min_periods=52).std().shift(1)).shift(1)   # released the Thursday after week end
    sig = -(z / 1.5).clip(-1, 1)
    nxt, wv = weekly_vol_normalised(fut_hybrid()[["NG=F"]].loc["2000":])
    s = sig.reindex(nxt.index)
    pnl = s * nxt["NG=F"] - s.diff().abs() * C.FUT_COST / (wv["NG=F"] * np.sqrt(5))
    return pnl.rename("ng_weather"), r2
