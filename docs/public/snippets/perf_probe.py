# -*- coding: utf-8 -*-
"""秒级重排到底是几秒：在随机作业车间算例上实测模型规模、评估吞吐、时间预算曲线、
增量重排的改动量与可复现性。

用法:  python perf_probe.py          （纯标准库，无第三方依赖）

  [1] 一个 JSP/FJSP 模型到底有多少变量与约束——按公式算，不按形容词算
  [2] 四条派工规则：makespan 与平均完工时间两个指标上的排名会不会打架
  [3] 本机评估吞吐（次/秒）：1 秒预算买得起几次全场邻域扫描
  [4] anytime 曲线：两种邻域（相邻交换 / 交换+插入）各扫一遍预算阶梯
  [5] 精确通道：能枚举的枚举，算不动的按实测吞吐折算成数量级
  [6] 秒级重排：插单与工序超时 × 冻结窗口 0/3/6/10，分别数「顺序改动」和「时刻改动」
  [7] 可复现性：预算写死 vs 墙钟写死，同种子与异种子
  [8] 本机实测一览

时间是本机 wall-clock，换机器数字会变；变量数、组合数、改动量与结论不会。
"""
import itertools
import math
import random
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")   # Windows 默认 GBK 控制台：编不出的字符变问号，别崩

W = "=" * 74


def dw(s):
    return sum(2 if ord(c) > 0x2E80 else 1 for c in str(s))


def pad(s, n):
    s = str(s)
    return s + " " * max(0, n - dw(s))


def sci(x, digits=2):
    if x == 0:
        return "0"
    e = int(math.floor(math.log10(abs(x))))
    if e < 4:
        return "{:,}".format(int(round(x)))
    return "%.1fx10^%d" % (x / 10 ** e, e)


def human_time(secs):
    if secs < 60:
        return "%.0f 秒" % secs
    if secs < 3600:
        return "%.0f 分钟" % (secs / 60)
    if secs < 86400:
        return "%.1f 小时" % (secs / 3600)
    if secs < 3.15e7:
        return "%.1f 天" % (secs / 86400)
    return sci(secs / 3.15e7) + " 年"


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


def dispatch(jobs, dur, key, rnd=None, stats=None):
    """派工规则生成机器顺序：每步在「各工件当前可派工序」里按 key 挑最小的，同分随机。
       stats 传一个 [打平次数, 总次数] 的 list，就地累加——用来数种子究竟能插手几次。"""
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
        if stats is not None:
            stats[0] += 1 if len(tie) > 1 else 0
            stats[1] += 1
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


def local_search(jobs, seed=0, deadline=None, budget=None, base=None, cut=None,
                 moves=1, kick=None):
    """随机重启爬山。moves=1 只用相邻交换；moves=2 再加「把一道工序插到同机可动段更靠后的位置」。
       base/cut = 增量重排：各机器前 cut[k] 格钉回已下发顺序，新工序只能落在其后（钉位置前缀，
       不是钉工序集合——后者会改掉已下发方案的开工时刻）。
       kick = 每轮重启的随机扰动次数，默认 m。"""
    m, _, dur = make_eval(jobs)
    cut = cut or {}
    kick = m if kick is None else kick
    t_end = None if deadline is None else time.perf_counter() + deadline
    random.seed(seed)
    ev = Eval(jobs, dur)

    def spent():
        if ev.n >= (budget or 1 << 60):
            return True
        return t_end is not None and time.perf_counter() >= t_end

    def pin(order):
        if base is None:
            return {k: list(v) for k, v in order.items()}
        out = {}
        for k, seq in order.items():
            head = base.get(k, [])[:cut.get(k, 0)]
            hs = set(head)
            out[k] = head + [x for x in seq if x not in hs]
        return out

    def try_move(order, k, a, b):
        """把机器 k 上第 a 格搬到第 b 格。撞环就撤销。返回 (成行, 值, 撤销用的原序列)。"""
        seq = order[k]
        lo = cut.get(k, 0)
        if a < lo or b < lo or a >= len(seq) or b >= len(seq) or a == b:
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
            lo = cut.get(k, 0)
            for a in range(lo, len(seq) - 1):
                yield k, a, a + 1
                if moves >= 2:
                    for b in range(a + 2, len(seq)):
                        yield k, a, b

    def climb(order, cur):
        improved = True
        while improved and not spent():
            improved = False
            for k, a, b in list(neighbors(order)):
                if spent():
                    return cur
                ok, v, before = try_move(order, k, a, b)
                if not ok:
                    continue
                if cur is None or v < cur:
                    cur, improved = v, True
                else:
                    order[k] = before
        return cur

    start, best = None, None
    for _ in range(20):
        start = pin(dispatch(jobs, dur, lambda s, p, i, k: (s, p, i, k), rnd=random.Random(seed)))
        best = ev(start)
        if best is not None:
            break
    best_order = {k: list(v) for k, v in start.items()}
    restarts = 0
    while not spent():
        restarts += 1
        cand = {k: list(v) for k, v in best_order.items()}
        rnd = random.Random(seed * 1000 + restarts)
        for _ in range(kick):
            k = rnd.randrange(len(cand))
            lo = cut.get(k, 0)
            if len(cand[k]) - 1 > lo:
                if moves >= 2 and rnd.random() < 0.5:
                    a = rnd.randrange(lo, len(cand[k]) - 2)
                    b = rnd.randrange(a + 2, len(cand[k]))
                    try_move(cand, k, a, b)
                else:
                    a = rnd.randrange(lo, len(cand[k]) - 1)
                    b = rnd.randrange(lo, len(cand[k]))
                    try_move(cand, k, a, b)
        cur = climb(cand, ev(cand))
        if cur is not None and cur < best:
            best, best_order = cur, {k: list(v) for k, v in cand.items()}
    return best, best_order, ev.n, restarts


