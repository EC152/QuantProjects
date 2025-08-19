# QuantProjects

A collection of quantitative finance projects to build skills in maths, statistics, programming, and trading research.

## Projects

1. Market Data Collector, Visualiser & EDA Toolkit (Foundation)
- Goal: Build a toolkit to fetch, clean, and explore financial data.
- Topics: Market data, simple/log returns, moving averages, volatility.
- Key Skills: pandas, matplotlib, yfinance.
- Deliverables: Annotated notebook with summary stats, plots, volatility cone.
- Stretch: Auto-download universes (e.g. S&P500), Sharpe ratio, volatility cones.

2. Backtesting Engine + Technical Signal Strategies (Execution infrastructure)
- Goal: Create a simple backtesting engine.
- Topics: Order simulation, vectorised backtesting, drawdowns.
- Key Skills: Modular code design, handling transaction costs.
- Deliverables: Backtests of moving average crossovers, RSI, Bollinger Bands.
- Stretch: Position sizing (Kelly, vol targeting), modular strategy interface.

3. Time Series Analysis of Returns (Statistics basics)
- Goal: Understand dependence and volatility clustering in returns.
- Topics: ACF/PACF, Ljung-Box test, rolling volatility, clustering.
- Key Skills: statsmodels, rolling windows.
- Deliverables: Notebook with ACF plots, volatility clustering evidence.
- Stretch: Fit AR(1) and GARCH(1,1).

4. Pairs Trading & Statistical Arbitrage (Progressive)
- Merge Pairs Trading (z-score) + Cointegration/OU Process into a single progressive project.
Stage 1:
- Test for cointegration, trade on z-scores.
- Skills: ADF test, z-scores, spread visualisation.
Stage 2:
- Ornstein-Uhlenbeck calibration, Johansen test, Kalman filter hedge ratios.
- Skills: OU process, dynamic hedge ratios.
- Deliverables: Backtests of pairs trades, Sharpe, drawdowns.

5. Option Pricing: Binomial → Black-Scholes → Greeks (Derivatives core)
- Merge Extended Binomial + Black-Scholes.
Stage 1: Implement binomial trees (European + American).
Stage 2: Black-Scholes formula, Greeks, dividend adjustment.
- Key Skills: Recombining trees, PDE intuition, closed forms.
- Deliverables: Prices + Greeks plotted vs strike/time.
- Stretch: Trinomial trees, barrier options, implied vol surface visualiser.

6. Monte Carlo Simulation (Options & Portfolio Forecasting) (Simulation)
- Merge Monte Carlo projects into one progression.
Stage 1: Random walks, GBM paths, option pricing vs Black-Scholes.
Stage 2: Portfolio return distribution forecasting.
Stage 3 (Advanced): Stochastic volatility (Heston model).
- Key Skills: Euler–Maruyama, variance reduction, correlated Brownian motions.
- Stretch: Exotic options (barrier, Asian), FFT pricing (Carr-Madan).

7. Portfolio Optimisation & Risk Modeling (Core quant research)
- Merge Markowitz + VaR + Risk Models.
Stage 1: Efficient frontier, Sharpe-max portfolio.
Stage 2: Risk measures → Historical, parametric, Monte Carlo VaR.
Stage 3 (Advanced): Black-Litterman, risk parity, shrinkage covariance.
- Deliverables: Efficient frontier plot, VaR comparison table.
- Stretch: Rolling window optimisation, CVaR.

8. Algorithmic Trading Simulator & Strategy Executor (Infrastructure, advanced)
- Goal: Build an execution simulator for order flow.
- Topics: Limit vs market orders, slippage, latency, order book simulation.
- Key Skills: Tick-level simulation, logging, real-time handling.
- Deliverables: Run technical/stat-arb strategies in a simulated environment.
- Stretch: Add stop-loss, bracket orders, backtest vs live toggle.

9. Machine Learning for Factor Alpha (Prediction-focused)
- Goal: Use ML to generate predictive signals.
- Topics: Feature engineering (lags, rolling stats, factors), ranking models.
- Key Skills: XGBoost/LightGBM, SHAP, walk-forward validation.
- Deliverables: ML model predicting stock return direction / alpha factors.
- Stretch: Integrate with risk model to form a long-short portfolio.

10. Cutting Edge: Geometry & Topology in Finance (Research frontier)
- Goal: Apply geometric/topological tools to financial data.
- Topics: PCA, Isomap, MDS, persistent homology, clustering.
- Key Skills: Dimensionality reduction, topological data analysis (TDA).
- Deliverables: Detect regime shifts via geometry.
- Stretch: Compare clustering results with standard correlation-based approaches.
