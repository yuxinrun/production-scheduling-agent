# -*- coding: utf-8 -*-
"""主数据缺陷注入实验：一份干净算例，一次只坏一个字段，量「报出来的方案」与「真实车间跑得
出来的方案」差多少，再量一份数据体检清单到底能抓住几个注入的缺陷。

用法:  python data_defect_probe.py   （纯标准库，无第三方依赖）

  [1] 干净基线：五张主数据表（设备台账 resources / 班次日历 / 工艺路线 route / 换型矩阵 /
      工单批量）有多干净——报出 makespan 与真实校验 makespan 相等、六类违规全 0，
      后面所有分歧都以它为对照
  [2] 缺陷注入：10 个缺陷各改一处字段，同一个求解器、同一 seed、同一评估预算，分别在
      「缺陷模型」与「真实数据」上跑，量 报出Cmax / 真实Cmax / 真值基线Cmax 三个数与它们的符号
  [3] 违规明细：把报出的开工时刻原样下发到真实车间（时刻不改，只按真实数据验收），
      数六类硬违规——工艺顺序、同机重叠、换型不足、窗口外、幽灵设备工序、漏排工序
  [4] 幻觉方向：交期违约工单数与瓶颈设备负荷率这两个维度上，报出的数字比真实好看的时刻
  [5] 数据体检门禁：10 条便宜规则在 11 份实例上的混淆矩阵，算 抓到/漏掉、召回、按规则的精确率
  [6] 成本账：同一缺陷在「建模时发现」与「上线后发现」的返工面；单价是假设，返工工序数是实测
  [7] 一览：把前六节的关键实测数压成一屏

全部随机量写死种子（seed=20261105），搜索预算是「评估次数」而不是墙钟，stdout 里没有任何依赖
机器快慢的数字（耗时只写 stderr），所以两次运行 stdout 逐字节相同。工时单位 = 小时，
时间轴 0 = 开工日 00:00。
"""
import copy
import random
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")   # Windows 默认 GBK 控制台：编不出的字符变问号，别崩
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(errors="replace")   # 墙钟只写 stderr，stdout 里一个速度数字都没有

T0 = time.perf_counter()

W = "=" * 74
SEED = 20261105
DAY = 24
NDAYS = 24
BUDGET = 320
DUE_MARGIN = 12        # 合同交期 = 基线完工时刻 + 12 小时余量
PD_PER_TASK = 0.5      # 人日/返工任务（[6] 的假设，不是实测）
PD_MODEL = 1.0         # 建模时发现：改 1 处 0.5 + 重算 1 次方案 0.5（同样是假设）


def dw(s):
    return sum(2 if ord(c) > 0x2E80 else 1 for c in str(s))


def pad(s, n):
    s = str(s)
    return s + " " * max(0, n - dw(s))


def wrap2(prefix, text, limit=150):
    """页面里的 text 块不许横向滚动：超宽的一行在最近的分隔符处折一次，续行缩进。"""
    if dw(prefix + text) <= limit:
        return [prefix + text]
    for sep in ("：", "，", "、", "；"):
        for k in range(len(text), 0, -1):
            if text[k - 1] == sep and dw(prefix + text[:k]) <= limit:
                return [prefix + text[:k], "      " + text[k:]]
    return [prefix + text]


def norm(code):
    """设备编号归一化：去首尾空格再大写。脏数据里 'M03' 与 'M03 ' 是两个字符串、同一台设备。"""
    return str(code).strip().upper()


# ---------------------------------------------------------------- 真实主数据
MACH_DEF = [
    ("M01", "2000T 模锻压机", "forge"),
    ("M02", "五轴加工中心", "machining"),
    ("M03", "真空热处理炉", "heat"),
    ("M04", "钣金焊接工位", "weld"),
    ("M05", "总装工位", "assembly"),
    ("M06", "试车台", "test"),
]
CODE_ORDER = [c for c, _, _ in MACH_DEF]
SHIFT = {"forge": [(8, 20)], "machining": [(8, 20)], "heat": [(0, 24)],
         "weld": [(8, 20)], "assembly": [(8, 20)], "test": [(8, 20)]}
REST_DAYS = {7, 14, 21}          # 周日整厂停产（真空炉连续运行，只有计划检修）
DOWN = {"M03": [(120, 156)]}     # 台账里的保养/检修停产窗口
FAMS = ["盘件", "叶片", "机匣", "轴件"]
FAM_OPS = {"盘件": 5, "叶片": 4, "机匣": 6, "轴件": 5}     # 产品族工艺模板工序数
JOB_DEF = [
    ("WO-1001", "盘件", 4, [("M01", 2), ("M02", 2), ("M03", 1), ("M05", 2), ("M06", 2)]),
    ("WO-1002", "叶片", 4, [("M02", 2), ("M04", 2), ("M03", 1), ("M02", 2)]),
    ("WO-1003", "机匣", 3, [("M01", 2), ("M04", 2), ("M02", 3), ("M03", 2), ("M05", 2), ("M06", 1)]),
    ("WO-1004", "轴件", 5, [("M01", 2), ("M02", 2), ("M03", 1), ("M05", 2), ("M06", 2)]),
    ("WO-1005", "盘件", 3, [("M01", 3), ("M02", 2), ("M03", 2), ("M05", 2), ("M06", 1)]),
    ("WO-1006", "叶片", 3, [("M02", 3), ("M04", 2), ("M03", 2), ("M02", 2)]),
    ("WO-1007", "机匣", 4, [("M01", 1), ("M04", 2), ("M02", 2), ("M03", 2), ("M05", 1), ("M06", 2)]),
    ("WO-1008", "轴件", 3, [("M01", 2), ("M02", 3), ("M03", 1), ("M05", 2), ("M06", 2)]),
    ("WO-1009", "盘件", 5, [("M01", 1), ("M02", 2), ("M03", 2), ("M05", 1), ("M06", 2)]),
    ("WO-1010", "叶片", 4, [("M02", 2), ("M04", 3), ("M03", 1), ("M02", 1)]),
    ("WO-1011", "轴件", 4, [("M01", 2), ("M02", 1), ("M03", 2), ("M05", 2), ("M06", 1)]),
    ("WO-1012", "机匣", 2, [("M01", 3), ("M04", 2), ("M02", 3), ("M03", 2), ("M05", 3), ("M06", 2)]),
]


def build_windows(kind, down=()):
    """班制模板 -> 可用窗口列表（小时）。down 是保养停产，整段减掉。"""
    out = []
    for d in range(NDAYS):
        if kind != "heat" and d in REST_DAYS:
            continue
        for (a, b) in SHIFT[kind]:
            out.append([d * DAY + a, d * DAY + b])
    for (ds, de) in down:
        nxt = []
        for (s, e) in out:
            if de <= s or ds >= e:
                nxt.append([s, e])
                continue
            if s < ds:
                nxt.append([s, ds])
            if e > de:
                nxt.append([de, e])
        out = nxt
    return [(s, e) for s, e in out if e > s]


def setup_true(code, fa, fb):
    """真实换型矩阵（产品族 A->B 的分钟数换算成小时）：同族 0，跨族 1~3 小时。"""
    if fa == fb:
        return 0
    c = CODE_ORDER.index(norm(code)) if norm(code) in CODE_ORDER else 0
    q = FAMS.index(fa) * len(FAMS) + FAMS.index(fb)
    return 1 + (c * 3 + q * 2) % 3


def make_clean():
    mach = {}
    for code, nm, kind in MACH_DEF:
        mach[code] = {"name": nm, "kind": kind, "down": list(DOWN.get(code, ())),
                      "wins": build_windows(kind, DOWN.get(code, ()))}
    jobs = []
    raw = []
    for no, fam, lot, route in JOB_DEF:
        ops = [{"seq": k, "mc": code, "unit": u, "wf": u * lot}
               for k, (code, u) in enumerate(route, start=1)]
        jobs.append({"no": no, "fam": fam, "lot": lot, "ops": ops,
                     "by_seq": {o["seq"]: o for o in ops},
                     "links": {o["seq"]: True for o in ops[:-1]}})
        for o in ops:
            raw.append((no, o["seq"], o["mc"], o["unit"]))
    setup = {code: {(fa, fb): setup_true(code, fa, fb) for fa in FAMS for fb in FAMS}
             for code in mach}
    erp = {j["no"]: j["lot"] for j in jobs}
    mes = {(j["no"], o["seq"]): o["wf"] for j in jobs for o in j["ops"]}
    return {"mach": mach, "jobs": jobs, "setup": setup, "raw": raw,
            "erp": erp, "mes": mes}


