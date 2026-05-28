"""
optimizer/heuristic.py
======================
基于峰谷套利规则的启发式调度策略（Gurobi 不可用时的备用方案）
以及无储能基线场景计算。

修复项：
  - FIX-B1: 光伏消纳计算加 max(0, ...) 防止负值
  - FIX-B2: 功率平衡溢出时打印警告
"""

from __future__ import annotations

import numpy as np

from highway_energy.config.params import (
    T, DT, TOU, C_SELL, DEMAND_CHARGE_DAILY,
    PV_OUT,
    E_CAP, P_CH_MAX, P_DIS_MAX, ETA_CH, ETA_DIS,
    SOC0, SOC_MIN, SOC_MAX, BATTERY_DEG_COST,
    BASE_LOAD, P_EV_MAX, EV_ENERGY_DEMAND, EV_WEIGHT,
    P_GRID_MAX, PV_CURTAIL_PENALTY,
)


def _distribute_ev() -> np.ndarray:
    """按权重比例分配 EV 日总需求到各时段。"""
    w_sum = EV_WEIGHT.sum()
    if w_sum <= 0:
        return np.zeros(T)
    p_ev = EV_WEIGHT / w_sum * EV_ENERGY_DEMAND
    # 确保任意时段不超过硬件上限
    p_ev = np.minimum(p_ev, EV_WEIGHT * P_EV_MAX)
    return p_ev


def heuristic_schedule() -> dict:
    """
    规则调度：
      - 谷段（TOU ≤ 0.42）：满功率充电
      - 峰段（TOU ≥ 1.15）：满功率放电
      - 平段：不动储能；若有光伏富余则额外充电

    Returns
    -------
    dict
        与 solve_milp 返回格式相同的调度结果字典。
    """
    P_buy_h      = np.zeros(T)
    P_sell_h     = np.zeros(T)
    P_ch_h       = np.zeros(T)
    P_dis_h      = np.zeros(T)
    SOC_h        = np.zeros(T + 1)
    P_pv_use_h   = np.zeros(T)
    P_pv_curt_h  = np.zeros(T)
    SOC_h[0]     = SOC0

    P_ev_h = _distribute_ev()

    for t in range(T):
        soc = SOC_h[t]

        # ── 充放电决策 ──────────────────────────────────────
        if TOU[t] <= 0.42:           # 谷段：充电
            p_ch = min(
                P_CH_MAX,
                max(0.0, (SOC_MAX - soc) * E_CAP / ETA_CH / DT),
            )
            p_dis = 0.0
        elif TOU[t] >= 1.15:         # 峰段：放电
            p_dis = min(
                P_DIS_MAX,
                max(0.0, (soc - SOC_MIN) * E_CAP * ETA_DIS / DT),
            )
            p_ch = 0.0
        else:                        # 平段：静止
            p_ch = p_dis = 0.0

        # ── 光伏富余时额外充电 ──────────────────────────────
        net_before_extra = BASE_LOAD[t] + P_ev_h[t] - PV_OUT[t] + p_ch - p_dis
        if net_before_extra < 0:     # 光伏富余 → 补充充电
            extra = -net_before_extra
            extra = min(
                extra,
                P_CH_MAX - p_ch,
                max(0.0, (SOC_MAX - soc) * E_CAP / ETA_CH / DT) - p_ch,
            )
            p_ch += max(0.0, extra)

        # ── 功率平衡 ────────────────────────────────────────
        grid = BASE_LOAD[t] + P_ev_h[t] - PV_OUT[t] + p_ch - p_dis
        if grid >= 0:
            P_buy_h[t]  = min(grid, P_GRID_MAX)
            P_sell_h[t] = 0.0
            if grid > P_GRID_MAX:
                print(
                    f"  [警告] t={t:02d}: 需购电 {grid:.0f} kW 超过电网上限 "
                    f"{P_GRID_MAX:.0f} kW，已截断"
                )
        else:
            P_buy_h[t]  = 0.0
            P_sell_h[t] = min(-grid, P_GRID_MAX)

        # ── 光伏消纳 / 弃光（FIX-B1：加 max(0,...) 防负值）──
        pv_consumed = BASE_LOAD[t] + P_ev_h[t] + p_ch - P_sell_h[t]
        P_pv_use_h[t]  = max(0.0, min(PV_OUT[t], pv_consumed))
        P_pv_curt_h[t] = max(0.0, PV_OUT[t] - P_pv_use_h[t])

        P_ch_h[t]  = p_ch
        P_dis_h[t] = p_dis
        SOC_h[t + 1] = np.clip(
            soc + (ETA_CH * p_ch - p_dis / ETA_DIS) * DT / E_CAP,
            SOC_MIN, SOC_MAX,
        )

    cost = (
        np.sum(TOU * P_buy_h * DT)
        - np.sum(C_SELL * P_sell_h * DT)
        + np.sum(BATTERY_DEG_COST * (P_ch_h + P_dis_h))
        + DEMAND_CHARGE_DAILY * np.max(P_buy_h)
        + np.sum(PV_CURTAIL_PENALTY * P_pv_curt_h)
    )

    return {
        "status"    : "Heuristic",
        "P_buy"     : P_buy_h.tolist(),
        "P_sell"    : P_sell_h.tolist(),
        "P_ch"      : P_ch_h.tolist(),
        "P_dis"     : P_dis_h.tolist(),
        "SOC"       : SOC_h.tolist(),
        "u"         : [0] * T,            # 启发式无二值变量
        "P_pv_use"  : P_pv_use_h.tolist(),
        "P_pv_curt" : P_pv_curt_h.tolist(),
        "P_ev"      : P_ev_h.tolist(),
        "P_peak"    : float(np.max(P_buy_h)),
        "cost"      : float(cost),
        "P_grid"    : (P_buy_h - P_sell_h).tolist(),
    }


def baseline_no_storage() -> dict:
    """
    无储能基线场景：EV 按权重比例充电，无储能套利。

    Returns
    -------
    dict
        基线场景各功率向量及日总成本。
    """
    P_ev_b = _distribute_ev()
    net    = BASE_LOAD + P_ev_b - PV_OUT

    P_buy_b  = np.maximum(0.0, net)
    P_buy_b  = np.minimum(P_buy_b, P_GRID_MAX)
    P_sell_b = np.maximum(0.0, -net)
    P_sell_b = np.minimum(P_sell_b, P_GRID_MAX)

    # 弃光 = 光伏出力 - 实际消纳（消纳 = 出力 - 向网售出）
    # FIX-B3: 正确符号：pv_curtail = PV_OUT - (Base+EV+売) 当PV过剩时
    pv_curtail = np.maximum(0.0, PV_OUT - BASE_LOAD - P_ev_b - P_sell_b)

    cost = (
        np.sum(TOU * P_buy_b * DT)
        - np.sum(C_SELL * P_sell_b * DT)
        + DEMAND_CHARGE_DAILY * np.max(P_buy_b)
        + np.sum(PV_CURTAIL_PENALTY * pv_curtail)
    )

    return {
        "P_grid"      : P_buy_b - P_sell_b,
        "P_buy"       : P_buy_b,
        "P_sell"      : P_sell_b,
        "P_ev"        : P_ev_b,
        "P_pv_curtail": pv_curtail,
        "cost"        : float(cost),
    }
