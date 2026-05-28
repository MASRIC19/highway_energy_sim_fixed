"""
visualization/dispatch_plot.py
==============================
24 小时调度仿真主图（7 个子图）：
  1. 功率调度堆叠图（供电侧 vs 用电侧）
  2. 储能 SOC 曲线
  3. 储能充放电功率
  4. 电网交互 + 分时电价
  5. 光伏出力与消纳
  6. EV 柔性充电
  7. 优化前后经济性对比柱状图
"""

from __future__ import annotations

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import Patch

from highway_energy.config.params import (
    T, TOU, PV_OUT, BASE_LOAD, P_EV_MAX, EV_WEIGHT, EV_ENERGY_DEMAND,
)
from highway_energy.visualization.style import (
    WHITE_BG, TEXT_C, MUTE_C, GRID_C,
    COLOR_BUY, COLOR_PV_USE, COLOR_DIS, COLOR_BASE, COLOR_EV,
    COLOR_CH, COLOR_SELL, COLOR_BATT_D, COLOR_BATT_C,
    COLOR_SOC, COLOR_TOU, COLOR_PV_LINE,
    apply_ax_style, draw_tou_background, configure_fonts,
)


def plot_dispatch(result: dict,
                  baseline: dict,
                  stats: dict,
                  save_path: str = "dispatch_result.png") -> None:
    """
    绘制 24 小时调度仿真主图并保存。

    Parameters
    ----------
    result   : 优化/启发式调度结果
    baseline : 无储能基线
    stats    : analyze() 返回的统计指标
    save_path: 图像输出路径
    """
    configure_fonts()
    hours = np.arange(T)

    P_buy     = np.array(result["P_buy"])
    P_sell    = np.array(result["P_sell"])
    P_ch      = np.array(result["P_ch"])
    P_dis     = np.array(result["P_dis"])
    SOC       = np.array(result["SOC"])
    P_pv_use  = np.array(result["P_pv_use"])
    P_pv_curt = np.array(result["P_pv_curt"])
    P_ev      = np.array(result["P_ev"])
    b_buy     = np.array(baseline["P_buy"])

    fig = plt.figure(figsize=(20, 22))
    fig.patch.set_facecolor(WHITE_BG)
    gs = gridspec.GridSpec(
        4, 2, figure=fig,
        hspace=0.55, wspace=0.35,
        left=0.06, right=0.97, top=0.93, bottom=0.04,
    )

    # ── 图1: 功率调度堆叠图 ───────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :])
    bar_w = 0.4
    ax1.bar(hours - bar_w/2, P_buy,             bar_w, label="电网购电",  color=COLOR_BUY,   alpha=0.85)
    ax1.bar(hours - bar_w/2, P_pv_use,          bar_w, bottom=P_buy,
            label="光伏消纳", color=COLOR_PV_USE, alpha=0.85)
    ax1.bar(hours - bar_w/2, P_dis,             bar_w, bottom=P_buy + P_pv_use,
            label="储能放电", color=COLOR_DIS,    alpha=0.75)
    ax1.bar(hours + bar_w/2, BASE_LOAD,         bar_w, label="基础负荷",  color=COLOR_BASE,  alpha=0.75)
    ax1.bar(hours + bar_w/2, P_ev,              bar_w, bottom=BASE_LOAD,
            label="EV 充电",  color=COLOR_EV,    alpha=0.80)
    ax1.bar(hours + bar_w/2, P_ch,              bar_w, bottom=BASE_LOAD + P_ev,
            label="储能充电", color=COLOR_CH,    alpha=0.70)
    ax1.bar(hours + bar_w/2, P_sell,            bar_w, bottom=BASE_LOAD + P_ev + P_ch,
            label="电网售电", color=COLOR_SELL,  alpha=0.70)
    draw_tou_background(ax1)
    apply_ax_style(ax1, "24 小时功率调度（左: 供电侧 | 右: 用电侧）")
    ax1.set_xlabel("时刻 (h)")
    ax1.set_ylabel("功率 (kW)")
    ax1.set_xticks(hours)
    ax1.legend(ncol=7, facecolor=WHITE_BG, edgecolor=GRID_C,
               labelcolor=TEXT_C, fontsize=7.5, loc="upper left")

    # ── 图2: 储能 SOC ─────────────────────────────────────────
    ax2 = fig.add_subplot(gs[1, 0])
    soc_h = np.arange(T + 1)
    ax2.fill_between(soc_h, SOC, alpha=0.30, color="#7b2fff")
    ax2.plot(soc_h, SOC, "o-", color=COLOR_SOC, lw=2, ms=3, label="SOC")
    from highway_energy.config.params import SOC_MAX, SOC_MIN, SOC0
    ax2.axhline(SOC_MAX, ls="--", color=COLOR_BATT_C, lw=1.2, label=f"上限 {SOC_MAX}")
    ax2.axhline(SOC_MIN, ls="--", color=COLOR_BATT_D, lw=1.2, label=f"下限 {SOC_MIN}")
    ax2.axhline(SOC0,    ls=":",  color=COLOR_TOU,    lw=1.0, label=f"初始 {SOC0}")
    apply_ax_style(ax2, "储能荷电状态 (SOC) 变化曲线")
    ax2.set_xlabel("时刻 (h)")
    ax2.set_ylabel("SOC")
    ax2.set_ylim(0, 1.05)
    ax2.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8)

    # ── 图3: 储能充放电功率 ───────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 1])
    batt_net = P_dis - P_ch
    colors3  = [COLOR_BATT_D if v >= 0 else COLOR_BATT_C for v in batt_net]
    ax3.bar(hours, batt_net, color=colors3, alpha=0.85)
    ax3.axhline(0, color=MUTE_C, lw=0.8)
    apply_ax_style(ax3, "储能充放电功率（正 = 放电，负 = 充电）")
    ax3.set_xlabel("时刻 (h)")
    ax3.set_ylabel("功率 (kW)")
    ax3.set_xticks(hours[::2])
    ax3.legend(
        handles=[
            Patch(facecolor=COLOR_BATT_D, label="放电"),
            Patch(facecolor=COLOR_BATT_C, label="充电"),
        ],
        facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8,
    )

    # ── 图4: 电网交互 + 分时电价 ──────────────────────────────
    ax4   = fig.add_subplot(gs[2, 0])
    ax4_r = ax4.twinx()
    ax4.bar(hours, P_buy,               color=COLOR_BUY,  alpha=0.70, label="优化购电量")
    ax4.bar(hours, b_buy, width=0.35,   color="#bdbdbd",  alpha=0.50, label="基线购电量")
    ax4.bar(hours, -P_sell,             color=COLOR_PV_USE, alpha=0.60, label="售电量 (负向)")
    ax4_r.step(
        np.append(hours, T), np.append(TOU, TOU[-1]),
        where="post", color=COLOR_TOU, lw=2, label="TOU 电价",
    )
    apply_ax_style(ax4, "电网交互功率与分时电价")
    ax4.set_xlabel("时刻 (h)")
    ax4.set_ylabel("功率 (kW)", color=MUTE_C)
    ax4_r.set_ylabel("电价 (元/kWh)", color=COLOR_TOU)
    ax4_r.tick_params(colors=COLOR_TOU)
    ax4_r.set_ylim(0, 1.8)
    ax4.set_xticks(hours[::2])
    h1, l1 = ax4.get_legend_handles_labels()
    h2, l2 = ax4_r.get_legend_handles_labels()
    ax4.legend(h1 + h2, l1 + l2,
               facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8)

    # ── 图5: 光伏出力与消纳 ───────────────────────────────────
    ax5 = fig.add_subplot(gs[2, 1])
    ax5.fill_between(hours, PV_OUT, alpha=0.15, color=COLOR_PV_LINE, step="mid")
    ax5.step(hours, PV_OUT,   where="mid", color=COLOR_PV_LINE, lw=1.5,
             label=f"光伏总出力 ({PV_OUT.sum():.0f} kWh)")
    ax5.step(hours, P_pv_use, where="mid", color=COLOR_PV_USE,  lw=1.5,
             label=f"光伏消纳 ({P_pv_use.sum():.0f} kWh)")
    ax5.fill_between(hours, P_pv_use, PV_OUT, step="mid",
                     alpha=0.40, color=COLOR_BATT_C,
                     label=f"弃光 ({P_pv_curt.sum():.0f} kWh)")
    apply_ax_style(ax5, "光伏出力与消纳分析")
    ax5.set_xlabel("时刻 (h)")
    ax5.set_ylabel("功率 (kW)")
    ax5.set_xticks(hours[::2])
    ax5.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8)

    # ── 图6: EV 柔性充电 ──────────────────────────────────────
    ax6 = fig.add_subplot(gs[3, 0])
    ev_window = EV_WEIGHT * P_EV_MAX
    ax6.fill_between(hours, ev_window, alpha=0.10, color="#87CEEB",
                     step="mid", label="充电窗口上限")
    ax6.bar(hours, P_ev, color=COLOR_EV, alpha=0.80, label="优化 EV 充电功率")
    draw_tou_background(ax6)
    ev_total = float(np.sum(P_ev) * 1.0)   # DT=1
    apply_ax_style(
        ax6,
        f"EV 柔性充电调度（日充电 {ev_total:.0f} kWh / 需求 {EV_ENERGY_DEMAND:.0f} kWh）",
    )
    ax6.set_xlabel("时刻 (h)")
    ax6.set_ylabel("功率 (kW)")
    ax6.set_xticks(hours[::2])
    ax6.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8)

    # ── 图7: 经济性对比 ───────────────────────────────────────
    ax7 = fig.add_subplot(gs[3, 1])
    metrics_labels = ["日购电量\n(kWh)", "峰时购电\n(kWh)", "需量峰值\n(kW)", "日费用\n(元)"]
    vals_b = [
        float(b_buy.sum()),
        float(b_buy[TOU >= 1.15].sum()),
        float(np.max(b_buy)),
        float(baseline["cost"]),
    ]
    vals_o = [
        stats["total_buy"],
        stats["peak_buy"],
        stats["peak_demand"],
        stats["cost"],
    ]
    x7 = np.arange(len(metrics_labels))
    ax7.bar(x7 - 0.2, vals_b, 0.35, label="无优化基线", color="#bdbdbd", alpha=0.80)
    ax7.bar(x7 + 0.2, vals_o, 0.35, label="光储优化",   color=COLOR_BUY,  alpha=0.85)
    max_val = max(vals_b) if vals_b else 1.0
    for i, (vb, vo) in enumerate(zip(vals_b, vals_o)):
        pct = (vb - vo) / vb * 100 if abs(vb) > 1e-9 else 0.0
        ax7.text(x7[i] + 0.2, vo + max_val * 0.015,
                 f"↓{pct:.1f}%", ha="center",
                 color=COLOR_BATT_D, fontsize=8.5, fontweight="bold")
    apply_ax_style(ax7, "优化前后经济性对比")
    ax7.set_xticks(x7)
    ax7.set_xticklabels(metrics_labels, color=TEXT_C, fontsize=9)
    ax7.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8)

    # ── 总标题 ────────────────────────────────────────────────
    fig.suptitle(
        "高速公路服务区光储充系统 · 24 小时优化调度仿真分析 (Gurobi MILP) — 修复版",
        color=TEXT_C, fontsize=13, fontweight="bold", y=0.97,
    )
    fig.text(
        0.5, 0.955,
        (f"日节约 {stats['saving']:.1f} 元 ({stats['saving_pct']:.2f}%)  |  "
         f"光伏利用率 {stats['pv_util']:.1f}%  |  "
         f"EV满足度 {stats['ev_fulfillment']:.1f}%  |  "
         f"策略: {result['status']}"),
        ha="center", color=COLOR_TOU, fontsize=9.5,
    )

    plt.savefig(save_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  [图表] 调度结果图已保存: {save_path}")


# ============================================================
# 拆分为 7 个独立子图
# ============================================================

def _parse_result(result: dict, baseline: dict) -> dict:
    """提取所有画图所需数组，避免重复解析。"""
    return {
        "hours"    : np.arange(T),
        "P_buy"    : np.array(result["P_buy"]),
        "P_sell"   : np.array(result["P_sell"]),
        "P_ch"     : np.array(result["P_ch"]),
        "P_dis"    : np.array(result["P_dis"]),
        "SOC"      : np.array(result["SOC"]),
        "P_pv_use" : np.array(result["P_pv_use"]),
        "P_pv_curt": np.array(result["P_pv_curt"]),
        "P_ev"     : np.array(result["P_ev"]),
        "b_buy"    : np.array(baseline["P_buy"]),
        "b_cost"   : baseline["cost"],
    }


def _new_fig(title: str = None, size: tuple = (10, 6)) -> tuple:
    """创建独立子图 fig/ax，统一风格。"""
    configure_fonts()
    fig, ax = plt.subplots(figsize=size)
    fig.patch.set_facecolor(WHITE_BG)
    if title:
        fig.suptitle(title, color=TEXT_C, fontsize=12, fontweight="bold")
    return fig, ax


def plot_sub1_power_stack(data: dict, save_path: str = "sub1_power_stack.png") -> None:
    """图1: 功率调度堆叠图（供电侧 vs 用电侧）"""
    fig, ax = _new_fig("24 小时功率调度（左: 供电侧 | 右: 用电侧）", (16, 6))
    h = data["hours"]
    bar_w = 0.4
    ax.bar(h - bar_w/2, data["P_buy"],    bar_w, label="电网购电", color=COLOR_BUY,   alpha=0.85)
    ax.bar(h - bar_w/2, data["P_pv_use"], bar_w, bottom=data["P_buy"],
           label="光伏消纳", color=COLOR_PV_USE, alpha=0.85)
    ax.bar(h - bar_w/2, data["P_dis"],    bar_w, bottom=data["P_buy"] + data["P_pv_use"],
           label="储能放电", color=COLOR_DIS, alpha=0.75)
    ax.bar(h + bar_w/2, BASE_LOAD,        bar_w, label="基础负荷", color=COLOR_BASE, alpha=0.75)
    ax.bar(h + bar_w/2, data["P_ev"],     bar_w, bottom=BASE_LOAD,
           label="EV 充电", color=COLOR_EV, alpha=0.80)
    ax.bar(h + bar_w/2, data["P_ch"],     bar_w, bottom=BASE_LOAD + data["P_ev"],
           label="储能充电", color=COLOR_CH, alpha=0.70)
    ax.bar(h + bar_w/2, data["P_sell"],   bar_w, bottom=BASE_LOAD + data["P_ev"] + data["P_ch"],
           label="电网售电", color=COLOR_SELL, alpha=0.70)
    draw_tou_background(ax)
    apply_ax_style(ax, "")
    ax.set_xlabel("时刻 (h)")
    ax.set_ylabel("功率 (kW)")
    ax.set_xticks(h)
    ax.legend(ncol=7, facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=7.5)
    _save_and_close(fig, save_path)


def plot_sub2_soc(data: dict, save_path: str = "sub2_soc.png") -> None:
    """图2: 储能 SOC 变化曲线"""
    fig, ax = _new_fig("储能荷电状态 (SOC) 变化曲线", (10, 6))
    soc_h = np.arange(T + 1)
    ax.fill_between(soc_h, data["SOC"], alpha=0.30, color="#7b2fff")
    ax.plot(soc_h, data["SOC"], "o-", color=COLOR_SOC, lw=2, ms=3, label="SOC")
    from highway_energy.config.params import SOC_MAX, SOC_MIN, SOC0
    ax.axhline(SOC_MAX, ls="--", color=COLOR_BATT_C, lw=1.2, label=f"上限 {SOC_MAX}")
    ax.axhline(SOC_MIN, ls="--", color=COLOR_BATT_D, lw=1.2, label=f"下限 {SOC_MIN}")
    ax.axhline(SOC0,    ls=":",  color=COLOR_TOU,    lw=1.0, label=f"初始 {SOC0}")
    apply_ax_style(ax, "")
    ax.set_xlabel("时刻 (h)")
    ax.set_ylabel("SOC")
    ax.set_ylim(0, 1.05)
    ax.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=9)
    _save_and_close(fig, save_path)


