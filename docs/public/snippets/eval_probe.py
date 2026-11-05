# -*- coding: utf-8 -*-
"""怎么评一个排产 Agent 才不让数字撒谎：用同一套 JSP 内核实测六件事。

用法:  python eval_probe.py   （纯标准库，无第三方依赖）

  [1] 指标相关性：同一批求解器的同一份解，在 makespan / 平均完工 / 总延迟 / 机器利用率
      四把尺子下两两 Spearman 多少、换指标时冠军在多少比例的算例上换人（标题数字）
  [2] 排名一致性：makespan 排名 vs 平均完工排名的逐算例 Spearman rho 与 Kendall tau（手写），
      小规模档与大规模档分开看均值
  [3] 评估集大小的功效：两个真实差距约 1% 的配置（爬山：只相邻交换 vs 加插入移动），
      按算例数 N 做 bootstrap，打印均值差的 90% 置信区间与 P(bootstrap 均值>0)，
      量出「N 到几，约 1% 的改进才测得出来」，并打印逐算例差距的标准差供复用
  [4] 下界间隙：3x3 / 4x3 / 3x4 全枚举重算精确最优，超下界% 与「与已知最优的间隙」
      两把尺子：单格内为什么必然同序、跨格混排名在哪里打架
  [5] 影子模式对照：规则模拟的「计划员方案」（先紧着大单 + 到达顺序整单连排）对阵爬山，
      四个指标各差多少、算法的领先主要出在 makespan 还是平均完工
  [6] 回归基线：评估次数预算连跑三次是否逐格相同；墙钟预算评估次数漂多少
  [7] 一句话结论：每个数都来自上面

时间是本机 wall-clock，换机器数字会变；指标关系、置信区间、排名结论不会。
"""
import collections
import itertools
import math
import random
import statistics
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")   # Windows GBK 控制台：编不出的字符变问号，别崩

W = "=" * 74


def dw(s):
    return sum(2 if ord(c) > 0x2E80 else 1 for c in str(s))


def pad(s, n):
    s = str(s)
    return s + " " * max(0, n - dw(s))


# ---------------------------------------------------------------- 调度内核
def make_eval(jobs):
    m = max(k for j in jobs for k, _ in j) + 1
    ops_of = {k: [] for k in range(m)}
    dur = {}
    for i, j in enumerate(jobs):
        for o, (k, p) in enumerate(j):
            ops_of[k].append((i, o))
            dur[(i, o)] = p
    return m, ops_of, dur


def starts(jobs, dur, order):
    """给定每台机器的加工顺序 -> 最早开工时间（半激活调度）。有环返回 None。"""
    nxt, indeg = {}, {n: 0 for n in dur}
    for seq in order.values():
        for a, b in zip(seq, seq[1:]):
            nxt.setdefault(a, []).append(b)
            indeg[b] += 1
    for i, j in enumerate(jobs):
        for o in range(len(j) - 1):
            nxt.setdefault((i, o), []).append((i, o + 1))
            indeg[(i, o + 1)] += 1
    st = {n: 0 for n in dur}
    ready = [n for n in dur if indeg[n] == 0]
    done = 0
    while ready:
        n = ready.pop()
        done += 1
        for c in nxt.get(n, []):
            if st[c] < st[n] + dur[n]:
                st[c] = st[n] + dur[n]
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
    return None if done < len(dur) else st


def cmax(jobs, dur, order):
    st = starts(jobs, dur, order)
    return None if st is None else max(s + dur[n] for n, s in st.items())


def mean_completion(jobs, dur, order):
    st = starts(jobs, dur, order)
    return None if st is None else sum(st[n] + dur[n] for n in st) / len(st)


def metrics(jobs, dur, order):
    """同一份解的四把尺子：makespan / 平均完工 / 总延迟 / 机器利用率(%)。
       交期取 1.3 x 工件总工时（同一算例内对所有求解器相同）。"""
    st = starts(jobs, dur, order)
    if st is None:
        return None
    n, m = len(jobs), len(order)
    C = [0.0] * n
    for (i, _o), s in st.items():
        c = s + dur[(i, _o)]
        if c > C[i]:
            C[i] = c
    due = [sum(p for _, p in j) * 1.3 for j in jobs]
    tard = sum(max(0.0, C[i] - due[i]) for i in range(n))
    mk = max(C)
    busy = sum(dur[op] for op in st)
    return (mk, sum(C) / n, tard, busy / (mk * m) * 100.0)


def dispatch(jobs, dur, key, rnd=None):
    """派工规则生成机器顺序：每步在「各工件当前可派工序」里按 key 挑最小的，同分随机。"""
    rnd = rnd or random
    m = max(k for j in jobs for k, _ in j) + 1
    ptr, mfree, jfree = [0] * len(jobs), [0.0] * m, [0.0] * len(jobs)
    order = {k: [] for k in range(m)}
    total = sum(len(j) for j in jobs)
    while sum(ptr) < total:
        cand = []
        for i in range(len(jobs)):
            if ptr[i] < len(jobs[i]):
                k, p = jobs[i][ptr[i]]
                cand.append((max(jfree[i], mfree[k]), p, i, k))
        best = min(key(*c) for c in cand)
        tie = [c for c in cand if key(*c) == best]
        _, _, i, k = rnd.choice(tie)
        p = jobs[i][ptr[i]][1]
        s = max(jfree[i], mfree[k])
        jfree[i] = mfree[k] = s + p
        order[k].append((i, ptr[i]))
        ptr[i] += 1
    return order


