"""Statistical evidence for the muni lag strategy (python -m src.stats_pack).

Writes results/stats_pack.json with:
  1. Distributed-lag (Dimson) regressions of muni ETF returns on current and lagged IEF returns
  2. Predictive regressions of next-day hedged muni returns on the catch-up signal,
     including a true out-of-sample R2 (coefficients fitted on 2008-17, applied to 2018-26)
  3. Trading diagnostics: hit rates, win/loss, turnover, holding period, cost drag
  4. Factor regression of strategy returns on Treasury, equity, muni, IG and HY credit
  5. Sharpe inference: standard error, bootstrap interval, probabilistic and deflated Sharpe
  6. Performance by Treasury-volatility regime
All standard errors are Newey-West (HAC).
"""
import json

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as st

from . import config as C
from .data import etf_returns
from . import muni

HAC = dict(cov_type="HAC", cov_kwds={"maxlags": 5})


def factors():
    p = C.RAW / "factor_ohlc.parquet"
    if not p.exists():
        from .fetch import yahoo
        yahoo()
    c = pd.read_parquet(p)["Close"]
    return np.log(c).diff()


def dimson(etf, lags=5):
    cc, _, _ = etf_returns()
    x = cc[[etf, "IEF"]].dropna()
    X = pd.concat({f"lag{k}": x.IEF.shift(k) for k in range(lags + 1)}, axis=1)
    d = pd.concat([x[etf].rename("y"), X], axis=1).dropna()
    m = sm.OLS(d.y, sm.add_constant(d.drop(columns="y"))).fit(**HAC)
    b = m.params.drop("const")
    lagsum = b.drop("lag0").sum()
    wald = m.wald_test(" + ".join(f"lag{k}" for k in range(1, lags + 1)) + " = 0", scalar=True)
    return dict(
        coef={k: float(v) for k, v in b.items()}, t={k: float(m.tvalues[k]) for k in b.index},
        r2=float(m.rsquared), n=int(m.nobs), total_beta=float(b.sum()),
        share_same_day=float(b["lag0"] / b.sum()), lagged_sum=float(lagsum),
        lagged_sum_p=float(wald.pvalue), lagged_sum_F=float(wald.statistic),
    )


def predictive(etf):
    d = muni.run_one(etf)
    cc, _, _ = etf_returns()
    x = cc[[etf, "IEF"]].dropna()
    res = (x[etf] - d.beta * x.IEF).reindex(d.index)
    y = (res / d.vol).shift(-1)                                  # next-day hedged return, vol units
    out = {}
    for name, sig in {"catch_up": d.catch_up, "composite": d.catch_up + 0.3 * d.risk + 0.5 * d.calendar + 0.5 * d.flow}.items():
        df = pd.concat([sig.rename("s"), y.rename("y")], axis=1).dropna()
        row = {}
        for lab, a, b in [("2008-17", *C.TRAIN), ("2018-26", *C.TEST), ("2008-26", "2007", "2027")]:
            s = df.loc[a:b]
            m = sm.OLS(s.y, sm.add_constant(s.s)).fit(**HAC)
            row[lab] = dict(beta=float(m.params.s), t=float(m.tvalues.s), r2=float(m.rsquared),
                            ic=float(s.s.corr(s.y, method="spearman")), n=int(m.nobs),
                            hit=float((np.sign(s.s) == np.sign(s.y))[s.s != 0].mean()))
        tr, te = df.loc[C.TRAIN[0]:C.TRAIN[1]], df.loc[C.TEST[0]:C.TEST[1]]
        m = sm.OLS(tr.y, sm.add_constant(tr.s)).fit()
        pred = m.params.const + m.params.s * te.s
        row["oos_r2"] = float(1 - ((te.y - pred) ** 2).sum() / ((te.y - tr.y.mean()) ** 2).sum())
        out[name] = row
    return out


