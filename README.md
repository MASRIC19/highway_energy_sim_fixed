# 高速公路服务区光储充系统优化调度仿真

基于 Gurobi MILP 的高速公路服务区光伏-储能-电动汽车充电微电网优化调度模型，支持双层优化（容量规划 + 运行调度）、负荷预测、碳排放评估与多目标经济性分析。

---

## 项目结构

```
new/
├── highway_energy/               # Python 包（主代码）
│   ├── __init__.py
│   ├── main_dispatch.py          # 调度仿真入口
│   ├── main_upgrade.py           # 升级模块入口
│   ├── config/
│   │   ├── __init__.py
│   │   └── params.py             # 全局参数（单一数据源）
│   ├── forecast/
│   │   ├── __init__.py
│   │   └── load_forecast.py      # 负荷预测
│   ├── optimizer/
│   │   ├── __init__.py
│   │   ├── milp_solver.py        # Gurobi MILP 精确求解
│   │   ├── heuristic.py          # 启发式调度 + 基线
│   │   └── capacity.py           # 容量枚举优化
│   ├── analysis/
│   │   ├── __init__.py
│   │   └── stats.py              # 统计分析 + CSV 导出
│   └── visualization/
│       ├── __init__.py
│       ├── style.py              # 共享样式
│       ├── dispatch_plot.py      # 调度仿真图表
│       ├── forecast_plot.py      # 负荷预测图表
│       └── capacity_plot.py      # 容量配置热力图 + Pareto
├── highway_energy_sim_fixed.py   # 原始单文件版（保留参考）
└── README.md
```

---

## 模块说明

### config/params.py — 全局参数

系统所有共享参数与常量，包括：

| 参数类别 | 内容 |
|----------|------|
| 时间 | T=24 小时，dt=1 小时步长 |
| 分时电价 | 谷(0.42) / 平(0.75) / 峰(1.15) 元/kWh，余电上网 0.35 元/kWh |
| 光伏 | PV_CAP=500kW，日总出力 3150kWh 曲线 |
| 储能 | 1000kWh 容量，250kW 充放电功率，SOC 范围 [10%,90%]，效率 95% |
| 基础负荷 | 24 小时逐时负荷曲线（300~600kW） |
| EV 充电 | 20 台 × 120kW，日总需求 18000kWh，柔性权重窗口 |
| 电网 | 购电上限 3000kW，变压器容量 3200kVA，需量电费 38 元/kW·月 |
| 投资成本 | 光伏 4000 元/kW，储能 1200 元/kWh，充电桩 80000 元/台 |
| 碳排放 | 排放因子 0.785 kg CO₂/kWh（华东电网） |
| 枚举范围 | 光伏 300~800kW × 储能 600~1500kWh（共 30 种组合） |

所有其他模块通过 `from highway_energy.config.params import ...` 引用。

---

### forecast/load_forecast.py — 负荷预测

核心函数：

- **`generate_history_data(days=60)`** — 生成 60 天逐小时合成历史负荷。包含工作日/周末差异因子（周末 ×0.90）、季节系数（正弦周期 +12% 振幅）、5% 高斯噪声扰动。返回 `(days, 24)` 数组。

- **`moving_average_forecast(history, window=7)`** — 移动平均预测。用最近 7 天同小时均值预测明日 24 小时负荷。返回 `(24,)` 数组。

- **`calc_forecast_metrics(y_true, y_pred)`** — 三项误差指标：MAE (kW)、RMSE (kW)、MAPE (%)。

---

### optimizer/capacity.py — 容量规划优化

外层枚举搜索 + 内层启发式调度的双层优化：

**经济模型：**

| 函数 | 功能 |
|------|------|
| `calc_capex(pv, ess_kwh, ess_kw, n_piles)` | 初始投资成本 CAPEX |
| `calc_lcc(capex, annual_opex)` | 全生命周期成本 LCC（20 年，8% 折现率） |
| `calc_daily_carbon(P_buy)` | 日碳排放量 (kg CO₂) |
| `calc_annual_carbon(daily_kg)` | 年碳排放量 (tCO₂) |

**内层调度：**

- **`_heuristic_inner(pv_cap, ess_kwh, ess_kw, n_piles)`** — 给定容量配置下运行峰谷套利调度。谷段(0.42)满功率充电，峰段(1.15)满功率放电，平段储能待机。返回日运营成本、需量峰值、光伏利用率、碳排放。

**外层搜索：**

- **`capacity_optimization()`** — 遍历 PV_RANGE × ESS_RANGE（6×5=30 种组合），调用内层调度计算各方案指标。综合得分 = 0.60×归一化LCC + 0.20×归一化碳排放 + 0.20×(1-归一化光伏利用率)。返回按得分排序的 DataFrame。

---

### optimizer/milp_solver.py + heuristic.py — 运行调度优化

固定容量下的 24 小时最优调度：

| 函数 | 方法 | 说明 |
|------|------|------|
| `solve_milp()` | Gurobi MILP | 混合整数线性规划精确求解。决策变量包括购售电、充放电功率、SOC、光伏消纳/弃光、EV 充电功率。目标最小化：购电费 − 售电收益 + 电池衰减 + 需量电费 + 弃光惩罚 |
| `heuristic_schedule()` | 启发式 | Gurobi 不可用时的备用策略。按分时电价规则决策充放电，光伏富余时段额外充电 |
| `baseline_no_storage()` | 解析计算 | 无储能基线。负荷 = 基础负荷 + EV 充电 − 光伏出力，净负荷由电网覆盖 |

