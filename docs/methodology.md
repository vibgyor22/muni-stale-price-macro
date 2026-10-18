# Methodology notes

## Timing and look-ahead control
- Signals are computed at the close of day t and positions are traded at the open of day t+1. P&L is split into the overnight segment (close to open, old position) and the session segment (open to close, new position).
- Volatility scalings, hedge betas and z-scores all use trailing windows shifted by one day.
- The Treasury hedge ratio is the rolling 250-day beta of each muni ETF to IEF, known at the time of the trade.

## Transaction costs
- Muni ETFs: 1bp per side (MUB quoted spread is about 0.9bp, VTEB about 2bp).
- IEF hedge: 0.5bp per side, times the absolute hedge ratio.
- Results are also reported at 2x and 3x costs.

## Specification choice
- The specification was selected on 2008-2017 data only from a 32-variant grid (`python -m src.select_spec`): equity weight {0, 0.3}, flow weight {0, 0.5}, calendar weight {0, 0.5}, half-life {1, 2, 3, 5}. 2018-2026 is reported as out of sample.

## Reported returns
- Daily P&L is in risk units (position times hedged return over trailing volatility). Weekly sums are scaled to a 10% annualised volatility target using trailing one-year realised volatility, so the scaling is ex ante.

## Statistics (`src/stats_pack.py`)
- Distributed-lag (Dimson) regressions of muni ETF returns on IEF returns at lags 0-5, Newey-West standard errors with 5 lags, Wald test that lags 1-5 sum to zero.
- Predictive regressions of next-day hedged muni returns on the signal, by period, with Spearman IC and hit rate. Out-of-sample R² follows Campbell and Thompson (2008): coefficients fitted on 2008-17, benchmark is the 2008-17 mean.
- Sharpe ratio standard error from Mertens (2002), allowing for skew and kurtosis. Moving-block bootstrap with 20-day blocks. Deflated Sharpe ratio from Bailey and López de Prado (2014), using the dispersion of the 32 grid Sharpe ratios.
- Factor regression of daily strategy returns on IEF, SPY, MUB, LQD and HYG returns.
- Regime split by terciles of trailing 60-day IEF volatility.
