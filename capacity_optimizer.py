"""
高速公路服务区光储充系统 — 容量优化模块
包含：投资成本模型、生命周期成本、碳排放、启发式内层调度、容量枚举
"""

import numpy as np
import pandas as pd
from config import (
    T, dt, TOU, c_sell, demand_charge,
    Base_load, EV_weight, P_ev_max, EV_energy_demand,
    eta_ch, eta_dis, SOC_min, SOC_max, SOC0,
    battery_deg_cost, P_grid_max,
    PV_COST_PER_KW, ESS_COST_PER_KWH, ESS_COST_PER_KW, EV_PILE_COST,
    LIFESPAN_YR, DISCOUNT_RATE, CARBON_FACTOR,
    PV_RANGE, ESS_RANGE, N_PILES,
)


def calc_capex(pv_cap_kw: float,
               ess_kwh: float,
               ess_kw: float,
               n_piles: int) -> float:
    """初始投资成本 (CAPEX)，单位：元"""
    return (pv_cap_kw * PV_COST_PER_KW
            + ess_kwh * ESS_COST_PER_KWH
            + ess_kw * ESS_COST_PER_KW
            + n_piles * EV_PILE_COST)


def calc_lcc(capex: float, annual_opex: float) -> float:
    """
    全生命周期成本 (LCC) = CAPEX + 年运营成本折现求和
    使用等额年金现值系数 (APVF)
    """
    if DISCOUNT_RATE == 0:
        apvf = LIFESPAN_YR
    else:
        apvf = (1 - (1 + DISCOUNT_RATE) ** (-LIFESPAN_YR)) / DISCOUNT_RATE
    return capex + annual_opex * apvf


def calc_daily_carbon(P_buy_arr: np.ndarray) -> float:
    """日碳排放量 (kg CO2) = Σ P_buy[t] × dt × carbon_factor"""
    return float(np.sum(P_buy_arr) * dt * CARBON_FACTOR)


def calc_annual_carbon(daily_carbon_kg: float) -> float:
    """年碳排放 (tCO2)"""
    return daily_carbon_kg * 365 / 1000


def _heuristic_inner(pv_cap: float,
                     ess_kwh: float,
                     ess_kw: float,
                     n_piles: int,
                     base_load: np.ndarray = None,
                     pv_profile_norm: np.ndarray = None) -> dict:
    """
    给定容量配置，运行启发式峰谷套利调度。
    pv_profile_norm: 归一化光伏曲线 (峰值=1)，shape=(24,)
    返回：日运营成本、碳排放、光伏利用率等指标
    """
    if base_load is None:
        base_load = Base_load.copy()
    if pv_profile_norm is None:
        _raw = np.array([0, 0, 0, 0, 0, 50, 120, 220, 350, 450, 500,
                          480, 420, 300, 180, 80, 0, 0, 0, 0, 0, 0, 0, 0],
                        dtype=float)
        pv_profile_norm = _raw / 500.0

    pv_out    = pv_profile_norm * pv_cap
    p_ch_max  = ess_kw
    p_dis_max = ess_kw
    ev_total  = EV_energy_demand

    w_sum = EV_weight.sum()
    p_ev = EV_weight / w_sum * ev_total if w_sum > 0 else np.zeros(T)

    P_buy = np.zeros(T)
    P_sell = np.zeros(T)
    P_ch = np.zeros(T)
    P_dis = np.zeros(T)
    P_pv_use = np.zeros(T)
    P_pv_curt = np.zeros(T)
    soc = SOC0

    for t in range(T):
        price = TOU[t]
        if price <= 0.42:
            p_c = min(p_ch_max,
                      (SOC_max - soc) * ess_kwh / eta_ch / dt)
            p_d = 0.0
        elif price >= 1.15:
            p_d = min(p_dis_max,
                      (soc - SOC_min) * ess_kwh * eta_dis / dt)
            p_c = 0.0
        else:
            p_c = p_d = 0.0

        net = base_load[t] + p_ev[t] - pv_out[t] + p_c - p_d
        if net >= 0:
            P_buy[t] = min(net, P_grid_max)
        else:
            P_sell[t] = min(-net, P_grid_max)

        P_pv_use[t] = min(pv_out[t],
                          base_load[t] + p_ev[t] + p_c - P_sell[t])
        P_pv_curt[t] = max(0.0, pv_out[t] - P_pv_use[t])
        P_ch[t] = p_c
        P_dis[t] = p_d
        soc = np.clip(soc + (eta_ch * p_c - p_d / eta_dis) * dt / ess_kwh,
                      SOC_min, SOC_max)

    cost = (np.sum(TOU * P_buy * dt)
            - np.sum(c_sell * P_sell * dt)
            + np.sum(battery_deg_cost * (P_ch + P_dis))
            + demand_charge * np.max(P_buy)
            + np.sum(0.02 * P_pv_curt))

    pv_total = pv_out.sum()
    pv_util = (P_pv_use.sum() / pv_total * 100) if pv_total > 0 else 0.0
    carbon_d = calc_daily_carbon(P_buy)

    return {"daily_cost": cost,
            "peak_demand": float(np.max(P_buy)),
            "pv_util_pct": round(pv_util, 1),
            "daily_carbon_kg": round(carbon_d, 1),
            "pv_curtail_kwh": round(P_pv_curt.sum(), 1)}


def capacity_optimization() -> pd.DataFrame:
    """
    枚举所有 (PV, ESS) 组合，计算 CAPEX、LCC、碳排放、光伏利用率。
    返回 DataFrame，按综合得分排序。
    """
    records = []
    for pv in PV_RANGE:
        for ess in ESS_RANGE:
            ess_kw = ess * 0.25
            capex = calc_capex(pv, ess, ess_kw, N_PILES)

            res = _heuristic_inner(pv, ess, ess_kw, N_PILES)
            annual_opex = res["daily_cost"] * 365
            lcc = calc_lcc(capex, annual_opex)
            annual_co2 = calc_annual_carbon(res["daily_carbon_kg"])

            records.append({
                "光伏容量(kW)": pv,
                "储能容量(kWh)": ess,
                "储能功率(kW)": int(ess_kw),
                "CAPEX(万元)": round(capex / 1e4, 1),
                "年运营成本(万元)": round(annual_opex / 1e4, 1),
                "LCC(万元)": round(lcc / 1e4, 1),
                "年碳排放(tCO2)": round(annual_co2, 1),
                "光伏利用率(%)": res["pv_util_pct"],
                "需量峰值(kW)": res["peak_demand"],
            })

    df = pd.DataFrame(records)

    def _norm(col):
        mn, mx = col.min(), col.max()
        return (col - mn) / (mx - mn + 1e-9)

    df["综合得分"] = (
        0.60 * _norm(df["LCC(万元)"])
        + 0.20 * _norm(df["年碳排放(tCO2)"])
        + 0.20 * (1 - _norm(df["光伏利用率(%)"]))
    ).round(4)

    df = df.sort_values("综合得分").reset_index(drop=True)
    df.index += 1
    return df