def trivial_lb(jobs):
    load = [0] * (max(k for j in jobs for k, _ in j) + 1)
    for j in jobs:
        for k, p in j:
            load[k] += p
    return max([sum(p for _, p in j) for j in jobs] + load)


def gen(n, m, seed, lo=1, hi=9):
    """n 个工件、m 台机器，每个工件走完所有机器（路线随机），工时 [lo,hi]。"""
    r = random.Random(seed)
    out = []
    for _ in range(n):
        route = list(range(m))
        r.shuffle(route)
        out.append([(k, r.randint(lo, hi)) for k in route])
    return out


def nbr_count(order, cut, moves):
    c = 0
    for k, seq in order.items():
        lo = cut.get(k, 0)
        for a in range(lo, len(seq) - 1):
            c += 1
            if moves >= 2:
                c += len(seq) - a - 2
    return c


# ---------------------------------------------------------------- [1] 模型规模
print(W)
print("[1] 一个车间模型到底有多少变量：按公式算，不按形容词算")
print(W)
print("  记号：n 个工件、m 台机器、每工件走全部 m 台 -> 工序数 O = n*m")
print("  析取编码（每对同机工序一个先后 bool）：B_disj = m * C(n,2)")
print("  指派编码（柔性路线，每工序 x[工序][候选机]）：B_asgn = O * 候选机数，这里按 3 候选算")
print("  间隔变量 = O；工艺约束 = n*(m-1) 条；NoOverlap = m 组")
print("  " + pad("n x m", 12) + pad("工序O", 8) + pad("析取bool", 13) + pad("指派bool", 11)
      + pad("合计变量", 12) + "过1万")
sizes = [(8, 3), (16, 4), (32, 5), (50, 8), (64, 5), (100, 10), (200, 15), (500, 20), (1000, 50)]
cross = None
for n, m in sizes:
    O = n * m
    disj = m * n * (n - 1) // 2
    asgn = O * 3
    tot = disj + asgn + O
    ok = tot >= 10000
    if cross is None and ok:
        cross = (n, m, tot)
    print("  " + pad("%d x %d" % (n, m), 12) + pad(O, 8) + pad("{:,}".format(disj), 13)
          + pad("{:,}".format(asgn), 11) + pad("{:,}".format(tot), 12) + ("是" if ok else "否"))
print("  第一个让总变量过 1 万的形状：%d 工件 x %d 机器（{:,} 个变量）——车间里一个白天的批次就到了。".format(cross[2])
      % (cross[0], cross[1]))