def plot_sub3_battery_power(data: dict, save_path: str = "sub3_battery_power.png") -> None:
    """图3: 储能充放电功率"""
    fig, ax = _new_fig("储能充放电功率（正 = 放电，负 = 充电）", (10, 6))
    h = data["hours"]
    batt_net = data["P_dis"] - data["P_ch"]
    colors3 = [COLOR_BATT_D if v >= 0 else COLOR_BATT_C for v in batt_net]
    ax.bar(h, batt_net, color=colors3, alpha=0.85)
    ax.axhline(0, color=MUTE_C, lw=0.8)
    apply_ax_style(ax, "")
    ax.set_xlabel("时刻 (h)")
    ax.set_ylabel("功率 (kW)")
    ax.set_xticks(h[::2])
    ax.legend(
        handles=[Patch(facecolor=COLOR_BATT_D, label="放电"),
                 Patch(facecolor=COLOR_BATT_C, label="充电")],
        facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=9,
    )
    _save_and_close(fig, save_path)


def plot_sub4_grid_interaction(data: dict, save_path: str = "sub4_grid_interaction.png") -> None:
    """图4: 电网交互功率与分时电价"""
    fig, ax = _new_fig("电网交互功率与分时电价", (10, 6))
    h = data["hours"]
    ax_r = ax.twinx()
    ax.bar(h, data["P_buy"],             color=COLOR_BUY,   alpha=0.70, label="优化购电量")
    ax.bar(h, data["b_buy"], width=0.35, color="#bdbdbd",   alpha=0.50, label="基线购电量")
    ax.bar(h, -data["P_sell"],           color=COLOR_PV_USE, alpha=0.60, label="售电量 (负向)")
    ax_r.step(np.append(h, T), np.append(TOU, TOU[-1]),
              where="post", color=COLOR_TOU, lw=2, label="TOU 电价")
    apply_ax_style(ax, "")
    ax.set_xlabel("时刻 (h)")
    ax.set_ylabel("功率 (kW)", color=MUTE_C)
    ax_r.set_ylabel("电价 (元/kWh)", color=COLOR_TOU)
    ax_r.tick_params(colors=COLOR_TOU)
    ax_r.set_ylim(0, 1.8)
    ax.set_xticks(h[::2])
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax_r.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2,
              facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=9)
    _save_and_close(fig, save_path)


