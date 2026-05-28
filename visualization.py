"""
高速公路服务区光储充系统 — 可视化模块
包含：原调度仿真图、负荷预测图、容量热力图、Pareto 散点图
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import Patch
import warnings
warnings.filterwarnings('ignore')

from config import T, TOU, PV_out, Base_load, EV_weight, P_ev_max, EV_energy_demand, SOC_min, SOC_max, SOC0

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

WHITE_BG = 'white'
TEXT_C   = '#333333'
MUTE_C   = '#666666'
GRID_C   = '#e0e0e0'


def _ax_style(ax, title):
    ax.set_facecolor(WHITE_BG)
    ax.tick_params(colors=MUTE_C, labelsize=9)
    ax.set_title(title, color=TEXT_C, fontsize=11, fontweight='bold', pad=8)
    for sp in ax.spines.values():
        sp.set_edgecolor(GRID_C)
    ax.grid(True, color=GRID_C, linewidth=0.5, linestyle='--', alpha=0.7)
    ax.yaxis.label.set_color(MUTE_C)
    ax.xaxis.label.set_color(MUTE_C)


def _tou_bg(ax):
    """分时电价背景色"""
    for t in range(T):
        c = '#e8f5e9' if TOU[t] == 0.42 else ('#fce4ec' if TOU[t] == 1.15 else '#e3f2fd')
        ax.axvspan(t - 0.5, t + 0.5, color=c, alpha=0.45, zorder=0)


def plot_results(result, baseline, stats, save_prefix="highway_energy_sim_fixed"):
    """原调度仿真 7 子图（功率堆叠、SOC、充放电、电网交互、光伏消纳、EV充电、经济对比）"""
    hours = np.arange(T)
    P_buy = np.array(result['P_buy'])
    P_sell = np.array(result['P_sell'])
    P_ch = np.array(result['P_ch'])
    P_dis = np.array(result['P_dis'])
    SOC = np.array(result['SOC'])
    P_pv_use = np.array(result['P_pv_use'])
    P_pv_curt = np.array(result['P_pv_curt'])
    P_ev = np.array(result['P_ev'])

    fig = plt.figure(figsize=(20, 22))
    fig.patch.set_facecolor(WHITE_BG)
    gs = gridspec.GridSpec(4, 2, figure=fig, hspace=0.55, wspace=0.35,
                           left=0.06, right=0.97, top=0.93, bottom=0.04)

    # 图1: 功率调度堆叠
    ax1 = fig.add_subplot(gs[0, :])
    bar_w = 0.4
    ax1.bar(hours - bar_w / 2, P_buy, bar_w, label='电网购电', color='#1f78b4', alpha=0.85)
    ax1.bar(hours - bar_w / 2, P_pv_use, bar_w, bottom=P_buy,
            label='光伏消纳', color='#33a02c', alpha=0.85)
    ax1.bar(hours - bar_w / 2, P_dis, bar_w, bottom=P_buy + P_pv_use,
            label='储能放电', color='#6a3d9a', alpha=0.75)
    ax1.bar(hours + bar_w / 2, Base_load, bar_w, label='基础负荷', color='#ff7f00', alpha=0.75)
    ax1.bar(hours + bar_w / 2, P_ev, bar_w, bottom=Base_load,
            label='EV 充电', color='#e31a1c', alpha=0.80)
    ax1.bar(hours + bar_w / 2, P_ch, bar_w, bottom=Base_load + P_ev,
            label='储能充电', color='#fb9a99', alpha=0.70)
    ax1.bar(hours + bar_w / 2, P_sell, bar_w, bottom=Base_load + P_ev + P_ch,
            label='电网售电', color='#b2df8a', alpha=0.70)
    _tou_bg(ax1)
    _ax_style(ax1, '24 小时功率调度（左: 供电侧 | 右: 用电侧）')
    ax1.set_xlabel('时刻 (h)')
    ax1.set_ylabel('功率 (kW)')
    ax1.set_xticks(hours)
    ax1.legend(ncol=7, facecolor=WHITE_BG, edgecolor=GRID_C,
               labelcolor=TEXT_C, fontsize=7.5, loc='upper left')

    # 图2: 储能 SOC
    ax2 = fig.add_subplot(gs[1, 0])
    soc_h = np.arange(T + 1)
    ax2.fill_between(soc_h, SOC, alpha=0.30, color='#7b2fff')
    ax2.plot(soc_h, SOC, 'o-', color='#a78bfa', lw=2, ms=3, label='SOC')
    ax2.axhline(SOC_max, ls='--', color='#d32f2f', lw=1.2, label=f'上限 {SOC_max}')
    ax2.axhline(SOC_min, ls='--', color='#388e3c', lw=1.2, label=f'下限 {SOC_min}')
    ax2.axhline(SOC0, ls=':', color='#f57f17', lw=1.0, label=f'初始 {SOC0}')
    _ax_style(ax2, '储能荷电状态 (SOC) 变化曲线')
    ax2.set_xlabel('时刻 (h)')
    ax2.set_ylabel('SOC')
    ax2.set_ylim(0, 1.05)
    ax2.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8)

    # 图3: 储能充放电功率
    ax3 = fig.add_subplot(gs[1, 1])
    batt_net = P_dis - P_ch
    colors3 = ['#388e3c' if v >= 0 else '#d32f2f' for v in batt_net]
    ax3.bar(hours, batt_net, color=colors3, alpha=0.85)
    ax3.axhline(0, color=MUTE_C, lw=0.8)
    _ax_style(ax3, '储能充放电功率（正 = 放电，负 = 充电）')
    ax3.set_xlabel('时刻 (h)')
    ax3.set_ylabel('功率 (kW)')
    ax3.set_xticks(hours[::2])
    ax3.legend(handles=[Patch(facecolor='#388e3c', label='放电'),
                        Patch(facecolor='#d32f2f', label='充电')],
               facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8)

    # 图4: 电网交互与分时电价
    ax4 = fig.add_subplot(gs[2, 0])
    ax4_r = ax4.twinx()
    ax4.bar(hours, P_buy, color='#1f78b4', alpha=0.70, label='优化购电量')
    ax4.bar(hours, baseline['P_buy'], width=0.35,
            color='#bdbdbd', alpha=0.50, label='基线购电量')
    ax4.bar(hours, -P_sell, color='#33a02c', alpha=0.60, label='售电量 (负向)')
    ax4_r.step(np.append(hours, T), np.append(TOU, TOU[-1]),
               where='post', color='#f57f17', lw=2, label='TOU 电价')
    _ax_style(ax4, '电网交互功率与分时电价')
    ax4.set_xlabel('时刻 (h)')
    ax4.set_ylabel('功率 (kW)', color=MUTE_C)
    ax4_r.set_ylabel('电价 (元/kWh)', color='#f57f17')
    ax4_r.tick_params(colors='#f57f17')
    ax4_r.set_ylim(0, 1.8)
    ax4.set_xticks(hours[::2])
    h1, l1 = ax4.get_legend_handles_labels()
    h2, l2 = ax4_r.get_legend_handles_labels()
    ax4.legend(h1 + h2, l1 + l2, facecolor=WHITE_BG, edgecolor=GRID_C,
               labelcolor=TEXT_C, fontsize=8)

    # 图5: 光伏出力与消纳
    ax5 = fig.add_subplot(gs[2, 1])
    ax5.fill_between(hours, PV_out, alpha=0.15, color='#fdd835', step='mid')
    ax5.step(hours, PV_out, where='mid', color='#fdd835', lw=1.5,
             label=f'光伏总出力 ({PV_out.sum():.0f} kWh)')
    ax5.step(hours, P_pv_use, where='mid', color='#388e3c', lw=1.5,
             label=f'光伏消纳 ({P_pv_use.sum():.0f} kWh)')
    ax5.fill_between(hours, P_pv_use, PV_out, step='mid',
                     alpha=0.40, color='#d32f2f',
                     label=f'弃光 ({P_pv_curt.sum():.0f} kWh)')
    _ax_style(ax5, '光伏出力与消纳分析')
    ax5.set_xlabel('时刻 (h)')
    ax5.set_ylabel('功率 (kW)')
    ax5.set_xticks(hours[::2])
    ax5.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8)

    # 图6: EV 柔性充电
    ax6 = fig.add_subplot(gs[3, 0])
    ev_window = EV_weight * P_ev_max
    ax6.fill_between(hours, ev_window, alpha=0.10, color='#87CEEB',
                     step='mid', label='充电窗口上限')
    ax6.bar(hours, P_ev, color='#e31a1c', alpha=0.80, label='优化 EV 充电功率')
    _tou_bg(ax6)
    ev_total = np.sum(P_ev) * 1.0
    _ax_style(ax6,
              f'EV 柔性充电调度（日充电 {ev_total:.0f} kWh / 需求 {EV_energy_demand} kWh）')
    ax6.set_xlabel('时刻 (h)')
    ax6.set_ylabel('功率 (kW)')
    ax6.set_xticks(hours[::2])
    ax6.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8)

    # 图7: 经济性对比
    ax7 = fig.add_subplot(gs[3, 1])
    metrics = ['日购电量\n(kWh)', '峰时购电\n(kWh)', '需量峰值\n(kW)', '日费用\n(元)']
    vals_b = [
        float(baseline['P_buy'].sum()),
        float(baseline['P_buy'][TOU >= 1.15].sum()),
        float(np.max(baseline['P_buy'])),
        float(baseline['cost']),
    ]
    vals_o = [
        stats['total_buy'],
        stats['peak_buy'],
        stats['peak_demand'],
        stats['cost'],
    ]
    x7 = np.arange(len(metrics))
    ax7.bar(x7 - 0.2, vals_b, 0.35, label='无优化基线', color='#bdbdbd', alpha=0.80)
    ax7.bar(x7 + 0.2, vals_o, 0.35, label='光储优化', color='#1f78b4', alpha=0.85)
    for i, (vb, vo) in enumerate(zip(vals_b, vals_o)):
        pct = (vb - vo) / vb * 100 if vb > 0 else 0
        ax7.text(x7[i] + 0.2, vo + max(vals_b) * 0.015,
                 f'↓{pct:.1f}%', ha='center',
                 color='#388e3c', fontsize=8.5, fontweight='bold')
    _ax_style(ax7, '优化前后经济性对比')
    ax7.set_xticks(x7)
    ax7.set_xticklabels(metrics, color=TEXT_C, fontsize=9)
    ax7.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8)

    fig.suptitle(
        '高速公路服务区光储充系统 · 24 小时优化调度仿真分析 (Gurobi MILP)',
        color=TEXT_C, fontsize=13, fontweight='bold', y=0.97)
    fig.text(0.5, 0.955,
             f'日节约 {stats["saving"]:.1f} 元 ({stats["saving_pct"]:.2f}%)  |  '
             f'光伏利用率 {stats["pv_util"]:.1f}%  |  EV满足度 {stats["ev_fulfillment"]:.1f}%  |  '
             f'策略: {result["status"]}',
             ha='center', color='#f57f17', fontsize=9.5)

    out = f"{save_prefix}.png"
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    print(f"  图表已保存: {out}")
    return fig


# ============================================================
# 升级模块图表
# ============================================================

def plot_forecast(history: np.ndarray,
                  forecast: np.ndarray,
                  y_true: np.ndarray,
                  metrics: dict,
                  save_path: str = "forecast_result.png"):
    """负荷预测结果图（2子图）"""
    T_val = history.shape[1]
    hours = np.arange(T_val)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    for i, day in enumerate(history[-7:]):
        alpha = 0.25 + 0.1 * i
        ax.plot(hours, day, color='steelblue', alpha=alpha, lw=1)
    ax.plot(hours, forecast, 'o-', color='#e74c3c', lw=2,
            ms=4, label='预测值（移动平均）')
    ax.plot(hours, y_true, 's--', color='#2ecc71', lw=2,
            ms=4, label='实际值（第61天）')
    ax.fill_between(hours,
                    forecast * 0.92, forecast * 1.08,
                    alpha=0.15, color='#e74c3c', label='±8% 误差带')
    ax.set_title('负荷预测对比（蓝色=近7天历史）', fontsize=11, fontweight='bold')
    ax.set_xlabel('时刻 (h)')
    ax.set_ylabel('负荷 (kW)')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.4)
    ax.set_xticks(hours[::2])

    metric_str = "\n".join(f"{k}: {v}" for k, v in metrics.items())
    ax.text(0.02, 0.97, metric_str, transform=ax.transAxes,
            fontsize=9, va='top',
            bbox=dict(facecolor='white', edgecolor='gray', alpha=0.8))

    ax2 = axes[1]
    err = np.abs(y_true - forecast)
    colors = ['#e74c3c' if e > 40 else '#3498db' for e in err]
    ax2.bar(hours, err, color=colors, alpha=0.85)
    ax2.axhline(err.mean(), color='#e67e22', lw=1.5,
                linestyle='--', label=f'平均误差 {err.mean():.1f} kW')
    ax2.set_title('逐小时预测绝对误差', fontsize=11, fontweight='bold')
    ax2.set_xlabel('时刻 (h)')
    ax2.set_ylabel('绝对误差 (kW)')
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.4)
    ax2.set_xticks(hours[::2])

    fig.suptitle('高速公路服务区负荷预测分析', fontsize=13,
                 fontweight='bold', y=1.01)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [图表] 负荷预测结果已保存: {save_path}")


def plot_capacity_heatmap(df,
                          save_path: str = "capacity_heatmap.png"):
    """容量配置结果可视化（4张热力图）"""
    import pandas as pd
    pvs = sorted(df["光伏容量(kW)"].unique())
    esss = sorted(df["储能容量(kWh)"].unique())

    def _pivot(col):
        return df.pivot_table(index="储能容量(kWh)",
                              columns="光伏容量(kW)",
                              values=col)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    targets = [
        ("LCC(万元)", "全生命周期成本 (万元)", "YlOrRd", True),
        ("年碳排放(tCO2)", "年碳排放量 (tCO₂)", "Greens", True),
        ("光伏利用率(%)", "光伏利用率 (%)", "Blues", False),
        ("综合得分", "综合得分（越低越优）", "RdYlGn_r", True),
    ]

    for ax, (col, title, cmap, annot_small) in zip(axes.flatten(), targets):
        mat = _pivot(col)
        im = ax.imshow(mat.values, cmap=cmap, aspect='auto')
        plt.colorbar(im, ax=ax, shrink=0.85)

        ax.set_xticks(range(len(pvs)))
        ax.set_xticklabels([f"{p}" for p in pvs], fontsize=9)
        ax.set_yticks(range(len(esss)))
        ax.set_yticklabels([f"{e}" for e in esss], fontsize=9)
        ax.set_xlabel("光伏容量 (kW)", fontsize=9)
        ax.set_ylabel("储能容量 (kWh)", fontsize=9)
        ax.set_title(title, fontsize=10, fontweight='bold')

        for i in range(len(esss)):
            for j in range(len(pvs)):
                val = mat.values[i, j]
                ax.text(j, i, f"{val:.1f}", ha='center', va='center',
                        fontsize=8,
                        color='white' if annot_small else 'black')

        best_idx = np.unravel_index(mat.values.argmin(), mat.values.shape)
        ax.add_patch(plt.Rectangle(
            (best_idx[1] - 0.5, best_idx[0] - 0.5), 1, 1,
            fill=False, edgecolor='lime', lw=3))

    fig.suptitle('光储容量配置多目标评估热力图\n（绿框 = 该指标最优点）',
                 fontsize=13, fontweight='bold')
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [图表] 容量配置热力图已保存: {save_path}")


def plot_capacity_pareto(df,
                         save_path: str = "capacity_pareto.png"):
    """经济 vs 碳排放散点图（模拟 Pareto 前沿）"""
    fig, ax = plt.subplots(figsize=(8, 6))

    sc = ax.scatter(df["LCC(万元)"], df["年碳排放(tCO2)"],
                    c=df["光伏利用率(%)"], cmap='RdYlGn',
                    s=120, alpha=0.85, edgecolors='gray', lw=0.5)
    cbar = plt.colorbar(sc, ax=ax)
    cbar.set_label("光伏利用率 (%)", fontsize=9)

    for idx in df.index[:5]:
        row = df.loc[idx]
        ax.annotate(
            f"PV{int(row['光伏容量(kW)'])}+ESS{int(row['储能容量(kWh)'])}",
            (row["LCC(万元)"], row["年碳排放(tCO2)"]),
            textcoords="offset points", xytext=(6, 4),
            fontsize=7.5, color='#2c3e50',
            arrowprops=dict(arrowstyle='->', color='gray', lw=0.8)
        )

    sorted_df = df.sort_values("LCC(万元)")
    pareto_pts = []
    min_co2 = float('inf')
    for _, row in sorted_df.iterrows():
        if row["年碳排放(tCO2)"] < min_co2:
            pareto_pts.append(row)
            min_co2 = row["年碳排放(tCO2)"]
    if len(pareto_pts) >= 2:
        px = [r["LCC(万元)"] for r in pareto_pts]
        py = [r["年碳排放(tCO2)"] for r in pareto_pts]
        ax.plot(px, py, 'k--', lw=1.5, label='Pareto 前沿（示意）', alpha=0.6)

    ax.set_xlabel("全生命周期成本 LCC（万元）", fontsize=10)
    ax.set_ylabel("年碳排放量（tCO₂）", fontsize=10)
    ax.set_title("容量配置方案：经济性 vs 碳排放\n（颜色=光伏利用率，标注=综合得分前5名）",
                 fontsize=11, fontweight='bold')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.4)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [图表] Pareto 散点图已保存: {save_path}")