CLEAN = make_clean()


def fresh():
    return copy.deepcopy(CLEAN)


def j_idx(inst, no):
    for i, j in enumerate(inst["jobs"]):
        if j["no"] == no:
            return i
    raise KeyError(no)


def all_ops(inst):
    return [(i, o["seq"]) for i, j in enumerate(inst["jobs"]) for o in j["ops"]]


def opdur(inst, op):
    return inst["jobs"][op[0]]["by_seq"][op[1]]["wf"]


def opmach(inst, op):
    return inst["jobs"][op[0]]["by_seq"][op[1]]["mc"]


def opfam(inst, op):
    return inst["jobs"][op[0]]["fam"]


def get_setup(inst, code, fa, fb):
    if fa == fb:
        return 0
    tbl = inst["setup"].get(code) or inst["setup"].get(norm(code)) or {}
    return tbl.get((fa, fb), 0)


def prec_arcs(inst):
    """工艺路线邻接表：只有 links[seq] 为真才建约束（缺边 = 模型认为这道工序可以提前开工）。"""
    out = []
    for i, j in enumerate(inst["jobs"]):
        for a, b in zip(j["ops"], j["ops"][1:]):
            if j["links"].get(a["seq"], True):
                out.append(((i, a["seq"]), (i, b["seq"]), opdur(inst, (i, a["seq"]))))
    return out


def fit(t, p, wins):
    """最早开工 s >= t 使 [s, s+p] 整段落进某个可用窗口；任何窗口都装不下时退回窗口起点，
       由 G5 判红——这正是「模型里可行、车间里不行」的样子。"""
    for (a, b) in wins:
        if b <= t or b - a < p:
            continue
        s = t if t >= a else a
        if s + p <= b:
            return s
    fb = None
    for (a, b) in wins:
        s = t if t >= a else a
        if fb is None or s < fb:
            fb = s
    return fb if fb is not None else t


def simulate(inst, order):
    """给定每台设备的加工顺序 -> 同时满足工艺先后、换型、班次窗口的最早开工时刻。有环返回 None。"""
    nodes = [op for seq in order.values() for op in seq]
    inset = set(nodes)
    if len(inset) != len(nodes):
        return None, None
    lag, indeg = {}, dict((op, 0) for op in nodes)
    for (a, b, w) in prec_arcs(inst):
        if a in inset and b in inset:
            lag.setdefault(a, []).append((b, w))
            indeg[b] += 1
    for seq in order.values():
        for a, b in zip(seq, seq[1:]):
            code = opmach(inst, a)
            w = opdur(inst, a) + get_setup(inst, code, opfam(inst, a), opfam(inst, b))
            lag.setdefault(a, []).append((b, w))
            indeg[b] += 1
    ready = sorted([op for op in nodes if indeg[op] == 0])
    st, done = {}, 0
    while ready:
        n = ready.pop(0)
        done += 1
        st.setdefault(n, 0)
        for (c, w) in lag.get(n, ()):
            if st.get(c, 0) < st[n] + w:
                st[c] = st[n] + w
            indeg[c] -= 1
            if indeg[c] == 0:
                pos = len(ready)
                while pos and ready[pos - 1] > c:
                    pos -= 1
                ready.insert(pos, c)
    if done < len(nodes):
        return None, None
    for _ in range(40):                                  # 班次顺延只会推后时刻，推后又得连带顺延
        moved = False
        for op in sorted(st, key=lambda x: (st[x], x)):
            p = opdur(inst, op)
            wins = inst["mach"].get(opmach(inst, op), {}).get("wins")
            if wins:
                s2 = fit(st[op], p, wins)
                if s2 > st[op]:
                    st[op] = s2
                    moved = True
            for (c, w) in lag.get(op, ()):
                if st[c] < st[op] + w:
                    st[c] = st[op] + w
                    moved = True
        if not moved:
            break
    return st, max(st[n] + opdur(inst, n) for n in st)


def greedy(inst, mode):
    """活动调度：每步在所有「硬前序已派」的工序里挑一个，换型与班次都算进最早开工时刻。"""
    order = dict((code, []) for code in inst["mach"])
    preds = {}
    for (a, b, w) in prec_arcs(inst):
        preds.setdefault(b, []).append(a)
    todo = all_ops(inst)
    st, done = {}, set()
    while len(done) < len(todo):
        cand = []
        for op in todo:
            if op in done or any(p not in done for p in preds.get(op, ())):
                continue
            code = opmach(inst, op)
            lo = 0
            for p in preds.get(op, ()):
                lo = max(lo, st[p] + opdur(inst, p))
            if order.get(code):
                last = order[code][-1]
                lo = max(lo, st[last] + opdur(inst, last)
                         + get_setup(inst, code, opfam(inst, last), opfam(inst, op)))
            p = opdur(inst, op)
            wins = inst["mach"][code]["wins"]
            s = fit(lo, p, wins) if wins else lo
            rest = sum(opdur(inst, (op[0], o["seq"])) for o in inst["jobs"][op[0]]["ops"]
                       if o["seq"] >= op[1])
            key = ((s, p, op) if mode == 0 else (p, s, op) if mode == 1 else (-rest, s, p, op))
            cand.append((key, op, s, code))
        if not cand:
            break
        cand.sort(key=lambda x: x[0])
        _, op, s, code = cand[0]
        st[op] = s
        order.setdefault(code, []).append(op)
        done.add(op)
    return order


def solve(inst, seed=SEED, budget=BUDGET):
    """三条派工规则取最优，再接固定评估次数的随机重启爬山（预算写死次数，不写墙钟）。"""
    ev = [0]

    def value(order):
        ev[0] += 1
        return simulate(inst, order)[1]

    best, best_order = None, None
    for mode in (0, 1, 2):
        o = greedy(inst, mode)
        v = value(o)
        if v is not None and (best is None or v < best):
            best, best_order = v, o
    if best is None:
        return None, {}, {}, ev[0]
    rnd = random.Random(seed)
    codes = sorted(best_order)
    while ev[0] < budget:
        cand = dict((k, list(v)) for k, v in best_order.items())
        for _ in range(2):
            k = rnd.choice(codes)
            seq = cand[k]
            if len(seq) >= 2:
                a = rnd.randrange(len(seq) - 1)
                b = rnd.randrange(a + 1, len(seq))
                seq.insert(b, seq.pop(a))
        cur = value(cand)
        if cur is None:
            continue
        improved = True
        while improved and ev[0] < budget:
            improved = False
            for k in sorted(cand):
                seq = cand[k]
                n = len(seq)
                for a in range(n - 1):
                    for b in range(a + 1, n):
                        if ev[0] >= budget:
                            break
                        before = list(seq)
                        seq.insert(b, seq.pop(a))
                        v = value(cand)
                        if v is not None and v < cur:
                            cur, improved = v, True
                        else:
                            cand[k] = before
                    if ev[0] >= budget:
                        break
                if ev[0] >= budget:
                    break
        if cur < best:
            best = cur
            best_order = dict((k, list(v)) for k, v in cand.items())
    st, cmax = simulate(inst, best_order)
    return cmax, best_order, st, ev[0]


def topo_ranks(inst):
    """只按工艺先后做拓扑排序（真实数据里的先后是无环的）：每台设备都按拓扑名次排，就不会成环。"""
    nodes = all_ops(inst)
    lag = dict((op, []) for op in nodes)
    indeg = dict((op, 0) for op in nodes)
    for (a, b, w) in prec_arcs(inst):
        if a in lag and b in indeg:
            lag[a].append(b)
            indeg[b] += 1
    ready = sorted([op for op in nodes if indeg[op] == 0])
    rank, k = {}, 0
    while ready:
        n = ready.pop(0)
        rank[n] = k
        k += 1
        for c in sorted(lag[n]):
            indeg[c] -= 1
            if indeg[c] == 0:
                pos = len(ready)
                while pos and ready[pos - 1] > c:
                    pos -= 1
                ready.insert(pos, c)
    for op in sorted(nodes):                     # 先后不明的工序排在最后，名次按工序号定
        if op not in rank:
            rank[op] = k
            k += 1
    return rank


