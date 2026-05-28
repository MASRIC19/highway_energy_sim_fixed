"""
analysis/stats.py
=================
调度结果统计分析：
  - 购售电量、峰时削减、需量峰值削减
  - 购电费用 / 售电收益 / 电池衰减 / 需量电费 / 弃光惩罚
  - 日 / 年节约估算
  - 光伏利用率 / EV 充电满足度

修复：
  FIX-S1: 所有百分比除法均加零值保护
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from highway_energy.config.params import (
    T, DT, TOU, C_SELL, DEMAND_CHARGE_DAILY, DEMAND_CHARGE_MONTHLY,
    PV_OUT, BASE_LOAD, EV_ENERGY_DEMAND, BATTERY_DEG_COST, PV_CURTAIL_PENALTY,
)


def _safe_pct(numerator: float, denominator: float) -> float:
    """零值安全的百分比计算。"""
    return (numerator / denominator * 100) if abs(denominator) > 1e-9 else 0.0


def analyze(result: dict, baseline: dict, label: str = "策略") -> dict:
    """
    对比优化结果与基线，输出格式化统计表，并返回指标字典。

    Parameters
    ----------
    result   : solve_milp 或 heuristic_schedule 返回的结果字典
    baseline : baseline_no_storage 返回的基线字典
    label    : 打印标题中显示的策略名称

    Returns
    -------
    dict  所有统计指标的键值对
    """
    P_buy  = np.array(result["P_buy"])
    P_sell = np.array(result["P_sell"])
    P_ch   = np.array(result["P_ch"])
    P_dis  = np.array(result["P_dis"])
    cost   = result["cost"]

    b_buy  = np.array(baseline["P_buy"])
    b_sell = np.array(baseline["P_sell"])
    b_cost = baseline["cost"]

    peak_mask     = TOU >= 1.15
    peak_buy      = float(np.sum(P_buy[peak_mask]))
    peak_buy_b    = float(np.sum(b_buy[peak_mask]))
    total_buy     = float(np.sum(P_buy))
    total_sell    = float(np.sum(P_sell))
    peak_demand   = result.get("P_peak", float(np.max(P_buy)))
    peak_demand_b = float(np.max(b_buy))

    P_pv_use  = np.array(result.get("P_pv_use",  np.zeros(T)))
    P_pv_curt = np.array(result.get("P_pv_curt", np.zeros(T)))
    pv_total  = float(np.sum(PV_OUT))
    pv_used   = float(np.sum(P_pv_use))
    pv_util   = _safe_pct(pv_used, pv_total)

    P_ev         = np.array(result.get("P_ev", np.zeros(T)))
    ev_delivered = float(np.sum(P_ev) * DT)
    ev_fulfill   = _safe_pct(ev_delivered, EV_ENERGY_DEMAND)

    energy_cost   = float(np.sum(TOU * P_buy  * DT))
    sell_revenue  = float(np.sum(C_SELL * P_sell * DT))
    battery_deg   = float(np.sum(BATTERY_DEG_COST * (P_ch + P_dis)))
    demand_cost_d = DEMAND_CHARGE_DAILY   * peak_demand
    demand_cost_m = DEMAND_CHARGE_MONTHLY * peak_demand
    pv_penalty    = float(np.sum(PV_CURTAIL_PENALTY * P_pv_curt))

    energy_cost_b = float(np.sum(TOU * b_buy  * DT))
    sell_revenue_b= float(np.sum(C_SELL * b_sell * DT))
    demand_cost_b = DEMAND_CHARGE_DAILY * peak_demand_b

    saving     = b_cost - cost
    saving_pct = _safe_pct(saving, b_cost)

    print(f"\n{'='*64}")
    print(f"  {label} 分析结果")
    print(f"{'='*64}")
    print(f"  日购电总量        : {total_buy:>10.0f} kWh   (基线 {np.sum(b_buy):.0f} kWh)")
    print(f"  日售电总量        : {total_sell:>10.0f} kWh")
    print(f"  峰时购电削减      : {peak_buy_b-peak_buy:>10.0f} kWh  "
          f"({_safe_pct(peak_buy_b-peak_buy, peak_buy_b):.1f}%)")
    print(f"  需量峰值削减      : {peak_demand_b-peak_demand:>10.0f} kW   "
          f"({_safe_pct(peak_demand_b-peak_demand, peak_demand_b):.1f}%)")
    print(f"  购电费用          : {energy_cost:>10.0f} 元    (基线 {energy_cost_b:.0f} 元)")
    print(f"  售电收益          : {sell_revenue:>10.0f} 元    (基线 {sell_revenue_b:.0f} 元)")
    print(f"  电池衰减成本      : {battery_deg:>10.1f} 元")
    print(f"  需量电费(日均)    : {demand_cost_d:>10.1f} 元    (基线 {demand_cost_b:.1f} 元)")
    print(f"  需量电费(月度参考): {demand_cost_m:>9.0f} 元/月 (峰值 {peak_demand:.0f} kW × 38元)")
    print(f"  弃光惩罚          : {pv_penalty:>10.1f} 元")
    print(f"  综合运行费用(日)  : {cost:>10.1f} 元    (基线 {b_cost:.1f} 元)")
    print(f"  日节约            : {saving:>10.1f} 元    ({saving_pct:.2f}%)")
    print(f"  年节约(估)        : {saving*365/1e4:>10.1f} 万元")
    print(f"  光伏利用率        : {pv_util:>10.1f}%")
    print(f"  EV 充电满足度     : {ev_fulfill:>10.1f}%")
    print(f"{'='*64}")

    return {
        "total_buy"     : total_buy,
        "total_sell"    : total_sell,
        "peak_buy"      : peak_buy,
        "peak_demand"   : peak_demand,
        "peak_demand_b" : peak_demand_b,
        "cost"          : cost,
        "saving"        : saving,
        "saving_pct"    : saving_pct,
        "pv_util"       : pv_util,
        "pv_total"      : pv_total,
        "pv_used"       : pv_used,
        "ev_fulfillment": ev_fulfill,
        "energy_cost"   : energy_cost,
        "sell_revenue"  : sell_revenue,
        "battery_deg"   : battery_deg,
        "demand_cost"   : demand_cost_d,
        "demand_cost_m" : demand_cost_m,
        "pv_penalty"    : pv_penalty,
    }


def export_schedule_csv(result: dict,
                         save_path: str = "schedule_table.csv") -> pd.DataFrame:
    """
    导出 24 小时调度明细至 CSV。

    Returns
    -------
    pd.DataFrame
    """
    P_buy     = np.array(result["P_buy"])
    P_sell    = np.array(result["P_sell"])
    P_ch      = np.array(result["P_ch"])
    P_dis     = np.array(result["P_dis"])
    SOC_arr   = np.array(result["SOC"])[:T]
    P_pv_use  = np.array(result.get("P_pv_use",  np.zeros(T)))
    P_pv_curt = np.array(result.get("P_pv_curt", np.zeros(T)))
    P_ev      = np.array(result.get("P_ev",       np.zeros(T)))

    df = pd.DataFrame({
        "时刻"            : [f"{t:02d}:00" for t in range(T)],
        "电价(元/kWh)"    : TOU,
        "光伏出力(kW)"    : PV_OUT,
        "光伏消纳(kW)"    : np.round(P_pv_use,  2),
        "弃光(kW)"        : np.round(P_pv_curt, 2),
        "EV充电(kW)"      : np.round(P_ev,       2),
        "基础负荷(kW)"    : BASE_LOAD,
        "电网购电(kW)"    : np.round(P_buy,      2),
        "电网售电(kW)"    : np.round(P_sell,     2),
        "净购电(kW)"      : np.round(P_buy - P_sell, 2),
        "储能充电(kW)"    : np.round(P_ch,       2),
        "储能放电(kW)"    : np.round(P_dis,      2),
        "SOC"             : np.round(SOC_arr,     3),
        "时段购电费(元)"  : np.round(TOU * P_buy  * DT, 2),
        "时段售电收益(元)": np.round(C_SELL * P_sell * DT, 2),
    })
    df.to_csv(save_path, index=False, encoding="utf-8-sig")
    print(f"  调度明细已保存: {save_path}")
    return df
