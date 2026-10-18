"""Paths, universe, cost assumptions and sample splits. Everything tunable lives here."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
for p in (RAW, PROC, RESULTS):
    p.mkdir(parents=True, exist_ok=True)

# Design choices were made looking at TRAIN only; TEST is reported as out-of-sample.
TRAIN = ("2008-01-01", "2017-12-31")
TEST = ("2018-01-01", "2026-12-31")

MUNI_ETFS = ["MUB", "VTEB"]                 # the two liquid national muni ETFs (> $250m/day)
MUNI_DRIVERS = {"rates": "IEF", "risk": "SPY"}
ETF_TICKERS = ["MUB", "VTEB", "IEF", "SPY"]
MUNI_COST = 1e-4                            # one-way, per $ traded (MUB quoted spread ~0.9bp, VTEB ~2bp)
HEDGE_COST = 0.5e-4                         # IEF, one-way
MUNI_PARAMS = dict(
    halflife=1,          # days: chosen on 2008-17 only (see results/muni_spec_grid.csv)
    w_rates=1.0,         # weight on recent Treasury moves (catch-up)
    w_risk=0.3,          # weight on recent equity moves (credit/risk catch-up)
    w_calendar=0.5,      # long in the first 5 business days of a month (coupon/redemption reinvestment)
    w_flow=0.5,          # 60-day momentum of the hedged muni residual (persistent fund flows)
    band=0.75,           # no-trade band, in position units
    cap=2.5,
)
VOL_TARGET = 0.10                           # annualised, for reported returns