def realize(truth, order, st):
    """把这份机器顺序搬到真实数据上：编号归一化落位、补齐模型漏排的工序、修好被违反的先后。"""
    items = []
    for code, seq in order.items():
        for op in seq:
            items.append((st.get(op, 0), op, code))
    items.sort(key=lambda x: (x[0], x[1], x[2]))
    merged = dict((code, []) for code in truth["mach"])
    for (_s, op, code) in items:
        merged.setdefault(norm(code), []).append(op)
    have = set(op for seq in merged.values() for op in seq)
    inserted = 0
    for op in all_ops(truth):
        if op in have:
            continue
        code = norm(opmach(truth, op))
        merged.setdefault(code, [])
        pos = len(merged[code])
        seqs = [o["seq"] for o in truth["jobs"][op[0]]["ops"]]
        for k in range(seqs.index(op[1]) - 1, -1, -1):
            prev = (op[0], seqs[k])
            if prev in have and norm(opmach(truth, prev)) == code:
                pos = merged[code].index(prev) + 1
                break
        merged[code].insert(pos, op)
        inserted += 1
        have.add(op)
    repairs = 0
    for _ in range(60):
        pos = {}
        for c, seq in merged.items():
            for k, op in enumerate(seq):
                pos[op] = (c, k)
        bad = None
        for (a, b, w) in prec_arcs(truth):
            if a in pos and b in pos and pos[a][0] == pos[b][0] and pos[b][1] < pos[a][1]:
                bad = (a, b, pos[a][0])
                break
        if bad is None:
            break
        a, b, c = bad
        seq = merged[c]
        seq.remove(b)
        seq.insert(seq.index(a) + 1, b)
        repairs += 1
    st2, cmax2 = simulate(truth, merged)
    resort = 0
    if cmax2 is None:                            # 同设备修补修不掉的环：整台设备按拓扑名次重排
        rk = topo_ranks(truth)
        last = len(rk)
        for code in sorted(merged):
            seq = merged[code]
            old = dict((op, k) for k, op in enumerate(seq))
            seq.sort(key=lambda op: (rk.get(op, last), op))
            resort += sum(1 for k, op in enumerate(seq) if old[op] != k)
        st2, cmax2 = simulate(truth, merged)
    return cmax2, st2, merged, repairs, inserted, resort


VKEYS = ["工艺顺序", "同机重叠", "换型不足", "窗口外", "幽灵工序", "漏排工序"]


def audit(truth, order, st):
    """把报出的时刻原样下发到真实车间验收：不改任何时刻，只按真实主数据数违规。"""
    v = dict((k, 0) for k in VKEYS)
    ops_in = {}
    for code, seq in order.items():
        for op in seq:
            ops_in[op] = code
    for code, seq in order.items():
        if code not in truth["mach"]:
            v["幽灵工序"] += len(seq)
    for op in all_ops(truth):
        if op not in ops_in:
            v["漏排工序"] += 1
    for (a, b, w) in prec_arcs(truth):
        if a in ops_in and b in ops_in and st[b] < st[a] + opdur(truth, a):
            v["工艺顺序"] += 1
    grp = {}
    for op, code in ops_in.items():
        grp.setdefault(norm(code), []).append(op)
    for code, seq in sorted(grp.items()):
        seq = sorted(seq, key=lambda o: (st.get(o, 0), o))
        wins = truth["mach"].get(code, {}).get("wins", [])
        for a, b in zip(seq, seq[1:]):
            gap = st.get(b, 0) - st.get(a, 0)
            need = opdur(truth, a)
            if gap < need:
                v["同机重叠"] += 1
            elif gap < need + setup_true(code, opfam(truth, a), opfam(truth, b)):
                v["换型不足"] += 1
        for op in seq:
            p = opdur(truth, op)
            if not any(w[0] <= st.get(op, 0) and st.get(op, 0) + p <= w[1] for w in wins):
                v["窗口外"] += 1
    return v


def lb_mach_cal(inst, code):
    """平凡下界（日历版）：这台设备的忙工时最早能在台账窗口里堆到几点，makespan 不可能早于它。"""
    busy = sum(opdur(inst, op) for op in all_ops(inst)
               if norm(opmach(inst, op)) == norm(code))
    rem = busy
    for (a, b) in sorted(inst["mach"][code]["wins"]):
        if b <= a:
            continue
        if rem <= b - a:
            return a + rem
        rem -= b - a
    return None


def loads(inst, cmax):
    """设备负荷率 = 该设备忙工时 / 它在方案周期内的可用工时；周期未知（无解）时返回 None。"""
    if cmax is None:
        return None
    out = {}
    for code in inst["mach"]:
        busy = sum(opdur(inst, op) for op in all_ops(inst)
                   if norm(opmach(inst, op)) == norm(code))
        avail = sum(max(0, min(e, cmax) - s) for (s, e) in inst["mach"][code]["wins"] if e > 0)
        out[code] = (busy, avail, busy / avail * 100 if avail > 0 else 0.0)
    return out

# ------------------------------------------------- 数据体检规则（[5] 节用，[3] 节也要查）
RULES = [
    ("G1", "工时>0", "标准工时列必须为正数"),
    ("G2", "工时=单件x批量", "工时列与「单件工时 x 批量 / 并行台数」复算一致"),
    ("G3", "工艺路线连通", "seq 连续 + 依赖边数 = 工序数-1 + 工序数 = 族模板"),
    ("G4", "编号唯一", "设备编号归一化后不重号；(工单,seq) 不重号；引用不悬空"),
    ("G5", "日历覆盖排入工序", "方案每道工序 [开工,完工) 落在台账窗口内"),
    ("G6", "换型时间非负", "换型矩阵无空值、无负值"),
    ("G7", "换型矩阵非全零", "同设备 >=2 个族时跨族格必须有正值"),
    ("G8", "日历对班制模板", "设备窗口 = 该类型标准班次扣除保养停产（外部模板）"),
    ("G9", "批量对 ERP 数量", "route 用到的批量 = ERP 订单数量（外部系统）"),
    ("G10", "工时对 MES 实绩", "标准工时 vs 上报实绩，偏差 >50% 判红（外部系统）"),
]
GCODES = [g for g, _, _ in RULES]
INNER = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]
EXT = ["G9", "G10"]


def checks(inst, order, st):
    c = {}
    c["G1"] = any(opdur(inst, op) <= 0 for op in all_ops(inst))
    c["G2"] = any(rec["wf"] != rec["unit"] * inst["jobs"][i]["lot"]
                  for i in range(len(inst["jobs"])) for rec in inst["jobs"][i]["ops"])
    bad = False
    for j in inst["jobs"]:
        sq = [o["seq"] for o in j["ops"]]
        if sq != list(range(1, len(sq) + 1)) or len(sq) != FAM_OPS[j["fam"]]:
            bad = True
        if any(v is False for v in j["links"].values()):
            bad = True
        if len(set(sq)) != len(sq):
            bad = True
    c["G3"] = bad
    codes = list(inst["mach"])
    refs = set(opmach(inst, op) for op in all_ops(inst))
    keys = set((r[0], r[1]) for r in inst["raw"])
    c["G4"] = (len(set(norm(x) for x in codes)) != len(codes)
               or any(norm(x) not in inst["mach"] for x in refs)
               or len(keys) != len(inst["raw"]))
    c["G5"] = st is None or any(
        not any(w[0] <= st[op] and st[op] + opdur(inst, op) <= w[1]
                for w in inst["mach"].get(opmach(inst, op), {}).get("wins", []))
        for op in all_ops(inst) if op in st)
    vals = [v for code in inst["setup"] for v in inst["setup"][code].values()]
    c["G6"] = any(v is None or v < 0 for v in vals)
    bad7 = False
    for code in inst["mach"]:
        fams = set(opfam(inst, op) for op in all_ops(inst)
                   if norm(opmach(inst, op)) == norm(code))
        if len(fams) >= 2 and all(get_setup(inst, code, fa, fb) == 0
                                  for fa in fams for fb in fams if fa != fb):
            bad7 = True
    c["G7"] = bad7
    c["G8"] = any(inst["mach"][code]["wins"]
                  != build_windows(inst["mach"][code]["kind"], inst["mach"][code]["down"])
                  for code in inst["mach"])
    c["G9"] = any(j["lot"] != inst["erp"][j["no"]] for j in inst["jobs"])
    c["G10"] = any(abs(rec["wf"] - inst["mes"][(j["no"], rec["seq"])])
                   > 0.5 * inst["mes"][(j["no"], rec["seq"])]
                   for j in inst["jobs"] for rec in j["ops"])
    return c

