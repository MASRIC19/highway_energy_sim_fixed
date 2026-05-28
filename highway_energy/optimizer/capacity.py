"""
optimizer/capacity.py
=====================
容量配置双层枚举优化

外层：遍历 (PV容量, ESS容量) 组合
内层：_heuristic_inner —— 轻量级启发式调度，评估运营成本
综合得分：加权标准化（经济60% + 碳排20% + 光伏利用率20%）
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from highway_energy.config.params import (
    T, DT, TOU, C_SELL, DEMAND_CHARGE_DAILY, PV_CURTAIL_PENALTY,
    ETA_CH, ETA_DIS, SOC0, SOC_MIN, SOC_MAX, BATTERY_DEG_COST,
    BASE_LOAD, P_EV_MAX, EV_ENERGY_DEMAND, EV_WEIGHT, P_GRID_MAX,
    PV_COST_PER_KW, ESS_COST_PER_KWH, ESS_COST_PER_KW, EV_PILE_COST,
    LIFESPAN_YR, DISCOUNT_RATE, CARBON_FACTOR,
    PV_RANGE, ESS_RANGE, N_PILES,
)

# 归一化光伏出力曲线（峰值=1），与容量配置无关
_PV_NORM: np.ndarray = np.array([
    0,    0,    0,    0,    0,
    0.10, 0.24, 0.44, 0.70, 0.90, 1.00,
    0.96, 0.84, 0.60, 0.36, 0.24, 0.18,
    0,    0,    0,    0,    0,    0,    0,
], dtype=float)

assert len(_PV_NORM) == T


# ─────────────────────────────────────────────────────────────
# 成本计算工具
# ─────────────────────────────────────────────────────────────

def calc_capex(pv_cap_kw: float,
               ess_kwh: float,
               ess_kw: float,
               n_piles: int) -> float:
    """初始投资成本 CAPEX（元）"""
    return (
        pv_cap_kw * PV_COST_PER_KW
        + ess_kwh  * ESS_COST_PER_KWH
        + ess_kw   * ESS_COST_PER_KW
        + n_piles  * EV_PILE_COST
    )


def calc_lcc(capex: float, annual_opex: float) -> float:
    """
    全生命周期成本 LCC = CAPEX + 年运营成本 × 等额年金现值系数

    APVF = [1 - (1+r)^(-n)] / r
    """
    if DISCOUNT_RATE == 0:
        apvf = float(LIFESPAN_YR)
    else:
        apvf = (1 - (1 + DISCOUNT_RATE) ** (-LIFESPAN_YR)) / DISCOUNT_RATE
    return capex + annual_opex * apvf


def calc_daily_carbon_kg(P_buy_arr: np.ndarray) -> float:
    """日碳排放（kg CO₂）"""
    return float(P_buy_arr.sum() * DT * CARBON_FACTOR)


def calc_annual_carbon_t(daily_carbon_kg: float) -> float:
    """年碳排放（tCO₂）"""
    return daily_carbon_kg * 365 / 1000


# ─────────────────────────────────────────────────────────────
# 内层启发式调度（针对任意容量配置）
# ─────────────────────────────────────────────────────────────

def _heuristic_inner(pv_cap: float,
                     ess_kwh: float,
                     ess_kw: float) -> dict:
    """
    给定 (pv_cap, ess_kwh, ess_kw)，运行峰谷套利启发式，
    返回日运营成本等关键指标。

    注意：末端 SOC 通过调整末时段放电强制回归 SOC0，确保不同容量配置
    之间的日运营成本可比。

    Parameters
    ----------
    pv_cap  : 光伏装机容量（kW）
    ess_kwh : 储能能量（kWh）
    ess_kw  : 储能功率（kW）

    Returns
    -------
    dict with keys: daily_cost, peak_demand, pv_util_pct,
                    daily_carbon_kg, pv_curtail_kwh
    """
    pv_out    = _PV_NORM * pv_cap
    p_ch_max  = ess_kw
    p_dis_max = ess_kw

    w_sum = EV_WEIGHT.sum()
    p_ev  = EV_WEIGHT / w_sum * EV_ENERGY_DEMAND if w_sum > 0 else np.zeros(T)
    p_ev  = np.minimum(p_ev, EV_WEIGHT * P_EV_MAX)

    P_buy      = np.zeros(T)
    P_sell     = np.zeros(T)
    P_ch_arr   = np.zeros(T)
    P_dis_arr  = np.zeros(T)
    P_pv_use   = np.zeros(T)
    P_pv_curt  = np.zeros(T)
    soc = SOC0

    for t in range(T):
        price = TOU[t]
        if price <= 0.42:
            p_c = min(p_ch_max, max(0.0, (SOC_MAX - soc) * ess_kwh / ETA_CH / DT))
            p_d = 0.0
        elif price >= 1.15:
            p_d = min(p_dis_max, max(0.0, (soc - SOC_MIN) * ess_kwh * ETA_DIS / DT))
            p_c = 0.0
        else:
            p_c = p_d = 0.0

        net = BASE_LOAD[t] + p_ev[t] - pv_out[t] + p_c - p_d
        if net >= 0:
            P_buy[t]  = min(net, P_GRID_MAX)
        else:
            P_sell[t] = min(-net, P_GRID_MAX)

        consumed = BASE_LOAD[t] + p_ev[t] + p_c - P_sell[t]
        P_pv_use[t]  = max(0.0, min(pv_out[t], consumed))
        P_pv_curt[t] = max(0.0, pv_out[t] - P_pv_use[t])

        P_ch_arr[t]  = p_c
        P_dis_arr[t] = p_d
        soc = np.clip(
            soc + (ETA_CH * p_c - p_d / ETA_DIS) * DT / ess_kwh,
            SOC_MIN, SOC_MAX,
        ) if ess_kwh > 0 else soc

    # 末端 SOC 回归修正：若最终 SOC > SOC0，补充分电以强制回归 SOC0
    if soc > SOC0 + 1e-4 and ess_kwh > 0:
        delta_soc = soc - SOC0
        p_extra = min(p_dis_max, delta_soc * ess_kwh * ETA_DIS / DT)
        # 在最后时段加入放电，同时减少购电或增加售电
        if T > 0:
            P_dis_arr[-1] += p_extra
            net_last = BASE_LOAD[-1] + p_ev[-1] - pv_out[-1] + P_ch_arr[-1] - P_dis_arr[-1]
            if net_last >= 0:
                P_buy[-1] = min(max(0.0, net_last), P_GRID_MAX)
                P_sell[-1] = 0.0
            else:
                P_buy[-1] = 0.0
                P_sell[-1] = min(-net_last, P_GRID_MAX)
            soc = np.clip(
                soc + (ETA_CH * P_ch_arr[-1] - P_dis_arr[-1] / ETA_DIS) * DT / ess_kwh,
                SOC_MIN, SOC_MAX,
            )

    cost = (
        np.sum(TOU * P_buy * DT)
        - np.sum(C_SELL * P_sell * DT)
        + np.sum(BATTERY_DEG_COST * (P_ch_arr + P_dis_arr))
        + DEMAND_CHARGE_DAILY * np.max(P_buy)
        + np.sum(PV_CURTAIL_PENALTY * P_pv_curt)
    )

    pv_total = pv_out.sum()
    pv_util  = (P_pv_use.sum() / pv_total * 100) if pv_total > 0 else 0.0
    carbon_d = calc_daily_carbon_kg(P_buy)

    return {
        "daily_cost"     : float(cost),
        "peak_demand"    : float(np.max(P_buy)),
        "pv_util_pct"    : round(pv_util, 1),
        "daily_carbon_kg": round(carbon_d, 1),
        "pv_curtail_kwh" : round(P_pv_curt.sum(), 1),
    }


# ─────────────────────────────────────────────────────────────
# 双层枚举优化
# ─────────────────────────────────────────────────────────────

def capacity_optimization() -> pd.DataFrame:
    """
    枚举所有 (PV, ESS) 组合（共 len(PV_RANGE)×len(ESS_RANGE) 次内层调度），
    计算 CAPEX / LCC / 年碳排放 / 光伏利用率 / 综合得分。

    Returns
    -------
    pd.DataFrame
        按综合得分升序排列，索引从 1 开始表示排名。
    """
    records = []
    for pv in PV_RANGE:
        for ess in ESS_RANGE:
            ess_kw = ess * 0.25     # 4 小时型储能，C 率 0.25
            capex  = calc_capex(pv, ess, ess_kw, N_PILES)
            res    = _heuristic_inner(pv, ess, ess_kw)

            annual_opex = res["daily_cost"] * 365
            lcc         = calc_lcc(capex, annual_opex)
            annual_co2  = calc_annual_carbon_t(res["daily_carbon_kg"])

            records.append({
                "光伏容量(kW)"    : pv,
                "储能容量(kWh)"   : ess,
                "储能功率(kW)"    : int(ess_kw),
                "CAPEX(万元)"     : round(capex / 1e4, 1),
                "年运营成本(万元)": round(annual_opex / 1e4, 1),
                "LCC(万元)"       : round(lcc / 1e4, 1),
                "年碳排放(tCO2)"  : round(annual_co2, 1),
                "光伏利用率(%)"   : res["pv_util_pct"],
                "需量峰值(kW)"    : res["peak_demand"],
            })

    df = pd.DataFrame(records)

    # ── 综合评分（加权标准化，越小越优）────────────────────
    def _norm(col: pd.Series) -> pd.Series:
        mn, mx = col.min(), col.max()
        span = mx - mn
        if span < 1e-9:       # 所有值相同时平均分
            return pd.Series(0.5, index=col.index)
        return (col - mn) / span

    df["综合得分"] = (
        0.60 * _norm(df["LCC(万元)"])
        + 0.20 * _norm(df["年碳排放(tCO2)"])
        + 0.20 * (1.0 - _norm(df["光伏利用率(%)"]))   # 利用率越高越好 → 取反
    ).round(4)

    df = df.sort_values("综合得分").reset_index(drop=True)
    df.index += 1   # 排名从 1 开始
    return df