def diagnostics(etf):
    d = muni.run_one(etf)
    pos = d.pos.shift(1)
    cost = (d.pos.shift(1) - d.pos.shift(2)).abs() * (C.MUNI_COST + d.beta.abs() * C.HEDGE_COST)
    gross = (d.pnl_raw + cost) / d.vol                             # risk units, as in the backtest
    net = d.pnl
    active = pos.abs() > 0
    changes = (d.pos.diff().abs() > 0).sum() / (len(d) / 252)
    w = net.resample("W-FRI").sum()
    return dict(
        sharpe_gross=float(gross.mean() / gross.std() * np.sqrt(252)),
        sharpe_net=float(net.mean() / net.std() * np.sqrt(252)),
        cost_share_of_gross=float(1 - net.sum() / gross.sum()),
        time_in_market=float(active.mean()),
        long_share=float((pos > 0).mean()), short_share=float((pos < 0).mean()),
        trades_per_year=float(changes),
        avg_holding_days=float(len(d) / max((d.pos.diff().abs() > 0).sum(), 1)),
        daily_hit=float((net[active] > 0).mean()), weekly_hit=float((w[w != 0] > 0).mean()),
        win_loss_ratio=float(net[net > 0].mean() / -net[net < 0].mean()),
        turnover_units_per_year=float(d.pos.diff().abs().sum() / (len(d) / 252)),
    )


def factor_regression():
    m = muni.run()                                                   # daily, risk units
    cc, _, _ = etf_returns()
    F = pd.concat([cc[["IEF", "SPY", "MUB"]], factors()[["HYG", "LQD"]]], axis=1)
    d = pd.concat([m.rename("y"), F], axis=1).dropna()
    mod = sm.OLS(d.y, sm.add_constant(d.drop(columns="y"))).fit(**HAC)
    return dict(alpha_t=float(mod.tvalues.const), r2=float(mod.rsquared),
                betas={k: float(v) for k, v in mod.params.drop("const").items()},
                t={k: float(v) for k, v in mod.tvalues.drop("const").items()},
                alpha_share_of_mean=float(mod.params.const / d.y.mean()))


def sharpe_inference(n_trials=32, n_boot=2000, block=20, seed=0):
    r = muni.run().dropna()
    T = len(r)
    sr = r.mean() / r.std()
    g3, g4 = st.skew(r), st.kurtosis(r, fisher=False)
    se = np.sqrt((1 - g3 * sr + (g4 - 1) / 4 * sr ** 2) / (T - 1))          # Mertens (2002)
    psr = st.norm.cdf(sr / se)
    # deflated Sharpe: expected max of N trial Sharpes under the null (Bailey & Lopez de Prado 2014)
    grid = pd.read_csv(C.RESULTS / "muni_spec_grid.csv")
    var_trials = (grid[["train", "test"]].mean(axis=1) / np.sqrt(252)).var()
    emc = 0.5772156649
    sr0 = np.sqrt(var_trials) * ((1 - emc) * st.norm.ppf(1 - 1 / n_trials) + emc * st.norm.ppf(1 - 1 / (n_trials * np.e)))
    dsr = st.norm.cdf((sr - sr0) / se)
    rng = np.random.default_rng(seed)
    vals = r.values
    boots = []
    for _ in range(n_boot):                                        # moving-block bootstrap
        idx = np.concatenate([np.arange(s, s + block) for s in rng.integers(0, T - block, T // block + 1)])[:T]
        x = vals[idx]
        boots.append(x.mean() / x.std() * np.sqrt(252))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return dict(sharpe=float(sr * np.sqrt(252)), se_annual=float(se * np.sqrt(252)),
                t_stat=float(sr / se), psr_vs_zero=float(psr), deflated_sharpe_prob=float(dsr),
                sr0_annual=float(sr0 * np.sqrt(252)), boot_ci=[float(lo), float(hi)],
                skew=float(g3), kurtosis=float(g4), n_days=int(T), n_trials=n_trials)


def regimes():
    m = muni.run()
    cc, _, _ = etf_returns()
    vol = cc.IEF.rolling(60).std().shift(1).reindex(m.index)
    q = pd.qcut(vol, 3, labels=["low", "mid", "high"])
    out = {}
    for lab in ["low", "mid", "high"]:
        x = m[q == lab].dropna()
        out[lab] = dict(sharpe=float(x.mean() / x.std() * np.sqrt(252)), share_of_pnl=float(x.sum() / m.sum()),
                        ief_vol_bp=float(vol[q == lab].mean() * 1e4))
    return out


def main():
    pack = {
        "dimson": {e: dimson(e) for e in C.MUNI_ETFS},
        "predictive": {e: predictive(e) for e in C.MUNI_ETFS},
        "diagnostics": {e: diagnostics(e) for e in C.MUNI_ETFS},
        "factor_regression": factor_regression(),
        "sharpe_inference": sharpe_inference(),
        "regimes": regimes(),
    }
    (C.RESULTS / "stats_pack.json").write_text(json.dumps(pack, indent=2))
    print(json.dumps(pack, indent=1))


if __name__ == "__main__":
    main()
