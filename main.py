"""
高速公路服务区光储充系统 — 主入口

用法:
    python main.py              → 原 Gurobi MILP 调度仿真
    python main.py --upgrade    → 负荷预测 + 容量枚举优化
"""

import sys
from operation_optimizer import solve_milp, heuristic_schedule, baseline_no_storage
from economic_analysis import analyze
from visualization import plot_results, plot_forecast, plot_capacity_heatmap, plot_capacity_pareto
from data_export import export_table


def run_original():
    """运行原有 Gurobi MILP 调度仿真"""
    print("\n" + "=" * 64)
    print("  高速公路服务区光储充系统优化调度仿真 (Gurobi)")
    print("=" * 64)

    print("\n[1/4] 尝试 MILP 精确求解 (Gurobi)...")
    result = solve_milp()
    if result is None:
        print("      切换至启发式策略...")
        result = heuristic_schedule()
    else:
        print(f"      求解成功 | 需量峰值: {result['P_peak']:.1f} kW | "
              f"目标值: {result['cost']:.2f} 元")

    print("\n[2/4] 计算无优化基线...")
    baseline = baseline_no_storage()

    print("\n[3/4] 统计分析...")
    stats = analyze(result, baseline, result['status'])

    print("\n[4/4] 可视化 + 导出...")
    plot_results(result, baseline, stats, "highway_energy_sim_output")
    df = export_table(result, "schedule_table_output.csv")

    print("\n  调度明细（前 8 行）：")
    print(df.head(8).to_string(index=False))
    print("\n  仿真完成！输出: highway_energy_sim_output.png, schedule_table_output.csv")


def run_upgrade():
    """运行升级模块：负荷预测 + 容量枚举优化"""
    from load_forecast import generate_history_data, moving_average_forecast, calc_forecast_metrics
    from capacity_optimizer import capacity_optimization

    print("\n" + "=" * 64)
    print("  升级模块：负荷预测 + 容量枚举 + 多目标评估")
    print("=" * 64)

    print("\n[1/4] 负荷预测模块 ...")
    history = generate_history_data(days=60)
    forecast = moving_average_forecast(history, window=7)
    y_true = history[-1]
    metrics = calc_forecast_metrics(y_true, forecast)

    print(f"       预测误差指标: {metrics}")
    plot_forecast(history, forecast, y_true, metrics,
                  save_path="forecast_result.png")

    print("\n[2/4] 容量配置枚举优化（30种组合）...")
    df_cap = capacity_optimization()

    best = df_cap.iloc[0]
    print(f"\n  ★ 综合最优方案（综合得分第1名）:")
    print(f"     光伏容量  : {best['光伏容量(kW)']} kW")
    print(f"     储能容量  : {best['储能容量(kWh)']} kWh")
    print(f"     储能功率  : {best['储能功率(kW)']} kW")
    print(f"     CAPEX     : {best['CAPEX(万元)']} 万元")
    print(f"     年运营成本: {best['年运营成本(万元)']} 万元")
    print(f"     LCC(20年) : {best['LCC(万元)']} 万元")
    print(f"     年碳排放  : {best['年碳排放(tCO2)']} tCO2")
    print(f"     光伏利用率: {best['光伏利用率(%)']} %")

    print("\n  Top-5 方案对比:")
    print(df_cap.head(5).to_string())

    print("\n[3/4] 生成可视化图表...")
    plot_capacity_heatmap(df_cap, save_path="capacity_heatmap.png")
    plot_capacity_pareto(df_cap, save_path="capacity_pareto.png")

    print("\n[4/4] 导出容量配置结果表...")
    df_cap.to_csv("capacity_optimization_results.csv",
                  encoding="utf-8-sig", index_label="排名")
    print("       已保存: capacity_optimization_results.csv")

    print("\n" + "=" * 64)
    print("  升级模块运行完成")
    print("  输出文件:")
    print("    forecast_result.png                — 负荷预测图")
    print("    capacity_heatmap.png               — 容量配置热力图")
    print("    capacity_pareto.png                — Pareto 散点图")
    print("    capacity_optimization_results.csv  — 所有方案明细")
    print("=" * 64)


if __name__ == "__main__":
    if "--upgrade" in sys.argv:
        run_upgrade()
    else:
        run_original()
