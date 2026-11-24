# QuantProjects

A portfolio of quantitative finance projects covering systematic trading, derivatives, market making, stochastic modelling, empirical finance, machine learning, and portfolio optimisation.

The repository focuses on applied research and implementation in Python, C++, and R. Each project is structured as a standalone piece of quantitative finance work, with emphasis on methodology, numerical implementation, backtesting discipline, model validation, and economic interpretation.

## Projects

| Project                                               | Description                                                                                                                                                                                                                    | Main Techniques                                                                                                                                                                                     |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 01 Systematic Trading with ML Meta-Labelling           | Multi-asset systematic trading pipeline estimating when primary signals should be traded, with probability forecasts converted into volatility-targeted strategy weights across equity indices, metals, and energy instruments | Triple-Barrier Labelling, Purged K-Fold CV, Embargoing, Sample-Uniqueness Weights, Calibration, SHAP/MDI/MDA Feature Importance, HMM/GMM/PCA Features, XGBoost, Neural Models, Volatility Targeting |
| 02 Heston Option Market Making                         | Option market-making framework where optimal bid/ask quotes are dynamically selected under stochastic volatility and Greek-driven inventory risk                                                                               | Heston Variance Dynamics, Black-Scholes Proxy Greeks, Poisson Order Arrivals, Stochastic Control, Backward Dynamic Programming, Greek-Weighted Inventory Penalties, Monte Carlo Backtesting         |
| 03 Multi-Strategy Trading Engine              | Live-style trading engine combining option market making, relative-value arbitrage, basis trades, dual-listed arbitrage, execution controls, and automated hedging                                                             | Black-Scholes Valuation, Implied Volatility, Option Greeks, Inventory-Skewed Quoting, Box/Vertical/Put-Call-Parity Arbitrage, Futures/ETF Basis Trading, Delta Hedging                              |
| 04 Systematic Equity Factor Strategy                   | Equity factor strategy combining residual momentum, constrained portfolio construction, risk controls, and regime-aware allocation                                                                                             | Residual Momentum, Convex Optimisation, Dollar/Beta/Sector Neutrality, Volatility Targeting, EWMA Covariance, Factor Backtesting, HMM/XGBoost Regime Allocation                                     |
| 05 C++ Markowitz Portfolio Optimiser                   | High-performance C++ implementation of mean-variance portfolio optimisation with rolling out-of-sample testing and robust strategy extensions                                                                                  | KKT Systems, Conjugate Gradient, Dense Matrix Design, Rolling Backtests, Covariance Shrinkage, Long-Only Constraints, Transaction-Cost Sweeps, Bootstrap Inference                                  |
| 06 Local-Volatility Barrier Option PDE Pricing         | Numerical pricer for an up-and-out European call under local volatility, implemented with explicit finite differences and stability diagnostics                                                                                | Local-Volatility PDEs, Barrier Boundary Conditions, Explicit Finite Differences, Conditional Stability Analysis, Convergence Testing, Value-Profile and Surface Visualisation                       |
| 07 Macro Regime Detection and Tactical Allocation      | Macro-financial regime detection framework used to classify market states and adapt equity/bond allocation dynamically                                                                                                         | PCA, K-Means Clustering, Hierarchical Clustering, Regime Labelling, Recession Validation, Out-of-Sample Testing, Transaction Costs, Tactical Allocation                                             |
| 08 FX Strategy Combination and Currency Factor Pricing | Empirical FX project combining long-short currency strategies ex-ante and testing whether currency portfolio returns are priced by common risk factors                                                                         | Currency Strategy Weighting, Volatility Targeting, Ledoit-Wolf Covariance Shrinkage, Regime-Conditional Sharpe Weighting, Fama-MacBeth Regressions, Newey-West/Shanken Inference                    |
| 09 Yield-Curve Forecasting and Dynamic Allocation      | Empirical study of whether term-spread signals improve equity return forecasts and generate economic value in tactical asset allocation                                                                                        | Predictive Regressions, Rolling-Window Forecasting, Stationarity Diagnostics, Clark-West Tests, Mark-Kilian Bootstrap, Volatility-Targeted Allocation, Performance-Fee Analysis                     |
| 10 Financial Statistics and Short-Rate Modelling      | Statistical finance toolkit covering equity factor regressions, directional prediction, and short-rate model estimation                                                                                                        | CAPM, Asymmetric Beta Regressions, F-Tests, T-Tests, Linear Probability Models, Hit-Ratio Optimisation, CIR Estimation, Vasicek Comparison, Maximum Likelihood                                      |
| 11 Equity Portfolio and APT Analysis                  | Portfolio-analysis project evaluating equity risk-return behaviour, diversification, investor utility, and factor exposures                                                                                                    | Return Calculation, Covariance Matrices, Sharpe Ratios, Capital Allocation Line, Mean-Variance Utility, Single-Factor APT Betas, Multi-Factor Extension Discussion                                  |
| 12 Short-Horizon Market Making with Order Book and Derivatives Signals | Tests whether derivatives-implied features improve 10-second adverse-selection prediction beyond limit order book signals, with robust validation and deployable market-making decision rules | LOB Feature Engineering, Order-Flow Imbalance, Implied-Volatility Surface Features, XGBoost, MLP Ensembles, HistGradientBoosting, TCN, SHAP, Isotonic Calibration, Day-Block Bootstrap, Placebo Testing, Within-Day AUC |

