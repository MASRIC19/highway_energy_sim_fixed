"""
高速公路服务区光储充系统 — 运行调度优化模块
包含：Gurobi MILP 精确求解、启发式峰谷套利、无储能基线
"""

import numpy as np
from config import (
    T, dt, TOU, c_sell, demand_charge, DEMAND_CHARGE_MONTHLY,
    PV_out, PV_CAP,
    E_cap, P_ch_max, P_dis_max, eta_ch, eta_dis,
    SOC0, SOC_min, SOC_max, battery_deg_cost,
    Base_load, EV_weight, P_ev_max, EV_energy_demand,
    P_grid_max, transformer_capacity,
)


def solve_milp():
    """Gurobi MILP 精确求解 (固定容量 PV_CAP / E_cap)"""
    try:
        from gurobipy import Model, GRB, quicksum
    except ImportError:
        print("  Gurobi 未安装，使用启发式策略")
        return None

    model = Model("Highway_MILP_Modular")
    model.setParam("OutputFlag", 0)
    model.setParam("MIPGap", 0.001)
    model.setParam("TimeLimit", 300)

    P_buy     = model.addVars(T, lb=0, ub=P_grid_max, name="P_buy")
    P_sell    = model.addVars(T, lb=0, ub=P_grid_max, name="P_sell")
    P_ch      = model.addVars(T, lb=0, ub=P_ch_max, name="P_ch")
    P_dis     = model.addVars(T, lb=0, ub=P_dis_max, name="P_dis")
    SOC       = model.addVars(T + 1, lb=SOC_min, ub=SOC_max, name="SOC")
    u         = model.addVars(T, vtype=GRB.BINARY, name="u")
    P_pv_use  = model.addVars(T, lb=0, name="P_pv_use")
    P_pv_curt = model.addVars(T, lb=0, name="P_pv_curt")
    P_ev      = model.addVars(T, lb=0, ub=P_ev_max, name="P_ev")
    P_peak    = model.addVar(lb=0, name="P_peak")

    obj = (
        quicksum(TOU[t] * P_buy[t] * dt for t in range(T))
        - quicksum(c_sell * P_sell[t] * dt for t in range(T))
        + quicksum(battery_deg_cost * (P_ch[t] + P_dis[t]) for t in range(T))
        + demand_charge * P_peak
        + quicksum(0.02 * P_pv_curt[t] for t in range(T))
    )
    model.setObjective(obj, GRB.MINIMIZE)

    model.addConstr(SOC[0] == SOC0, "InitSOC")
    model.addConstr(SOC[T] == SOC0, "TermSOC")

    for t in range(T):
        model.addConstr(
            P_buy[t] - P_sell[t] + P_pv_use[t] + P_dis[t]
            == Base_load[t] + P_ev[t] + P_ch[t], f"PB_{t}")
        model.addConstr(
            SOC[t + 1] == SOC[t]
            + eta_ch * P_ch[t] * dt / E_cap
            - P_dis[t] * dt / (eta_dis * E_cap), f"SOC_{t}")
        model.addConstr(P_ch[t] <= u[t] * P_ch_max, f"ChLim_{t}")
        model.addConstr(P_dis[t] <= (1 - u[t]) * P_dis_max, f"DisLim_{t}")
        model.addConstr(P_pv_use[t] + P_pv_curt[t] == PV_out[t], f"PV_{t}")
        model.addConstr(P_buy[t] <= P_peak, f"Peak_{t}")
        model.addConstr(P_buy[t] <= transformer_capacity, f"Trans_{t}")
        model.addConstr(P_ev[t] <= EV_weight[t] * P_ev_max, f"EVWin_{t}")

    model.addConstr(
        quicksum(P_ev[t] * dt for t in range(T)) >= EV_energy_demand,
        "EVTotal")

    model.optimize()

    if model.Status == GRB.OPTIMAL:
        return {
            'status': 'Optimal (MILP)',
            'P_buy': [P_buy[t].X for t in range(T)],
            'P_sell': [P_sell[t].X for t in range(T)],
            'P_ch': [P_ch[t].X for t in range(T)],
            'P_dis': [P_dis[t].X for t in range(T)],
            'SOC': [SOC[t].X for t in range(T + 1)],
            'u': [u[t].X for t in range(T)],
            'P_pv_use': [P_pv_use[t].X for t in range(T)],
            'P_pv_curt': [P_pv_curt[t].X for t in range(T)],
            'P_ev': [P_ev[t].X for t in range(T)],
            'P_peak': P_peak.X,
            'cost': model.ObjVal,
            'P_grid': [P_buy[t].X - P_sell[t].X for t in range(T)],
        }

    print(f"  求解状态: {model.Status}，改用启发式")
    return None


