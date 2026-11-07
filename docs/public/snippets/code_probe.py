#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
code_probe.py —— 「代码：从贪心到 CP-SAT 到 Agent」一页的全部实测输出

同一份 12 工件 × 4 机器的作业车间算例（seed 写死），五级台阶逐级量：
  [1] 算例与评估器：怎么用一个纯标准库内核把「一张排程表」变成「一个数」
  [2] 贪心：四条派工规则，免费能买到哪一档
  [3] CP-SAT：同一个算例交给约束规划（子进程隔离运行——崩了不许带走主服务）
  [4] 增量评估：邻域移动全量重算 vs 增量重算，各要摸多少个工序
  [5] 冻结窗口右移修复：设备停机后只动该动的部分，改动量怎么控制
  [6] Agent 护栏：方案放行前的硬约束校验，注入一个违规看它挡不挡

用法:
  python code_probe.py            # 全部六节（[3] 在子进程里跑，失败自动降级）
  python code_probe.py --cpsat    # 只跑 [3]，供主进程调起
依赖:
  [1][2][4][5][6] 纯标准库；[3] 需要 ortools >= 9.8（pip install ortools）
"""

import random
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# 算例：n 个工件 × m 台机器的作业车间（job shop）
# pt[(j, o)] = (机器号, 工时)；工件 j 的第 o 道工序先后串行、同机互斥
# ---------------------------------------------------------------------------

N_JOBS, N_MACH, SEED = 12, 4, 42


def gen(n=N_JOBS, m=N_MACH, seed=SEED):
    """每个工件把 m 台机器各走一遍（随机路径），工时 3~17。"""
    rng = random.Random(seed)
    pt = {}
    for j in range(n):
        route = list(range(m))
        rng.shuffle(route)
        for o, mach in enumerate(route):
            pt[(j, o)] = (mach, rng.randrange(3, 18))
    return pt


JOBS = list(range(N_JOBS))
MACHS = list(range(N_MACH))
PT = gen()


# ---------------------------------------------------------------------------
# 评估器：给定每台机器上的工序顺序，前向推进算最早开工时间（纯标准库）
# ---------------------------------------------------------------------------

def topo_order(seq):
    """Kahn 拓扑：节点 = 工序，边 = 工件内先后 + 同机先后。seq 有环则不可行。"""
    succs = {op: [] for op in PT}
    indeg = {op: 0 for op in PT}
    for j in JOBS:
        for o in range(N_MACH - 1):
            succs[(j, o)].append((j, o + 1))
            indeg[(j, o + 1)] += 1
    for m in MACHS:
        for a, b in zip(seq[m], seq[m][1:]):
            succs[a].append(b)
            indeg[b] += 1
    order, queue = [], [op for op in PT if indeg[op] == 0]
    while queue:
        op = queue.pop()
        order.append(op)
        for s in succs[op]:
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    return order if len(order) == len(PT) else None   # None = 有环，不可行


def forward(order, seq, pt=PT, cache=None, seeds=()):
    """沿拓扑序前向传播。cache 给定时只重访 seeds 及其后继（增量评估）。"""
    starts = {} if cache is None else dict(cache)
    dirty = set(seeds)
    succs = {}
    for j in JOBS:
        for o in range(N_MACH - 1):
            succs.setdefault((j, o), []).append((j, o + 1))
    for m in MACHS:
        for a, b in zip(seq[m], seq[m][1:]):
            succs.setdefault(a, []).append(b)
    visited = 0
    for op in order:
        if cache is not None and op not in dirty:
            continue
        visited += 1
        j, o = op
        s = starts[(j, o - 1)] + pt[(j, o - 1)][1] if o > 0 else 0
        mp = seq[pt[op][0]]
        i = mp.index(op)
        if i > 0:
            pred = mp[i - 1]
            s = max(s, starts[pred] + pt[pred][1])
        old = starts.get(op)
        starts[op] = s
        if old != starts[op]:
            dirty.update(succs.get(op, ()))
    return starts, visited


def makespan(order, seq, **kw):
    st, _ = forward(order, seq, **kw)
    return max(s + PT[op][1] for op, s in st.items()), st


def greedy(rule):
    """非延迟派工：机器空闲时，在「前道工序已完」的候选里按 rule 挑一个。"""
    job_ready = {(j, 0): 0 for j in JOBS}          # (j,o) -> 最早可开工时刻
    mach_free = {m: 0 for m in MACHS}
    seq = {m: [] for m in MACHS}
    starts = {}
    nxt = {j: 0 for j in JOBS}
    remaining = N_JOBS * N_MACH
    while remaining:
        cand = [(j, nxt[j]) for j in JOBS if nxt[j] < N_MACH]
        best = min(
            cand,
            key=lambda op: (
                max(mach_free[PT[op][0]], job_ready[op]),
                rule(op),
            ),
        )
        j, o = best
        mach = PT[best][0]
        s = max(mach_free[mach], job_ready[best])
        starts[best] = s
        seq[mach].append(best)
        mach_free[mach] = s + PT[best][1]
        if o + 1 < N_MACH:
            job_ready[(j, o + 1)] = mach_free[mach]
        nxt[j] += 1
        remaining -= 1
    return seq, starts


def rule_key(name):
    if name == "FIFO":                              # 先来先干：按工件号
        return lambda op: (op[0], op[1])
    if name == "SPT":                               # 短工时优先
        return lambda op: PT[op][1]
    if name == "LPT":                               # 长工时优先
        return lambda op: -PT[op][1]
    if name == "MWKR":                              # 剩余工作量最多优先
        return lambda op: -sum(PT[(op[0], o)][1] for o in range(op[1], N_MACH))
    raise ValueError(name)


def rule_name(name):
    return {
        "FIFO": "先来先干 (FIFO)",
        "SPT": "短工时优先 (SPT)",
        "LPT": "长工时优先 (LPT)",
        "MWKR": "剩余量最多优先 (MWKR)",
    }[name]


# ---------------------------------------------------------------------------
# [1] 算例与评估器
# ---------------------------------------------------------------------------

def sec1():
    total = sum(d for _, d in PT.values())
    print("[1] 算例与评估器")
    print(f"  算例：{N_JOBS} 工件 x {N_MACH} 机器，seed={SEED}，工序 {len(PT)} 个，总工时 {total}")
    print(f"  工时分布：min {min(d for _, d in PT.values())} / "
          f"avg {total / len(PT):.1f} / max {max(d for _, d in PT.values())}")
    print(f"  理论下界（粗）：max(总工时/机器数 {total // N_MACH}, 单工件链 "
          f"{max(sum(PT[(j, o)][1] for o in range(N_MACH)) for j in JOBS)})")
    # 评估器自检：随机机器顺序多半有环 —— topo 返回 None 就是「不可行」的判据
    rng = random.Random(SEED)
    seq = {m: [] for m in MACHS}
    all_ops = list(PT)
    rng.shuffle(all_ops)
    for op in all_ops:
        seq[PT[op][0]].append(op)
    o1 = topo_order(seq)
    print(f"  评估器自检 ①：随机机器顺序 → topo {'有环，判不可行（环检测即可行性判据）' if o1 is None else '可行'}")
    seq, _ = greedy(rule_key("FIFO"))                # 换一条确定可行的序列做一致性检查
    o2 = topo_order(seq)
    ms1, st1 = makespan(o2, seq)
    ms2, st2 = makespan(topo_order(seq), seq)
    print(f"  评估器自检 ②：可行序列（FIFO 贪心）makespan={ms1}，重算一次={ms2}，"
          f"{'逐格一致' if st1 == st2 else '不一致(BUG)'}")
    print(f"  评估器复杂度：一次全量评估走访 {len(PT)} 个工序，O(工序数)")


# ---------------------------------------------------------------------------
# [2] 贪心派工规则
# ---------------------------------------------------------------------------

def sec2():
    print()
    print("[2] 贪心：四条派工规则，零求解器成本")
    rows = []
    for name in ("FIFO", "SPT", "LPT", "MWKR"):
        t0 = time.perf_counter()
        seq, starts = greedy(rule_key(name))
        ms = max(s + PT[op][1] for op, s in starts.items())
        dt = (time.perf_counter() - t0) * 1000
        rows.append((rule_name(name), ms, dt))
    base = min(r[1] for r in rows)
    for name, ms, dt in rows:
        print(f"  {name:<22} makespan={ms:>3}   求解耗时 {dt:5.2f} ms   vs 最好贪心 +{ms - base}")
    lb = max(sum(d for _, d in PT.values()) // N_MACH,
             max(sum(PT[(j, o)][1] for o in range(N_MACH)) for j in JOBS))
    print(f"  粗下界 {lb}：最好贪心离它还有 {base - lb}。这一段差距就是 [3] 节求解器要挣的钱。")


# ---------------------------------------------------------------------------
# [3] CP-SAT（独立入口：--cpsat 时只跑这一节）
# ---------------------------------------------------------------------------

def best_greedy_ms():
    return min(max(s + PT[op][1] for op, s in greedy(rule_key(n))[1].items())
               for n in ("FIFO", "SPT", "LPT", "MWKR"))


def sec3():
    from ortools.sat.python import cp_model

    horizon = sum(d for _, d in PT.values())
    model = cp_model.CpModel()
    start, end, interval = {}, {}, {}
    for op, (m, d) in PT.items():
        start[op] = model.new_int_var(0, horizon, f"s{op[0]}_{op[1]}")
        end[op] = model.new_int_var(0, horizon, f"e{op[0]}_{op[1]}")
        interval[op] = model.new_interval_var(start[op], d, end[op], f"i{op[0]}_{op[1]}")
    for j in JOBS:                                   # 工件内先后
        for o in range(N_MACH - 1):
            model.add(start[(j, o + 1)] >= end[(j, o)])
    for m in MACHS:                                  # 同机互斥：一组 NoOverlap 搞定
        ops = [op for op in PT if PT[op][0] == m]
        model.add_no_overlap([interval[op] for op in ops])
    mk = model.new_int_var(0, horizon, "makespan")
    for j in JOBS:
        model.add(mk >= end[(j, N_MACH - 1)])
    model.minimize(mk)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    solver.parameters.num_search_workers = 8
    t0 = time.perf_counter()
    status = solver.solve(model)
    wall = time.perf_counter() - t0
    print("[3] CP-SAT：同一个算例，交给约束规划")
    print(f"  模型规模：{len(PT)} 个 interval，{N_MACH} 组 NoOverlap，{N_JOBS * (N_MACH - 1)} 条工艺先后")
    print(f"  状态：{solver.status_name(status)}  墙钟 {wall:.3f} s  分支 {solver.num_branches}")
    ms = int(solver.value(mk))
    lb = max(sum(d for _, d in PT.values()) // N_MACH,
             max(sum(PT[(j, o)][1] for o in range(N_MACH)) for j in JOBS))
    print(f"  makespan = {ms}   求解器下界 = {int(solver.best_objective_bound)}"
          f"   粗下界（[1] 的账）= {lb}")
    print(f"  对比 [2] 最好贪心 {best_greedy_ms()}：改进 "
          f"{(best_greedy_ms() - ms) / best_greedy_ms() * 100:.1f}%")
    seq = {m: [] for m in MACHS}
    plan = {}
    for op in PT:
        s = solver.value(start[op])
        plan[op] = s
        seq[PT[op][0]].append(op)
    for m in MACHS:
        seq[m].sort(key=lambda op: plan[op])
    chk, _ = makespan(topo_order(seq), seq)
    print(f"  自检：CP-SAT 解喂回标准库评估器重算 makespan = {chk}"
          f"（{'一致，评估器与求解器口径对齐' if chk == ms else '不一致，有 BUG'}）")


def run_cpsat_isolated():
    """把 CP-SAT 放进子进程：求解器原生崩溃时，主进程和服务都必须活着。"""
    print()
    print("[3] CP-SAT（子进程隔离运行：崩了不许带走主服务）")
    try:
        r = subprocess.run(
            [sys.executable, "-X", "utf8", __file__, "--cpsat"],
            capture_output=True, text=True, encoding="utf-8",
            timeout=180, errors="replace",
        )
    except subprocess.TimeoutExpired:
        print("  子进程超时（>180s）：按预算砍掉，退回贪心档方案，服务继续")
        return
    if r.stdout:
        print(r.stdout.rstrip())
    if r.returncode != 0:
        tail = (r.stderr or "").strip().splitlines()
        print(f"  子进程退出码 {r.returncode}（非零）——CP-SAT 原生库没跑完，本机不产出 [3] 的数字")
        for line in tail[-2:]:
            print(f"    stderr 尾行: {line}")
        print("  主进程毫发无损。这就是「求解器降级链」的第一课：解不动就退回贪心档，别让排产跟着挂。")
    else:
        print("  （子进程正常退出）")


# ---------------------------------------------------------------------------
# [4] 增量评估
# ---------------------------------------------------------------------------

def sec4():
    print()
    print("[4] 增量评估：邻域移动后，全量重算 vs 增量重算")
    rng = random.Random(7)
    seq, _ = greedy(rule_key("SPT"))                 # 以可行基线序列为缓存起点
    order0 = topo_order(seq)
    ms0, st0 = makespan(order0, seq)
    # 造 200 个「同机相邻交换」移动，统计增量评估要走访多少工序
    full_visits, delta_visits, full_ms, delta_ms, skipped = [], [], 0.0, 0.0, 0
    for _ in range(200):
        m = rng.randrange(N_MACH)
        if len(seq[m]) < 3:
            continue
        i = rng.randrange(len(seq[m]) - 1)
        seq2 = {k: list(v) for k, v in seq.items()}
        seq2[m][i], seq2[m][i + 1] = seq2[m][i + 1], seq2[m][i]
        order2 = topo_order(seq2)
        if order2 is None:                           # 交换制造了环：这是非法移动，直接跳过
            skipped += 1
            continue
        t0 = time.perf_counter()
        ms_full, _ = makespan(order2, seq2)
        full_ms += time.perf_counter() - t0
        t0 = time.perf_counter()
        _, v = forward(order2, seq2, cache=st0, seeds=(seq2[m][i], seq2[m][i + 1]))
        delta_ms += time.perf_counter() - t0
        full_visits.append(len(PT))
        delta_visits.append(v)
    nf, nd = len(full_visits), len(delta_visits)
    print(f"  算例 {len(PT)} 工序；同机相邻交换 x{nd}（另 {skipped} 个交换产生环，判非法移动跳过）")
    print(f"  基线 makespan={ms0}；全量重算每次走访 {full_visits[0]} 工序，均耗时 {full_ms / nf * 1e6:.1f} us")
    print(f"  增量重算：平均走访 {sum(delta_visits) / nd:.1f} 工序"
          f"（{sum(delta_visits) / nd / full_visits[0] * 100:.1f}% of 全量），"
          f"均耗时 {delta_ms / nd * 1e6:.1f} us")
    print(f"  结论：评估吞吐 ≈ x{full_ms / delta_ms:.1f}；邻域大小不变时，"
          f"增量评估直接把「一次点击能搜多少」放大同倍数")


# ---------------------------------------------------------------------------
# [5] 冻结窗口右移修复（设备停机）
# ---------------------------------------------------------------------------

def repair_rightshift(plan, seq, m_broken, b0, b1, freeze_until):
    """第一档修复：只右移。与停机窗口相交的工序推到 b1 之后，后继顺延；冻结工序钉死。"""
    frozen = {op: s for op, s in plan.items() if s < freeze_until}
    order = topo_order(seq)
    starts, hops = {}, []
    for op in order:
        j, o = op
        m, d = PT[op]
        if op in frozen:
            starts[op] = frozen[op]
            continue
        s = 0
        if o > 0:
            s = max(s, starts[(j, o - 1)] + PT[(j, o - 1)][1])
        mp = seq[m]
        i = mp.index(op)
        if i > 0:
            pred = mp[i - 1]
            s = max(s, starts[pred] + PT[pred][1])
        if m == m_broken and s < b1 and s + d > b0:  # 撞上停机窗口：整体推到窗口后
            s = b1
            hops.append(op)
        starts[op] = s
    return starts, frozen, hops


def sec5():
    print()
    print("[5] 冻结窗口右移修复：设备停机后，只动该动的部分")
    seq0, plan0 = greedy(rule_key("SPT"))
    ms0 = max(s + PT[op][1] for op, s in plan0.items())
    freeze_until = int(ms0 * 0.3)                    # 前 30% 时间已开工：冻结
    frozen = {op: s for op, s in plan0.items() if s < freeze_until}
    m_broken = max(MACHS, key=lambda m: sum(1 for op in PT if PT[op][0] == m and op not in frozen))
    b0, b1 = int(ms0 * 0.25), int(ms0 * 0.25) + 18   # 该机停机 18 分钟
    print(f"  基线：SPT 贪心 makespan={ms0}；冻结开工时刻 <{freeze_until} 的 {len(frozen)} 个工序")
    print(f"  扰动：M{m_broken} 在第 {b0}~{b1} 分钟停机（窗口 {b1 - b0} 分钟）")
    plan1, frozen, hops = repair_rightshift(plan0, seq0, m_broken, b0, b1, freeze_until)
    ms1 = max(s + PT[op][1] for op, s in plan1.items())
    moved = [op for op in PT if plan1[op] != plan0[op]]
    shifts = [plan1[op] - plan0[op] for op in moved]
    print(f"  右移修复：makespan {ms0} -> {ms1}（+{ms1 - ms0}）；被移动 {len(moved)} 个工序"
          f"（占可动部分 {len(moved) / max(1, len(PT) - len(frozen)) * 100:.0f}%），其中直接跳窗 {len(hops)} 个")
    if moved:
        print(f"  位移：min +{min(shifts)} / max +{max(shifts)} / avg +{sum(shifts) / len(shifts):.1f} 分钟，"
              f"全部右移 {all(x > 0 for x in shifts)}")
    ok, bad = check(plan1)
    print(f"  护栏复检：{'PASS，0 条违规' if ok else f'FAIL，{len(bad)} 条违规'}")
    for b in bad[:3]:
        print(f"    - {b}")
    if not ok:
        print("  冲突读法：被冻结的工序挡住了右移路径 —— 右移档救不了，升级到 CP-SAT 局部重排或人工裁决")
    print("  口径提醒：冻结按「开工时刻 < freeze_until」判定，不是按机器序列前缀（后者是 perf 页第六节的反例）")


# ---------------------------------------------------------------------------
# [6] Agent 护栏：硬约束校验
# ---------------------------------------------------------------------------

def check(plan):
    """返回 (通过?, 违规列表)。每条违规带「哪条约束、哪两个工序」的归因。"""
    bad = []
    for m in MACHS:
        ops = sorted([op for op in PT if PT[op][0] == m], key=lambda op: plan[op])
        for a, b in zip(ops, ops[1:]):
            if plan[a] + PT[a][1] > plan[b]:
                bad.append(f"同机互斥 M{m}: {a}（{plan[a]}+{PT[a][1]}）压住 {b}（开工 {plan[b]}）")
    for j in JOBS:
        for o in range(N_MACH - 1):
            if plan[(j, o)] + PT[(j, o)][1] > plan[(j, o + 1)]:
                bad.append(f"工艺先后 J{j}: 工序 {o} 未完，工序 {o + 1} 已开工")
    return (not bad), bad


def sec6():
    print()
    print("[6] Agent 护栏：方案放行前，硬约束逐条校验（LLM 永远不碰这一步）")
    seq6, plan = greedy(rule_key("MWKR"))
    ok, bad = check(plan)
    print(f"  贪心解：{'PASS，0 条违规，放行进暂存区（还不许写基线）' if ok else 'FAIL'}")
    bad_plan = dict(plan)
    victim = (0, 1)
    bad_plan[victim] = plan[victim] - 5              # 注入违规：提前开工 5 分钟
    ok2, bad2 = check(bad_plan)
    print(f"  注入违规（把 {victim} 提前 5 分钟）：{'PASS' if ok2 else f'FAIL，{len(bad2)} 条违规，阻断 + 归因'}")
    for b in bad2[:3]:
        print(f"    - {b}")
    print("  归因粒度是硬要求：「违规」两个字计划员没法干活，「谁压住了谁、差几分钟」可以")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--cpsat" in sys.argv:
        sec3()
    else:
        sec1()
        sec2()
        run_cpsat_isolated()
        sec4()
        sec5()
        sec6()
