"""
main_upgrade.py
===============
高速公路服务区光储充系统 — 升级模块主入口
（负荷预测 + 容量枚举配置 + 生命周期分析）

运行步骤：
  1. 生成合成历史负荷数据并进行移动平均预测
  2. 容量枚举双层优化（30 种 PV×ESS 组合）
  3. 生成热力图 + Pareto 散点图
  4. 导出容量配置结果 CSV

用法：
    python main_upgrade.py [--output-dir <dir>] [--history-days <n>]
"""

import sys
import io
import argparse
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from highway_energy.forecast.load_forecast          import (
    generate_history_data, moving_average_forecast, calc_forecast_metrics,
)
from highway_energy.optimizer.capacity              import capacity_optimization
from highway_energy.visualization.forecast_plot     import plot_forecast
from highway_energy.visualization.capacity_plot     import (
    plot_capacity_heatmap, plot_capacity_pareto,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="高速公路服务区容量配置升级模块")
    parser.add_argument("--output-dir",    default="output", help="输出文件目录")
    parser.add_argument("--history-days",  default=60, type=int, help="历史数据天数")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out  = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 64)
    print("  升级模块：负荷预测 + 容量配置枚举优化")
    print("=" * 64)

    # ── Step 1: 负荷预测 ──────────────────────────────────────
    print(f"\n[1/4] 负荷预测（历史 {args.history_days} 天，窗口 7 天）...")
    history  = generate_history_data(days=args.history_days)
    forecast = moving_average_forecast(history, window=7)
    y_true   = history[-1]      # 最后一天作为"实际值"对比
    metrics  = calc_forecast_metrics(y_true, forecast)
    print(f"      预测误差: {metrics}")

    forecast_png = str(out / "forecast_result.png")
    plot_forecast(history, forecast, y_true, metrics, save_path=forecast_png)

    # ── Step 2: 容量枚举 ──────────────────────────────────────
    n_combos = __import__(
        "highway_energy.config.params", fromlist=["PV_RANGE", "ESS_RANGE"]
    )
    n = len(n_combos.PV_RANGE) * len(n_combos.ESS_RANGE)
    print(f"\n[2/4] 容量配置枚举优化（{n} 种组合）...")
    df_cap = capacity_optimization()

    best = df_cap.iloc[0]
    print(f"\n  ★ 综合最优方案（第1名）:")
    print(f"     光伏容量   : {best['光伏容量(kW)']} kW")
    print(f"     储能容量   : {best['储能容量(kWh)']} kWh")
    print(f"     储能功率   : {best['储能功率(kW)']} kW")
    print(f"     CAPEX      : {best['CAPEX(万元)']} 万元")
    print(f"     年运营成本 : {best['年运营成本(万元)']} 万元")
    print(f"     LCC(20年)  : {best['LCC(万元)']} 万元")
    print(f"     年碳排放   : {best['年碳排放(tCO2)']} tCO₂")
    print(f"     光伏利用率 : {best['光伏利用率(%)']} %")
    print(f"     综合得分   : {best['综合得分']}")
    print(f"\n  Top-5 方案对比:")
    print(df_cap.head(5).to_string())

    # ── Step 3: 可视化 ────────────────────────────────────────
    print("\n[3/4] 生成容量配置可视化图表...")
    heatmap_png = str(out / "capacity_heatmap.png")
    pareto_png  = str(out / "capacity_pareto.png")
    plot_capacity_heatmap(df_cap, save_path=heatmap_png)
    plot_capacity_pareto( df_cap, save_path=pareto_png)

    # ── Step 4: 导出 CSV ──────────────────────────────────────
    print("\n[4/4] 导出容量配置结果表...")
    cap_csv = str(out / "capacity_optimization_results.csv")
    df_cap.to_csv(cap_csv, encoding="utf-8-sig", index_label="排名")
    print(f"      已保存: {cap_csv}")

    print("\n" + "=" * 64)
    print("  升级模块运行完成，输出文件：")
    for f in [forecast_png, heatmap_png, pareto_png, cap_csv]:
        print(f"    {f}")
    print("=" * 64)


if __name__ == "__main__":
    main()