# ---------------------------------------------------------------- 缺陷注入
CASES = []


def add(tag, label, spot, expect, build):
    truth, model, note = build()
    CASES.append({"tag": tag, "label": label, "spot": spot, "expect": expect,
                  "truth": truth, "model": model, "note": note})


def b_d1a():
    m = fresh()
    op = (j_idx(m, "WO-1004"), 2)
    old = opdur(m, op)
    m["jobs"][op[0]]["by_seq"][op[1]]["wf"] = old * 10
    return fresh(), m, "route 表 %s seq=%d（%s）工时列 %dh -> %dh：小数点错位，单件工时列没动" % (
        m["jobs"][op[0]]["no"], op[1], opmach(m, op), old, old * 10)


def b_d1b():
    m = fresh()
    op = (j_idx(m, "WO-1009"), 2)
    old = opdur(m, op)
    m["jobs"][op[0]]["by_seq"][op[1]]["wf"] = 0
    return fresh(), m, "route 表 %s seq=%d（%s）工时列 %dh -> 0：空值当 0 落库" % (
        m["jobs"][op[0]]["no"], op[1], opmach(m, op), old)


def b_d1c():
    m = fresh()
    op = (j_idx(m, "WO-1007"), 4)
    rec = m["jobs"][op[0]]["by_seq"][op[1]]
    old, lot = rec["unit"], m["jobs"][op[0]]["lot"]
    rec["unit"] = old * 10
    rec["wf"] = rec["unit"] * lot
    return fresh(), m, "工艺参数 %s seq=%d（%s）单件工时 %dh -> %dh，工时列跟着重算 = 内部自洽（%dh -> %dh）" % (
        m["jobs"][op[0]]["no"], op[1], opmach(m, op), old, old * 10, old * lot, old * 10 * lot)


def b_d2a():
    m = fresh()
    i = j_idx(m, "WO-1004")
    seqs = [o["seq"] for o in m["jobs"][i]["ops"]]
    drop = seqs[1]
    m["jobs"][i]["links"][drop] = False
    a = m["jobs"][i]["by_seq"][drop]
    b = m["jobs"][i]["by_seq"][seqs[2]]
    return fresh(), m, "工序先后邻接表删一行：(%s,%d) -> (%s,%d) 这条边丢了，" \
        "模型认为 %s 那道可以不等 %s 做完就开工" % (
            a["mc"], drop, b["mc"], seqs[2], b["mc"], a["mc"])


def b_d2b():
    m = fresh()
    i = j_idx(m, "WO-1002")
    rec = m["jobs"][i]["by_seq"][3]
    gone = "%s(%s)" % (rec["mc"], CLEAN["mach"][norm(rec["mc"])]["name"])
    m["jobs"][i]["ops"] = [o for o in m["jobs"][i]["ops"] if o["seq"] != 3]
    del m["jobs"][i]["by_seq"][3]
    m["jobs"][i]["links"] = dict((o["seq"], True) for o in m["jobs"][i]["ops"][:-1])
    m["raw"] = [r for r in m["raw"] if not (r[0] == "WO-1002" and r[1] == 3)]
    return fresh(), m, "工艺路线表整行漏录：%s 那道工序在模型里不存在（真空炉被整体绕过）" % gone


def b_d3():
    m = fresh()
    m["mach"]["M05"]["wins"] = [(d * DAY, d * DAY + DAY) for d in range(NDAYS)]
    return fresh(), m, "设备日历：M05 %s 由 8-20 两班录成 0-24 连续（漏录班制与周日停产）" % (
        CLEAN["mach"]["M05"]["name"])


def b_d4a():
    m = fresh()
    ghost = "M02 "
    m["mach"][ghost] = {"name": CLEAN["mach"]["M02"]["name"], "kind": "machining",
                        "down": [], "wins": build_windows("machining")}
    m["setup"][ghost] = dict(CLEAN["setup"]["M02"])
    i = j_idx(m, "WO-1003")
    m["jobs"][i]["by_seq"][3]["mc"] = ghost
    for r in m["raw"]:
        if r[0] == "WO-1003" and r[1] == 3:
            m["raw"][m["raw"].index(r)] = (r[0], r[1], ghost, r[3])
    return fresh(), m, "resources 台账把五轴加工中心登记两行（'M02' 与 'M02 ' 差一个尾随空格），" \
                       "WO-1003 的铣工序被引到 'M02 ' 这台幽灵设备上，与真 M02 并行开工"


def b_d4b():
    t = fresh()
    m = fresh()
    i = j_idx(t, "WO-1006")
    t["jobs"][i]["ops"] = t["jobs"][i]["ops"] + [{"seq": 5, "mc": "M02", "unit": 2,
                                                 "wf": 2 * t["jobs"][i]["lot"]}]
    t["jobs"][i]["by_seq"] = dict((o["seq"], o) for o in t["jobs"][i]["ops"])
    t["jobs"][i]["links"] = dict((o["seq"], True) for o in t["jobs"][i]["ops"][:-1])
    m["raw"] = m["raw"] + [("WO-1006", 4, "M02", 2)]     # 光整那道按 (工单,seq)=(WO-1006,4) 落库
    return t, m, "路线表 (工单,seq) 重号：(WO-1006,4) 有两行（粗铣与光整），" \
                 "模型按键去重只留一道，M02 上少排一道工序"


def b_d5():
    m = fresh()
    for code in m["setup"]:
        for k in m["setup"][code]:
            m["setup"][code][k] = 0
    return fresh(), m, "换型矩阵整表写成 0（交付清单 A4 的族 A->B 二维表没给，只有全局常数）"


def b_d6a():
    m = fresh()
    i = j_idx(m, "WO-1004")
    old = m["jobs"][i]["lot"]
    m["jobs"][i]["lot"] = 1
    for o in m["jobs"][i]["ops"]:
        o["wf"] = o["unit"] * 1
    return fresh(), m, "订单数量：WO-1004 批量 %d 件 -> 1 件（ERP 改单没回写 route），" \
                       "该单 %d 道工序工时等比缩小" % (old, len(m["jobs"][i]["ops"]))


SPOTS = [("D1a", "工时 x10（小数点错位）", "route.标准工时", ["G2"]),
         ("D1b", "工时 = 0（漏录）", "route.标准工时", ["G1"]),
         ("D1c", "单件工时 x10（自洽）", "工艺参数.单件工时", ["G10"]),
         ("D2a", "工艺路线依赖边缺失", "邻接表.(order_no,seq)", ["G3"]),
         ("D2b", "工序行缺失（绕过炉子）", "route.整行", ["G3"]),
         ("D3", "设备日历错录为连续", "日历.班制", ["G5", "G8"]),
         ("D4a", "设备编号重复（幽灵）", "resources.编号", ["G4"]),
         ("D4b", "工序号重号（去重）", "route.(工单,seq)", ["G4"]),
         ("D5", "换型时间当成 0", "换型矩阵", ["G6", "G7"]),
         ("D6a", "批量/数量录错", "订单.数量", ["G9"])]
for (tag, label, spot, exp), fn in zip(SPOTS, [b_d1a, b_d1b, b_d1c, b_d2a, b_d2b,
                                              b_d3, b_d4a, b_d4b, b_d5, b_d6a]):
    add(tag, label, spot, exp, fn)


# ---------------------------------------------------------------- [1] 干净基线
print(W)
print("[1] 干净基线：五张主数据表喂进同一个求解器，报出=真实、违规=0")
print(W)
NOP = len(all_ops(CLEAN))
TOTH = sum(opdur(CLEAN, op) for op in all_ops(CLEAN))
print("  算例：工单 %d 张（%s 共 %d 族），设备 %d 台，工序 %d 道，加工工时合计 %dh（各工序之和，与并行无关）"
      % (len(CLEAN["jobs"]), "/".join(FAMS), len(FAMS), len(CLEAN["mach"]), NOP, TOTH))
print("  时间单位 = 小时，0 = 开工日 00:00；周日整厂停产（真空炉例外，它只有计划检修 %d-%dh）"
      % DOWN["M03"][0])
print("  " + pad("编号", 6) + pad("设备名称", 18) + pad("班制", 12) + pad("日均可用", 10)
      + pad("停产窗口", 12) + pad("排入工序", 9) + pad("忙工时", 8) + "台账负荷")
