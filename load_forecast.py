"""
高速公路服务区光储充系统 — 负荷预测模块
包含：历史数据生成、移动平均预测、误差指标计算
"""

import numpy as np
from config import T


def generate_history_data(days: int = 60) -> np.ndarray:
    """
    生成 days 天逐小时合成历史负荷 (kW)。
    工作日/周末差异 + 季节系数 + 随机扰动。
    shape = (days, 24)
    """
    base_curve = np.array([
        300, 300, 300, 300, 300, 310,
        450, 460, 470, 480, 490, 500,
        600, 610, 620, 630, 610, 600,
        520, 510, 500, 490, 470, 450,
    ], dtype=float)

    history = []
    for d in range(days):
        is_weekend = (d % 7 >= 5)
        day_factor = 0.90 if is_weekend else 1.00
        season_factor = 1.0 + 0.12 * np.sin(2 * np.pi * d / 90)
        noise = np.random.normal(0, 0.05, T)
        daily = base_curve * day_factor * season_factor * (1 + noise)
        history.append(np.clip(daily, 200, 900))

    return np.array(history)


def moving_average_forecast(history: np.ndarray, window: int = 7) -> np.ndarray:
    """
    用最近 window 天的同小时均值预测明日负荷。
    history shape = (days, 24)，返回 (24,)
    """
    recent = history[-window:]
    return recent.mean(axis=0)


def calc_forecast_metrics(y_true: np.ndarray,
                           y_pred: np.ndarray) -> dict:
    """
    负荷预测三项误差指标：MAE / RMSE / MAPE。
    y_true, y_pred: shape = (24,)
    """
    mae = np.mean(np.abs(y_true - y_pred))
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
    mape = np.mean(np.abs((y_true - y_pred) /
                           np.maximum(np.abs(y_true), 1.0))) * 100
    return {"MAE(kW)": round(mae, 2),
            "RMSE(kW)": round(rmse, 2),
            "MAPE(%)": round(mape, 2)}
