# Methodology notes

## Timing and look-ahead control
- Every signal uses only information public at the decision time. EIA weekly data are applied the week after the reference week; storage and inventory normals use prior years only.
- Muni sleeve: signals computed at the close of day t, positions traded at the open of day t+1. P&L is split into the overnight segment (old position) and the session segment (new position).
- All volatility scalings, hedge betas and z-scores use trailing windows shifted by one period.

## Transaction costs
- Muni ETFs: 1bp per side (MUB quoted spread is about 0.9bp, VTEB about 2bp). IEF hedge: 0.5bp per side.
- Energy futures: 3bp per side on outright positions; one tick per calendar-spread trade.
- Equity/bond rebalancing sleeve: 1bp per side.
- Results are also reported at 2x and 3x costs.

## Data cleaning
- **Continuous futures.** Yahoo's front-month series splice contracts without adjustment. Daily returns are rebuilt from the session return (open to close, always one contract) plus the overnight gap, which is dropped when it is an outlier relative to its own history (the signature of a contract switch).
- **EIA futures curves.** EIA reports NYMEX contracts 1-4 by position. Each expiry is located with the exchange calendar rule, confirmed in the data, and returns are stitched for the contract actually held. Days within two sessions of an expiry are excluded from calendar-spread P&L.
- **Weather.** NOAA GHCN-Daily airport stations, quality-flagged observations only; these are available the next morning.

## Specification choice
- The muni sleeve's specification was selected on 2008-2017 data only from a 32-variant grid (`python -m src.select_spec`); 2018-2026 is reported as out-of-sample.

## Portfolio construction
- Each sleeve's weekly return is normalised by its trailing two-year volatility. The book weights the muni sleeve at 50% of risk and the four diversifiers at 12.5% each, then targets 10% annualised volatility using trailing one-year realised volatility.