for code, nm, kind in MACH_DEF:
    wins = CLEAN["mach"][code]["wins"]
    per = sum(e - s for (s, e) in wins) / NDAYS
    nin = sum(1 for op in all_ops(CLEAN) if opmach(CLEAN, op) == code)
    busy = sum(opdur(CLEAN, op) for op in all_ops(CLEAN) if opmach(CLEAN, op) == code)
    dn = CLEAN["mach"][code]["down"]
    print("  " + pad(code, 6) + pad(nm, 18) + pad("%d 班段/日" % len(SHIFT[kind]), 12)
          + pad("%.1fh" % per, 10) + pad("无" if not dn else "%d-%dh" % dn[0], 12)
          + pad(nin, 9) + pad("%dh" % busy, 8) + "%.0f%%" % (busy / (per * NDAYS) * 100))
NSW = len(CODE_ORDER) * len(FAMS) * (len(FAMS) - 1)
NZW = sum(1 for c in CODE_ORDER for fa in FAMS for fb in FAMS if setup_true(c, fa, fb) > 0)
print("  换型矩阵：%d 台 x %d 个跨族转移 = %d 格，非零 %d 格；路线模板按族给工序数 %s"
      % (len(CODE_ORDER), len(FAMS) * (len(FAMS) - 1), NSW, NZW,
         "、".join("%s %d 道" % (f, FAM_OPS[f]) for f in FAMS)))
cmax0, order0, st0, ev0 = solve(CLEAN)
cmax0b, order0b, st0b, ev0b = solve(CLEAN)
assert cmax0 == cmax0b and order0 == order0b and st0 == st0b, "基线不可复现"
LB_CHAIN = max(sum(opdur(CLEAN, (i, o["seq"])) for o in j["ops"])
               for i, j in enumerate(CLEAN["jobs"]))
LB_MACH = max(sum(opdur(CLEAN, op) for op in all_ops(CLEAN) if opmach(CLEAN, op) == c)
              for c in CLEAN["mach"])
LB_CAL = max(lb_mach_cal(CLEAN, c) or 0 for c in CLEAN["mach"])
LB = max(LB_CHAIN, LB_CAL)
aud0 = audit(CLEAN, order0, st0)
assert sum(aud0.values()) == 0, aud0
real0, rst0, rord0, rep0, ins0, rs0 = realize(CLEAN, order0, st0)
print("  基线方案：报出 makespan %dh（%.2f 天），评估 %d 次；"
      "平凡下界 %dh（最长工艺链 %d / 最忙设备纯工时 %d / 该设备日历累计 %d）"
      % (cmax0, cmax0 / DAY, ev0, LB, LB_CHAIN, LB_MACH, LB_CAL))
print("  真实校验同一份方案：报出=真实（%d vs %d），六类硬违规合计 %d 个，"
      "顺序修补 %d 次、拓扑重排 %d 道、补排 %d 道"
      % (cmax0, real0, sum(aud0.values()), rep0, rs0, ins0))
LOAD0 = loads(CLEAN, cmax0)
BN0 = max(LOAD0, key=lambda c: LOAD0[c][2])
DUE = {}
for i, j in enumerate(CLEAN["jobs"]):
    DUE[j["no"]] = max(st0[(i, o["seq"])] + opdur(CLEAN, (i, o["seq"])) for o in j["ops"]) + DUE_MARGIN
print("  对照行成立的条件：这一行的违规必须是 0，否则后面所有分歧都不是「数据坏了」造成的。")
print("  瓶颈 %s %s，方案周期内负荷 %.1f%%；合同交期按基线完工 +%dh 锁死，此后只换数据不换承诺。"
      % (BN0, CLEAN["mach"][BN0]["name"], LOAD0[BN0][2], DUE_MARGIN))
_iv = sorted((st0[op], st0[op] + opdur(CLEAN, op)) for op in all_ops(CLEAN))
_pk, _cur = 0, 0
for _t, _d in sorted([(a, 1) for a, _b in _iv] + [(b, -1) for _a, b in _iv]):
    _cur += _d
    if _cur > _pk:
        _pk = _cur
_idle = sum(1 for t in range(int(cmax0)) if not any(a <= t < b for a, b in _iv))
print("  并行度核对：峰值同时在跑 %d 道工序；%dh 方案周期里 %dh 全厂零工序在跑（班次窗口 + 周日停产）。"
      % (_pk, cmax0, _idle))
print("  makespan %dh 与加工工时合计 %dh 数值相等是两件事抵消的结果：确有并行（峰值 %d），但也有 %dh 谁都没干活。"
      % (cmax0, TOTH, _pk, _idle))

# ---------------------------------------------------------------- [2] 注入主表
print()
print(W)
print("[2] 缺陷注入：一次只坏一个字段，报出来的数与真实的数各是多少")
print(W)
print("  同一个求解器、同一 seed=%d、同一预算 %d 次评估，只有「模型看到的数据」不同。" % (SEED, BUDGET))
print("  注入点（其余字段与真实台账逐格相同）：")
for case in CASES:
    for ln in wrap2("    %s %s @ %s：" % (pad(case["tag"], 3), pad(case["label"], 22),
                                         pad(case["spot"], 22)), case["note"]):
        print(ln)
print("  报出 = 缺陷模型自己的 makespan；真实 = 那份设备顺序搬到真实数据上重算；基线 = 用真实数据重解。")
print("  " + pad("缺陷", 28) + pad("报出Cmax", 9) + pad("真实Cmax", 9) + pad("真值基线", 9)
      + pad("幻觉=报出-真实", 16) + pad("真实-基线", 12) + "方向")
RES = []
for case in CASES:
    mc, mo, mst, mev = solve(case["model"])
    rc, rst, rord, repairs, inserted, resort = realize(case["truth"], mo, mst)
    bc, _, _, bev = solve(case["truth"])
    hall = None if (mc is None or rc is None) else mc - rc
    gap = None if (rc is None or bc is None) else rc - bc
    if hall is None:
        direction = "这份顺序在真实数据下不可行"
    elif hall < 0:
        direction = "报得比真实好（乐观幻觉）"
    elif hall > 0:
        direction = "报得比真实差（保守）"
    else:
        direction = "无分歧"
    RES.append({"case": case, "mc": mc, "real": rc, "base": bc, "hall": hall, "gap": gap,
                "repairs": repairs, "inserted": inserted, "resort": resort,
                "real_st": rst, "model_st": mst,
                "real_order": rord, "model_order": mo, "dir": direction,
                "chk": checks(case["model"], mo, mst),
                "ev_model": mev, "ev_truth": bev,
                "audit": audit(case["truth"], mo, mst)})
    print("  " + pad("%s %s" % (case["tag"], case["label"]), 28)
          + pad("无解" if mc is None else mc, 9)
          + pad("无解" if rc is None else rc, 9)
          + pad(bc, 9)
          + pad("n/a" if hall is None else "%+d" % hall, 16)
          + pad("n/a" if gap is None else "%+d" % gap, 12) + direction)
opt = [r for r in RES if r["hall"] is not None and r["hall"] < 0]
pes = [r for r in RES if r["hall"] is not None and r["hall"] > 0]
zer = [r for r in RES if r["hall"] == 0]
print("  %d 个缺陷让报出的方案比真实更好（%s）；%d 个更差（%s）；%d 个报出=真实。"
      % (len(opt), "/".join(r["case"]["tag"] for r in opt) or "无",
         len(pes), "/".join(r["case"]["tag"] for r in pes) or "无", len(zer)))
if opt:
    bh = min(opt, key=lambda r: r["hall"])
    for ln in wrap2("  最危险的是 %s：" % bh["case"]["tag"], bh["case"]["note"]):
        print(ln)
    print("  报出 %dh、真实 %dh，小了 %dh——评审会上它是好消息，上线那天才是坏消息。"
          % (bh["mc"], bh["real"], -bh["hall"]))
gaps = [r for r in RES if r["gap"] is not None]
wg = max(gaps, key=lambda r: r["gap"])
print("  真实代价最大的是 %s：真实 %dh、基线 %dh，多花 %dh（%+.1f%%）。"
      % (wg["case"]["tag"], wg["real"], wg["base"], wg["gap"], wg["gap"] / wg["base"] * 100))