def heuristic_schedule():
    """启发式峰谷套利 (Gurobi 不可用时的备用策略)"""
    P_buy_h = np.zeros(T)
    P_sell_h = np.zeros(T)
    P_ch_h = np.zeros(T)
    P_dis_h = np.zeros(T)
    SOC_h = np.zeros(T + 1)
    SOC_h[0] = SOC0

    w_sum = np.sum(EV_weight)
    P_ev_h = EV_weight / w_sum * EV_energy_demand if w_sum > 0 else np.zeros(T)

    P_pv_use_h = np.zeros(T)
    P_pv_curt_h = np.zeros(T)

    for t in range(T):
        net_load = Base_load[t] + P_ev_h[t] - PV_out[t]
        soc = SOC_h[t]

        if TOU[t] <= 0.42:
            p_ch = min(P_ch_max, (SOC_max - soc) * E_cap / eta_ch / dt)
            p_ch = max(0.0, p_ch)
            p_dis = 0.0
        elif TOU[t] >= 1.15:
            p_dis = min(P_dis_max, (soc - SOC_min) * E_cap * eta_dis / dt)
            p_dis = max(0.0, p_dis)
            p_ch = 0.0
        else:
            p_ch = p_dis = 0.0

        grid_before = net_load + p_ch - p_dis
        if grid_before < 0:
            extra = -grid_before
            p_ch += min(extra, P_ch_max - p_ch,
                        (SOC_max - soc) * E_cap / eta_ch / dt)

        grid = net_load + p_ch - p_dis
        if grid >= 0:
            P_buy_h[t] = min(grid, P_grid_max)
            P_sell_h[t] = 0.0
        else:
            P_buy_h[t] = 0.0
            P_sell_h[t] = min(-grid, P_grid_max)

        P_pv_use_h[t] = max(0.0, min(PV_out[t],
                             Base_load[t] + P_ev_h[t] + p_ch - P_sell_h[t]))
        P_pv_curt_h[t] = PV_out[t] - P_pv_use_h[t]
        P_ch_h[t] = p_ch
        P_dis_h[t] = p_dis
        SOC_h[t + 1] = np.clip(
            soc + (eta_ch * p_ch - p_dis / eta_dis) * dt / E_cap,
            SOC_min, SOC_max)

    cost = (np.sum(TOU * P_buy_h * dt)
            - np.sum(c_sell * P_sell_h * dt)
            + np.sum(battery_deg_cost * (P_ch_h + P_dis_h))
            + demand_charge * np.max(P_buy_h)
            + np.sum(0.02 * P_pv_curt_h))

    return {
        'status': 'Heuristic',
        'P_buy': P_buy_h.tolist(),
        'P_sell': P_sell_h.tolist(),
        'P_ch': P_ch_h.tolist(),
        'P_dis': P_dis_h.tolist(),
        'SOC': SOC_h.tolist(),
        'P_pv_use': P_pv_use_h.tolist(),
        'P_pv_curt': P_pv_curt_h.tolist(),
        'P_ev': P_ev_h.tolist(),
        'P_peak': float(np.max(P_buy_h)),
        'cost': cost,
        'P_grid': (P_buy_h - P_sell_h).tolist(),
    }


def baseline_no_storage():
    """无储能基线"""
    w_sum = np.sum(EV_weight)
    P_ev_b = EV_weight / w_sum * EV_energy_demand if w_sum > 0 else np.zeros(T)
    net = Base_load + P_ev_b - PV_out
    P_buy_b = np.maximum(0.0, net)
    P_sell_b = np.minimum(np.maximum(0.0, -net), P_grid_max)
    pv_curtail = np.maximum(0.0, PV_out - Base_load - P_ev_b + P_sell_b)
    cost = (np.sum(TOU * P_buy_b * dt)
            - np.sum(c_sell * P_sell_b * dt)
            + demand_charge * np.max(P_buy_b)
            + np.sum(0.02 * pv_curtail))
    return {
        'P_grid': P_buy_b - P_sell_b,
        'P_buy': P_buy_b,
        'P_sell': P_sell_b,
        'P_ev': P_ev_b,
        'cost': cost,
    }