def plot_sub5_pv_utilization(data: dict, save_path: str = "sub5_pv_utilization.png") -> None:
    """图5: 光伏出力与消纳分析"""
    fig, ax = _new_fig("光伏出力与消纳分析", (10, 6))
    h = data["hours"]
    ax.fill_between(h, PV_OUT,    alpha=0.15, color=COLOR_PV_LINE, step="mid")
    ax.step(h, PV_OUT,           where="mid", color=COLOR_PV_LINE, lw=1.5,
            label=f"光伏总出力 ({PV_OUT.sum():.0f} kWh)")
    ax.step(h, data["P_pv_use"], where="mid", color=COLOR_PV_USE,  lw=1.5,
            label=f"光伏消纳 ({data['P_pv_use'].sum():.0f} kWh)")
    ax.fill_between(h, data["P_pv_use"], PV_OUT, step="mid",
                    alpha=0.40, color=COLOR_BATT_C,
                    label=f"弃光 ({data['P_pv_curt'].sum():.0f} kWh)")
    apply_ax_style(ax, "")
    ax.set_xlabel("时刻 (h)")
    ax.set_ylabel("功率 (kW)")
    ax.set_xticks(h[::2])
    ax.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=9)
    _save_and_close(fig, save_path)


def plot_sub6_ev_charging(data: dict, save_path: str = "sub6_ev_charging.png") -> None:
    """图6: EV 柔性充电调度"""
    fig, ax = _new_fig(
        f"EV 柔性充电调度（日充电 {data['P_ev'].sum():.0f} kWh / 需求 {EV_ENERGY_DEMAND:.0f} kWh）",
        (10, 6))
    h = data["hours"]
    ev_window = EV_WEIGHT * P_EV_MAX
    ax.fill_between(h, ev_window, alpha=0.10, color="#87CEEB",
                    step="mid", label="充电窗口上限")
    ax.bar(h, data["P_ev"], color=COLOR_EV, alpha=0.80, label="优化 EV 充电功率")
    draw_tou_background(ax)
    apply_ax_style(ax, "")
    ax.set_xlabel("时刻 (h)")
    ax.set_ylabel("功率 (kW)")
    ax.set_xticks(h[::2])
    ax.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=9)
    _save_and_close(fig, save_path)


