"""
visualization/forecast_plot.py
===============================
负荷预测可视化（2 个子图）：
  左图：近 7 天历史 + 预测值 + ±8% 误差带 + 实际值
  右图：逐小时绝对误差柱状图 + 平均误差线
"""

from __future__ import annotations

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from highway_energy.config.params import T
from highway_energy.visualization.style import configure_fonts


def plot_forecast(history: np.ndarray,
                  forecast: np.ndarray,
                  y_true: np.ndarray,
                  metrics: dict,
                  save_path: str = "forecast_result.png") -> None:
    """
    绘制负荷预测结果图。

    Parameters
    ----------
    history  : shape = (days, T) 历史负荷数据
    forecast : shape = (T,)      预测曲线
    y_true   : shape = (T,)      实际值（用于误差对比）
    metrics  : calc_forecast_metrics 返回的指标字典
    save_path: 图像输出路径
    """
    configure_fonts()
    hours = np.arange(T)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # ── 左图：历史 + 预测对比 ───────────────────────────────
    ax = axes[0]
    for i, day in enumerate(history[-7:]):       # 最近 7 天历史
        alpha = 0.25 + 0.10 * i
        ax.plot(hours, day, color="steelblue", alpha=alpha, lw=1)
    ax.plot(hours, forecast, "o-", color="#e74c3c", lw=2,
            ms=4, label="预测值（移动平均）")
    ax.plot(hours, y_true,   "s--", color="#2ecc71", lw=2,
            ms=4, label="实际值（最后一天）")
    ax.fill_between(
        hours,
        forecast * 0.92, forecast * 1.08,
        alpha=0.15, color="#e74c3c", label="±8% 误差带",
    )
    ax.set_title("负荷预测对比（蓝色=近7天历史）", fontsize=11, fontweight="bold")
    ax.set_xlabel("时刻 (h)")
    ax.set_ylabel("负荷 (kW)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.4)
    ax.set_xticks(hours[::2])

    metric_str = "\n".join(f"{k}: {v}" for k, v in metrics.items())
    ax.text(0.02, 0.97, metric_str, transform=ax.transAxes,
            fontsize=9, va="top",
            bbox=dict(facecolor="white", edgecolor="gray", alpha=0.8))

    # ── 右图：逐小时绝对误差 ────────────────────────────────
    ax2 = axes[1]
    err    = np.abs(y_true - forecast)
    colors = ["#e74c3c" if e > 40 else "#3498db" for e in err]
    ax2.bar(hours, err, color=colors, alpha=0.85)
    ax2.axhline(
        err.mean(), color="#e67e22", lw=1.5, linestyle="--",
        label=f"平均误差 {err.mean():.1f} kW",
    )
    ax2.set_title("逐小时预测绝对误差", fontsize=11, fontweight="bold")
    ax2.set_xlabel("时刻 (h)")
    ax2.set_ylabel("绝对误差 (kW)")
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.4)
    ax2.set_xticks(hours[::2])

    fig.suptitle("高速公路服务区负荷预测分析",
                 fontsize=13, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [图表] 负荷预测结果已保存: {save_path}")
