"""
main_dispatch.py
================
高速公路服务区光储充系统 — 24 小时调度仿真主入口

运行步骤：
  1. Gurobi MILP 精确求解（不可用时自动降级为启发式）
  2. 无储能基线计算
  3. 统计对比分析
  4. 可视化图表输出
  5. 调度明细 CSV 导出

用法：
    python main_dispatch.py [--output-dir <dir>] [--split]
"""

import sys
import io
import argparse
from pathlib import Path

# 确保终端中文输出正常（Windows 环境）
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from highway_energy.optimizer.milp_solver  import solve_milp
from highway_energy.optimizer.heuristic    import heuristic_schedule, baseline_no_storage
from highway_energy.analysis.stats         import analyze, export_schedule_csv
from highway_energy.visualization.dispatch_plot import plot_dispatch, plot_dispatch_split


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="高速公路服务区光储充调度仿真")
    parser.add_argument(
        "--output-dir", default="output",
        help="输出文件目录（默认: ./output）",
    )
    parser.add_argument(
        "--split", action="store_true",
        help="将调度图拆分为 7 张独立子图",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out  = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 64)
    print("  高速公路服务区光储充系统优化调度仿真 — 修复版")
    print("=" * 64)

    # ── Step 1: 求解调度策略 ──────────────────────────────────
    print("\n[1/4] 尝试 MILP 精确求解 (Gurobi)...")
    result = solve_milp()
    if result is None:
        print("      切换至启发式峰谷套利策略...")
        result = heuristic_schedule()
    else:
        print(
            f"      求解成功 | 需量峰值: {result['P_peak']:.1f} kW"
            f" | 目标值: {result['cost']:.2f} 元"
        )

    # ── Step 2: 基线 ──────────────────────────────────────────
    print("\n[2/4] 计算无优化基线...")
    baseline = baseline_no_storage()

    # ── Step 3: 统计分析 ──────────────────────────────────────
    print("\n[3/4] 统计对比分析...")
    stats = analyze(result, baseline, label=result["status"])

    # ── Step 4: 可视化 + 导出 ─────────────────────────────────
    print("\n[4/4] 可视化 + 导出 CSV...")
    schedule_csv = str(out / "schedule_table.csv")

    if args.split:
        plot_dispatch_split(result, baseline, stats, output_dir=str(out))
        output_files = [f"{out}/sub{i}_{name}.png" for i, name in enumerate([
            "power_stack", "soc", "battery_power", "grid_interaction",
            "pv_utilization", "ev_charging", "economic_comparison",
        ], 1)]
    else:
        dispatch_png = str(out / "dispatch_result.png")
        plot_dispatch(result, baseline, stats, save_path=dispatch_png)
        output_files = [dispatch_png]

    df = export_schedule_csv(result, save_path=schedule_csv)

    print("\n  调度明细（前 8 行）：")
    print(df.head(8).to_string(index=False))

    print("\n" + "=" * 64)
    print("  仿真完成！输出文件：")
    for f in output_files:
        print(f"    {f}")
    print(f"    {schedule_csv}")
    print("=" * 64)


if __name__ == "__main__":
    main()