neg = [r for r in gaps if r["gap"] < 0]
print("  真实 makespan 低于基线的缺陷 %d 个（%s）：基线是启发式解不是最优解，"
      % (len(neg), "、".join(r["case"]["tag"] for r in neg) or "无"))
print("  所以「比基线好」不能当缺陷的证据，只有「报出与真实分叉」才是。")

# ---------------------------------------------------------------- [3] 违规明细
print()
print(W)
print("[3] 原样下发：把报出的开工时刻搬到真实车间，谁先在当天撞车")
print(W)
print("  这一节一个时刻都不改，只按真实主数据验收 [2] 那份方案——违规数就是车间当天要处理的条数。")
print("  " + pad("缺陷", 28) + pad("工艺顺序", 9) + pad("同机重叠", 9) + pad("换型不足", 9)
      + pad("窗口外", 7) + pad("幽灵工序", 9) + pad("漏排工序", 9) + pad("违规合计", 9)
      + pad("修补/重排", 11) + "补排工序")
tot_v = dict((k, 0) for k in VKEYS)
for r in RES:
    a = r["audit"]
    r["viol"] = sum(a.values())
    for k in VKEYS:
        tot_v[k] += a[k]
    print("  " + pad("%s %s" % (r["case"]["tag"], r["case"]["label"]), 28)
          + pad(a["工艺顺序"], 9) + pad(a["同机重叠"], 9) + pad(a["换型不足"], 9)
          + pad(a["窗口外"], 7) + pad(a["幽灵工序"], 9) + pad(a["漏排工序"], 9)
          + pad(r["viol"], 9) + pad("%d/%d" % (r["repairs"], r["resort"]), 11)
          + str(r["inserted"]))
print("  " + pad("基线（干净数据）", 28) + "".join(pad(0, 9) if k != "窗口外" else pad(0, 7)
                                                    for k in VKEYS)
      + pad(0, 9) + pad("%d/%d" % (rep0, rs0), 11) + str(ins0))
print("  分类合计：工艺顺序 %d、同机重叠 %d、换型不足 %d、窗口外 %d、幽灵工序 %d、漏排工序 %d，"
      % (tot_v["工艺顺序"], tot_v["同机重叠"], tot_v["换型不足"], tot_v["窗口外"],
         tot_v["幽灵工序"], tot_v["漏排工序"]))
print("  共 %d 处；顺序修补 %d 次、拓扑重排 %d 道（成环的方案必须重排才能开工），补排 %d 道工序。"
      % (sum(tot_v.values()), sum(r["repairs"] for r in RES),
         sum(r["resort"] for r in RES), sum(r["inserted"] for r in RES)))
quiet = [r for r in RES if r["viol"] == 0]
loud = max(RES, key=lambda r: r["viol"])
print("  %d/%d 个缺陷让方案在真实车间当天就撞车；违规最多的是 %s（%d 处）。"
      % (len(RES) - len(quiet), len(RES), loud["case"]["tag"], loud["viol"]))
if quiet:
    qdiv = [r for r in quiet if r["hall"]]
    print("  违规 0 处的缺陷 %d 个（%s）：原样下发不撞车也不报错，%s；"
          % (len(quiet), "、".join(r["case"]["tag"] for r in quiet),
             "只有 makespan 分了叉" if qdiv else "连 makespan 都没动"))
    print("  执行验收对%s完全无感：%s——只剩 [5] 的体检规则这一道关。"
          % ("它" if len(quiet) == 1 else "它们",
             "、".join("%s 报出 %dh/真实 %dh、%d 条规则报警"
                       % (r["case"]["tag"], r["mc"], r["real"],
                          sum(1 for g in GCODES if r["chk"][g])) for r in quiet)))
cyc = [r for r in RES if r["repairs"] > 0 or r["resort"] > 0]
if cyc:
    print("  顺序要动过才能落地的 %d 个（%s）：模型缺了先后边之后同设备顺序排反，"
          % (len(cyc), "、".join("%s 补%d/重排%d" % (r["case"]["tag"], r["repairs"], r["resort"])
                                 for r in cyc)))
    print("  [2] 的「真实Cmax」是这份顺序按真实先后重排之后重算的，不是模型自己报的数。")
else:
    print("  没有任何一份方案在真实数据下成环（修补与重排全 0）——缺先后边这次只是提前开工，没排反。")

# ---------------------------------------------------------------- [4] 幻觉方向
print()
print(W)
print("[4] 交期与产能：报出的数字在哪两个维度上比真实好看")
print(W)
print("  交期在 [1] 就按基线锁死了（每单完工 +%dh），下面只换数据、不换承诺。" % DUE_MARGIN)
print("  " + pad("缺陷", 28) + pad("报出违约", 10) + pad("真实违约", 10) + pad("违约幻觉", 10)
      + pad("报出承诺", 10) + "真实承诺")


def finish(i, inst, order, st):
    ops = [(i, o["seq"]) for o in inst["jobs"][i]["ops"]
           if any((i, o["seq"]) in s for s in order.values())]
    if not ops:
        return None
    return max(st.get(op, 0) + opdur(inst, op) for op in ops)


rows4 = []
for r in RES:
    truth, mo, mst = r["case"]["truth"], r["model_order"], r["model_st"]
    mm = mr = 0
    for i, j in enumerate(truth["jobs"]):
        fm = finish(i, r["case"]["model"], mo, mst)
        if fm is None or fm > DUE[j["no"]]:
            mm += 1
        fr = finish(i, truth, r["real_order"], r["real_st"]) if r["real_st"] else None
        if fr is None or fr > DUE[j["no"]]:
            mr += 1
    rows4.append((r, mm, mr))
    print("  " + pad("%s %s" % (r["case"]["tag"], r["case"]["label"]), 28) + pad(mm, 10)
          + pad(mr, 10) + pad("%+d" % (mm - mr), 10)
          + pad("n/a" if r["mc"] is None else "%.2f 天" % (r["mc"] / DAY), 10)
          + ("n/a" if r["real"] is None else "%.2f 天" % (r["real"] / DAY)))
print("  " + pad("基线（干净数据）", 28) + pad(0, 10) + pad(0, 10) + pad("+0", 10)
      + pad("%.2f 天" % (cmax0 / DAY), 10) + "%.2f 天" % (cmax0 / DAY))
liar = [(r, a, b) for (r, a, b) in rows4 if a < b]
print("  报出违约 < 真实违约的缺陷 %d 个（%s）：合同上一张单都不欠，落地才欠。"
      % (len(liar), "、".join(r["case"]["tag"] for r, a, b in liar) or "无"))
print("  其余 %d 个缺陷报出的违约数已经不小于真实（%s）：交期这一关它们是自己会暴露的。"
      % (len(rows4) - len(liar),
         "、".join(r["case"]["tag"] for r, a, b in rows4 if a >= b) or "无"))
print("  瓶颈识别错位：模型眼里的瓶颈 vs 真实台账算出来的瓶颈（负荷 = 忙工时/周期内可用工时）")
print("  " + pad("缺陷", 28) + pad("报出瓶颈", 12) + pad("报出负荷", 10) + pad("真实瓶颈", 12)
      + pad("真实负荷", 10) + "错位")
mis = 0
load_gap = []
for r in RES:
    truth = r["case"]["truth"]
    lm = loads(r["case"]["model"], r["mc"])
    lt = loads(truth, r["real"])
    if lm is None or lt is None:
        mis += 1
        print("  " + pad("%s %s" % (r["case"]["tag"], r["case"]["label"]), 28)
              + pad("n/a", 12) + pad("n/a", 10) + pad("n/a", 12) + pad("n/a", 10)
              + "是（周期算不出来，负荷率没了分母）")
        continue
    bm = max(lm, key=lambda c: (lm[c][2], c))
    bt = max(lt, key=lambda c: (lt[c][2], c))
    shift = norm(bm) != norm(bt)
    if shift:
        mis += 1
    ghost = "" if bm in truth["mach"] else "(幽灵)"
    load_gap.append((r, abs(lm[bm][2] - lt[bt][2]), bm, bt, lm[bm][2], lt[bt][2]))
    print("  " + pad("%s %s" % (r["case"]["tag"], r["case"]["label"]), 28)
          + pad(bm + ghost, 12) + pad("%.1f%%" % lm[bm][2], 10) + pad(bt, 12)
          + pad("%.1f%%" % lt[bt][2], 10) + ("是" if shift else "否"))
