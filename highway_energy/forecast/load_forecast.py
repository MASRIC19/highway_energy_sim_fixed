"""
forecast/load_forecast.py
=========================
负荷预测模块：
  - 合成历史数据生成（工作日/周末 + 季节系数 + 高斯噪声）
  - 移动平均预测（最近 window 天同小时均值）
  - 误差指标：MAE / RMSE / MAPE
"""

from __future__ import annotations

import numpy as np

from highway_energy.config.params import T, RANDOM_SEED


# ─────────────────────────────────────────────
# 历史数据生成
# ─────────────────────────────────────────────

# 基础日内负荷曲线（kW），与仿真主体一致
_BASE_CURVE: np.ndarray = np.array([
    300, 300, 300, 300, 300, 310,
    450, 460, 470, 480, 490, 500,
    600, 610, 620, 630, 610, 600,
    520, 510, 500, 490, 470, 450,
], dtype=float)

assert len(_BASE_CURVE) == T


def generate_history_data(days: int = 60,
                           seed: int = RANDOM_SEED) -> np.ndarray:
    """
    生成 days 天逐小时合成历史负荷数据。

    特征：
      - 工作日（周一~五）负荷系数 1.00，周末（周六日）0.90
      - 季节系数：正弦波周期 90 天，振幅 ±12%
      - 高斯噪声：±5%（σ=0.05）

    Parameters
    ----------
    days : 历史天数
    seed : 随机种子（保证可复现）

    Returns
    -------
    np.ndarray, shape = (days, T)
    """
    rng = np.random.default_rng(seed)
    history = []

    for d in range(days):
        is_weekend    = (d % 7 >= 5)
        day_factor    = 0.90 if is_weekend else 1.00
        season_factor = 1.0 + 0.12 * np.sin(2 * np.pi * d / 90)
        noise         = rng.normal(0.0, 0.05, T)

        daily = _BASE_CURVE * day_factor * season_factor * (1 + noise)
        history.append(np.clip(daily, 200, 900))

    return np.array(history, dtype=float)   # (days, T)


# ─────────────────────────────────────────────
# 移动平均预测
# ─────────────────────────────────────────────

def moving_average_forecast(history: np.ndarray,
                             window: int = 7) -> np.ndarray:
    """
    用最近 window 天同小时均值预测"明天"。

    Parameters
    ----------
    history : shape = (days, T)
    window  : 滑动窗口天数

    Returns
    -------
    np.ndarray, shape = (T,)
    """
    if len(history) < window:
        window = len(history)
    recent = history[-window:]          # (window, T)
    return recent.mean(axis=0)          # (T,)


# ─────────────────────────────────────────────
# 误差指标
# ─────────────────────────────────────────────

def calc_forecast_metrics(y_true: np.ndarray,
                           y_pred: np.ndarray) -> dict:
    """
    计算三项预测误差指标。

    Parameters
    ----------
    y_true, y_pred : shape = (T,) 单日逐小时值

    Returns
    -------
    dict with keys: MAE(kW), RMSE(kW), MAPE(%)
    """
    diff = y_true - y_pred
    mae  = float(np.mean(np.abs(diff)))
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    # MAPE：分母取 max(|y_true|, 1) 防除零
    mape = float(
        np.mean(np.abs(diff) / np.maximum(np.abs(y_true), 1.0)) * 100
    )
    return {
        "MAE(kW)" : round(mae,  2),
        "RMSE(kW)": round(rmse, 2),
        "MAPE(%)" : round(mape, 2),
    }