## Technical Coverage

### Programming and Implementation

* Python: pandas, NumPy, scikit-learn, PyTorch, TensorFlow, XGBoost, matplotlib, seaborn
* C++: Custom Matrix Classes, Numerical Linear Algebra, Conjugate Gradient, Rolling Backtest Architecture
* R: Regression Modelling, Statistical Inference, Short-Rate Estimation
* Jupyter Notebooks, Python Scripts, and Report-Style Research Documentation

### Trading and Market Microstructure

* Limit Order Book Feature Engineering
* Order-Flow Imbalance and Signed Trade Flow
* Adverse-Selection Modelling
* Systematic Trading Signal Validation
* ML Meta-Labelling
* Volatility-Targeted Strategy Construction
* Option Market Making
* Inventory-Skewed Quoting
* Relative-Value Arbitrage
* Basis Trading
* Execution Controls
* Automated Hedging
* Transaction-Cost-Aware Backtesting

### Derivatives and Numerical Finance

* Black-Scholes Pricing and Greeks
* Implied Volatility and Volatility-Surface Features
* Volatility Risk Premium Analysis
* Heston Stochastic Volatility
* Local-Volatility Models
* Barrier Option Pricing
* Finite-Difference PDE Methods
* Monte Carlo Backtesting
* Dynamic Programming for Stochastic Control

### Portfolio Construction and Risk

* Markowitz Mean-Variance Optimisation
* KKT Systems and Constrained Optimisation
* Convex Portfolio Optimisation
* Dollar, Beta, and Sector Neutrality
* Covariance Shrinkage
* Long-Only and Equal-Weight Benchmarks
* Rolling Out-of-Sample Evaluation
* Volatility Targeting
* Drawdowns, Turnover, Sharpe Ratios, and Bootstrap Inference

### Empirical Finance and Statistical Learning

* XGBoost, MLP Ensembles, and Temporal Convolutional Networks
* SHAP Feature Importance
* Isotonic Probability Calibration
* Placebo and Robustness Testing
* Day-Block Bootstrap Inference
* Pooled vs Within-Day Model Evaluation
* FX Strategy Combination
* Currency Factor Pricing
* Fama-MacBeth Regressions
* Term-Spread Forecasting
* Clark-West Forecast Comparison
* Mark-Kilian Bootstrap Inference
* PCA, K-Means, Hierarchical Clustering, HMM/GMM Regime Features
* CAPM, APT, CIR, and Vasicek Modelling

## Repository Structure

```text
QuantProjects/
├── 01_systematic_trading_ml_meta_labelling/
├── 02_heston_option_market_making/
├── 03_optibook_multistrategy_trading_engine/
├── 04_systematic_equity_factor_strategy/
├── 05_cpp_markowitz_portfolio_optimiser/
├── 06_local_volatility_barrier_pde_pricing/
├── 07_macro_regime_detection_tactical_allocation/
├── 08_fx_strategy_combination_currency_factor_pricing/
├── 09_yield_curve_forecasting_dynamic_allocation/
├── 10_financial_statistics_short_rate_modelling/
├── 11_equity_portfolio_apt_analysis/
└── 12_short_horizon_market_making_lob_derivatives/
```
