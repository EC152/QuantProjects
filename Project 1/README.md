# Project 1 — Market Data Collector & EDA Toolkit

## 📌 Overview
This project is the first in my **Quantitative Finance Projects** series.  
It focuses on **collecting, cleaning, and exploring market data** as the foundation for trading strategy research.

The goal is to:
- Download historical price data for a set of tickers
- Perform basic exploratory data analysis (EDA)
- Visualize important metrics such as returns, volatility, and drawdowns

All work is documented in **Jupyter Notebooks** to clearly show methodology, results, and annotations.

---

## 🛠 Features
- Pull OHLCV data from Yahoo Finance (`yfinance`)
- Compute:
  - Daily returns & log returns
  - Rolling volatility
  - Maximum drawdown
- Generate plots:
  - Price history
  - Rolling volatility
  - Drawdown curves
- Modular structure for easy extension in future projects