def plot_sub7_economic_comparison(data: dict, stats: dict, save_path: str = "sub7_economic_comparison.png") -> None:
    """图7: 优化前后经济性对比"""
    fig, ax = _new_fig("优化前后经济性对比", (10, 6))
    metrics_labels = ["日购电量\n(kWh)", "峰时购电\n(kWh)", "需量峰值\n(kW)", "日费用\n(元)"]
    vals_b = [
        float(data["b_buy"].sum()),
        float(data["b_buy"][TOU >= 1.15].sum()),
        float(np.max(data["b_buy"])),
        float(data["b_cost"]),
    ]
    vals_o = [
        stats["total_buy"],
        stats["peak_buy"],
        stats["peak_demand"],
        stats["cost"],
    ]
    x7 = np.arange(len(metrics_labels))
    ax.bar(x7 - 0.2, vals_b, 0.35, label="无优化基线", color="#bdbdbd", alpha=0.80)
    ax.bar(x7 + 0.2, vals_o, 0.35, label="光储优化",   color=COLOR_BUY,  alpha=0.85)
    max_val = max(vals_b) if vals_b else 1.0
    for i, (vb, vo) in enumerate(zip(vals_b, vals_o)):
        pct = (vb - vo) / vb * 100 if abs(vb) > 1e-9 else 0.0
        ax.text(x7[i] + 0.2, vo + max_val * 0.015,
                f"↓{pct:.1f}%", ha="center",
                color=COLOR_BATT_D, fontsize=9, fontweight="bold")
    apply_ax_style(ax, "")
    ax.set_xticks(x7)
    ax.set_xticklabels(metrics_labels, color=TEXT_C, fontsize=9)
    ax.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=9)
    _save_and_close(fig, save_path)