print("  基线瓶颈 %s（%.1f%%），忙工时比第二名多 %dh。"
      % (BN0, LOAD0[BN0][2],
         max(LOAD0[c][0] for c in LOAD0) - sorted(LOAD0[c][0] for c in LOAD0)[-2]))
if mis:
    print("  %d/%d 个缺陷把瓶颈挪到了另一台设备（%s）：加的那班人、买的那台设备都跟着错。"
          % (mis, len(RES),
             "、".join("%s 报出%s/真实%s" % (g[0]["case"]["tag"], g[2], g[3])
                       for g in load_gap if norm(g[2]) != norm(g[3]))))
else:
    print("  把瓶颈设备认错的缺陷 %d/%d：%s 从头到尾都是它——瓶颈这一列本次没出现「越坏越好看」。"
          % (mis, len(RES), BN0))
wg2 = max(load_gap, key=lambda x: x[1])
print("  但负荷率看错是实打实的：%s 报出 %.1f%%、真实 %.1f%%，差 %.1f 个百分点；"
      % (wg2[0]["case"]["tag"], wg2[4], wg2[5], wg2[1]))
print("  负荷差最大的四个（个百分点）%s——「加人/加设备」的建议照的就是这一列。"
      % "、".join("%s %.1f" % (g[0]["case"]["tag"], g[1])
                  for g in sorted(load_gap, key=lambda y: -y[1])[:4]))

# ---------------------------------------------------------------- [5] 门禁
print()
print(W)
print("[5] 数据体检：10 条便宜规则在 11 份实例上，抓到几个、漏掉几个")
print(W)


CHK0 = checks(CLEAN, order0, st0)
print("  " + pad("实例", 28) + "".join(pad(g, 5) for g in GCODES) + "报警规则条数")
print("  " + pad("基线（干净数据）", 28) + "".join(pad("Y" if CHK0[g] else ".", 5) for g in GCODES)
      + str(sum(1 for g in GCODES if CHK0[g])))
for r in RES:
    print("  " + pad("%s %s" % (r["case"]["tag"], r["case"]["label"]), 28)
          + "".join(pad("Y" if r["chk"][g] else ".", 5) for g in GCODES)
          + str(sum(1 for g in GCODES if r["chk"][g])))
print("  格子含义：Y = 这条规则对这份实例报警，. = 没报警。")
print("  " + pad("规则", 6) + pad("判据名", 20) + pad("设计该抓", 13) + pad("报警实例", 9)
      + pad("设计内命中", 10) + pad("跨类", 6) + pad("误报", 6) + pad("精确率", 7) + "判据原文")
EXPECT = dict((c["tag"], c["expect"]) for c in CASES)
WANT = dict((g, [r["case"]["tag"] for r in RES if g in EXPECT[r["case"]["tag"]]])
            for g, _, _ in RULES)
fp0 = sum(1 for g in GCODES if CHK0[g])
for g, nm, desc in RULES:
    fire = [r for r in RES if r["chk"][g]]
    inside = sum(1 for r in fire if g in EXPECT[r["case"]["tag"]])
    prec = inside / (len(fire) + fp0) * 100 if (len(fire) + fp0) else 0.0
    print("  " + pad(g, 6) + pad(nm, 20) + pad("/".join(WANT[g]) or "无", 13)
          + pad("%d/%d" % (len(fire), len(RES)), 9) + pad(inside, 10)
          + pad(len(fire) - inside, 6) + pad(fp0, 6) + pad("%.0f%%" % prec, 7) + desc)
caught = [r for r in RES if any(r["chk"][g] for g in GCODES)]
missed = [r for r in RES if not any(r["chk"][g] for g in GCODES)]
ci = [r for r in RES if any(r["chk"][g] for g in INNER)]
ce = [r for r in RES if any(r["chk"][g] for g in EXT)]
print("  抓到 %d/%d（召回 %.0f%%），漏掉：%s" % (len(caught), len(RES),
      len(caught) / len(RES) * 100, "、".join(r["case"]["tag"] for r in missed) or "无"))
print("  拆开看：只上内部一致性 %d 条抓 %d/%d；只上与 ERP/MES 对账那 %d 条抓 %d/%d。"
      % (len(INNER), len(ci), len(RES), len(EXT), len(ce), len(RES)))
print("  误报：干净数据上报警 %d 条规则（%s），精确率的分母里因此%s虚警。"
      % (fp0, "、".join(g for g in GCODES if CHK0[g]) or "无", "没有" if fp0 == 0 else "有"))
never = [g for g, _, _ in RULES if not any(r["chk"][g] for r in RES)]
if never:
    caught_tag = dict((r["case"]["tag"], any(r["chk"][g] for g in GCODES)) for r in RES)
    print("  全程 0 次报警：%s" % "；".join(
        "%s「%s」设计目标 %s，其中 %d/%d 由别的规则兜住"
        % (g, nm, "/".join(WANT[g]) or "无",
           sum(1 for t in WANT[g] if caught_tag.get(t)), len(WANT[g]))
        for g, nm, desc in RULES if g in never))
zprec = [(g, nm, sum(1 for r in RES if r["chk"][g])) for g, nm, desc in RULES
         if any(r["chk"][g] for r in RES)
         and not any(r["chk"][g] and g in EXPECT[r["case"]["tag"]] for r in RES)]
if zprec:
    print("  报了警但从没报在自己设计的缺陷上：%s——照这 %d 条写验收条款，功劳全是别的规则的。"
          % ("、".join("%s「%s」%d 次报警全属跨类" % (g, nm, n) for g, nm, n in zprec),
             len(zprec)))
only_ext = [r for r in RES if not any(r["chk"][g] for g in INNER)
            and any(r["chk"][g] for g in EXT)]
print("  只有外部对账才抓到的缺陷 %d 个（%s）：这类数据在 %d 条内部一致性规则里全绿，"
      % (len(only_ext), "、".join(r["case"]["tag"] for r in only_ext) or "无", len(INNER)))
print("  只有跟 ERP/MES 比才看得见——门禁不是脚本问题，是接口问题。")
cross = [(r["case"]["tag"], g) for r in RES for g in GCODES
         if r["chk"][g] and g not in EXPECT[r["case"]["tag"]]]
nfire = sum(1 for r in RES for g in GCODES if r["chk"][g])
print("  跨类命中 %d 处（%s）：全部 %d 次报警里 %d 次是规则本来没设计的错——能拦是好事，但别写进验收条款。"
      % (len(cross), "、".join("%s->%s" % (t, g) for t, g in cross) or "无", nfire, len(cross)))

# ---------------------------------------------------------------- [6] 成本账
print()
print(W)
print("[6] 成本账：同一处脏数据，建模时改 vs 上线后返工，差几倍")
print(W)
print("  先把假设摆出来——这一节的两个单价是假设，不是实测：")
print("    假设 1：改一处主数据 = %.1f 人日（找工艺员确认 + 改 + 复核）" % PD_PER_TASK)
print("    假设 2：方案下发后返工一个下游任务 = %.1f 人日（撤单、重新派工、现场改派）" % PD_PER_TASK)
print("    假设 3：建模时发现 = 改 1 处 + 重算 1 次方案 = %.1f 人日，与缺陷种类无关" % PD_MODEL)
print("  实测那一列是返工下游任务数 = 开工时刻被改动的工序数 + 模型漏排必须补上的工序数，")
print("  由 [2][3] 两份时刻表逐工序对比得到（同 seed、同顺序、只把数据换成真实的）。")
print("  " + pad("缺陷", 28) + pad("返工任务数", 11) + pad("占工序总数", 11)
      + pad("建模时", 10) + pad("上线后", 10) + pad("倍数", 8) + "上线后折人周")


def rework(r):
    """返工任务数 = 开工时刻被改动的工序数 + 模型里根本不存在、必须补排的工序数（不重复计）。"""
    n = 0
    for op in all_ops(r["case"]["truth"]):
        a = r["model_st"].get(op)
        if a is None:                       # 模型漏排的工序记在 inserted 那一列
            continue
        b = (r["real_st"] or {}).get(op)
        if b is None or b != a:
            n += 1
    return n + r["inserted"]


def gpp(r):
    """真实-基线 的百分比；真实算不出来（None）时返回 None，不参与统计。"""
    if r["gap"] is None or not r["base"]:
        return None
    return 100.0 * r["gap"] / r["base"]


def fg(v):
    return "n/a" if v is None else "%+.1f%%" % v


