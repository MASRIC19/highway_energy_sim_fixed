"""
高速公路服务区光储充系统 — 经济性分析模块
"""

import numpy as np
from config import T, dt, TOU, c_sell, demand_charge, DEMAND_CHARGE_MONTHLY, PV_out, EV_energy_demand, battery_deg_cost


def analyze(result, baseline, label="策略"):
    """对比优化策略与无储能基线的经济性指标"""
    P_buy = np.array(result['P_buy'])
    P_sell = np.array(result['P_sell'])
    P_ch = np.array(result['P_ch'])
    P_dis = np.array(result['P_dis'])
    cost = result['cost']
    b_cost = baseline['cost']
    b_buy = np.array(baseline['P_buy'])
    b_sell = np.array(baseline['P_sell'])

    peak_mask = TOU >= 1.15
    peak_buy = np.sum(P_buy[peak_mask])
    peak_buy_b = np.sum(b_buy[peak_mask])
    total_buy = np.sum(P_buy)
    total_sell = np.sum(P_sell)
    peak_demand = result.get('P_peak', np.max(P_buy))
    peak_demand_b = np.max(b_buy)

    P_pv_use = np.array(result.get('P_pv_use', np.zeros(T)))
    P_pv_curt = np.array(result.get('P_pv_curt', np.zeros(T)))
    pv_total = np.sum(PV_out)
    pv_used = np.sum(P_pv_use)
    pv_util = pv_used / pv_total * 100 if pv_total > 0 else 0.0

    P_ev = np.array(result.get('P_ev', np.zeros(T)))
    ev_delivered = np.sum(P_ev) * dt
    ev_fulfill = ev_delivered / EV_energy_demand * 100

    energy_cost = np.sum(TOU * P_buy * dt)
    sell_revenue = np.sum(c_sell * P_sell * dt)
    battery_deg = np.sum(battery_deg_cost * (P_ch + P_dis))
    demand_cost_d = demand_charge * peak_demand
    demand_cost_m = DEMAND_CHARGE_MONTHLY * peak_demand
    pv_penalty = np.sum(0.02 * P_pv_curt)

    energy_cost_b = np.sum(TOU * b_buy * dt)
    sell_revenue_b = np.sum(c_sell * b_sell * dt)
    demand_cost_b = demand_charge * peak_demand_b

    print(f"\n{'='*64}")
    print(f"  {label} 分析结果")
    print(f"{'='*64}")
    print(f"  日购电总量       : {total_buy:>10.0f} kWh   (基线 {np.sum(b_buy):.0f} kWh)")
    print(f"  日售电总量       : {total_sell:>10.0f} kWh")
    print(f"  峰时购电削减     : {peak_buy_b-peak_buy:>10.0f} kWh  ({(peak_buy_b-peak_buy)/peak_buy_b*100:.1f}%)")
    print(f"  需量峰值削减     : {peak_demand_b-peak_demand:>10.0f} kW   ({(peak_demand_b-peak_demand)/peak_demand_b*100:.1f}%)")
    print(f"  购电费用         : {energy_cost:>10.0f} 元    (基线 {energy_cost_b:.0f} 元)")
    print(f"  售电收益         : {sell_revenue:>10.0f} 元    (基线 {sell_revenue_b:.0f} 元)")
    print(f"  电池衰减成本     : {battery_deg:>10.1f} 元")
    print(f"  需量电费(日均)   : {demand_cost_d:>10.1f} 元    (基线 {demand_cost_b:.1f} 元)")
    print(f"  需量电费(月度参考): {demand_cost_m:>9.0f} 元/月 (峰值 {peak_demand:.0f} kW × 38元)")
    print(f"  弃光惩罚         : {pv_penalty:>10.1f} 元")
    print(f"  综合运行费用(日) : {cost:>10.1f} 元    (基线 {b_cost:.1f} 元)")
    print(f"  日节约           : {b_cost-cost:>10.1f} 元    ({(b_cost-cost)/b_cost*100:.2f}%)")
    print(f"  年节约(估)       : {(b_cost-cost)*365/1e4:>10.1f} 万元")
    print(f"  光伏利用率       : {pv_util:>10.1f}%")
    print(f"  EV 充电满足度    : {ev_fulfill:>10.1f}%")
    print(f"{'='*64}")

    return {
        'total_buy': total_buy, 'total_sell': total_sell,
        'peak_buy': peak_buy, 'peak_demand': peak_demand,
        'peak_demand_b': peak_demand_b,
        'cost': cost, 'saving': b_cost - cost,
        'saving_pct': (b_cost - cost) / b_cost * 100 if b_cost > 0 else 0.0,
        'pv_util': pv_util, 'pv_total': pv_total,
        'pv_used': pv_used, 'ev_fulfillment': ev_fulfill,
        'energy_cost': energy_cost, 'sell_revenue': sell_revenue,
        'battery_deg': battery_deg, 'demand_cost': demand_cost_d,
        'demand_cost_m': demand_cost_m, 'pv_penalty': pv_penalty,
    }
