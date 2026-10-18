"""Tearsheet-style metrics and charts (in the spirit of QuantStats / pyfolio, no extra dependency)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config as C

INK, MUTED, GRID = "#1f2937", "#6b7280", "#e5e7eb"
BLUE, ORANGE, GREEN, RED, PURPLE = "#2563eb", "#f59e0b", "#059669", "#dc2626", "#7c3aed"
plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.titlecolor": INK})


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=GRID, lw=0.6)


def vol_target(x, freq=52, target=C.VOL_TARGET, window=52):
    """Ex-ante volatility targeting: scale by trailing realised vol (no look-ahead)."""
    lev = target / np.sqrt(freq) / x.rolling(window, min_periods=26).std().shift(1)
    return (x * lev.clip(upper=5)).dropna()


def metrics(r, freq=52):
    """r: periodic simple returns at the target vol."""
    r = r.dropna()
    yrs = len(r) / freq
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    vol = r.std() * np.sqrt(freq)
    sharpe = r.mean() / r.std() * np.sqrt(freq)
    down = r[r < 0].std() * np.sqrt(freq)
    monthly = (1 + r).resample("ME").prod() - 1
    return {
        "CAGR": cagr, "Volatility": vol, "Sharpe": sharpe,
        "Sortino": r.mean() * freq / down, "Max drawdown": dd.min(),
        "Calmar": cagr / abs(dd.min()), "t-stat (Sharpe)": sharpe * np.sqrt(yrs),
        "% positive months": (monthly > 0).mean(), "Best month": monthly.max(),
        "Worst month": monthly.min(), "Skew (weekly)": r.skew(), "Years": yrs,
    }


def metrics_table(r, splits, freq=52):
    cols = {lab: metrics(r.loc[a:b], freq) for lab, a, b in splits}
    cols["Full sample"] = metrics(r, freq)
    df = pd.DataFrame(cols)
    pct = ["CAGR", "Volatility", "Max drawdown", "% positive months", "Best month", "Worst month"]
    out = df.copy().astype(object)
    for i in df.index:
        for c in df.columns:
            v = df.loc[i, c]
            out.loc[i, c] = f"{v:.1%}" if i in pct else (f"{v:.1f}" if i == "Years" else f"{v:.2f}")
    return out


def tearsheet(r, sleeves, path, title, test_start):
    """Equity curve (log), underwater curve and rolling 1-year Sharpe."""
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    roll = r.rolling(52).mean() / r.rolling(52).std() * np.sqrt(52)
    fig, axs = plt.subplots(3, 1, figsize=(10.5, 8.2), sharex=True, gridspec_kw={"height_ratios": [3, 1.1, 1.3]})
    ax = axs[0]
    for k, (s, col) in sleeves.items():
        e = (1 + s).cumprod()
        ax.plot(e, color=col, lw=0.9, alpha=0.75, label=k)
    ax.plot(eq, color=INK, lw=2.2, label="Book")
    ax.set_yscale("log")
    ax.set_ylabel("growth of $1 (log), 10% vol target")
    ax.axvspan(pd.Timestamp(test_start), eq.index[-1], color="#f3f4f6", lw=0, zorder=0)
    ax.text(pd.Timestamp(test_start), ax.get_ylim()[0] * 1.15, "  out-of-sample period", color=MUTED)
    ax.legend(frameon=False, ncol=2, fontsize=8.5, loc="upper left")
    ax.set_title(title, loc="left", fontsize=11.5, fontweight="bold")
    _style(ax)
    axs[1].fill_between(dd.index, dd * 100, 0, color=RED, alpha=0.35, lw=0)
    axs[1].set_ylabel("drawdown %")
    _style(axs[1])
    axs[2].plot(roll, color=BLUE, lw=1.2)
    axs[2].axhline(0, color=MUTED, lw=0.6)
    axs[2].axhline(roll.mean(), color=BLUE, lw=0.8, ls="--")
    axs[2].text(roll.index[-1], roll.mean() + 0.15, f"average {roll.mean():.1f}", color=BLUE, fontsize=8.5, ha="right")
    axs[2].set_ylabel("rolling 1y Sharpe")
    _style(axs[2])
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def monthly_heatmap(r, path, title):
    m = (1 + r).resample("ME").prod() - 1
    t = pd.DataFrame({"y": m.index.year, "m": m.index.month, "v": m.values}).pivot(index="y", columns="m", values="v")
    yr = (1 + r).groupby(r.index.year).prod() - 1
    fig, ax = plt.subplots(figsize=(10.5, 0.36 * len(t) + 1.2))
    lim = np.nanpercentile(np.abs(t.values), 95)
    ax.imshow(t.values, cmap="RdYlGn", vmin=-lim, vmax=lim, aspect="auto")
    for i in range(t.shape[0]):
        for j in range(t.shape[1]):
            v = t.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v*100:.1f}", ha="center", va="center", fontsize=7.5, color=INK)
        ax.text(12.2, i, f"{yr.loc[t.index[i]]*100:+.1f}%", va="center", fontsize=8, color=INK, fontweight="bold")
    ax.set_xticks(range(12), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    ax.set_yticks(range(len(t)), t.index)
    ax.text(12.2, -0.9, "Year", fontsize=8.5, color=MUTED)
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xlim(-0.5, 13.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def robustness_bars(table, path):
    t = table[["sharpe train 2008-17", "sharpe test 2018-26"]].dropna()
    fig, ax = plt.subplots(figsize=(10.5, 0.32 * len(t) + 1.2))
    y = np.arange(len(t))
    ax.barh(y - 0.2, t.iloc[:, 0], height=0.38, color="#93c5fd", label="2008-17 (design)")
    ax.barh(y + 0.2, t.iloc[:, 1], height=0.38, color=BLUE, label="2018-26 (out-of-sample)")
    ax.set_yticks(y, t.index)
    ax.invert_yaxis()
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.set_xlabel("Sharpe ratio (daily, net of costs)")
    ax.set_title("Slow munis: robustness checks (the placebo should be ~0)", loc="left", fontsize=11, fontweight="bold")
    ax.legend(frameon=True, facecolor="white", edgecolor=GRID, loc="lower left", bbox_to_anchor=(0.62, 0.22))
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="x", color=GRID, lw=0.6)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def corr_heatmap(Z, path):
    c = Z.corr()
    fig, ax = plt.subplots(figsize=(5.6, 4.6))
    ax.imshow(c.values, cmap="RdBu_r", vmin=-1, vmax=1)
    for i in range(len(c)):
        for j in range(len(c)):
            ax.text(j, i, f"{c.values[i, j]:.2f}", ha="center", va="center", fontsize=8.5, color=INK)
    lab = [x.replace("_", "\n") for x in c.columns]
    ax.set_xticks(range(len(c)), lab, fontsize=8)
    ax.set_yticks(range(len(c)), lab, fontsize=8)
    ax.set_title("Sleeve correlations (weekly)", loc="left", fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