cost = []
n0 = rework({"case": {"truth": CLEAN}, "model_st": st0, "real_st": rst0, "inserted": ins0})
print("  " + pad("基线（干净数据）", 28) + pad(n0, 11) + pad("%.0f%%" % (n0 / NOP * 100), 11)
      + pad("%.1f 人日" % PD_MODEL, 10) + pad("%.1f 人日" % (PD_PER_TASK + n0 * PD_PER_TASK), 10)
      + pad("x%.1f" % ((PD_PER_TASK + n0 * PD_PER_TASK) / PD_MODEL), 8)
      + "%.2f 人周" % ((PD_PER_TASK + n0 * PD_PER_TASK) / 5))
for r in RES:
    n = rework(r)
    pd_a = PD_PER_TASK + n * PD_PER_TASK
    tot_op = len(all_ops(r["case"]["truth"]))
    cost.append((r, n, pd_a, pd_a / PD_MODEL, gpp(r)))
    print("  " + pad("%s %s" % (r["case"]["tag"], r["case"]["label"]), 28) + pad(n, 11)
          + pad("%.0f%%" % (n / tot_op * 100), 11) + pad("%.1f 人日" % PD_MODEL, 10)
          + pad("%.1f 人日" % pd_a, 10) + pad("x%.1f" % (pd_a / PD_MODEL), 8)
          + "%.2f 人周" % (pd_a / 5))
nch = [c[1] for c in cost]
_srt = sorted(nch)
_k = len(_srt)
MED = (_srt[_k // 2 - 1] + _srt[_k // 2]) / 2.0 if _k % 2 == 0 else float(_srt[_k // 2])
print("  %d 个缺陷的返工任务数 %d ~ %d 道（中位 %.1f），倍数 x%.1f ~ x%.1f——差别不在单价，在下发了多少道工序。"
      % (len(cost), min(nch), max(nch), MED,
         min(c[3] for c in cost), max(c[3] for c in cost)))
small = min(cost, key=lambda x: x[1])
big = max(cost, key=lambda x: x[1])
if small[4] is not None and small[4] > 0:
    print("  返工面最小 %s（%d 道）：时刻表几乎没动，代价全压在 [2] 的「真实-基线」%s 那一列；"
          % (small[0]["case"]["tag"], small[1], fg(small[4])))
else:
    print("  返工面最小 %s（%d 道，真实-基线 %s、硬违规 %d 处）：工期与时刻表都没怎么动，代价只剩执行与验收；"
          % (small[0]["case"]["tag"], small[1], fg(small[4]), small[0]["viol"]))
print("  返工面最大 %s（%d 道，占全部工序 %.0f%%）：上线后等于整个车间重新下发一次方案。"
      % (big[0]["case"]["tag"], big[1], big[1] / len(all_ops(big[0]["case"]["truth"])) * 100))
qiet = [c for c in cost if c[1] <= 2]
if qiet:
    print("  时刻表几乎没动（返工 <= 2 道）的缺陷 %d 个（%s），返工倍数 x%.1f ~ x%.1f。"
          % (len(qiet), "、".join(c[0]["case"]["tag"] for c in qiet),
             min(c[3] for c in qiet), max(c[3] for c in qiet)))
    worse = [c for c in qiet if c[0]["gap"] is not None and c[0]["gap"] > 0]
    if worse:
        print("  返工账上它们最便宜，真实 makespan 却变差了 %d 个（%s）——这笔延误没进上表。"
              % (len(worse), "、".join("%s %s" % (c[0]["case"]["tag"], fg(c[4]))
                                      for c in worse)))
    else:
        vq = [c for c in qiet if c[0]["viol"] > 0]
        print("  这 %d 个连真实 makespan 都没变差（%s；基准是 [2] 真值基线列，不是 [1] 的 %dh）："
              % (len(qiet), "、".join("%s %s" % (c[0]["case"]["tag"], fg(c[4]))
                                      for c in qiet), cmax0))
        print("  代价只在执行与验收上：%d 个有硬违规（%s），其余 %d 个全靠 [5] 的门禁规则拦。"
              % (len(vq), "、".join(c[0]["case"]["tag"] for c in vq) or "无",
                 len(qiet) - len(vq)))
else:
    print("  没有「返工 0 道」的缺陷：最小的一个也要动 %d 道工序，上线后没有免费的坏数据。"
          % min(nch))
tot_a = sum(c[2] for c in cost)
print("  %d 个缺陷一起漏到上线后 = %.1f 人日（%.1f 人周）；一起卡在建模时 = %.1f 人日，差 x%.1f。"
      % (len(RES), tot_a, tot_a / 5, len(RES) * PD_MODEL, tot_a / (len(RES) * PD_MODEL)))

# ---------------------------------------------------------------- [7] 一览
print()
print(W)
print("[7] 一览：把前六节的关键实测数压成一屏")
print(W)
gaps2 = [r for r in RES if r["gap"] is not None]
print("  算例：%d 张工单 / %d 台设备 / %d 道工序；基线 makespan %dh，超平凡下界 %+.1f%%；"
      % (len(CLEAN["jobs"]), len(CLEAN["mach"]), NOP, cmax0, (cmax0 - LB) / LB * 100))
print("  同一份方案拿真实数据验收：六类硬违规 %d 处，顺序修补 %d 次——所以基线是可用的对照。"
      % (sum(aud0.values()), rep0))
print("  注入 %d 个缺陷、一次一处：%d 个让报出的方案比真实好看（最大 %dh），"
      % (len(RES), len(opt), -min(r["hall"] for r in opt) if opt else 0))
print("  %d 个让方案变差（最大 %+dh），%d 个报出=真实（%s）。"
      % (len(pes), max((r["hall"] for r in pes), default=0), len(zer),
         "、".join(r["case"]["tag"] for r in zer) or "无"))
print("  真实 makespan 相对各自的真值基线 %+dh ~ %+dh；原样下发最多 %d 处硬违规在同一天爆出来（%s）。"
      % (min(r["gap"] for r in gaps2), max(r["gap"] for r in gaps2),
         max(r["viol"] for r in RES), loud["case"]["tag"]))
print("  违规 0 处的「静默坏数据」%d 个（%s）：只看方案能不能执行的验收会放走%s。"
      % (len(quiet), "、".join(r["case"]["tag"] for r in quiet) or "无",
         "它们" if len(quiet) > 1 else "它"))
print("  %d 条体检规则：召回 %.0f%%（%d/%d），漏掉 %s；干净数据上误报 %d 条。"
      % (len(RULES), len(caught) / len(RES) * 100, len(caught), len(RES),
         "、".join(r["case"]["tag"] for r in missed) or "无", fp0))
print("  内部一致性 %d 条单独上只抓 %d/%d，其余 %d 个必须与 ERP/MES 对账——门禁不是脚本问题，是接口问题。"
      % (len(INNER), len(ci), len(RES), len(RES) - len(ci)))
print("  交期违约报出 < 真实的 %d 个、报出Cmax 低于真实Cmax 的 %d 个——「越坏越好看」在这两列成立；"
      % (len(liar), len(opt)))
print("  瓶颈设备认错 %d/%d 个（负荷率最大差 %.1f 个百分点），这一列本次没成立。"
      % (mis, len(RES), max(g[1] for g in load_gap)))
print("  按 %.1f 人日/返工任务的假设，建模时改与上线后返工差 x%.1f ~ x%.1f；"
      % (PD_PER_TASK, min(c[3] for c in cost), max(c[3] for c in cost)))
print("  %d 个缺陷一起漏到上线后是 %.1f 人日，卡在建模时是 %.1f 人日。"
      % (len(RES), tot_a, len(RES) * PD_MODEL))
TOTAL_EV = ev0 + ev0b + sum(r["ev_model"] + r["ev_truth"] for r in RES)
print("  工作量是结构性的：爬山共 %d 次 makespan 评估（基线求解 2 次 + 每个缺陷求解 2 次 x %d 类），"
      % (TOTAL_EV, len(RES)))
print("  复现：seed=%d、每次搜索预算 %d 次评估写死（不是墙钟）；stdout 里没有任何墙钟/毫秒数字，"
      % (SEED, BUDGET))
print("  所以换机器不会改变一个字——两次运行 stdout 逐字节相同（墙钟只写 stderr）。")
sys.stderr.write("wall %.2fs (deliberately kept out of stdout)\n"
                 % (time.perf_counter() - T0))