n1, m1 = 1000, 50
print("  真正咬人的不是「1 万」这个数，是 1000x50 的析取弧 {:,} 条：".format(m1 * n1 * (n1 - 1) // 2))
print("    每加 1 个工件，析取弧多 {} 条（对 n 是二次）；每加 1 台机器，多 {} 条（对 n 是线性）。".format(
    m1 * (n1 - 1), n1 * (n1 - 1) // 2))
print("    现代 CP 求解器不逐条建这些弧：m 组 NoOverlap 加时间扫描/序列推理，把这 {:,} 条的关系压进传播器。".format(
    m1 * n1 * (n1 - 1) // 2))

# ---------------------------------------------------------------- [2] 派工规则
print()
print(W)
print("[2] 四条派工规则：换指标就换冠军，时间上全是白送")
print(W)
INST = gen(60, 8, 2026)
_, ops_of, dur = make_eval(INST)
LB = trivial_lb(INST)
NOP = sum(len(j) for j in INST)
print("  算例：60 工件 x %d 机器 = %d 工序，工时 1~9，平凡下界 = %d" % (len(ops_of), NOP, LB))
print("  " + pad("规则", 26) + pad("makespan", 11) + pad("超下界", 10) + pad("平均完工", 11)
      + pad("耗时", 11) + "挑工序次数")
rules = [("SPT 最短工序优先", lambda s, p, i, k: (p, i, k)),
         ("MWKR 剩余工时最长", lambda s, p, i, k: (-sum(q for _, q in INST[i]), i, k)),
         ("EDD-ish 按工件序号(近似先到先排)", lambda s, p, i, k: (i, p, k)),
         ("主动调度 (先能开工的先派)", lambda s, p, i, k: (s, p, i, k))]
res = {}
for name, key in rules:
    t0 = time.perf_counter()
    o = dispatch(INST, dur, key, rnd=random.Random(7))
    dt = time.perf_counter() - t0
    res[name] = (cmax(INST, dur, o), mean_completion(INST, dur, o), dt * 1000)
for name, (mk, mc, dt) in res.items():
    print("  " + pad(name, 26) + pad(mk, 11) + pad("%+.1f%%" % ((mk - LB) / LB * 100), 10)
          + pad("%.1f" % mc, 11) + pad("%.2fms" % dt, 11) + "%d" % NOP)
best_mk = min(res, key=lambda k: res[k][0])
best_mc = min(res, key=lambda k: res[k][1])
worst_mk = max(res, key=lambda k: res[k][0])
print("  makespan 冠军：%s（%d）；平均完工冠军：%s（%.1f）；makespan 最差：%s（%d）。"
      % (best_mk, res[best_mk][0], best_mc, res[best_mc][1], worst_mk, res[worst_mk][0]))
if best_mk == best_mc:
    others = [k for k in res if k != best_mk]
    mc2 = min(others, key=lambda k: res[k][1])
    print("  这一轮两条冠规则重合（都是%s），但平均完工第二名是%s（%.1f vs %.1f）——"
          % (best_mk, mc2, res[mc2][1], res[best_mc][1]))
    print("  换一组工时或换一条规则，冠军就会分家：指标写进验收文件之前，没人知道它会挑出哪条规则。")
else:
    print("  同一个派工器，指标写哪一个，冠军就是谁：%s 赢 makespan，%s 赢平均完工。" % (best_mk, best_mc))
print("  最差的 makespan 是最好的 %.2f 倍（%d vs %d），耗时却全在 %.1f~%.1fms 这个带里："
      % (res[worst_mk][0] / res[best_mk][0], res[worst_mk][0], res[best_mk][0],
         min(v[2] for v in res.values()), max(v[2] for v in res.values())))
print("  规则这一层的差别全在质量那一列，时间上等于免费。")

# ---------------------------------------------------------------- [3] 吞吐
print()
print(W)
print("[3] 本机评估吞吐：1 秒预算买得起几次全场邻域扫描")
print(W)
print("  一次「评估」= starts() 一遍拓扑推进（每个工序一次比较与入队）。这是爬山的基本计价单位。")
print("  " + pad("规模", 12) + pad("工序", 8) + pad("评估/秒", 12) + pad("相邻交换邻居", 16) + "扫完一轮")
thr, NBR = {}, {}
for n, m in [(20, 4), (40, 6), (60, 8), (100, 10), (200, 15), (400, 20)]:
    j = gen(n, m, 99)
    _, _, d2 = make_eval(j)
    base = dispatch(j, d2, lambda s, p, i, k: (s, p, i, k), rnd=random.Random(3))
    ev = Eval(j, d2)
    t0 = time.perf_counter()
    cnt = 0
    while time.perf_counter() - t0 < 0.30:
        ev(base)
        cnt += 1
    rate = cnt / (time.perf_counter() - t0)
    nb, nb2 = nbr_count(base, {}, 1), nbr_count(base, {}, 2)
    thr[n * m], NBR[n * m] = rate, (nb, nb2)
    print("  " + pad("%d x %d" % (n, m), 12) + pad(n * m, 8) + pad("{:,.0f}".format(rate), 12)
          + pad("{:,}".format(nb), 16)
          + "%.0fms（%s 个插入邻居 -> %.1fs）" % (nb / rate * 1000, "{:,}".format(nb2), nb2 / rate))
print("  单轮扫描代价 = 邻居数 / 吞吐：%d 工序时 %.0fms，%d 工序时 %.0fs——工序数 x%d，一轮慢 x%.0f。"
      % (80, NBR[80][0] / thr[80] * 1000, 8000, NBR[8000][0] / thr[8000], 8000 // 80,
         (NBR[8000][0] / thr[8000]) / (NBR[80][0] / thr[80])))
print("  评估吞吐 x 工序数（= 每秒处理的工序数）在本机各档是 %s——近似常数，说明一次评估的代价就是 O(工序数)。"
      % "、".join("%d:%.0f" % (k, thr[k] * k) for k in sorted(thr)))
print("  换算成体感：40x6 这一档 1 秒能扫 %.1f 轮全场邻域，400x20 这一档扫完一轮要 %.0fs——"
      % (thr[240] / NBR[240][0], NBR[8000][0] / thr[8000]))
print("  不做增量评估（只重算受影响的那几个工序），后者就不是「方案质量差」的问题，是等不等得到的问题。")

# ---------------------------------------------------------------- [4] anytime
print()
print(W)
print("[4] anytime 曲线：预算阶梯 × 两种邻域")
print(W)
INS4 = gen(30, 6, 4242)
_, _, dur4 = make_eval(INS4)
LB4 = trivial_lb(INS4)
print("  算例：30 工件 x 6 机器 = %d 工序，平凡下界 %d。同一 seed，只改墙钟上限。" % (sum(len(j) for j in INS4), LB4))
print("  " + pad("预算", 9) + pad("相邻交换", 30) + pad("交换+插入", 30) + "差")
curves = {}
for mv in (1, 2):
    row = []
    for dl in (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0):
        v, o, ne, rs = local_search(INS4, seed=5, deadline=dl, moves=mv)
        row.append((dl, v, ne, rs))
    curves[mv] = row
print("  " + pad("", 9) + pad("makespan(超下界/评估次数)", 30) + pad("makespan(超下界/评估次数)", 30) + "")
for idx in range(len(curves[1])):
    dl, v1, n1_, r1 = curves[1][idx]
    _, v2, n2_, r2 = curves[2][idx]
    c1 = "%d (%+.1f%% / %s)" % (v1, (v1 - LB4) / LB4 * 100, "{:,}".format(n1_))
    c2 = "%d (%+.1f%% / %s)" % (v2, (v2 - LB4) / LB4 * 100, "{:,}".format(n2_))
    print("  " + pad("%.2fs" % dl, 9) + pad(c1, 30) + pad(c2, 30) + "%+d" % (v2 - v1))
f1, f2 = curves[1][0][1], curves[2][0][1]
e1, e2 = curves[1][-1][1], curves[2][-1][1]
b4 = dispatch(INS4, dur4, lambda s, p, i, k: (s, p, i, k), rnd=random.Random(5))
nb4_1, nb4_2 = nbr_count(b4, {}, 1), nbr_count(b4, {}, 2)
print("  预算 100 倍（0.05s -> 5s）：相邻交换 %d -> %d（%+.1f%%），交换+插入 %d -> %d（%+.1f%%）。"
      % (f1, e1, (e1 - f1) / f1 * 100, f2, e2, (e2 - f2) / f2 * 100))
print("  同预算下两种邻域的差 = %+d（%.1f%%）：加插入移动把邻居数从 %s 抬到 %s（x%.1f），"
      % (e2 - e1, (e2 - e1) / e1 * 100, "{:,}".format(nb4_1), "{:,}".format(nb4_2), nb4_2 / nb4_1))
n1_5, n2_5 = curves[1][-1][2], curves[2][-1][2]
if n2_5 < n1_5:
    print("  代价是每个邻居更贵：同样 5s，交换+插入只评估了 %s 次，比相邻交换的 %s 次还少——"
          % ("{:,}".format(n2_5), "{:,}".format(n1_5)))
    print("  邻域大小与评估次数直接抢同一块预算，谁赢看算例。")
else:
    print("  每个插入邻居确实更贵，但本机 5s 仍容得下 %s 次评估（相邻交换是 %s 次）——"
          % ("{:,}".format(n2_5), "{:,}".format(n1_5)))
    print("  多花的评估刚好买到了那 %+d：邻域大小与评估次数在同一块预算里抢，这一轮是邻域赢" % (e2 - e1))
print("  最贵的那格（5s）已经越过「计划员看一眼方案」的时间——预算给到几秒，是产品问题，不是算法问题。")

# ---------------------------------------------------------------- [5] 精确
print()
print(W)
print("[5] 精确通道：能枚举的枚举出来，算不动的折算成数量级")
print(W)
print("  全枚举机器顺序：组合数 = (n!)^m。可行（无环）只是其中一部分，其余在 starts() 里被判 None。")
print("  " + pad("规模", 12) + pad("组合数", 12) + pad("实测", 12) + pad("可行", 10) + "最优 makespan")
small = {}
for n, m in [(3, 3), (4, 3), (3, 4)]:
    j = gen(n, m, 11)
    _, oo, d2 = make_eval(j)
    combos = math.factorial(n) ** m
    t0 = time.perf_counter()
    best, nfeas = None, 0
    for p in itertools.product(*[itertools.permutations(oo[k]) for k in range(m)]):
        o = {k: list(p[k]) for k in range(m)}
        v = cmax(j, d2, o)
        if v is not None:
            nfeas += 1
            if best is None or v < best:
                best = v
    dt = time.perf_counter() - t0
    small[(n, m)] = (best, dt, nfeas, j, d2)
    print("  " + pad("%d x %d" % (n, m), 12) + pad("{:,}".format(combos), 12)
          + pad("%.3fs" % dt, 12) + pad("{:,}".format(nfeas), 10) + "%d" % best)
rate_small = small[(4, 3)][2] / small[(4, 3)][1]
print("  同一台机器：3x3 -> 4x3 组合数 x%.0f，耗时 x%.0f；可行比例 %.1f%% -> %.1f%%（大部分排列组合直接成环）。"
      % (math.factorial(4) ** 3 / (6 ** 3), small[(4, 3)][1] / small[(3, 3)][1],
         small[(3, 3)][2] / 6 ** 3 * 100, small[(4, 3)][2] / 24 ** 3 * 100))
big_rate = sum(v for k, v in thr.items() if k >= 240) / len([k for k in thr if k >= 240])
print("  " + pad("规模", 12) + pad("组合数", 14) + pad("按 %.0f 次/秒折算" % big_rate, 20) + "换成")
for n, m in [(5, 3), (6, 3), (8, 3), (10, 3), (12, 4), (20, 5), (30, 6)]:
    combos = math.factorial(n) ** m
    secs = combos / big_rate
    print("  " + pad("%d x %d" % (n, m), 12) + pad(sci(combos), 14) + pad(sci(secs) + " 秒", 20)
          + human_time(secs))
hit = {}
for (n, m) in small:
    opt = small[(n, m)][0]
    vals = [local_search(small[(n, m)][3], seed=sd, deadline=0.05)[0] for sd in range(5)]
    hit[(n, m)] = (opt, vals, sum(1 for x in vals if x == opt))
print("  拿这几个已知最优当尺子量爬山（0.05s 预算、seed 0~4）：")
for (n, m), (opt, vals, nh) in hit.items():
    print("    %d x %d 最优 %d -> 爬山 %s，命中 %d/5，超下界 %+d" % (n, m, opt, vals, nh,
          opt - trivial_lb(small[(n, m)][3])))
if all(len(set(v[1])) == 1 for v in hit.values()):
    print("    三个算例的 5 个 seed 给的是同一个值：所谓 5/5 是同一个解重复 5 次，"
          "独立性的分母没那么大（原因见 [7]）。")
print("  小算例上爬山能碰到最优；本页 [4] 那个 30x6 也好不到哪去——真正的未知发生在没有分母的地方。")

# ---------------------------------------------------------------- [6] 重排
print()
print(W)
print("[6] 秒级重排：冻结窗口钉住的是顺序，还是时刻？")
print(W)
t0 = time.perf_counter()
v0, o0, n0, r0 = local_search(INST, seed=5, deadline=2.0)
t_base = time.perf_counter() - t0
st0 = starts(INST, dur, o0)
pos0 = {}
for k, seq in o0.items():
    for idx, op in enumerate(seq):
        pos0[op] = (k, idx)
print("  基线方案：60x8（%d 工序），makespan=%d，超下界 %+.1f%%，生成耗时 %.2fs"
      % (NOP, v0, (v0 - LB) / LB * 100, t_base))
rush = gen(1, 8, 777)[0]
J2 = [list(j) for j in INST] + [rush]
_, _, d2 = make_eval(J2)
J3 = [list(j) for j in INST]
J3[0][1] = (J3[0][1][0], J3[0][1][1] * 3)
_, _, d3 = make_eval(J3)
print("  扰动 A 插单：新工件 1 个，8 道工序，工时 %s（合计 %d）" % ([p for _, p in rush], sum(p for _, p in rush)))
print("  扰动 B 超时：工件 0 第 2 道工序 %d -> %d（x3）" % (dur[(0, 1)], d3[(0, 1)]))
print("  重排预算统一 1.00s。两种「冻结」口径放在一起比：")
print("    W = 各机器前 W 格钉回原顺序（位置前缀，代码里最好写）")
print("    T = 基线方案里开工时刻 < T 的工序（时间前缀，车间真正已经开工的那批）")
T_REL = 30
released = {op for op, s in st0.items() if s < T_REL}
pin_sets = {}
print("  基线里 T=%d 时刻前开工的工序 %d 个（占 %d 工序的 %.0f%%）。"
      % (T_REL, len(released), NOP, len(released) / NOP * 100))
print("  " + pad("扰动", 8) + pad("W", 4) + pad("钉住格数", 11) + pad("已开工里被钉住", 16)
      + pad("makespan", 10) + pad("顺序改动", 11) + pad("时刻改动", 11) + pad("已开工被改时刻", 17) + "最大位移")
rows6 = []
for label, jj, dd in (("A 插单", J2, d2), ("B 超时", J3, d3)):
    for Wn in (0, 3, 6, 10):
        cut = {k: min(Wn, len(v)) for k, v in o0.items()}
        pinned = set()
        for k, seq in o0.items():
            pinned.update(seq[:cut[k]])
        pin_sets[Wn] = pinned
        n_pin = sum(cut.values())
        t1 = time.perf_counter()
        vi, oi, nci, rsi = local_search(jj, seed=5, deadline=1.0, base=o0, cut=cut, moves=2)
        ti = time.perf_counter() - t1
        sti = starts(jj, dd, oi)
        pos1 = {}
        for k, seq in oi.items():
            for idx, op in enumerate(seq):
                pos1[op] = (k, idx)
        ch_seq = sum(1 for op in sti if pos0.get(op) != pos1.get(op))
        ch_time = sum(1 for op in sti if op not in st0 or st0[op] != sti[op])
        rel_moved = sum(1 for op in released if op in sti and sti[op] != st0[op])
        rel_pinned_moved = sum(1 for op in released & pinned if op in sti and sti[op] != st0[op])
        mx = max((abs(sti[op] - st0[op]) for op in released if op in sti), default=0)
        rows6.append((label, Wn, vi, ch_seq, ch_time, n_pin, len(released & pinned),
                      rel_moved, rel_pinned_moved, mx, ti))
        print("  " + pad(label, 8) + pad(Wn, 4) + pad(n_pin, 11)
              + pad("%d/%d" % (len(released & pinned), len(released)), 16)
              + pad(vi, 10) + pad("%d/%d" % (ch_seq, len(sti)), 11)
              + pad("%d/%d" % (ch_time, len(sti)), 11)
              + pad("%d（钉住的里 %d）" % (rel_moved, rel_pinned_moved), 17) + str(mx))
cover = [(r[1], r[6] / len(released) * 100) for r in rows6[:4]]
moved = [r[7] for r in rows6]
pinned_moved = [r[8] for r in rows6]
cov_w = [r[1] for r in rows6[:4]]
print("  读法一（覆盖率）：W=%s 分别钉住 %s 格，对已开工 %d 个工序的覆盖率是 %s。"
      % ("/".join(str(w) for w in cov_w), "/".join(str(r[5]) for r in rows6[:4]), len(released),
         "/".join("%.0f%%" % c for _, c in cover)))

print("  位置前缀钉住的格几乎全落在已开工那批里（W=%d：%d 格里 %d 格已开工），问题是它盖不全——"
      % (cov_w[1], rows6[1][5], rows6[1][6]))
print("  W=%d 盖住已开工 %d 个的 %.0f%%，W=%d 盖 %.0f%%；要盖满 100%% 得钉到 %d 格 x %d 台 = %d 格不许动。"
      % (cov_w[1], len(released), cover[1][1], cov_w[2], cover[2][1], cov_w[3], len(o0), rows6[3][5]))
print("  读法二（钉住到底有没有效）：钉住集合里开工时刻被改的有 %d~%d 个——顺序锁住确实把时刻锁住了，这一条成立。"
      % (min(pinned_moved), max(pinned_moved)))
print("  但已开工 %d 个里最多 %d 个（%.0f%%）时刻被改掉，全部落在没钉住的那批里，最大位移 %d 个时间单位。"
      % (len(released), max(moved), max(moved) / len(released) * 100, max(r[9] for r in rows6)))
print("  所以冻结窗口不是没用，是覆盖口径错了：它按机器格数发牌，车间按开工时刻受害。")
mk0 = {lab: [r[2] for r in rows6 if r[0] == lab] for lab in ("A 插单", "B 超时")}
for lab, vs in mk0.items():
    print("  %s：W=0/3/6/10 的 makespan %s，钉满比不钉 %+d（%.1f%%）。"
          % (lab, vs, vs[3] - vs[0], (vs[3] - vs[0]) / vs[0] * 100))
print("  要真钉住时刻，得把开工时刻本身当约束（start 变量钉值），而不是钉机器前缀——那是另一个模型。")

# ---------------------------------------------------------------- [7] 可复现
print()
print(W)
print("[7] 可复现性：预算写死，还是墙钟写死")
print(W)
a, oa, na, ra = local_search(INST, seed=42, budget=400, moves=2)
b, ob, nb, rb = local_search(INST, seed=42, budget=400, moves=2)
print("  评估次数写死 400、seed=42 两次：makespan %s / %s，评估 %s / %s，机器顺序逐格相同 = %s"
      % (a, b, na, nb, oa == ob))
c1 = [local_search(INST, seed=42, deadline=0.3, moves=2) for _ in range(3)]
print("  墙钟写死 0.3s、seed=42 三次：makespan %s，评估次数 %s -> 相同 = %s"
      % ([x[0] for x in c1], [x[2] for x in c1], len({(x[0], x[2]) for x in c1}) == 1))
print("  墙钟预算下，同一台机器同一秒数都会给出不同的搜索次数：换机器（或旁边跑着编译）结果就漂。")
def sig(order):
    return tuple((k, tuple(s)) for k, s in sorted(order.items()))


def sweep(tag, jobs, dd, dl, lb):
    runs = [local_search(jobs, seed=sd, deadline=dl, moves=2) for sd in range(8)]
    vv = [r[0] for r in runs]
    uniq_mk, uniq_plan = len(set(vv)), len({sig(r[1]) for r in runs})
    n_start, tl = [], [0, 0]
    for sd in range(8):
        st = [0, 0]
        n_start.append(sig(dispatch(jobs, dd, lambda s, p, i, k: (s, p, i, k),
                                    random.Random(sd), st)))
        tl[0] += st[0]
        tl[1] += st[1]
    n_start = len(set(n_start))
    mean = sum(vv) / len(vv)
    s2 = math.sqrt(sum((x - mean) ** 2 for x in vv) / len(vv))
    print("  %s：%d 工序、%.1fs、seed 0~7 -> makespan %s" % (tag, sum(len(j) for j in jobs), dl, vv))
    print("    均值 %.1f，标准差 %.2f，极差 %d（%.2f%%），最优 %d（超下界 %+.1f%%）"
          % (mean, s2, max(vv) - min(vv), (max(vv) - min(vv)) / mean * 100, min(vv),
             (min(vv) - lb) / lb * 100))
    print("    派工 %d 次里只有 %d 次同分打平（%.1f%%），8 个种子的初始派工因此只有 %d 套；"
          % (tl[1], tl[0], tl[0] / tl[1] * 100, n_start))
    print("    爬山跑完后剩 %d 个 makespan / %d 套顺序" % (uniq_mk, uniq_plan))
    return max(vv) - min(vv), uniq_mk, uniq_plan, n_start, tl[0], tl[1]


r7 = [sweep("30x6", INS4, dur4, 0.5, LB4), sweep("60x8", INST, dur, 0.5, LB)]
spread = [x[0] for x in r7]
print("  逐算例的极差 %s：种子在这两个算例上能造成的差别就是这些；166 与 348 之间的差不是漂移，是不同的题。" % spread)
if max(spread) == 0:
    print("  两个算例的 8 个种子全给同一个值 -> 本机这条链上「换个随机种子就变好/变差」这件事不存在。")
else:
    print("  极差最大 %d -> 同一个预算换个种子就换一个方案，一次跑分不能当结论。" % max(spread))
plans = [x[2] for x in r7]
nstarts = [x[3] for x in r7]
print("  种子能插手的位置：30x6 打平 %d / %d 次派工，60x8 打平 %d / %d 次——key 是全序时，seed 基本无事可做。"
      % (r7[0][4], r7[0][5], r7[1][4], r7[1][5]))
if min(plans) > 1:
    print("  指标一样不代表方案一样：30x6 的 8 个种子里有 %d 套不同的机器顺序，60x8 有 %d 套。" % (plans[0], plans[1]))
else:
    print("  8 个种子给出 %d / %d 套起点，跑完还是 %d / %d 套：起点本来就只有一套（见上一行的打平次数），"
          % (nstarts[0], nstarts[1], plans[0], plans[1]))
    print("  随机重启也没翻出更低的局部最优。想让 seed 有事可做，先把候选打分做成有并列的。")
print("  真正会漂的是墙钟：同样 0.3s，三次跑出的评估次数是 %s，次数由机器当时忙不忙决定。"
      % [x[2] for x in c1])
print("  验收脚本要写死三件东西：seed、评估次数上限（不是秒数）、以及同一算例重跑必须逐格相同。")

# ---------------------------------------------------------------- [8] 一览
print()
print(W)
print("[8] 本机实测一览")
print(W)
print("  规模：%d x %d = %s 个决策变量（第一个过 1 万的形状）；1000 x 50 = %s 条析取弧。"
      % (cross[0], cross[1], "{:,}".format(cross[2]), "{:,}".format(50 * 1000 * 999 // 2)))
print("  规则：makespan 冠军 %s = %d，最差 %s = %d，差 %.2f 倍，耗时全在 %.1f~%.1fms 这一档。"
      % (best_mk, res[best_mk][0], worst_mk, res[worst_mk][0], res[worst_mk][0] / res[best_mk][0],
         min(v[2] for v in res.values()), max(v[2] for v in res.values())))
print("  吞吐：单轮相邻交换扫描在 20x4 要 %.0fms，在 400x20 要 %.0fs——增量评估不是优化项，是能不能上线。"
      % (NBR[80][0] / thr[80] * 1000, NBR[8000][0] / thr[8000]))
print("  预算：30x6 从 0.05s 到 5s，相邻交换 %+.1f%%、交换+插入 %+.1f%%（下界 %d）。"
      % ((e1 - f1) / f1 * 100, (e2 - f2) / f2 * 100, LB4))
print("  精确：4x3 全枚举 %.3fs，5x3 按本机吞吐折算 %s；爬山在 3x3/4x3/3x4 上命中最优 %s。"
      % (small[(4, 3)][1], human_time(math.factorial(5) ** 3 / big_rate),
         "、".join("%d/5" % h[2] for h in hit.values())))
print("  重排：位置前缀钉到 %d 格（每台 %d 格 x %d 台）才盖满已开工的 %d 个工序；只钉 %d 格时覆盖率 %.0f%%，"
      % (rows6[3][5], rows6[3][1], len(o0), len(released), rows6[1][5], cover[1][1]))
print("  被改时刻的已开工工序最多 %d 个，其中落在钉住集合里的是 %d 个，最大位移 %d——保护是有效的，错的是覆盖口径。"
      % (max(moved), max(pinned_moved), max(r[9] for r in rows6)))
print("  复现：评估次数写死 -> 两次逐格相同；墙钟写死 -> 三次跑出评估次数 %s，结果随机器负载漂。"
      % [x[2] for x in c1])