class Eval:
    def __init__(self, jobs, dur):
        self.jobs, self.dur, self.n = jobs, dur, 0

    def __call__(self, order):
        self.n += 1
        return cmax(self.jobs, self.dur, order)


def local_search(jobs, seed=0, budget=None, deadline=None, moves=1):
    """随机重启爬山，预算优先按「评估次数」写死（budget），只有 [6] 的墙钟档用 deadline。
       moves=1 只相邻交换；moves=2 再加插入移动。返回 (best, order, evals)。"""
    _, _, dur = make_eval(jobs)
    t_end = None if deadline is None else time.perf_counter() + deadline

    def spent(ev):
        if ev.n >= (budget or 1 << 60):
            return True
        return t_end is not None and time.perf_counter() >= t_end

    def try_move(order, k, a, b, ev):
        seq = order[k]
        if a >= len(seq) or b >= len(seq) or a == b:
            return False, None, None
        before = list(seq)
        x = seq.pop(a)
        seq.insert(b, x)
        v = ev(order)
        if v is None:
            order[k] = before
            return False, None, None
        return True, v, before

    def neighbors(order):
        for k in range(len(order)):
            seq = order[k]
            for a in range(len(seq) - 1):
                yield k, a, a + 1
                if moves >= 2:
                    for b in range(a + 2, len(seq)):
                        yield k, a, b

    ev = Eval(jobs, dur)
    order = dispatch(jobs, dur, lambda s, p, i, k: (s, p, i, k), rnd=random.Random(seed))
    cur = ev(order)
    best, best_order = cur, {k: list(v) for k, v in order.items()}
    restarts = 0
    while not spent(ev):
        restarts += 1
        cand = {k: list(v) for k, v in best_order.items()}
        rnd = random.Random(seed * 1000 + restarts)
        for _ in range(len(cand)):
            k = rnd.randrange(len(cand))
            if len(cand[k]) > 1:
                if moves >= 2 and rnd.random() < 0.5:
                    a = rnd.randrange(0, len(cand[k]) - 2)
                    try_move(cand, k, a, rnd.randrange(a + 2, len(cand[k])), ev)
                else:
                    a = rnd.randrange(0, len(cand[k]) - 1)
                    try_move(cand, k, a, rnd.randrange(0, len(cand[k])), ev)
        cur = ev(cand)
        if cur is None:
            continue
        improved = True
        while improved and not spent(ev):
            improved = False
            for k, a, b in list(neighbors(cand)):
                if spent(ev):
                    break
                ok, v, before = try_move(cand, k, a, b, ev)
                if not ok:
                    continue
                if v < cur:
                    cur, improved = v, True
                else:
                    cand[k] = before
        if cur < best:
            best, best_order = cur, {k: list(v) for k, v in cand.items()}
    return best, best_order, ev.n


def fcfs_bigfirst(jobs, dur):
    """[5] 的人工方案代理：整单连排，「先紧着大单」（走满全部机器的工件在前），
       同档按到达顺序（工件序号）。每个工件按自己路线依次等机器，机器空了就上。"""
    n = len(jobs)
    m = max(k for j in jobs for k, _ in j) + 1
    full = max(len(j) for j in jobs)
    order = {k: [] for k in range(m)}
    mfree = [0.0] * m
    seq_jobs = sorted(range(n), key=lambda i: (0 if len(jobs[i]) == full else 1, i))
    for i in seq_jobs:
        t = 0.0
        for o, (k, p) in enumerate(jobs[i]):
            s = max(t, mfree[k])
            t = mfree[k] = s + p
            order[k].append((i, o))
    return order


def trivial_lb(jobs):
    load = [0] * (max(k for j in jobs for k, _ in j) + 1)
    for j in jobs:
        for k, p in j:
            load[k] += p
    return max([sum(p for _, p in j) for j in jobs] + load)


def exact_enum(jobs):
    """全枚举机器顺序求精确最优 makespan——只用于 3x3 / 4x3 / 3x4 这个量级。"""
    _, ops_of, dur = make_eval(jobs)
    m = len(ops_of)
    best = None
    for p in itertools.product(*[itertools.permutations(ops_of[k]) for k in range(m)]):
        o = {k: list(p[k]) for k in range(m)}
        v = cmax(jobs, dur, o)
        if v is not None and (best is None or v < best):
            best = v
    return best


def gen(n, m, seed, lo=1, hi=9):
    """n 个工件、m 台机器，每个工件走完所有机器（路线随机），工时 [lo,hi]。"""
    r = random.Random(seed)
    out = []
    for _ in range(n):
        route = list(range(m))
        r.shuffle(route)
        out.append([(k, r.randint(lo, hi)) for k in route])
    return out


