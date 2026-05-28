"""
visualization/style.py
======================
共享的 matplotlib 样式常量与辅助函数。
所有绘图模块统一从此处导入，避免重复定义。
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from highway_energy.config.params import T, TOU

# ─────────────────────────────────────────────
# 颜色方案
# ─────────────────────────────────────────────
WHITE_BG  = "white"
TEXT_C    = "#333333"
MUTE_C    = "#666666"
GRID_C    = "#e0e0e0"

# 各功率分量颜色
COLOR_BUY     = "#1f78b4"
COLOR_PV_USE  = "#33a02c"
COLOR_DIS     = "#6a3d9a"
COLOR_BASE    = "#ff7f00"
COLOR_EV      = "#e31a1c"
COLOR_CH      = "#fb9a99"
COLOR_SELL    = "#b2df8a"
COLOR_BATT_D  = "#388e3c"   # 放电（正）
COLOR_BATT_C  = "#d32f2f"   # 充电（负）
COLOR_SOC     = "#a78bfa"
COLOR_TOU     = "#f57f17"
COLOR_PV_LINE = "#fdd835"

# TOU 背景色
TOU_COLORS = {
    "valley": "#e8f5e9",  # 谷段 绿
    "peak"  : "#fce4ec",  # 峰段 红
    "flat"  : "#e3f2fd",  # 平段 蓝
}


def apply_ax_style(ax: "plt.Axes", title: str) -> None:
    """统一设置子图风格（背景/标题/网格/刻度颜色）。"""
    ax.set_facecolor(WHITE_BG)
    ax.tick_params(colors=MUTE_C, labelsize=9)
    ax.set_title(title, color=TEXT_C, fontsize=11, fontweight="bold", pad=8)
    for sp in ax.spines.values():
        sp.set_edgecolor(GRID_C)
    ax.grid(True, color=GRID_C, linewidth=0.5, linestyle="--", alpha=0.7)
    ax.yaxis.label.set_color(MUTE_C)
    ax.xaxis.label.set_color(MUTE_C)


def draw_tou_background(ax: "plt.Axes") -> None:
    """为子图绘制分时电价背景色带。"""
    for t in range(T):
        if TOU[t] <= 0.42:
            c = TOU_COLORS["valley"]
        elif TOU[t] >= 1.15:
            c = TOU_COLORS["peak"]
        else:
            c = TOU_COLORS["flat"]
        ax.axvspan(t - 0.5, t + 0.5, color=c, alpha=0.45, zorder=0)


def configure_fonts() -> None:
    """配置中文字体（按环境优先级尝试）。"""
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei", "DejaVu Sans"
    ]
    plt.rcParams["axes.unicode_minus"] = False