def _save_and_close(fig, path: str) -> None:
    """保存并关闭图像。"""
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  [图表] {path}")


def plot_dispatch_split(result: dict,
                        baseline: dict,
                        stats: dict,
                        output_dir: str = "output") -> None:
    """
    将调度结果拆分为 7 个独立 PNG 文件保存到指定目录。

    Parameters
    ----------
    result     : 优化/启发式调度结果
    baseline   : 无储能基线
    stats      : analyze() 返回的统计指标
    output_dir : 输出目录
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    data = _parse_result(result, baseline)

    plot_sub1_power_stack(data,        os.path.join(output_dir, "sub1_power_stack.png"))
    plot_sub2_soc(data,                os.path.join(output_dir, "sub2_soc.png"))
    plot_sub3_battery_power(data,      os.path.join(output_dir, "sub3_battery_power.png"))
    plot_sub4_grid_interaction(data,   os.path.join(output_dir, "sub4_grid_interaction.png"))
    plot_sub5_pv_utilization(data,     os.path.join(output_dir, "sub5_pv_utilization.png"))
    plot_sub6_ev_charging(data,        os.path.join(output_dir, "sub6_ev_charging.png"))
    plot_sub7_economic_comparison(data, stats, os.path.join(output_dir, "sub7_economic_comparison.png"))
    print(f"  [图表] 7 张子图已保存至: {output_dir}/")
