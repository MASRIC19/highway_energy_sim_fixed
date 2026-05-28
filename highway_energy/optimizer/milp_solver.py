"""
optimizer/milp_solver.py
========================
Gurobi MILP 精确求解器

决策变量：
  P_buy, P_sell    — 购售电功率
  P_ch, P_dis      — 充放电功率
  SOC              — 荷电状态
  u                — 充放电互斥二值变量
  P_pv_use, P_pv_curt — 光伏消纳/弃光
  P_ev             — EV 充电功率
  P_peak           — 需量峰值（用于需量电费）

目标：最小化日综合运行成本（购电 - 售电 + 电池衰减 + 需量电费 + 弃光惩罚）
"""

from __future__ import annotations
from typing import Optional

import numpy as np

from highway_energy.config.params import (
    T, DT, TOU, C_SELL, DEMAND_CHARGE_DAILY,
    PV_OUT,
    E_CAP, P_CH_MAX, P_DIS_MAX, ETA_CH, ETA_DIS,
    SOC0, SOC_MIN, SOC_MAX, BATTERY_DEG_COST,
    BASE_LOAD, P_EV_MAX, EV_ENERGY_DEMAND, EV_WEIGHT,
    P_GRID_MAX, TRANSFORMER_CAPACITY, PV_CURTAIL_PENALTY,
)


def solve_milp() -> Optional[dict]:
    """
    调用 Gurobi 求解 MILP。

    Returns
    -------
    dict
        包含各决策变量最优值的字典；若 Gurobi 不可用或求解失败则返回 None。
    """
    try:
        from gurobipy import Model, GRB, quicksum
    except ImportError:
        print("  [MILP] Gurobi 未安装，跳过精确求解")
        return None

    model = Model("Highway_MILP_Fixed")
    model.setParam("OutputFlag", 0)
    model.setParam("MIPGap",    0.001)
    model.setParam("TimeLimit", 300)

    # ── 决策变量 ────────────────────────────────────────────
    P_buy     = model.addVars(T, lb=0, ub=P_GRID_MAX,  name="P_buy")
    P_sell    = model.addVars(T, lb=0, ub=P_GRID_MAX,  name="P_sell")
    P_ch      = model.addVars(T, lb=0, ub=P_CH_MAX,    name="P_ch")
    P_dis     = model.addVars(T, lb=0, ub=P_DIS_MAX,   name="P_dis")
    SOC       = model.addVars(T + 1, lb=SOC_MIN, ub=SOC_MAX, name="SOC")
    u         = model.addVars(T, vtype=GRB.BINARY,     name="u")
    P_pv_use  = model.addVars(T, lb=0,                 name="P_pv_use")
    P_pv_curt = model.addVars(T, lb=0,                 name="P_pv_curt")
    P_ev      = model.addVars(T, lb=0, ub=P_EV_MAX,    name="P_ev")
    P_peak    = model.addVar(lb=0,                      name="P_peak")

    # ── 目标函数（FIX-2：demand_charge 已为日均值）────────────
    obj = (
        quicksum(TOU[t] * P_buy[t] * DT for t in range(T))
        - quicksum(C_SELL * P_sell[t] * DT for t in range(T))
        + quicksum(BATTERY_DEG_COST * (P_ch[t] + P_dis[t]) for t in range(T))
        + DEMAND_CHARGE_DAILY * P_peak
        + quicksum(PV_CURTAIL_PENALTY * P_pv_curt[t] for t in range(T))
    )
    model.setObjective(obj, GRB.MINIMIZE)

    # ── 初末 SOC ────────────────────────────────────────────
    model.addConstr(SOC[0] == SOC0, "InitSOC")
    model.addConstr(SOC[T] == SOC0, "TermSOC")

    # ── 逐时段约束 ──────────────────────────────────────────
    for t in range(T):
        # 功率平衡
        model.addConstr(
            P_buy[t] - P_sell[t] + P_pv_use[t] + P_dis[t]
            == BASE_LOAD[t] + P_ev[t] + P_ch[t],
            f"PwrBal_{t}",
        )
        # SOC 递推
        model.addConstr(
            SOC[t + 1]
            == SOC[t]
            + ETA_CH * P_ch[t] * DT / E_CAP
            - P_dis[t] * DT / (ETA_DIS * E_CAP),
            f"SOC_{t}",
        )
        # 充放电互斥（Big-M，u=1 → 充电，u=0 → 放电）
        model.addConstr(P_ch[t]  <= u[t]       * P_CH_MAX,  f"ChLim_{t}")
        model.addConstr(P_dis[t] <= (1 - u[t]) * P_DIS_MAX, f"DisLim_{t}")
        # 光伏平衡
        model.addConstr(
            P_pv_use[t] + P_pv_curt[t] == PV_OUT[t], f"PV_{t}"
        )
        # 需量追踪
        model.addConstr(P_buy[t] <= P_peak, f"Peak_{t}")
        # 变压器容量
        model.addConstr(P_buy[t] <= TRANSFORMER_CAPACITY, f"Trans_{t}")
        # EV 充电窗口（FIX-3：EV_WEIGHT 已裁剪 ≤1.0）
        model.addConstr(
            P_ev[t] <= EV_WEIGHT[t] * P_EV_MAX, f"EVWin_{t}"
        )

    # EV 日总需求（≥ 确保满足，= 也可用，此处保留下界以增加调度弹性）
    model.addConstr(
        quicksum(P_ev[t] * DT for t in range(T)) >= EV_ENERGY_DEMAND,
        "EVTotal",
    )

    model.optimize()

    if model.Status == GRB.OPTIMAL:
        return {
            "status"    : "Optimal (MILP)",
            "P_buy"     : [P_buy[t].X     for t in range(T)],
            "P_sell"    : [P_sell[t].X    for t in range(T)],
            "P_ch"      : [P_ch[t].X      for t in range(T)],
            "P_dis"     : [P_dis[t].X     for t in range(T)],
            "SOC"       : [SOC[t].X       for t in range(T + 1)],
            "u"         : [u[t].X         for t in range(T)],
            "P_pv_use"  : [P_pv_use[t].X  for t in range(T)],
            "P_pv_curt" : [P_pv_curt[t].X for t in range(T)],
            "P_ev"      : [P_ev[t].X      for t in range(T)],
            "P_peak"    : P_peak.X,
            "cost"      : model.ObjVal,
            "P_grid"    : [P_buy[t].X - P_sell[t].X for t in range(T)],
        }

    print(f"  [MILP] 求解状态: {model.Status}，改用启发式")
    return None