约束条件：功率平衡、SOC 递推、充放电互斥、光伏平衡、需量约束、变压器容量、EV 充电窗口、EV 日总需求、初末 SOC 相等。

---

### analysis/stats.py — 经济性分析与数据导出

- **`analyze(result, baseline, label)`** — 对比优化策略与无储能基线，输出：
  - 日购/售电量、峰时购电削减率
  - 需量峰值削减率
  - 购电费用、售电收益、电池衰减成本
  - 需量电费（日均）、弃光惩罚、综合运行费用
  - 日节约金额与比例、年节约估算
  - 光伏利用率、EV 充电满足度

返回 stats 字典供可视化使用。

---

### visualization/ — 可视化

**共享样式（style.py）：** 颜色方案、中文字体配置、`apply_ax_style()` 和 `draw_tou_background()` 辅助函数。

**dispatch_plot.py：** 原调度仿真 7 子图组合

1. **功率堆叠图** — 左侧供电侧（购电+光伏+储能放电）vs 右侧用电侧（基础负荷+EV充电+储能充电+售电）
2. **储能 SOC 曲线** — 24 小时 SOC 变化，标注上下限和初始值
3. **储能充放电功率** — 正=放电(绿)，负=充电(红)
4. **电网交互与分时电价** — 优化购电量 vs 基线购电量，叠加 TOU 电价曲线
5. **光伏出力与消纳** — 总出力、消纳、弃光堆叠
6. **EV 柔性充电调度** — 优化充电功率 vs 窗口上限
7. **经济性对比** — 优化前后四项指标柱状图 + 下降百分比标注

所有图面标注分时电价背景色（谷=绿、平=蓝、峰=红）。

**升级模块图表（forecast_plot.py / capacity_plot.py）：**

| 函数 | 输出 | 说明 |
|------|------|------|
| `plot_forecast()` | forecast_result.png | 左：近 7 天历史+预测+实际值对比；右：逐小时绝对误差柱状图 |
| `plot_capacity_heatmap()` | capacity_heatmap.png | 4 张热力图（LCC/碳排放/光伏利用率/综合得分），绿框标注各指标最优点 |
| `plot_capacity_pareto()` | capacity_pareto.png | LCC vs 碳排放散点图，颜色=光伏利用率，标注 Top-5 方案，示意 Pareto 前沿 |

---

---

### 主入口

两个独立入口脚本，均支持 `--output-dir` 指定输出目录，`--history-days` 控制历史数据天数：

```bash
# 原 Gurobi MILP 调度仿真（固定容量）
python -m highway_energy.main_dispatch --output-dir output

# 升级模块：负荷预测 + 容量枚举 + 多目标评估
python -m highway_energy.main_upgrade --output-dir output --history-days 60
```

**流程：**

| 步骤 | 默认模式 | 升级模式 |
|------|----------|----------|
| 1 | Gurobi MILP 求解 / 启发式备用 | 60 天历史数据生成 + 移动平均预测 + 误差评估 |
| 2 | 无储能基线计算 | 30 种容量组合枚举搜索 |
| 3 | 经济性对比分析 | 热力图 + Pareto 散点图 |
| 4 | 7 子图可视化 + CSV 导出 | 结果表导出 |

---

## 依赖

```bash
pip install numpy pandas matplotlib gurobipy
```

Gurobi 需要独立安装并获取许可证：https://www.gurobi.com/downloads/

Gurobi 不可用时，`--upgrade` 模式使用内置启发式策略，无需 Gurobi。

---

## 输出文件

所有输出统一到 `--output-dir` 指定目录（默认 `output/`）。

| 文件 | 来源 | 说明 |
|------|------|------|
| dispatch_result.png | `main_dispatch` | 原版 7 子图调度仿真 |
| schedule_table.csv | `main_dispatch` | 24 小时调度明细 |
| forecast_result.png | `main_upgrade` | 负荷预测对比图 |
| capacity_heatmap.png | `main_upgrade` | 容量配置热力图 |
| capacity_pareto.png | `main_upgrade` | Pareto 散点图 |
| capacity_optimization_results.csv | `main_upgrade` | 30 种方案明细与排名 |

---

## 理论架构

```
                    ┌──────────────────┐
                    │   历史负荷数据     │
                    │ (60天逐小时生成)   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   负荷预测层      │
                    │ 移动平均 + 误差   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   容量规划层      │
                    │ 枚举搜索 + LCC   │
                    │ + 碳排放 + 综合   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   运行调度层      │
                    │ Gurobi MILP /    │
                    │ 启发式峰谷套利   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   经济性评价层    │
                    │ 日/年节约 +       │
                    │ 光伏利用率 + EV   │
                    └──────────────────┘
```

---

## 修复记录

| 编号 | 修复内容 |
|------|----------|
| FIX-1 | 分时电价时段对齐：谷段 7h（t=0..6），与设计说明一致 |
| FIX-2 | 需量电费月→日折算：38/30≈1.267 元/kW·日 |
| FIX-3 | EV 充电窗口上限限幅：权重 ≤1.0，窗口 ≤2400kW |
| FIX-4 | 光伏出力曲线日总 3150kWh，有效时段 06:00-16:00 |