# ---------------------------------------------------------------- 秩统计（手写）
def ranks(v):
    idx = sorted(range(len(v)), key=lambda i: v[i])
    rk = [0.0] * len(v)
    i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and v[idx[j + 1]] == v[idx[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for t in range(i, j + 1):
            rk[idx[t]] = avg
        i = j + 1
    return rk


def spearman(a, b):
    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return 1.0 if den == 0 else num / den


def kendall(a, b):
    n = len(a)
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = (a[i] - a[j]) * (b[i] - b[j])
            if s > 0:
                conc += 1
            elif s < 0:
                disc += 1
    tot = n * (n - 1) // 2
    return 1.0 if tot == 0 else (conc - disc) / tot


# ---------------------------------------------------------------- 全局求解器与算例族
LS5 = "爬山500"
NAMES = ["SPT", "MWKR", "FCFS-i", "主动", LS5]
MET_NAMES = ["makespan", "平均完工", "总延迟", "利用率"]
BUDGET3 = 500
SIZES = [(10, 3), (15, 4), (20, 3), (25, 4), (30, 4)]


def solver_orders(jobs, dur):
    tot = {i: sum(p for _, p in j) for i, j in enumerate(jobs)}
    out = {}
    out["SPT"] = dispatch(jobs, dur, lambda s, p, i, k: (p, i, k), rnd=random.Random(7))
    out["MWKR"] = dispatch(jobs, dur, lambda s, p, i, k: (-tot[i], p, k), rnd=random.Random(7))
    out["FCFS-i"] = dispatch(jobs, dur, lambda s, p, i, k: (i, p, k), rnd=random.Random(7))
    out["主动"] = dispatch(jobs, dur, lambda s, p, i, k: (s, p, i, k), rnd=random.Random(7))
    v, o, _e = local_search(jobs, seed=5, budget=BUDGET3, moves=1)
    out[LS5] = o
    return out


FAMILY = []
for _n, _mm in SIZES:
    for _sd in range(4):
        _j = gen(_n, _mm, 1000 * _n + _sd)
        _, _, _d = make_eval(_j)
        _so = solver_orders(_j, _d)
        _rows = {}
        for _nm in NAMES:
            _mt = metrics(_j, _d, _so[_nm])
            assert _mt is not None and _so[_nm] is not None, _nm
            _rows[_nm] = _mt
        FAMILY.append({"n": _n, "m": _mm, "seed": _sd, "jobs": _j, "dur": _d, "met": _rows})

# ---------------------------------------------------------------- [1] 指标相关性
print(W)
print("[1] 指标相关性：同一份解四把尺子，两两 Spearman 与换冠军次数")
print(W)
print("  算例族：%d 个规模 x 每规模 4 个种子 = %d 个算例；求解器 %s（前 4 个是毫秒级派工规则，"
      % (len(SIZES), len(FAMILY), "/".join(NAMES)))
print("  第 5 个是 %d 次评估的爬山，只按 makespan 优化）。矩阵元素 = 逐算例对 %d 个求解器求秩后的平均 Spearman。"
      % (BUDGET3, len(NAMES)))
cor = {}
for a in range(4):
    for b in range(4):
        if a == b:
            cor[(a, b)] = 1.0
        else:
            rs = [spearman([i["met"][nm][a] for nm in NAMES], [i["met"][nm][b] for nm in NAMES])
                  for i in FAMILY]
            cor[(a, b)] = sum(rs) / len(rs)
print("  " + pad("", 12) + "".join(pad(MET_NAMES[k], 12) for k in range(4)))
for a in range(4):
    print("  " + pad(MET_NAMES[a], 12) + "".join(pad("%.2f" % cor[(a, b)], 12) for b in range(4)))
pairs = [(a, b) for a in range(4) for b in range(a + 1, 4)]
lo_pair = min(pairs, key=lambda p: cor[p])
hi_pair = max(pairs, key=lambda p: cor[p])
print("  最一致：%s vs %s，平均 rho = %.2f；最不一致：%s vs %s，rho = %.2f。"
      % (MET_NAMES[hi_pair[0]], MET_NAMES[hi_pair[1]], cor[hi_pair],
         MET_NAMES[lo_pair[0]], MET_NAMES[lo_pair[1]], cor[lo_pair]))
if cor[(0, 3)] < -0.99:
    print("  实测利用率与 makespan 的 rho = %.2f：利用率 = 总加工工时 / (makespan x m)，分子在算例内是常数——" % cor[(0, 3)])
    print("  它不是第四把尺子，是第一把尺子换了个朝向。要它说话，得先让机器可停可关（本内核不含）。")
def champion(inst, mi):
    vals = {nm: inst["met"][nm][mi] for nm in NAMES}
    if mi == 3:
        return max(NAMES, key=lambda k: (vals[k], -NAMES.index(k)))
    return min(NAMES, key=lambda k: (vals[k], NAMES.index(k)))
champ = {mi: [champion(i, 0) != champion(i, mi) for i in FAMILY] for mi in (1, 2, 3)}
print("  换冠军统计（makespan 冠军 vs 各指标冠军，同一算例同一批解）：")
print("  " + pad("换成", 12) + pad("冠军换人", 12) + pad("占比", 10) + "说明")
for mi in (1, 2, 3):
    cs = sum(champ[mi])
    note = "同一份解，换个列名换个冠军" if cs else "这一列与 makespan 从不分歧"
    print("  " + pad(MET_NAMES[mi], 12) + pad("%d/%d" % (cs, len(FAMILY)), 12)
          + pad("%.0f%%" % (cs / len(FAMILY) * 100), 10) + note)
cs12 = sum(champ[1])
if cs12 == 0:
    print("  标题数字：makespan 与平均完工的冠军在这 %d 个算例上 0 次互换——" % len(FAMILY))
    print("  「换指标就换冠军」在这一族随机算例上发生在延迟/利用率上；perf 页那个 60x8 的规则互搏是另一回事。")
else:
    print("  标题数字：换到平均完工，%d%% 的算例（%d/%d）冠军换人——验收文件里指标名一个字都不能省。"
          % (cs12 / len(FAMILY) * 100, cs12, len(FAMILY)))
cs2 = sum(champ[2])
cnt0 = collections.Counter(min(NAMES, key=lambda k: i["met"][k][0]) for i in FAMILY)
cnt1 = collections.Counter(min(NAMES, key=lambda k: i["met"][k][1]) for i in FAMILY)
fmt_cnt = lambda c: "、".join("%s x%d" % (nm, c[nm]) for nm in NAMES if c[nm])
print("  冠军分布（%d 个算例逐一取该列最优的求解器）：makespan 列 = %s；平均完工列 = %s。"
      % (len(FAMILY), fmt_cnt(cnt0), fmt_cnt(cnt1)))
if cnt0 != cnt1:
    print("  两列的冠军户口册不同：同一批解、同一族算例，只是换列名，赢家的名字分布就变了。")
else:
    print("  这一轮两列户口册相同：平均完工暂时不提供新信息，新信息在延迟列（换人 %d 次）。" % cs2)

# ---------------------------------------------------------------- [2] 排名一致性
print()
print(W)
print("[2] 排名一致性：makespan 排名 vs 平均完工排名的逐算例 rho 与 tau")
print(W)
print("  小规模档：n <= 20（%s）；大规模档：n >= 25（%s）。"
      % ("/".join("%dx%d" % s for s in SIZES[:3]), "/".join("%dx%d" % s for s in SIZES[3:])))
print("  " + pad("算例", 12) + pad("Spearman rho", 14) + pad("Kendall tau", 13) + "完全同序")
rhos = {"small": [], "large": []}
full_agree = 0
for inst in FAMILY:
    va = [inst["met"][nm][0] for nm in NAMES]
    vb = [inst["met"][nm][1] for nm in NAMES]
    rho = spearman(va, vb)
    tau = kendall(va, vb)
    rhos["small" if inst["n"] <= 20 else "large"].append(rho)
    if rho == 1.0:
        full_agree += 1
    print("  " + pad("%dx%d s%d" % (inst["n"], inst["m"], inst["seed"]), 12)
          + pad("%.3f" % rho, 14) + pad("%.3f" % tau, 13) + ("是" if rho == 1.0 else "否"))
m_small = sum(rhos["small"]) / len(rhos["small"])
m_large = sum(rhos["large"]) / len(rhos["large"])
m_all = (sum(rhos["small"]) + sum(rhos["large"])) / len(FAMILY)
print("  平均 rho：小规模档（%d 个）%.3f，大规模档（%d 个）%.3f，全体 %.3f；完全同序 %d/%d 个算例。"
      % (len(rhos["small"]), m_small, len(rhos["large"]), m_large, m_all, full_agree, len(FAMILY)))
if abs(m_small - m_large) < 0.05:
    print("  两档差距只有 %.3f：把算例做大并没有让两把尺子更打架——分歧藏在排名的后段：" % abs(m_small - m_large))
    print("  两个名次完全同序的算例只有 %d/%d 个，%d%% 的算例冠军直接换人（[1]）——头部看着一致，尾部各排各的。"
          % (full_agree, len(FAMILY), round(sum(champ[1]) / len(FAMILY) * 100)))
else:
    print("  %s规模档的 rho 明显更低（%.3f vs %.3f）：算例越大，makespan 与平均完工越各说各话。"
          % ("大" if m_large < m_small else "小", min(m_small, m_large), max(m_small, m_large)))
if full_agree == len(FAMILY):
    print("  全部 %d 个算例两个排名逐位相同：makespan 与平均完工在「同一份解」上是连体的，" % len(FAMILY))
    print("  分开报它们不增加任何信息——分开报「不同解各自的最优值」才有戏（那由 [1] 的换人率说话）。")

# ---------------------------------------------------------------- [3] 评估集大小的功效
print()
print(W)
print("[3] 评估集大小的功效：约 1% 的改进要几个算例才测得出来")
print(W)
BUD3 = 1200
DIMS = [(20, 4), (30, 5), (40, 6)]
POOL = []
for nn, mm in DIMS:
    for sd in range(20):
        j = gen(nn, mm, 70000 + 991 * sd + 7 * mm + 3 * nn)
        _, _, d = make_eval(j)
        va, oa, ea = local_search(j, seed=11, budget=BUD3, moves=2)   # 基线：交换+插入
        vb, ob, eb = local_search(j, seed=11, budget=BUD3, moves=1)   # 变体：只相邻交换
        assert va is not None and vb is not None and ea <= BUD3 + 40 and eb <= BUD3 + 40
        POOL.append((va, vb))
diffs = [(a - b) / a * 100.0 for a, b in POOL]   # A=基线 B=变体；正数 = 变体的 makespan 更小 = 改进
n_pool = len(diffs)
mean_d = statistics.mean(diffs)
sd_d = statistics.stdev(diffs) if n_pool > 1 else 0.0
n_neg = sum(1 for x in diffs if x < 0)
n_zero = sum(1 for x in diffs if x == 0)
n_pos = n_pool - n_neg - n_zero
print("  A = 基线爬山（相邻交换+插入移动），B = 变体（只相邻交换），同种子、同 %d 次评估预算，越小越好。" % BUD3)
if mean_d > 0:
    print("  实测方向先报：变体在均值上赢 %+0.3f%%——改进来自「去掉插入移动」，与直觉相反，按数据报。" % mean_d)
else:
    print("  实测方向：基线（含插入移动）均值赢 %+0.3f%%，方向与 perf 页 anytime 曲线一致。" % (-mean_d))
print("  评估集：%d 个算例（%s，各 20 个种子）。逐算例改进 (A-B)/A：均值 %+0.3f%%，标准差 %.3f%%；"
      % (n_pool, "、".join("%dx%d" % s for s in DIMS), mean_d, sd_d))
print("  变体更差 %d 个、打平 %d 个、更好 %d 个——「打平 %d」就是功效问题的来源。"
      % (n_neg, n_zero, n_pos, n_zero))
BOOT_B = 4000
boot = random.Random(20261128)
print("  bootstrap 90%% 置信区间（每档 %d 次重抽样，种子 20261128）；P(>0) = 重抽样里均值差为正的比例：" % BOOT_B)
print("  " + pad("N", 5) + pad("均值差", 11) + pad("90%CI", 20) + pad("CI含0", 8) + pad("CI宽", 9) + "P(>0)")
ci = {}
detect_n = None
for N in (1, 2, 5, 10, 20, n_pool):
    reps = sorted(statistics.mean([diffs[boot.randrange(n_pool)] for _ in range(N)])
                  for _ in range(BOOT_B))
    lo, hi = reps[int(0.05 * BOOT_B)], reps[min(int(0.95 * BOOT_B), BOOT_B - 1)]
    frac = sum(1 for x in reps if x > 0) / BOOT_B
    excl = hi < 0 or lo > 0
    if excl and detect_n is None:
        detect_n = N
    ci[N] = (lo, hi, frac, excl)
    print("  " + pad(N, 5) + pad("%+0.3f%%" % statistics.mean(reps), 11)
          + pad("[%+0.3f, %+0.3f]" % (lo, hi), 20) + pad("否" if excl else "是", 8)
          + pad("%0.3f" % (hi - lo), 9) + "%.2f" % frac)
n_list = (1, 2, 5, 10, 20, n_pool)
theor_last = 2 * 1.645 * sd_d / math.sqrt(n_pool)
print("  可复用公式：CI 宽约 2 x 1.645 x sd / sqrt(N)；sd = %.3f%% 代入 -> N=5 宽 %.3f，N=%d 宽 %.3f。"
      % (sd_d, 2 * 1.645 * sd_d / math.sqrt(5), n_pool, theor_last))
print("  公式值 %.3f 与实测 %.3f 同量级：正态近似在这份池子上够用，读者可以直接拿 sd 去开自己的 N。"
      % (theor_last, ci[n_pool][1] - ci[n_pool][0]))
if detect_n is None:
    need_n = int(math.ceil((2 * 1.645 * sd_d / mean_d) ** 2)) if mean_d > 0 else -1
    print("  检出阈值（本节标题）：真实均值 %+0.3f%%、sd %.3f%%，在 N 到 %d 的范围内 90%% CI 始终含 0——"
          % (mean_d, sd_d, n_pool))
    print("  约 1%% 的改进用本评估集测不出来；按公式要把 CI 压进均值内需 N 约 %d 个算例（N=(2x1.645xsd/均值)^2）。" % need_n)
    print("  连 N=%d 档 P(>0) 也只有 %.2f——离「有 95%% 把握说 B 更好」差得远。"
          % (n_pool, max(ci[N][2] for N in ci)))
else:
    lo5, hi5 = ci[5][0], ci[5][1]
    below = [N for N in n_list if N < detect_n]
    print("  检出阈值（本节标题）：N=%d 起 90%% CI 不含 0（均值 %+0.3f%%、sd %.3f%% 的组合就这样）。"
          % (detect_n, mean_d, sd_d))
    if detect_n > 5 and not ci[5][3]:
        print("  N=5 的 CI [%+0.3f, %+0.3f] 含 0：约 1%% 的改进在 5 个算例上测不出来——评估集的账要先算再立项。"
              % (lo5, hi5))
    elif detect_n <= 5:
        print("  预期「N=5 测不出」被数据推翻：N=5 的 CI [%+0.3f, %+0.3f] 已经不含 0——" % (lo5, hi5))
        print("  %d/%d 个打平样本把 bootstrap 分布压向一侧，检出比正态近似说的更早。" % (n_zero, n_pool))
    if below and detect_n > 5:
        print("  也别说反话：N=%s 档 CI 全部含 0，「B 更好」在这些档位只是愿望不是结论。"
              % "/".join(str(N) for N in below))
if n_neg:
    print("  另有 %d/%d 个算例上变体反而更差：单算例胜负既反映不了配置，也预测不了池子。" % (n_neg, n_pool))

# ---------------------------------------------------------------- [4] 下界间隙
print()
print(W)
print("[4] 下界间隙是骗人的：超下界% 与「与已知最优的间隙」两把尺子")
print(W)
SMALLS = [(3, 3, 11), (4, 3, 11), (3, 4, 11)]
EXPECT = {(3, 3): 25, (4, 3): 33, (3, 4): 29}
print("  只在全枚举跑得起的量级上对照（perf 页实测 4x3 枚举 13,824 组合 < 0.2s），最优重算一遍对答案。")
s4 = {}
for n, mm, sd0 in SMALLS:
    j = gen(n, mm, sd0)
    _, _, d = make_eval(j)
    opt = exact_enum(j)
    lb = trivial_lb(j)
    so = solver_orders(j, d)
    agree = "与 perf 页记录 %d 一致" % EXPECT[(n, mm)] if opt == EXPECT[(n, mm)] else "与 perf 页记录 %d 不一致" % EXPECT[(n, mm)]
    print("  算例 %dx%d：全枚举最优 %d（%s），平凡下界 %d，下界松了 %d（占最优 %.1f%%）。"
          % (n, mm, opt, agree, lb, opt - lb, (opt - lb) / opt * 100))
    rows4 = {}
    for nm in NAMES:
        v = cmax(j, d, so[nm])
        assert v is not None
        rows4[nm] = (v, (v - lb) / lb * 100.0, (v - opt) / opt * 100.0)
    s4[(n, mm)] = (lb, opt, rows4)
    rlb = sorted(NAMES, key=lambda k: rows4[k][1])
    rop = sorted(NAMES, key=lambda k: rows4[k][2])
    print("  " + pad("求解器", 10) + pad("makespan", 10) + pad("超下界", 10) + pad("与最优间隙", 12)
          + pad("下界排名", 10) + "最优排名")
    for nm in NAMES:
        v, glb, gopt = rows4[nm]
        print("  " + pad(nm, 10) + pad("%d" % v, 10) + pad("%+.1f%%" % glb, 10)
              + pad("%+.1f%%" % gopt, 12) + pad(rlb.index(nm) + 1, 10) + str(rop.index(nm) + 1))
    assert rlb == rop, "单格内两把尺子都是 makespan 的增函数，排名必须一致"
print("  单格内 %d/%d 格排名相同——这是构造性的：同一格只有一份工时，(v-lb)/lb 与 (v-opt)/opt 都是 v 的增函数。"
      % (len(SMALLS), len(SMALLS)))
print("  骗人在跨格：拿超下界% 当分数横向比，下界越松的格给的分越「好看」。把 3 格平均再排一次名：")
mean_g = {nm: (sum(s4[k][2][nm][1] for k in s4) / len(s4),
               sum(s4[k][2][nm][2] for k in s4) / len(s4)) for nm in NAMES}
o_lb = sorted(NAMES, key=lambda k: mean_g[k][0])
o_op = sorted(NAMES, key=lambda k: mean_g[k][1])
print("  " + pad("求解器", 10) + pad("平均超下界", 12) + pad("平均与最优间隙", 15) + pad("下界名次", 10) + "最优名次")
for nm in NAMES:
    print("  " + pad(nm, 10) + pad("%+.1f%%" % mean_g[nm][0], 12) + pad("%+.1f%%" % mean_g[nm][1], 15)
          + pad(o_lb.index(nm) + 1, 10) + str(o_op.index(nm) + 1))
conflict = [nm for nm in NAMES if o_lb.index(nm) != o_op.index(nm)]
if conflict:
    print("  跨格平均有 %d 个求解器的名次变了（%s）：超下界%% 把在松下界格子上吃亏的求解器抬上来了。"
          % (len(conflict), "、".join(conflict)))
else:
    print("  这一轮跨格平均 %d/%d 个求解器名次没变——但两把尺子的绝对分差最多 %.1f 个百分点，"
          % (len(NAMES), len(NAMES), max(abs(mean_g[nm][0] - mean_g[nm][1]) for nm in NAMES)))
    print("  名次不变是 3 格太相似，不是刻度可靠；把「算例 x 求解器」全放一张表再排一次：")
pair_rows = [(k, nm) for k in s4 for nm in NAMES]
pair_lb = sorted(pair_rows, key=lambda p: s4[p[0]][2][p[1]][1])
pair_op = sorted(pair_rows, key=lambda p: s4[p[0]][2][p[1]][2])
inver = sum(1 for i in range(len(pair_rows)) for j in range(i + 1, len(pair_rows))
            if s4[pair_lb[i][0]][2][pair_lb[i][1]][2] > s4[pair_lb[j][0]][2][pair_lb[j][1]][2])
tot_pairs = len(pair_rows) * (len(pair_rows) - 1) // 2
print("  %d 个（算例 x 求解器）格子混排：按超下界%% 与按最优间隙的逆序对 %d / %d（不一致率 %.1f%%）。"
      % (len(pair_rows), inver, tot_pairs, inver / tot_pairs * 100))
ex = None
for i, pj in enumerate(pair_lb):
    gj = s4[pj[0]][2][pj[1]][2]
    for pk in pair_lb[:i]:
        gk = s4[pk[0]][2][pk[1]][2]
        if gk > gj:
            ex = (pk, pj)
            break
    if ex:
        break
if ex:
    (ka, na), (kb, nb) = ex
    ga, gb = s4[ka][2][na], s4[kb][2][nb]
    print("  现场例子：超下界%% 把 %s@%dx%d（间隙 %+.1f%%，未达最优）排在 %s@%dx%d（间隙 %+.1f%%，已是该格最优）前面——"
          % (na, ka[0], ka[1], ga[2], nb, kb[0], kb[1], gb[2]))
    print("  满分的方案排在了有缺陷的方案后面，只因为后者所在格子的下界更松。分母换了，名次就该换；不换名次才是怪事。")
else:
    print("  混排 0 个逆序对：这一族格子的下界松度接近，两把尺子没分家——下界一松（见下）这事必然发生。")
loose_key = max(s4, key=lambda k: (s4[k][1] - s4[k][0]) / s4[k][1])
lk_lb, lk_opt, lk_rows = s4[loose_key]
if lk_opt == lk_lb:
    print("  三格下界全紧（松度 0%）：本节「超下界 = 间隙」同值，演示不出分母骗局，收工。")
else:
    hit = min(NAMES, key=lambda k: lk_rows[k][2])
    print("  下界最松的 %dx%d（松 %.1f%%）：%s 打到最优（间隙 %+.1f%%）却显示「超下界 %+.1f%%」——"
          % (loose_key[0], loose_key[1], (lk_opt - lk_lb) / lk_opt * 100, hit, lk_rows[hit][2], lk_rows[hit][1]))
    print("  按超下界%% 发验收分，满分方案也得替尺子的误差背债。" % ())
print("  3 格下界松度分别为 %s：报「超下界 +x%%」时，x 里最多 %.1f%% 是尺子的误差不是方案的误差。"
      % ("、".join("%dx%d %.1f%%" % (k[0], k[1], (s4[k][1] - s4[k][0]) / s4[k][1] * 100) for k in s4),
         max((s4[k][1] - s4[k][0]) / s4[k][1] * 100 for k in s4)))

# ---------------------------------------------------------------- [5] 影子模式
print()
print(W)
print("[5] 影子模式对照：规则模拟的人工方案 vs 算法方案，四个指标各差多少")
print(W)
INS5 = gen(25, 5, 31337)
_, _, dur5 = make_eval(INS5)
LB5 = trivial_lb(INS5)
o_h = fcfs_bigfirst(INS5, dur5)
v_a, o_a, e_a = local_search(INS5, seed=3, budget=2000, moves=1)
met_h, met_a = metrics(INS5, dur5, o_h), metrics(INS5, dur5, o_a)
assert met_h is not None and met_a is not None
print("  算例：25 工件 x 5 机器 = %d 工序，平凡下界 %d。算法 = 爬山 %d 次评估（预算用次数不用秒）。"
      % (sum(len(j) for j in INS5), LB5, e_a))
print("  先说清楚：人工方案是用规则模拟的（先紧着大单 + 到达顺序整单连排），不是真人排的——是代理，不当证人。")
print("  " + pad("指标", 12) + pad("影子人工", 12) + pad("算法方案", 12) + pad("算法相对优", 13) + "赢家")
rel = []
for mi, mname in enumerate(MET_NAMES):
    if mi < 3:
        better = "算法" if met_a[mi] < met_h[mi] else "人工"
        r = (met_h[mi] - met_a[mi]) / met_h[mi] * 100.0
    else:
        better = "算法" if met_a[mi] > met_h[mi] else "人工"
        r = (met_a[mi] - met_h[mi]) / met_h[mi] * 100.0
    rel.append(r)
    print("  " + pad(mname, 12) + pad("%0.1f" % met_h[mi], 12) + pad("%0.1f" % met_a[mi], 12)
          + pad("%+.1f%%" % r, 13) + better)
mk_rel, mc_rel, tl_rel = rel[0], rel[1], rel[2]
if mk_rel > 0 > mc_rel:
    print("  本节标题数字：算法赢 makespan %.1f%%，却在平均完工上输 %.1f%%，总延迟 %+.1f%%——"
          % (mk_rel, -mc_rel, tl_rel))
    print("  按 makespan 优化的 Agent，影子对照第一天就会在延迟列上输给人工：差距的大头在指标之间，不只在方案之间。")
else:
    bigger = "makespan" if abs(mk_rel) >= abs(mc_rel) else "平均完工"
    print("  本节标题数字：算法在 makespan %+.1f%%、平均完工 %+.1f%%、总延迟 %+.1f%%——领先的大头在 %s 那一列。"
          % (mk_rel, mc_rel, tl_rel, bigger))
    print("  只打印 %s 一行的影子报告，等于把另外三列的账悄悄挂给计划员。" % bigger)
win_h = sum(1 for mi in range(4)
            if (met_h[mi] < met_a[mi]) == (mi < 3) and met_h[mi] != met_a[mi])
print("  四列里人工代理赢 %d 列。影子模式如果只打印 makespan 一行，%s。"
      % (win_h, "输赢都被这一个指标定死了" if win_h else "剩下三列没人看，赢了也算没测"))

# ---------------------------------------------------------------- [6] 回归基线
print()
print(W)
print("[6] 回归基线：预算写死连跑三次，墙钟写死连跑三次")
print(W)
def sig(order):
    return tuple((k, tuple(s)) for k, s in sorted(order.items()))

g = [local_search(INS5, seed=7, budget=600, moves=2) for _ in range(3)]
same = len({x[0] for x in g}) == 1 and len({sig(x[1]) for x in g}) == 1 and len({x[2] for x in g}) == 1
print("  评估次数预算 600、seed=7 连跑三次：makespan %s，评估次数 %s，机器顺序逐格相同 = %s"
      % ([x[0] for x in g], [x[2] for x in g], "是" if same else "否"))
assert same, "固定评估次数预算必须可复现"
WALL6 = 1.00
w_runs = [local_search(INS5, seed=7, deadline=WALL6, moves=2) for _ in range(3)]
eq_eval = len({x[2] for x in w_runs}) == 1
eq_mk = len({x[0] for x in w_runs}) == 1
print("  墙钟预算 %.2fs、同 seed 连跑三次：三次 makespan 相同 = %s，三次评估次数全相同 = %s"
      % (WALL6, "是" if eq_mk else "否", "是" if eq_eval else "否"))
print("  （三次评估次数的具体值本行刻意不打印：它们逐秒变，打出来就破坏本页「两次运行逐字节相同」——")
print("  墙钟数字连进 stdout 的资格都没有，这正是本页一切预算按评估次数写死的原因。）")
diff_budget = [local_search(INS5, seed=7, budget=b, moves=2)[0] for b in (100, 300, 600, 1200)]
if len(set(diff_budget)) == 1:
    print("  写死评估次数 100/300/600/1200 四档 makespan = %s（四档全同）：这个算例 100 次评估就收敛，"
          % diff_budget)
    print("  预算档位在本算例上不改变分数——但分数什么时候改由算例决定，基线仍须连预算一起写死才不赌运气。")
else:
    print("  写死评估次数 100/300/600/1200 四档 makespan = %s：预算本身就是分数的一部分，回归基线必须连预算一起钉死。"
          % diff_budget)
reg_new, reg_old = [], []
for inst in FAMILY[:6]:
    _v, _o, _e = local_search(inst["jobs"], seed=5, budget=BUDGET3, moves=1)
    reg_new.append(cmax(inst["jobs"], inst["dur"], _o))
    reg_old.append(inst["met"][LS5][0])
print("  拿 [1] 的前 6 个算例（同 seed 同预算）隔着四节再重跑：新 %s vs 旧 %s -> 逐格相同 = %s"
      % (reg_new, reg_old, "是" if reg_new == reg_old else "否"))

# ---------------------------------------------------------------- [7] 一句话结论
print()
print(W)
print("[7] 一句话结论（每个数都在上面生成）")
print(W)
cs2pct = round(sum(champ[2]) / len(FAMILY) * 100)
cs1pct = round(sum(champ[1]) / len(FAMILY) * 100)
cs3pct = round(sum(champ[3]) / len(FAMILY) * 100)
if detect_n is None:
    eff = "约 1%% 的真改进（均值 %+0.3f%%、sd %.3f%%）在 N 到 %d 的范围内 90%% CI 始终含 0，测不出来" % (mean_d, sd_d, n_pool)
elif detect_n is not None and detect_n > 5 and not ci[5][3]:
    eff = "约 1%% 的真改进（均值 %+0.3f%%、sd %.3f%%）要到 N=%d 才被 90%% CI 检出；N=5 的 CI [%+0.3f, %+0.3f] 含 0" % (
        mean_d, sd_d, detect_n, ci[5][0], ci[5][1])
else:
    eff = "真改进均值 %+0.3f%%、sd %.3f%%，N=%d 就检出（预期「N=5 测不出」被数据推翻）" % (mean_d, sd_d, detect_n)
loose_pct = [(s4[k][1] - s4[k][0]) / s4[k][1] * 100 for k in s4]
shadow = "算法 vs 人工代理 makespan %+.1f%%、平均完工 %+.1f%%、总延迟 %+.1f%%" % (mk_rel, mc_rel, tl_rel)
print("  指标层：makespan 与平均完工换冠军 %d%%、与总延迟 %d%%、与利用率 %d%%（后者实为 rho %.2f 的反向尺子，利用率不算第四把尺子）；"
      % (cs1pct, cs2pct, cs3pct, cor[(0, 3)]))
print("  功效层：%s；下界层：混排逆序对 %d/%d，最松格下界松 %.1f%%（满分方案背着尺子的债）；"
      % (eff, inver, tot_pairs, max(loose_pct)))
print("  影子层：%s；复现层：评估次数写死三次逐格相同，墙钟写死三次评估次数全相同 = %s。"
      % (shadow, "是" if eq_eval else "否"))
print("  所以验收文件要钉死四件事：指标是哪一个（[1]）、评估集至少几个（[3]）、分母是下界还是最优（[4]）、")
print("  预算按评估次数写死（[6]）——少钉一件，数字就会撒谎。")
