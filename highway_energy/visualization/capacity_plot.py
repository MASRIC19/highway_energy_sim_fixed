"""
visualization/capacity_plot.py
================================
容量配置结果可视化：
  plot_capacity_heatmap — 4 张热力图（LCC / 碳排放 / 光伏利用率 / 综合得分）
  plot_capacity_pareto  — 经济 vs 碳排放散点图（含 Pareto 前沿示意线）
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from highway_energy.visualization.style import configure_fonts


def plot_capacity_heatmap(df: pd.DataFrame,
                          save_path: str = "capacity_heatmap.png") -> None:
    """
    绘制容量配置多目标评估热力图（2×2，4 个指标）。

    Parameters
    ----------
    df        : capacity_optimization() 返回的 DataFrame
    save_path : 图像输出路径
    """
    configure_fonts()

    pvs  = sorted(df["光伏容量(kW)"].unique())
    esss = sorted(df["储能容量(kWh)"].unique())

    def _pivot(col: str) -> pd.DataFrame:
        return df.pivot_table(
            index="储能容量(kWh)", columns="光伏容量(kW)", values=col
        )

    targets = [
        ("LCC(万元)",      "全生命周期成本 (万元)",  "YlOrRd",   True),
        ("年碳排放(tCO2)", "年碳排放量 (tCO2)",      "Greens",   True),
        ("光伏利用率(%)",  "光伏利用率 (%)",          "Blues",    False),
        ("综合得分",       "综合得分（越低越优）",    "RdYlGn_r", True),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    for ax, (col, title, cmap, annot_dark) in zip(axes.flatten(), targets):
        mat = _pivot(col)
        im  = ax.imshow(mat.values, cmap=cmap, aspect="auto")
        plt.colorbar(im, ax=ax, shrink=0.85)

        ax.set_xticks(range(len(pvs)))
        ax.set_xticklabels([str(p) for p in pvs], fontsize=9)
        ax.set_yticks(range(len(esss)))
        ax.set_yticklabels([str(e) for e in esss], fontsize=9)
        ax.set_xlabel("光伏容量 (kW)", fontsize=9)
        ax.set_ylabel("储能容量 (kWh)", fontsize=9)
        ax.set_title(title, fontsize=10, fontweight="bold")

        # 数值标注
        for i in range(len(esss)):
            for j in range(len(pvs)):
                val = mat.values[i, j]
                txt_color = "white" if annot_dark else "black"
                ax.text(j, i, f"{val:.1f}", ha="center", va="center",
                        fontsize=8, color=txt_color)

        # 最优点（最小值）绿框
        best_idx = np.unravel_index(mat.values.argmin(), mat.values.shape)
        ax.add_patch(plt.Rectangle(
            (best_idx[1] - 0.5, best_idx[0] - 0.5), 1, 1,
            fill=False, edgecolor="lime", lw=3,
        ))

    fig.suptitle(
        "光储容量配置多目标评估热力图\n（绿框 = 该指标最优点）",
        fontsize=13, fontweight="bold",
    )
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [图表] 容量配置热力图已保存: {save_path}")


def plot_capacity_pareto(df: pd.DataFrame,
                         save_path: str = "capacity_pareto.png") -> None:
    """
    绘制经济性 vs 碳排放散点图，含简单 Pareto 前沿线。

    Parameters
    ----------
    df        : capacity_optimization() 返回的 DataFrame
    save_path : 图像输出路径
    """
    configure_fonts()

    fig, ax = plt.subplots(figsize=(8, 6))

    sc = ax.scatter(
        df["LCC(万元)"], df["年碳排放(tCO2)"],
        c=df["光伏利用率(%)"], cmap="RdYlGn",
        s=120, alpha=0.85, edgecolors="gray", lw=0.5,
    )
    cbar = plt.colorbar(sc, ax=ax)
    cbar.set_label("光伏利用率 (%)", fontsize=9)

    # 标注综合得分前 5 名
    top5 = df.head(5)
    for idx in top5.index:
        row = df.loc[idx]
        ax.annotate(
            f"PV{int(row['光伏容量(kW)'])}+ESS{int(row['储能容量(kWh)'])}",
            (row["LCC(万元)"], row["年碳排放(tCO2)"]),
            textcoords="offset points", xytext=(6, 4),
            fontsize=7.5, color="#2c3e50",
            arrowprops=dict(arrowstyle="->", color="gray", lw=0.8),
        )

    # Pareto 前沿（按 LCC 升序取不被支配点）
    sorted_df = df.sort_values("LCC(万元)")
    pareto_pts: list[pd.Series] = []
    min_co2 = float("inf")
    for _, row in sorted_df.iterrows():
        if row["年碳排放(tCO2)"] < min_co2:
            pareto_pts.append(row)
            min_co2 = row["年碳排放(tCO2)"]

    plot_count = 0
    if len(pareto_pts) >= 2:
        px = [r["LCC(万元)"]      for r in pareto_pts]
        py = [r["年碳排放(tCO2)"]  for r in pareto_pts]
        ax.plot(px, py, "k--", lw=1.5, label="Pareto 前沿（示意）", alpha=0.6)
        plot_count += 1

    ax.set_xlabel("全生命周期成本 LCC（万元）", fontsize=10)
    ax.set_ylabel("年碳排放量（tCO2）", fontsize=10)
    ax.set_title(
        "容量配置方案：经济性 vs 碳排放\n（颜色=光伏利用率，标注=综合得分前5名）",
        fontsize=11, fontweight="bold",
    )
    if plot_count > 0:
        ax.legend(fontsize=9)
    ax.grid(True, alpha=0.4)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [图表] Pareto 散点图已保存: {save_path}")
