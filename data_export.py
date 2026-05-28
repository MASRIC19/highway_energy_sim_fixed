"""
高速公路服务区光储充系统 — 数据导出模块
"""

import numpy as np
import pandas as pd
from config import T, TOU, c_sell, dt, PV_out, Base_load


def export_table(result, save_path="schedule_table_fixed.csv"):
    """导出24小时调度明细为 CSV"""
    P_buy = np.array(result['P_buy'])
    P_sell = np.array(result['P_sell'])
    P_ch = np.array(result['P_ch'])
    P_dis = np.array(result['P_dis'])
    SOC_arr = np.array(result['SOC'])[:T]
    P_pv_use = np.array(result.get('P_pv_use', np.zeros(T)))
    P_pv_curt = np.array(result.get('P_pv_curt', np.zeros(T)))
    P_ev = np.array(result.get('P_ev', np.zeros(T)))

    df = pd.DataFrame({
        '时刻': [f"{t:02d}:00" for t in range(T)],
        '电价(元/kWh)': TOU,
        '光伏出力(kW)': PV_out,
        '光伏消纳(kW)': np.round(P_pv_use, 2),
        '弃光(kW)': np.round(P_pv_curt, 2),
        'EV充电(kW)': np.round(P_ev, 2),
        '基础负荷(kW)': Base_load,
        '电网购电(kW)': np.round(P_buy, 2),
        '电网售电(kW)': np.round(P_sell, 2),
        '净购电(kW)': np.round(P_buy - P_sell, 2),
        '储能充电(kW)': np.round(P_ch, 2),
        '储能放电(kW)': np.round(P_dis, 2),
        'SOC': np.round(SOC_arr, 3),
        '时段购电费(元)': np.round(TOU * P_buy * dt, 2),
        '时段售电收益(元)': np.round(c_sell * P_sell * dt, 2),
    })
    df.to_csv(save_path, index=False, encoding='utf-8-sig')
    print(f"  调度明细已保存: {save_path}")
    return df
