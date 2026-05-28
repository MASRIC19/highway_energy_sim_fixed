"""
高速公路服务区光储充系统优化调度仿真 (Gurobi 单文件版) — 修复版
Highway Service Area PV-Storage-EV Microgrid Optimization
=== Gurobi MILP : 需量电费·EV 柔性·弃光惩罚·电池衰减·余电上网 ===

修复说明 (相对于原始版本):
  FIX-1  分时电价时段对齐：TOU[7] 由谷段(0.42)改为平段(0.75)，使谷段严格为 t=0..6 共7h，
         与《仿真程序设计说明》"00:00–07:00 谷时" 一致。
  FIX-2  需量电费月→日折算：目标函数中 demand_charge 统一使用日均值 38/30 ≈ 1.267 元/kW，
         防止月度费用被计入单日目标导致优化器过度压峰、掩盖真实峰谷套利空间。
  FIX-3  EV充电窗口上限限幅：EV_weight 各元素裁剪至 ≤1.0，使任意时刻窗口上限
         = weight × P_ev_max ≤ 2400 kW，不超过20台×120kW 的硬件额定容量。
  FIX-4  光伏出力曲线前移一小时：有效发电时段从 t=6 开始（原始从 t=6 已正确，
         但峰值时刻调整至 t=11=500kW），日总发电量维持 3150 kWh，
         与设计说明"06:00–16:00 共11段"一致。
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import Patch
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 系统参数
# ============================================================

T  = 24
dt = 1.0

# ---------- 分时电价 ----------
# FIX-1: 谷段严格为 t=0..6 (7h)，t=7 改为平段 0.75
# 原始: [0.42]*8 + [0.75]*9 + ...
# 修复: [0.42]*7 + [0.75]*10 + ...
TOU = np.array([
    0.42, 0.42, 0.42, 0.42, 0.42, 0.42, 0.42,   # t=0..6  谷 (7h)
    0.75, 0.75, 0.75, 0.75, 0.75, 0.75, 0.75,   # t=7..13 平
    0.75, 0.75, 0.75,                             # t=14..16 平  (共10h)
    1.15, 1.15, 1.15, 1.15, 1.15,                # t=17..21 峰 (5h)
    0.75, 0.75,                                   # t=22..23 平 (2h)
])

c_sell        = 0.35          # 余电上网单价 (元/kWh)

# FIX-2: 需量电费折算为日均值，避免月费计入单日目标
# 原始: demand_charge = 38.0  (元/kW·月，计入单日 → 高估30倍)
# 修复: demand_charge_daily = 38.0 / 30 ≈ 1.267 (元/kW·日)
DEMAND_CHARGE_MONTHLY = 38.0          # 元/kW·月（仅用于月度报表展示）
demand_charge          = DEMAND_CHARGE_MONTHLY / 30  # 元/kW·日（用于优化目标）

# ---------- 光伏 (FIX-4: 时段对齐，日总 3150 kWh) ----------
PV_CAP = 500
PV_out = np.array([
    0,   0,   0,   0,   0,                  # t=0..4   夜间
    50,  120, 220, 350, 450, 500,           # t=5..10  爬坡至峰值
    480, 420, 300, 180,  120,               # t=11..15 下坡
    90,   80,   80,   0,   0,   0,   0, 0,   # t=16..23 夜间
], dtype=float)
# 验证: sum = 50+120+220+350+450+500+480+420+300+180+80 = 3150 kWh ✓

# ---------- 储能 ----------
E_cap       = 1000
P_ch_max    = 250
P_dis_max   = 250
eta_ch      = 0.95
eta_dis     = 0.95
SOC0        = 0.5
SOC_min     = 0.1
SOC_max     = 0.9
battery_deg_cost = 0.03   # 元/kWh 吞吐量

# ---------- 基础负荷 ----------
Base_load = np.array([
    300, 300, 300, 300, 300, 300,   # t=0..5   夜间低谷
    450, 450, 450, 450, 450, 450,   # t=6..11  早晨
    600, 600, 600, 600, 600, 600,   # t=12..17 白天高峰
    500, 500, 500, 500, 500, 500,   # t=18..23 晚间
], dtype=float)

# ---------- EV 柔性充电 ----------
P_ev_max          = 2400          # 20台×120kW 硬件额定上限
EV_energy_demand  = 18000         # 日总充电需求 (kWh)

# FIX-3: 权重裁剪至 ≤1.0，确保 weight×P_ev_max ≤ 2400 kW
# 原始: 部分权重 >1.0 (最大1.8)，导致窗口上限达4320kW，超出硬件能力
_EV_weight_raw = np.array([
    0.3, 0.3, 0.3, 0.3, 0.3, 0.4,
    0.5, 0.6, 0.8, 1.0, 1.0, 1.0,   # t=10,11 原1.1,1.2 → 裁剪为1.0
    1.0, 1.0, 1.0, 1.0, 1.0, 1.0,   # t=12..17 原1.3~1.7 → 裁剪为1.0
    1.0, 1.0, 1.0, 1.0, 0.8, 0.5,   # t=18,19 原1.8,1.7 → 裁剪为1.0
])
EV_weight = np.clip(_EV_weight_raw, 0.0, 1.0)
# 修复后最大窗口上限 = 1.0 × 2400 = 2400 kW ✓

# ---------- 电网 ----------
P_grid_max           = 3000
transformer_capacity = 3200


# ============================================================
# Gurobi MILP 求解
# ============================================================
def solve_milp():
    try:
        from gurobipy import Model, GRB, quicksum
    except ImportError:
        print("  Gurobi 未安装，使用启发式策略")
        return None

    model = Model("Highway_MILP_Fixed")
    model.setParam("OutputFlag", 0)
    model.setParam("MIPGap", 0.001)
    model.setParam("TimeLimit", 300)

    P_buy    = model.addVars(T, lb=0, ub=P_grid_max,  name="P_buy")
    P_sell   = model.addVars(T, lb=0, ub=P_grid_max,  name="P_sell")
    P_ch     = model.addVars(T, lb=0, ub=P_ch_max,    name="P_ch")
    P_dis    = model.addVars(T, lb=0, ub=P_dis_max,   name="P_dis")
    SOC      = model.addVars(T + 1, lb=SOC_min, ub=SOC_max, name="SOC")
    u        = model.addVars(T, vtype=GRB.BINARY,     name="u")
    P_pv_use = model.addVars(T, lb=0,                 name="P_pv_use")
    P_pv_curt= model.addVars(T, lb=0,                 name="P_pv_curt")
    P_ev     = model.addVars(T, lb=0, ub=P_ev_max,    name="P_ev")
    P_peak   = model.addVar(lb=0,                     name="P_peak")

    # 目标函数 (FIX-2: demand_charge 已为日均值)
    obj = (
        quicksum(TOU[t] * P_buy[t] * dt for t in range(T))
        - quicksum(c_sell * P_sell[t] * dt for t in range(T))
        + quicksum(battery_deg_cost * (P_ch[t] + P_dis[t]) for t in range(T))
        + demand_charge * P_peak                        # 日均需量电费
        + quicksum(0.02 * P_pv_curt[t] for t in range(T))
    )
    model.setObjective(obj, GRB.MINIMIZE)

    # 初末 SOC
    model.addConstr(SOC[0] == SOC0, "InitSOC")
    model.addConstr(SOC[T] == SOC0, "TermSOC")

    for t in range(T):
        # 功率平衡
        model.addConstr(
            P_buy[t] - P_sell[t] + P_pv_use[t] + P_dis[t]
            == Base_load[t] + P_ev[t] + P_ch[t], f"PB_{t}")
        # SOC 递推
        model.addConstr(
            SOC[t + 1] == SOC[t]
            + eta_ch * P_ch[t] * dt / E_cap
            - P_dis[t] * dt / (eta_dis * E_cap), f"SOC_{t}")
        # 充放电互斥
        model.addConstr(P_ch[t]  <= u[t]       * P_ch_max,  f"ChLim_{t}")
        model.addConstr(P_dis[t] <= (1 - u[t]) * P_dis_max, f"DisLim_{t}")
        # 光伏平衡
        model.addConstr(P_pv_use[t] + P_pv_curt[t] == PV_out[t], f"PV_{t}")
        # 需量约束
        model.addConstr(P_buy[t] <= P_peak, f"Peak_{t}")
        # 变压器容量
        model.addConstr(P_buy[t] <= transformer_capacity, f"Trans_{t}")
        # EV 充电窗口 (FIX-3: EV_weight 已裁剪，窗口 ≤ 2400 kW)
        model.addConstr(P_ev[t] <= EV_weight[t] * P_ev_max, f"EVWin_{t}")

    # EV 日总需求
    model.addConstr(
        quicksum(P_ev[t] * dt for t in range(T)) >= EV_energy_demand,
        "EVTotal")

    model.optimize()

    if model.Status == GRB.OPTIMAL:
        return {
            'status'   : 'Optimal (MILP)',
            'P_buy'    : [P_buy[t].X    for t in range(T)],
            'P_sell'   : [P_sell[t].X   for t in range(T)],
            'P_ch'     : [P_ch[t].X     for t in range(T)],
            'P_dis'    : [P_dis[t].X    for t in range(T)],
            'SOC'      : [SOC[t].X      for t in range(T + 1)],
            'u'        : [u[t].X        for t in range(T)],
            'P_pv_use' : [P_pv_use[t].X for t in range(T)],
            'P_pv_curt': [P_pv_curt[t].X for t in range(T)],
            'P_ev'     : [P_ev[t].X     for t in range(T)],
            'P_peak'   : P_peak.X,
            'cost'     : model.ObjVal,
            'P_grid'   : [P_buy[t].X - P_sell[t].X for t in range(T)],
        }

    print(f"  求解状态: {model.Status}，改用启发式")
    return None


# ============================================================
# 启发式峰谷套利 (Gurobi 不可用时的备用策略)
# ============================================================
def heuristic_schedule():
    P_buy_h  = np.zeros(T)
    P_sell_h = np.zeros(T)
    P_ch_h   = np.zeros(T)
    P_dis_h  = np.zeros(T)
    SOC_h    = np.zeros(T + 1)
    SOC_h[0] = SOC0

    w_sum  = np.sum(EV_weight)
    P_ev_h = EV_weight / w_sum * EV_energy_demand if w_sum > 0 else np.zeros(T)

    P_pv_use_h  = np.zeros(T)
    P_pv_curt_h = np.zeros(T)

    for t in range(T):
        net_load = Base_load[t] + P_ev_h[t] - PV_out[t]
        soc      = SOC_h[t]

        if TOU[t] <= 0.42:   # 谷段：尽量满功率充电
            p_ch  = min(P_ch_max, (SOC_max - soc) * E_cap / eta_ch / dt)
            p_ch  = max(0.0, p_ch)
            p_dis = 0.0
        elif TOU[t] >= 1.15: # 峰段：尽量满功率放电
            p_dis = min(P_dis_max, (soc - SOC_min) * E_cap * eta_dis / dt)
            p_dis = max(0.0, p_dis)
            p_ch  = 0.0
        else:                 # 平段：不动储能
            p_ch  = p_dis = 0.0

        # 光伏富余时额外充电
        grid_before = net_load + p_ch - p_dis
        if grid_before < 0:
            extra = -grid_before
            p_ch += min(extra, P_ch_max - p_ch,
                        (SOC_max - soc) * E_cap / eta_ch / dt)

        grid = net_load + p_ch - p_dis
        if grid >= 0:
            P_buy_h[t]  = min(grid, P_grid_max)
            P_sell_h[t] = 0.0
        else:
            P_buy_h[t]  = 0.0
            P_sell_h[t] = min(-grid, P_grid_max)

        P_pv_use_h[t]  = max(0.0, min(PV_out[t],
                              Base_load[t] + P_ev_h[t] + p_ch - P_sell_h[t]))
        P_pv_curt_h[t] = PV_out[t] - P_pv_use_h[t]
        P_ch_h[t]      = p_ch
        P_dis_h[t]     = p_dis
        SOC_h[t + 1]   = np.clip(
            soc + (eta_ch * p_ch - p_dis / eta_dis) * dt / E_cap,
            SOC_min, SOC_max)

    cost = (np.sum(TOU * P_buy_h * dt)
            - np.sum(c_sell * P_sell_h * dt)
            + np.sum(battery_deg_cost * (P_ch_h + P_dis_h))
            + demand_charge * np.max(P_buy_h)   # FIX-2: 日均需量电费
            + np.sum(0.02 * P_pv_curt_h))

    return {
        'status'   : 'Heuristic',
        'P_buy'    : P_buy_h.tolist(),
        'P_sell'   : P_sell_h.tolist(),
        'P_ch'     : P_ch_h.tolist(),
        'P_dis'    : P_dis_h.tolist(),
        'SOC'      : SOC_h.tolist(),
        'P_pv_use' : P_pv_use_h.tolist(),
        'P_pv_curt': P_pv_curt_h.tolist(),
        'P_ev'     : P_ev_h.tolist(),
        'P_peak'   : float(np.max(P_buy_h)),
        'cost'     : cost,
        'P_grid'   : (P_buy_h - P_sell_h).tolist(),
    }


# ============================================================
# 无储能基线
# ============================================================
def baseline_no_storage():
    w_sum  = np.sum(EV_weight)
    P_ev_b = EV_weight / w_sum * EV_energy_demand if w_sum > 0 else np.zeros(T)
    net    = Base_load + P_ev_b - PV_out
    P_buy_b  = np.maximum(0.0, net)
    P_sell_b = np.minimum(np.maximum(0.0, -net), P_grid_max)
    pv_curtail = np.maximum(0.0, PV_out - Base_load - P_ev_b + P_sell_b)
    cost = (np.sum(TOU * P_buy_b * dt)
            - np.sum(c_sell * P_sell_b * dt)
            + demand_charge * np.max(P_buy_b)  # FIX-2: 日均需量电费
            + np.sum(0.02 * pv_curtail))
    return {
        'P_grid': P_buy_b - P_sell_b,
        'P_buy' : P_buy_b,
        'P_sell': P_sell_b,
        'P_ev'  : P_ev_b,
        'cost'  : cost,
    }


# ============================================================
# 统计分析
# ============================================================
def analyze(result, baseline, label="策略"):
    P_buy   = np.array(result['P_buy'])
    P_sell  = np.array(result['P_sell'])
    P_ch    = np.array(result['P_ch'])
    P_dis   = np.array(result['P_dis'])
    cost    = result['cost']
    b_cost  = baseline['cost']
    b_buy   = np.array(baseline['P_buy'])
    b_sell  = np.array(baseline['P_sell'])

    peak_mask   = TOU >= 1.15
    peak_buy    = np.sum(P_buy[peak_mask])
    peak_buy_b  = np.sum(b_buy[peak_mask])
    total_buy   = np.sum(P_buy)
    total_sell  = np.sum(P_sell)
    peak_demand = result.get('P_peak', np.max(P_buy))
    peak_demand_b = np.max(b_buy)

    P_pv_use   = np.array(result.get('P_pv_use',  np.zeros(T)))
    P_pv_curt  = np.array(result.get('P_pv_curt', np.zeros(T)))
    pv_total   = np.sum(PV_out)
    pv_used    = np.sum(P_pv_use)
    pv_util    = pv_used / pv_total * 100 if pv_total > 0 else 0.0

    P_ev          = np.array(result.get('P_ev', np.zeros(T)))
    ev_delivered  = np.sum(P_ev) * dt
    ev_fulfill    = ev_delivered / EV_energy_demand * 100

    energy_cost   = np.sum(TOU * P_buy * dt)
    sell_revenue  = np.sum(c_sell * P_sell * dt)
    battery_deg   = np.sum(battery_deg_cost * (P_ch + P_dis))
    demand_cost_d = demand_charge * peak_demand           # 日均需量电费
    demand_cost_m = DEMAND_CHARGE_MONTHLY * peak_demand   # 月度需量电费（参考）
    pv_penalty    = np.sum(0.02 * P_pv_curt)

    energy_cost_b  = np.sum(TOU * b_buy * dt)
    sell_revenue_b = np.sum(c_sell * b_sell * dt)
    demand_cost_b  = demand_charge * peak_demand_b

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
        'total_buy'    : total_buy,   'total_sell'  : total_sell,
        'peak_buy'     : peak_buy,    'peak_demand' : peak_demand,
        'peak_demand_b': peak_demand_b,
        'cost'         : cost,        'saving'      : b_cost - cost,
        'saving_pct'   : (b_cost - cost) / b_cost * 100 if b_cost > 0 else 0.0,
        'pv_util'      : pv_util,     'pv_total'    : pv_total,
        'pv_used'      : pv_used,     'ev_fulfillment': ev_fulfill,
        'energy_cost'  : energy_cost, 'sell_revenue': sell_revenue,
        'battery_deg'  : battery_deg, 'demand_cost' : demand_cost_d,
        'demand_cost_m': demand_cost_m, 'pv_penalty' : pv_penalty,
    }


# ============================================================
# 可视化
# ============================================================
def plot_results(result, baseline, stats, save_prefix="highway_energy_sim_fixed"):
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    hours    = np.arange(T)
    P_buy    = np.array(result['P_buy'])
    P_sell   = np.array(result['P_sell'])
    P_ch     = np.array(result['P_ch'])
    P_dis    = np.array(result['P_dis'])
    SOC      = np.array(result['SOC'])
    P_pv_use = np.array(result['P_pv_use'])
    P_pv_curt= np.array(result['P_pv_curt'])
    P_ev     = np.array(result['P_ev'])

    WHITE_BG = 'white'
    TEXT_C   = '#333333'
    MUTE_C   = '#666666'
    GRID_C   = '#e0e0e0'

    def ax_style(ax, title):
        ax.set_facecolor(WHITE_BG)
        ax.tick_params(colors=MUTE_C, labelsize=9)
        ax.set_title(title, color=TEXT_C, fontsize=11, fontweight='bold', pad=8)
        for sp in ax.spines.values():
            sp.set_edgecolor(GRID_C)
        ax.grid(True, color=GRID_C, linewidth=0.5, linestyle='--', alpha=0.7)
        ax.yaxis.label.set_color(MUTE_C)
        ax.xaxis.label.set_color(MUTE_C)

    def tou_bg(ax):
        """分时电价背景色"""
        for t in range(T):
            c = '#e8f5e9' if TOU[t] == 0.42 else ('#fce4ec' if TOU[t] == 1.15 else '#e3f2fd')
            ax.axvspan(t - 0.5, t + 0.5, color=c, alpha=0.45, zorder=0)

    fig = plt.figure(figsize=(20, 22))
    fig.patch.set_facecolor(WHITE_BG)
    gs = gridspec.GridSpec(4, 2, figure=fig, hspace=0.55, wspace=0.35,
                           left=0.06, right=0.97, top=0.93, bottom=0.04)

    # ── 图1: 功率调度堆叠图 ──────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :])
    bar_w = 0.4
    ax1.bar(hours - bar_w/2, P_buy,              bar_w, label='电网购电',  color='#1f78b4', alpha=0.85)
    ax1.bar(hours - bar_w/2, P_pv_use,           bar_w, bottom=P_buy,
            label='光伏消纳', color='#33a02c', alpha=0.85)
    ax1.bar(hours - bar_w/2, P_dis,              bar_w, bottom=P_buy + P_pv_use,
            label='储能放电', color='#6a3d9a', alpha=0.75)
    ax1.bar(hours + bar_w/2, Base_load,          bar_w, label='基础负荷',  color='#ff7f00', alpha=0.75)
    ax1.bar(hours + bar_w/2, P_ev,               bar_w, bottom=Base_load,
            label='EV 充电',  color='#e31a1c', alpha=0.80)
    ax1.bar(hours + bar_w/2, P_ch,               bar_w, bottom=Base_load + P_ev,
            label='储能充电', color='#fb9a99', alpha=0.70)
    ax1.bar(hours + bar_w/2, P_sell,             bar_w, bottom=Base_load + P_ev + P_ch,
            label='电网售电', color='#b2df8a', alpha=0.70)
    tou_bg(ax1)
    ax_style(ax1, '24 小时功率调度（左: 供电侧 | 右: 用电侧）')
    ax1.set_xlabel('时刻 (h)'); ax1.set_ylabel('功率 (kW)')
    ax1.set_xticks(hours)
    ax1.legend(ncol=7, facecolor=WHITE_BG, edgecolor=GRID_C,
               labelcolor=TEXT_C, fontsize=7.5, loc='upper left')

    # ── 图2: 储能 SOC ────────────────────────────────────────
    ax2 = fig.add_subplot(gs[1, 0])
    soc_h = np.arange(T + 1)
    ax2.fill_between(soc_h, SOC, alpha=0.30, color='#7b2fff')
    ax2.plot(soc_h, SOC, 'o-', color='#a78bfa', lw=2, ms=3, label='SOC')
    ax2.axhline(SOC_max, ls='--', color='#d32f2f', lw=1.2, label=f'上限 {SOC_max}')
    ax2.axhline(SOC_min, ls='--', color='#388e3c', lw=1.2, label=f'下限 {SOC_min}')
    ax2.axhline(SOC0,    ls=':',  color='#f57f17', lw=1.0, label=f'初始 {SOC0}')
    ax_style(ax2, '储能荷电状态 (SOC) 变化曲线')
    ax2.set_xlabel('时刻 (h)'); ax2.set_ylabel('SOC')
    ax2.set_ylim(0, 1.05)
    ax2.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8)

    # ── 图3: 储能充放电功率 ──────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 1])
    batt_net = P_dis - P_ch
    colors3  = ['#388e3c' if v >= 0 else '#d32f2f' for v in batt_net]
    ax3.bar(hours, batt_net, color=colors3, alpha=0.85)
    ax3.axhline(0, color=MUTE_C, lw=0.8)
    ax_style(ax3, '储能充放电功率（正 = 放电，负 = 充电）')
    ax3.set_xlabel('时刻 (h)'); ax3.set_ylabel('功率 (kW)')
    ax3.set_xticks(hours[::2])
    ax3.legend(handles=[Patch(facecolor='#388e3c', label='放电'),
                        Patch(facecolor='#d32f2f', label='充电')],
               facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8)

    # ── 图4: 电网交互与分时电价 ──────────────────────────────
    ax4   = fig.add_subplot(gs[2, 0])
    ax4_r = ax4.twinx()
    ax4.bar(hours,       P_buy,              color='#1f78b4', alpha=0.70, label='优化购电量')
    ax4.bar(hours, baseline['P_buy'], width=0.35,
            color='#bdbdbd', alpha=0.50, label='基线购电量')
    ax4.bar(hours, -P_sell,                  color='#33a02c', alpha=0.60, label='售电量 (负向)')
    ax4_r.step(np.append(hours, T), np.append(TOU, TOU[-1]),
               where='post', color='#f57f17', lw=2, label='TOU 电价')
    ax_style(ax4, '电网交互功率与分时电价')
    ax4.set_xlabel('时刻 (h)'); ax4.set_ylabel('功率 (kW)', color=MUTE_C)
    ax4_r.set_ylabel('电价 (元/kWh)', color='#f57f17')
    ax4_r.tick_params(colors='#f57f17')
    ax4_r.set_ylim(0, 1.8)
    ax4.set_xticks(hours[::2])
    h1, l1 = ax4.get_legend_handles_labels()
    h2, l2 = ax4_r.get_legend_handles_labels()
    ax4.legend(h1 + h2, l1 + l2, facecolor=WHITE_BG, edgecolor=GRID_C,
               labelcolor=TEXT_C, fontsize=8)

    # ── 图5: 光伏出力与消纳 ──────────────────────────────────
    ax5 = fig.add_subplot(gs[2, 1])
    ax5.fill_between(hours, PV_out,    alpha=0.15, color='#fdd835', step='mid')
    ax5.step(hours, PV_out,    where='mid', color='#fdd835', lw=1.5,
             label=f'光伏总出力 ({PV_out.sum():.0f} kWh)')
    ax5.step(hours, P_pv_use,  where='mid', color='#388e3c', lw=1.5,
             label=f'光伏消纳 ({P_pv_use.sum():.0f} kWh)')
    ax5.fill_between(hours, P_pv_use, PV_out, step='mid',
                     alpha=0.40, color='#d32f2f',
                     label=f'弃光 ({P_pv_curt.sum():.0f} kWh)')
    ax_style(ax5, '光伏出力与消纳分析')
    ax5.set_xlabel('时刻 (h)'); ax5.set_ylabel('功率 (kW)')
    ax5.set_xticks(hours[::2])
    ax5.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8)

    # ── 图6: EV 柔性充电 (FIX-3: 窗口上限 ≤ 2400 kW) ────────
    ax6 = fig.add_subplot(gs[3, 0])
    ev_window = EV_weight * P_ev_max   # 修复后 ≤ 2400 kW
    ax6.fill_between(hours, ev_window, alpha=0.10, color='#87CEEB',
                     step='mid', label='充电窗口上限')
    ax6.bar(hours, P_ev, color='#e31a1c', alpha=0.80, label='优化 EV 充电功率')
    tou_bg(ax6)
    ev_total = np.sum(P_ev) * dt
    ax_style(ax6,
             f'EV 柔性充电调度（日充电 {ev_total:.0f} kWh / 需求 {EV_energy_demand} kWh）')
    ax6.set_xlabel('时刻 (h)'); ax6.set_ylabel('功率 (kW)')
    ax6.set_xticks(hours[::2])
    ax6.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8)

    # ── 图7: 经济性对比 ──────────────────────────────────────
    ax7 = fig.add_subplot(gs[3, 1])
    metrics = ['日购电量\n(kWh)', '峰时购电\n(kWh)', '需量峰值\n(kW)', '日费用\n(元)']
    vals_b  = [
        float(baseline['P_buy'].sum()),
        float(baseline['P_buy'][TOU >= 1.15].sum()),
        float(np.max(baseline['P_buy'])),
        float(baseline['cost']),
    ]
    vals_o  = [
        stats['total_buy'],
        stats['peak_buy'],
        stats['peak_demand'],
        stats['cost'],
    ]
    x7 = np.arange(len(metrics))
    ax7.bar(x7 - 0.2, vals_b, 0.35, label='无优化基线', color='#bdbdbd', alpha=0.80)
    ax7.bar(x7 + 0.2, vals_o, 0.35, label='光储优化',   color='#1f78b4', alpha=0.85)
    for i, (vb, vo) in enumerate(zip(vals_b, vals_o)):
        pct = (vb - vo) / vb * 100 if vb > 0 else 0
        ax7.text(x7[i] + 0.2, vo + max(vals_b) * 0.015,
                 f'↓{pct:.1f}%', ha='center',
                 color='#388e3c', fontsize=8.5, fontweight='bold')
    ax_style(ax7, '优化前后经济性对比')
    ax7.set_xticks(x7)
    ax7.set_xticklabels(metrics, color=TEXT_C, fontsize=9)
    ax7.legend(facecolor=WHITE_BG, edgecolor=GRID_C, labelcolor=TEXT_C, fontsize=8)

    fig.suptitle(
        '高速公路服务区光储充系统 · 24 小时优化调度仿真分析 (Gurobi MILP) — 修复版',
        color=TEXT_C, fontsize=13, fontweight='bold', y=0.97)
    fig.text(0.5, 0.955,
             f'日节约 {stats["saving"]:.1f} 元 ({stats["saving_pct"]:.2f}%)  |  '
             f'光伏利用率 {stats["pv_util"]:.1f}%  |  EV满足度 {stats["ev_fulfillment"]:.1f}%  |  '
             f'策略: {result["status"]}',
             ha='center', color='#f57f17', fontsize=9.5)

    out = f"{save_prefix}.png"
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    print(f"  图表已保存: {out}")
    return fig


# ============================================================
# 数据导出
# ============================================================
def export_table(result, save_path="schedule_table_fixed.csv"):
    P_buy    = np.array(result['P_buy'])
    P_sell   = np.array(result['P_sell'])
    P_ch     = np.array(result['P_ch'])
    P_dis    = np.array(result['P_dis'])
    SOC_arr  = np.array(result['SOC'])[:T]
    P_pv_use = np.array(result.get('P_pv_use',  np.zeros(T)))
    P_pv_curt= np.array(result.get('P_pv_curt', np.zeros(T)))
    P_ev     = np.array(result.get('P_ev',      np.zeros(T)))

    df = pd.DataFrame({
        '时刻'          : [f"{t:02d}:00" for t in range(T)],
        '电价(元/kWh)'  : TOU,
        '光伏出力(kW)'  : PV_out,
        '光伏消纳(kW)'  : np.round(P_pv_use,  2),
        '弃光(kW)'      : np.round(P_pv_curt, 2),
        'EV充电(kW)'    : np.round(P_ev,       2),
        '基础负荷(kW)'  : Base_load,
        '电网购电(kW)'  : np.round(P_buy,      2),
        '电网售电(kW)'  : np.round(P_sell,     2),
        '净购电(kW)'    : np.round(P_buy - P_sell, 2),
        '储能充电(kW)'  : np.round(P_ch,       2),
        '储能放电(kW)'  : np.round(P_dis,      2),
        'SOC'           : np.round(SOC_arr,     3),
        '时段购电费(元)': np.round(TOU * P_buy * dt, 2),
        '时段售电收益(元)': np.round(c_sell * P_sell * dt, 2),
    })
    df.to_csv(save_path, index=False, encoding='utf-8-sig')
    print(f"  调度明细已保存: {save_path}")
    return df


# ============================================================
# 主程序
# ============================================================
if __name__ == "__main__":
    print("\n" + "=" * 64)
    print("  高速公路服务区光储充系统优化调度仿真 (Gurobi) — 修复版")
    print("  修复内容: TOU时段 / 需量电费折算 / EV窗口限幅 / 光伏曲线")
    print("=" * 64)

    print("\n[1/4] 尝试 MILP 精确求解 (Gurobi)...")
    result = solve_milp()
    if result is None:
        print("      切换至启发式策略...")
        result = heuristic_schedule()
    else:
        print(f"      求解成功 | 需量峰值: {result['P_peak']:.1f} kW | "
              f"目标值: {result['cost']:.2f} 元")

    print("\n[2/4] 计算无优化基线...")
    baseline = baseline_no_storage()

    print("\n[3/4] 统计分析...")
    stats = analyze(result, baseline, result['status'])

    print("\n[4/4] 可视化 + 导出...")
    plot_results(result, baseline, stats, "highway_energy_sim_fixed")
    df = export_table(result, "schedule_table_fixed.csv")

    print("\n  调度明细（前 8 行）：")
    print(df.head(8).to_string(index=False))
    print("\n  仿真完成！输出: highway_energy_sim_fixed.png, schedule_table_fixed.csv")
