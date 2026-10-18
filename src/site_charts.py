"""Dark-theme chart for the project website (python -m src.site_charts)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import pandas as pd

from . import config as C
from . import report as RP

BG, TEXT, MUTED, LINE, ACCENT, SAGE, RED = "#0c0c0b", "#e8e4dc", "#9a968e", "#2a2926", "#b8a88a", "#8a9a82", "#c27a6b"


def main():
    w = pd.read_csv(C.RESULTS / "weekly_returns.csv", index_col=0, parse_dates=True)
    m = RP.vol_target(w["muni"].dropna())
    eq_m = (1 + m).cumprod()
    dd = eq_m / eq_m.cummax() - 1

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.color": TEXT,
                         "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED})
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5.6), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor(BG)
    for ax in (a1, a2):
        ax.set_facecolor(BG)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(LINE)
        ax.grid(axis="y", color=LINE, lw=0.6)
    a1.axvspan(pd.Timestamp(C.TEST[0]), eq_m.index[-1], color="#141413", lw=0, zorder=0)
    a1.plot(eq_m, color=ACCENT, lw=2.2, label="Muni lag strategy, net of costs")
    a1.set_yscale("log")
    a1.set_ylabel("Growth of $1 (log scale)")
    a1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    a1.text(pd.Timestamp(C.TEST[0]), eq_m.max() * 0.9, "  out of sample", color=MUTED, fontsize=9, va="top")
    a1.legend(frameon=False, loc="upper left", labelcolor=TEXT)
    a2.fill_between(dd.index, dd * 100, 0, color=RED, alpha=0.55, lw=0)
    a2.set_ylabel("Drawdown %")
    fig.tight_layout()
    out = C.ROOT / "site" / "img"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "muni_equity_dark.png", dpi=160, facecolor=BG)
    plt.close(fig)


if __name__ == "__main__":
    main()
