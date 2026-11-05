# -*- coding: utf-8 -*-
"""20 个真实翻车现场：每条都在本机实测，破坏力是量出来的，不是讲出来的。

用法:  python pitfalls_probe.py      （纯标准库，无第三方依赖）

  [1] 数据类 P01~P05：单位、重复工单、缺工序、机器别名、时间戳倒挂
  [2] 模型类 P06~P10：路线写宽、换型漏建模、班次日历、无限产能、多目标压成一个
  [3] 集成/状态类 P11~P15：冻结窗口口径、幂等重放、超时当无解、版本漂移、回写失败
  [4] 交付类 P16~P20：没有分母的提升、演示吞吐、甘特图视觉欺骗、只报平均、反馈闭环
  [5] 一览：P01~P20 的实测影响与检测难度

所有随机量都写死种子；时间是本机 wall-clock，换机器只有时间那一栏会变。
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


# ---------------------------------------------------------------- 小工具
def pct(x, d=1):
    return "%+.*f%%" % (d, x * 100)


def loads(jobs):
    m, ops_of, dur = make_eval(jobs)
    L = [sum(dur[op] for op in ops_of.get(k, [])) for k in range(m)]
    return m, ops_of, dur, L


def median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def deps(jobs, dur, order):
    """返回 (前驱表, 后继表, 拓扑序)；拓扑序为空表示有环。"""
    pre, suc, indeg = {n: [] for n in dur}, {n: [] for n in dur}, {n: 0 for n in dur}
    for seq in order.values():
        for a, b in zip(seq, seq[1:]):
            suc[a].append(b)
            pre[b].append(a)
            indeg[b] += 1
    for i, j in enumerate(jobs):
        for o in range(len(j) - 1):
            suc[(i, o)].append((i, o + 1))
            pre[(i, o + 1)].append((i, o))
            indeg[(i, o + 1)] += 1
    ready = [n for n in dur if indeg[n] == 0]
    out = []
    while ready:
        n = ready.pop()
        out.append(n)
        for c in suc[n]:
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
    return pre, suc, out


def starts_setup(jobs, dur, order, setup):
    """半激活 + 换型时间：同机相邻两道工序来自不同工件时，后一道多等 setup。"""
    nxt = {n: [] for n in dur}
    indeg = {n: 0 for n in dur}
    for k, seq in order.items():
        for a, b in zip(seq, seq[1:]):
            nxt[a].append((b, dur[a] + (setup if a[0] != b[0] else 0)))
            indeg[b] += 1
    for i, j in enumerate(jobs):
        for o in range(len(j) - 1):
            nxt[(i, o)].append(((i, o + 1), dur[(i, o)]))
            indeg[(i, o + 1)] += 1
    st = {n: 0 for n in dur}
    ready = [n for n in dur if indeg[n] == 0]
    done = 0
    while ready:
        n = ready.pop()
        done += 1
        for c, lag in nxt[n]:
            if st[c] < st[n] + lag:
                st[c] = st[n] + lag
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
    return None if done < len(dur) else st


def cmax_setup(jobs, dur, order, setup):
    st = starts_setup(jobs, dur, order, setup)
    return None if st is None else max(s + dur[n] for n, s in st.items())


def n_switch(order):
    return sum(1 for seq in order.values() for a, b in zip(seq, seq[1:]) if a[0] != b[0])


def job_done(jobs, dur, st):
    out = []
    for i, j in enumerate(jobs):
        out.append(max(st[(i, o)] + dur[(i, o)] for o in range(len(j))))
    return out


def sig(order):
    return tuple((k, tuple(v)) for k, v in sorted(order.items()))


def grouped_order(jobs, dur):
    """把每台机器上的工序按工单号排在一起（换型最少的朴素画法），用于 P07。"""
    m, ops_of, _ = make_eval(jobs)
    return {k: sorted(ops_of[k]) for k in range(m)}


def climb_mean(jobs, dur, order0, budget, seed):
    """与 local_search 同构的随机爬山，但目标换成「平均完工」——P10 要两个目标各爬一次。"""
    rnd = random.Random(seed)
    cur_order = {k: list(v) for k, v in order0.items()}
    ev = Eval(jobs, dur)

    def val(order):
        ev.n += 1
        return mean_completion(jobs, dur, order)

    best, best_order = val(cur_order), {k: list(v) for k, v in cur_order.items()}
    movable = [k for k, v in best_order.items() if len(v) >= 2]
    while ev.n < budget and movable:
        order = {k: list(v) for k, v in best_order.items()}
        k = rnd.choice(movable)
        seq = order[k]
        a = rnd.randrange(len(seq) - 1)
        x = seq.pop(a)
        seq.insert(a + 1, x)
        v = val(order)
        if v is not None and v < best:
            best, best_order = v, order
    return best, best_order, ev.n


T_START = time.perf_counter()
ROWS = []
NOBITE = []
KIND = {1: "是", 0: "否", 2: "部分"}


def row(pid, name, impact, flag, extra=""):
    ROWS.append((pid, name, impact, KIND[flag]))
    if extra:
        NOBITE.append((pid, extra))


# ---------------------------------------------------------------- [1] 数据类
print()
print(W)
print("[1] 数据类翻车：ERP 里一个字段错位，在本机量出来是多少")
print(W)
MAIN = gen(24, 6, 2026)
M0, OPS0, DUR0 = make_eval(MAIN)
NOP = sum(len(j) for j in MAIN)
LB0 = trivial_lb(MAIN)
K_SPT = lambda s, p, i, k: (p, i, k)
K_ACT = lambda s, p, i, k: (s, p, i, k)
O_SPT = dispatch(MAIN, DUR0, K_SPT, rnd=random.Random(11))
T_SPT = cmax(MAIN, DUR0, O_SPT)
MC_SPT = mean_completion(MAIN, DUR0, O_SPT)
T_REF, O_REF, N_REF, R_REF = local_search(MAIN, seed=5, budget=600, moves=2)
MC_REF = mean_completion(MAIN, DUR0, O_REF)
print("  干净算例：%d 工件 x %d 机器 = %d 工序，工时 1~9 小时，平凡下界 %d，机器负载 %s"
      % (len(MAIN), M0, NOP, LB0, loads(MAIN)[3]))
print("  参照方案（爬山 600 次评估、seed 5）：makespan %d 小时（超下界 %s），平均完工 %.1f 小时；"
      % (T_REF, pct((T_REF - LB0) / LB0), MC_REF))
print("  对照的派工方案（SPT、seed 11）：makespan %d 小时（%s）——P01~P04 用同一条规则比，改动才可归因。"
      % (T_SPT, pct((T_SPT - LB0) / LB0)))

# ---- P01 工时报错单位
u60 = [[(k, p * 60) for k, p in j] for j in MAIN]
_, _, d60 = make_eval(u60)
o_u = dispatch(u60, d60, K_SPT, rnd=random.Random(11))
t_u, lb_u = cmax(u60, d60, o_u), trivial_lb(u60)
same_u = (o_u == O_SPT)
m60 = [list(j) if i % 4 else [(k, p * 60) for k, p in j] for i, j in enumerate(MAIN)]
_, _, dm6 = make_eval(m60)
o_m = dispatch(m60, dm6, K_SPT, rnd=random.Random(11))
t_m_real = cmax(MAIN, DUR0, o_m)
q60 = [list(j) if i % 4 else [(k, p // 60) for k, p in j] for i, j in enumerate(MAIN)]
_, _, dq = make_eval(q60)
o_q = dispatch(q60, dq, K_SPT, rnd=random.Random(11))
t_q = cmax(q60, dq, o_q)
t_q_real = cmax(MAIN, DUR0, o_q)
n_zero = sum(1 for j in q60 for _, p in j if p == 0)
print("  P01 工时报错单位")
print("    全场 x60（分钟当小时）：makespan %d -> %d（x%.2f），下界 %d -> %d（x%.2f），机器顺序逐格相同=%s"
      % (T_SPT, t_u, t_u / T_SPT, LB0, lb_u, lb_u / LB0, same_u))
if same_u:
    print("    等比缩放不改任何比较关系：这一向的错不动方案，只动承诺——交期被口头放大 %.0f 倍，没有一行数据自证异常。"
          % (t_u / T_SPT))
else:
    print("    等比缩放竟然改了方案：说明 key 里有并列，seed 介入了（见 P14）。")
chg_m = sum(1 for k in O_SPT for idx, op in enumerate(o_m[k]) if O_SPT[k][idx] != op)
t_m = cmax(m60, dm6, o_m)
print("    只有 1/4 工单 x60：账面 makespan %d（干净数据同规则方案的 %.1f 倍），放回真实工时 %d（%s）"
      % (t_m, t_m / T_SPT, t_m_real, pct((t_m_real - T_SPT) / T_SPT)))
print("    机器顺序被改掉 %d/%d 格：一个字段错位就换一批方案，而账面只看得见「变慢了」这一件事。" % (chg_m, NOP))
print("    反向 ÷60（整型除法）：%d/%d 道工序工时直接归零；账面 %d、真实 %d -> 承诺少算 %.1f%%（现场会按前面那个数接单）"
      % (n_zero, NOP, t_q, t_q_real, (1 - t_q / t_q_real) * 100))
print("    纯本地自检：工时<=0 的工序 %d 条（可检），x60 那侧 0 条异常（要单位口径与外部对照才行）" % n_zero)
row("P01", "工时报错单位", "x60 使承诺 x%.2f 而方案不变；÷60 归零 %d 道工序、账面少算 %.0f%%"
    % (t_u / T_SPT, n_zero, (1 - t_q / t_q_real) * 100), 2)

# ---- P02 重复工单
dup = [list(j) for j in MAIN] + [list(MAIN[3])]
_, odup, ddup, ldup = loads(dup)
o_d = dispatch(dup, ddup, K_SPT, rnd=random.Random(11))
t_d = cmax(dup, ddup, o_d)
lb_d = trivial_lb(dup)
busy0 = sum(dur for dur in DUR0.values())
busy1 = sum(dur for dur in ddup.values())


def op_sig(js):
    c = {}
    for i, j in enumerate(js):
        for o, (k, p) in enumerate(j):
            c[(k, o, p)] = c.get((k, o, p), 0) + 1
    return sum(v - 1 for v in c.values() if v > 1)


def job_sig(js):
    c = {}
    for j in js:
        key = tuple(j)
        c[key] = c.get(key, 0) + 1
    return sum(v - 1 for v in c.values() if v > 1)


clean_op_dup, dup_op_dup = op_sig(MAIN), op_sig(dup)
clean_job_dup, dup_job_dup = job_sig(MAIN), job_sig(dup)
print("  P02 重复工单（同一张工单入库两次）")
print("    总负载 %d -> %d 小时（%s），工序数 %d -> %d，makespan %d -> %d（%s），下界 %d -> %d（%s）"
      % (busy0, busy1, pct((busy1 - busy0) / busy0), NOP, sum(len(j) for j in dup),
         T_SPT, t_d, pct((t_d - T_SPT) / T_SPT), LB0, lb_d, pct((lb_d - LB0) / LB0)))
print("    粗口径「同机器+同工序位+同工时」：干净算例本身就报 %d 条，注入后 %d 条（增量 %d）——单靠它对不上号"
      % (clean_op_dup, dup_op_dup, dup_op_dup - clean_op_dup))
print("    细口径整单工序序列签名：干净算例重复 %d 条，注入后重复 %d 条 -> 纯本地数据可精确自检"
      % (clean_job_dup, dup_job_dup))
row("P02", "重复工单", "负载 %s、makespan %s；整单签名重复 %d 条可自检（粗口径误报基数 %d）"
    % (pct((busy1 - busy0) / busy0), pct((t_d - T_SPT) / T_SPT), dup_job_dup - clean_job_dup, clean_op_dup), 1)

# ---- P03 工艺路线缺工序
miss = []
n_miss_op = 0
for i, j in enumerate(MAIN):
    if i % 3 == 0:
        miss.append(list(j[:-1]))
        n_miss_op += 1
    else:
        miss.append(list(j))
_, _, d_ms, _ = loads(miss)
o_ms = dispatch(miss, d_ms, K_SPT, rnd=random.Random(11))
t_ms = cmax(miss, d_ms, o_ms)
lb_ms = trivial_lb(miss)
feas_ms = starts(miss, d_ms, o_ms) is not None
n_lost = sum(p for i, j in enumerate(MAIN) if i % 3 == 0 for _, p in [j[-1]])
print("  P03 工艺路线缺工序（每 3 张工单丢最后一道）")
print("    丢掉 %d 道工序、共 %d 小时工作量；可行 = %s（starts 没返回 None），makespan %d -> %d（%s）"
      % (n_miss_op, n_lost, feas_ms, T_SPT, t_ms, pct((t_ms - T_SPT) / T_SPT)))
print("    下界同步塌 %s（%d -> %d）：缺工序让指标变好，所以任何求解器都不会报警——丢的是那 %d 小时实际加工。"
      % (pct((lb_ms - LB0) / LB0), LB0, lb_ms, n_lost))
row("P03", "工艺路线缺工序", "指标变好 %s（丢 %d 道工序 / %d 小时），零报警"
    % (pct((t_ms - T_SPT) / T_SPT), n_miss_op, n_lost), 0)

# ---- P04 机器编号断裂 / 别名
_, _, _, L_true = loads(MAIN)
K_ALI = max(range(M0), key=lambda k: L_true[k])
gh = []
for i, j in enumerate(MAIN):
    gh.append([(99 if (k == K_ALI and i % 2 == 1) else k, p) for k, p in j])
m_gh, og_gh, dg_gh, L_gh = loads(gh)
n_empty = sum(1 for x in L_gh if x == 0)
L_real6 = [L_gh[k] for k in range(M0)]
rank_true = sorted(L_true, reverse=True).index(L_true[K_ALI]) + 1
rank_ghost = sorted(L_real6, reverse=True).index(L_gh[K_ALI]) + 1
o_gh = dispatch(gh, dg_gh, K_SPT, rnd=random.Random(11))
t_gh = cmax(gh, dg_gh, o_gh)
print("  P04 机器编号断裂 / 别名（最忙设备 %d 的一半工序标到幽灵设备 99）" % K_ALI)
print("    主数据 %d 台设备，make_eval 实际算出 m = %d（静默按最大编号+1 建机器数组），空机器 %d 台"
      % (M0, m_gh, n_empty))
print("    设备 %d 负载 %d -> %d 小时（%s），幽灵 99 白拿 %d 小时（= 全场工时的 %.1f%%）；忙机排名 第%d -> 第%d"
      % (K_ALI, L_true[K_ALI], L_gh[K_ALI], pct((L_gh[K_ALI] - L_true[K_ALI]) / L_true[K_ALI]),
         L_gh[99], L_gh[99] / busy0 * 100, rank_true, rank_ghost))
print("    同一批工序排出来的 makespan %d -> %d（%s）：过载告警看的是账面负载，瓶颈被别名拆走就再也不响"
      % (T_SPT, t_gh, pct((t_gh - T_SPT) / T_SPT)))
row("P04", "机器编号别名", "m 从 %d 静默涨到 %d、空机 %d 台；瓶颈负载 -%d%%、忙机排名 第%d->第%d"
    % (M0, m_gh, n_empty, int(round((L_true[K_ALI] - L_gh[K_ALI]) / L_true[K_ALI] * 100)), rank_true, rank_ghost), 1)

# ---- P05 时间戳倒挂
st_b = starts(MAIN, DUR0, O_SPT)
pre_b, suc_b, topo_b = deps(MAIN, DUR0, O_SPT)
rec = dict(st_b)
r5 = random.Random(5)
picks = r5.sample(sorted(rec, key=lambda n: (n[0], n[1])), 6)
for op in picks:
    rec[op] = max(0, rec[op] - r5.randint(1, 6))
viol = []
for i, j in enumerate(MAIN):
    for o in range(1, len(j)):
        if rec[(i, o)] < rec[(i, o - 1)] + DUR0[(i, o - 1)]:
            viol.append((i, o))
fix_all = dict(rec)
chg_all = set()
for n in topo_b:
    need = max((fix_all[p] + DUR0[p] for p in pre_b[n]), default=0)
    if need > fix_all[n]:
        fix_all[n] = need
        chg_all.add(n)


def closure_one(seed_op):
    R, stack = set(), [seed_op]
    while stack:
        n = stack.pop()
        if n in R:
            continue
        R.add(n)
        stack.extend(suc_b[n])
    fix = dict(rec)
    ch = set()
    for n in topo_b:
        if n not in R:
            continue
        need = max((fix[p] if p in R else rec[p]) + DUR0[p] for p in pre_b[n]) if pre_b[n] else 0
        if need > fix[n]:
            fix[n] = need
            ch.add(n)
    return len(ch)


clos = [closure_one(op) for op in viol]
print("  P05 时间戳倒挂（开工时刻早于上道工序完工：随机把 %d 个上报时刻往前提 1~6 小时）" % len(picks))
print("    纯自检数出的倒挂违反：%d 处（在 %d 道工序、%d 条工艺链边上）" % (len(viol), NOP, NOP - len(MAIN)))
print("    修一处倒挂的连带改动闭包：min/median/max = %d/%d/%d 个工序的时刻（闭包 = 沿工艺+机器弧往后推）"
      % (min(clos), median(clos), max(clos)))
print("    整张表一次修完要改 %d 个时刻（占工序 %.1f%%），最大推移 %d 小时"
      % (len(chg_all), len(chg_all) / NOP * 100,
         max((fix_all[n] - rec[n]) for n in chg_all) if chg_all else 0))
row("P05", "时间戳倒挂", "违反 %d 处；修 1 处最多连带改 %d 个时刻，全修要改 %d 个" % (len(viol), max(clos), len(chg_all)), 1)

# ---------------------------------------------------------------- [2] 模型类
print()
print(W)
print("[2] 模型类翻车：模型写得宽一点/省一点，值多少工时")
print(W)

# ---- P06 工艺路线写宽
SP = [j[:3] for j in MAIN]
_, osp, dsp, lsp = loads(SP)
m_sp = max(k for j in SP for k, _ in j) + 1
o_sp = dispatch(SP, dsp, K_SPT, rnd=random.Random(11))
t_sp = cmax(SP, dsp, o_sp)
lb_sp = trivial_lb(SP)
print("  P06 把「每个工件走全部机器」当成真的（路线写宽）")
print("    真实稀疏路线（每工件 3 台）：%d 工序、m=%d、负载 %s，下界 %d，makespan %d"
      % (sum(len(j) for j in SP), m_sp, lsp, lb_sp, t_sp))
print("    写宽成全走 6 台：%d 工序（x%.2f），下界 %d -> %d（%s），makespan %d -> %d（%s）"
      % (NOP, NOP / sum(len(j) for j in SP), lb_sp, LB0, pct((LB0 - lb_sp) / lb_sp),
         t_sp, T_SPT, pct((T_SPT - t_sp) / t_sp)))
print("    同一条工单，模型写宽就多要求 %d 次机器占用、多 %d 小时工时——车间会照这张宽路线备料备机时。"
      % (NOP - sum(len(j) for j in SP), sum(dur for dur in DUR0.values()) - sum(dur for dur in dsp.values())))
row("P06", "工艺路线写宽", "下界被抬 %s、makespan %s；凭空多 %d 道工序"
    % (pct((LB0 - lb_sp) / lb_sp), pct((T_SPT - t_sp) / t_sp), NOP - sum(len(j) for j in SP)), 0)

# ---- P07 准备/换型时间漏建模
SET = 2
t_blind_claim = cmax_setup(MAIN, DUR0, O_REF, 0)
t_blind_true = cmax_setup(MAIN, DUR0, O_REF, SET)
grp = grouped_order(MAIN, DUR0)
grp_feas = starts_setup(MAIN, DUR0, grp, SET) is not None
grp_set = cmax_setup(MAIN, DUR0, grp, SET)
cands7 = [O_REF, O_SPT, grp] + [dispatch(MAIN, DUR0, K_ACT, rnd=random.Random(sd)) for sd in (1, 2, 3)] \
    + [local_search(MAIN, seed=sd, budget=300, moves=2)[1] for sd in (2, 7)]
t_aware, o_aware = min(((cmax_setup(MAIN, DUR0, c, SET), c) for c in cands7), key=lambda z: z[0])
sw_set = sorted({n_switch(c) for c in cands7})
L0 = loads(MAIN)[3]
cnt0 = [len(OPS0[k]) for k in range(M0)]
lb_setup = max(max(L0[k] + max(0, cnt0[k] - 1) * SET for k in range(M0)), max(sum(p for _, p in j) for j in MAIN))
sw_blind, sw_aware = n_switch(O_REF), n_switch(o_aware)
print("  P07 准备/换型时间漏建模（setup=0 vs 每次切换 +%d 小时）" % SET)
print("    下发方案（爬山解）：账面 makespan %d，把换型加回去 %d（%s），换型 %d 次"
      % (t_blind_claim, t_blind_true, pct((t_blind_true - t_blind_claim) / t_blind_claim), sw_blind))
print("    换型次数能不能压？本机 %d 个候选（派工 / 爬山 / 按工单分组）实测切换次数只有 %s 这一种取值；"
      % (len(cands7), sw_set))
if len(sw_set) == 1:
    print("    因为每个工件在一台机器上只出现一次，切换次数恒等于 工序数 - 机器数 = %d —— 「少换型」在这个建模里是伪目标，"
          % (NOP - M0))
    print("    能挪的只是换型落在哪一格：按含换型值在候选里重挑，最优还是 %d（省 %d 小时），"
          % (t_aware, t_blind_true - t_aware))
    print("    省不回来。这条的伤害全额落在承诺上：账面 %d 小时、现场要 %d 小时。" % (t_blind_claim, t_blind_true))
    NOBITE.append(("P07", "换型次数无法优化（恒等式 %d 次 = 工序数-机器数），事后重挑省 %d 小时；"
                          "但漏建模本身仍让 makespan %+d 小时" % (NOP - M0, t_blind_true - t_aware,
                                                                 t_blind_true - t_blind_claim)))
else:
    print("    切换次数在候选间有 %d 种取值（%s，含按工单分组的 %d 次，其含换型 makespan %d）："
          % (len(sw_set), sw_set, n_switch(grp), grp_set if grp_feas else 0))
    print("    按含换型值重挑最优 %d（换型 %d 次），比漏建模方案省 %d 小时（%s）"
          % (t_aware, sw_aware, t_blind_true - t_aware, pct((t_aware - t_blind_true) / t_blind_true)))
print("    下界口径也要改：单机负载 + %d 小时/次切换后 %d -> %d（%s）"
      % (SET, LB0, lb_setup, pct((lb_setup - LB0) / LB0)))
row("P07", "换型时间漏建模", "真实 makespan %s（+%d 小时）；换型次数恒为 %d 次、重挑省 %d；下界 %s"
    % (pct((t_blind_true - t_blind_claim) / t_blind_claim), t_blind_true - t_blind_claim,
       sw_blind, t_blind_true - t_aware, pct((lb_setup - LB0) / LB0)), 1)

# ---- P08 班次日历没算
DAY = 8
T0 = T_REF
d_cont = T0 / 24.0
d_cal = math.ceil(T0 / DAY)
Lmax = max(loads(MAIN)[3])
d_machine = math.ceil(Lmax / DAY)
print("  P08 班次日历没算（把 24x7 连续时间当成工作日，每天 %d 小时）" % DAY)
print("    下发方案 makespan = %d 小时 -> 方案页写「%.2f 天」；按每天 %d 小时折算要 %d 个班次日（%.2f 天）"
      % (T0, d_cont, DAY, d_cal, T0 / DAY))
print("    倍数 = %.2f（= 24/%d 再叠加取整）；最忙一台机器累计 %d 小时 = 单独占 %d 个班次日"
      % (d_cal / d_cont, DAY, Lmax, d_machine))
print("    「排得下但做不完」的量化：按 %.1f 天承诺，实际要 %d 天，晚 %.1f 天（%s）"
      % (d_cont, d_cal, d_cal - d_cont, pct((d_cal - d_cont) / d_cont)))
print("    诚实说明：这一条的倍数本质就是 24/%d 的单位换算（取整才让 %.2f 不等于 3.00），"
      % (DAY, d_cal / d_cont))
print("    它不涌现任何新现象，翻车点在于「换算这一步在真实项目里通常没人做」——所以它能骗过所有指标。")
row("P08", "班次日历没算", "%d 小时 -> 声称 %.2f 天、日历要 %d 天（倍数 %.2f）；瓶颈机独占 %d 班次日"
    % (T0, d_cont, d_cal, d_cal / d_cont, d_machine), 0)

# ---- P09 无限产能假设
blind = {}
for i, j in enumerate(MAIN):
    t = 0
    for o in range(len(j)):
        blind[(i, o)] = t
        t += DUR0[(i, o)]
t_blind = max(blind[n] + DUR0[n] for n in blind)
ov_pairs, ov_hours = 0, 0
for k, ops in OPS0.items():
    seq = sorted(ops, key=lambda op: (blind[op], op))
    for a, b in zip(seq, seq[1:]):
        fa, fb = blind[a] + DUR0[a], blind[b]
        if fb < fa:
            ov_pairs += 1
            ov_hours += fa - fb
j9 = gen(4, 3, 7)
_, o9, d9 = make_eval(j9)
tot9, none9 = 0, 0
for perm in itertools.product(*[list(itertools.permutations(o9[k])) for k in range(3)]):
    tot9 += 1
    if starts(j9, d9, {k: list(perm[k]) for k in range(3)}) is None:
        none9 += 1
print("  P09 无限产能假设（两道同机工序排在同一时刻）")
print("    完全不看机器的「盲排」makespan 只有 %d 小时，下发方案 %d 小时：账面省 %d 小时（%s）——"
      % (t_blind, T_REF, T_REF - t_blind, pct((t_blind - T_REF) / T_REF)))
print("    省下来的全是幻觉：同机同刻重叠 %d 对、被藏起来的冲突时间 %d 小时（= 全场加工工时 %d 小时的 %.1f%%）。"
      % (ov_pairs, ov_hours, busy0, ov_hours / busy0 * 100))
print("    反过来问「模型会不会让我同刻开工」：不会。%d x %d 全枚举 %d 组机器顺序，其中 %d 组（%.1f%%）直接成环"
      % (4, 3, tot9, none9, none9 / tot9 * 100))
print("    starts() 对成环返回 None 而不是给出同刻开工——产能靠顺序表达，非法方案被挡在门外，这才是可行为主建模的安全感来源。")
row("P09", "无限产能假设", "盲排账面省 %d 小时（%s）、藏 %d 对重叠；%d/%d 组机器顺序成环返回 None"
    % (T_REF - t_blind, pct((t_blind - T_REF) / T_REF), ov_pairs, none9, tot9), 1)

# ---- P10 多目标写成一个
KEYS = [("SPT 最短工序", K_SPT),
        ("MWKR 剩余工时最长", lambda s, p, i, k: (-sum(q for _, q in MAIN[i]), i, k)),
        ("FIFO 按工单号", lambda s, p, i, k: (i, p, k)),
        ("ACTIVE 最早可开工", K_ACT)]
POOL = []
for nm, key in KEYS:
    for sd in (0, 1, 2):
        oo = dispatch(MAIN, DUR0, key, rnd=random.Random(31 + sd))
        POOL.append((nm + "#" + str(sd), oo, cmax(MAIN, DUR0, oo), mean_completion(MAIN, DUR0, oo)))
POOL.append(("爬山-目标 makespan", O_REF, T_REF, MC_REF))
o_start = dispatch(MAIN, DUR0, K_ACT, rnd=random.Random(3))
mc_val, o_mc, n_mc = climb_mean(MAIN, DUR0, o_start, 600, 13)
POOL.append(("爬山-目标 平均完工", o_mc, cmax(MAIN, DUR0, o_mc), mc_val))
xs = [p[2] for p in POOL]
ys = [p[3] for p in POOL]
mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
sx = math.sqrt(sum((a - mx) ** 2 for a in xs) / len(xs))
sy = math.sqrt(sum((b - my) ** 2 for b in ys) / len(ys))
corr = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / len(xs) / (sx * sy) if sx and sy else None
A = min(POOL, key=lambda p: p[2])
B = min(POOL, key=lambda p: p[3])
nd = sum(1 for p in POOL if not any(q[2] <= p[2] and q[3] <= p[3] and (q[2] < p[2] or q[3] < p[3]) for q in POOL))
print("  P10 多目标写成一个（拿平均完工当 makespan 优化，或反之）")
print("    候选池 %d 个方案：makespan %d~%d，平均完工 %.1f~%.1f，两个指标的相关系数 r = %s"
      % (len(POOL), min(xs), max(xs), min(ys), max(ys), "%.2f" % corr if corr is not None else "无法计算"))
print("    同一批搜索、两种选法：按 makespan 选 %s = %d / %.1f；按平均完工选 %s = %d / %.1f"
      % (A[0], A[2], A[3], B[0], B[2], B[3]))
if A is B:
    print("    这一轮两个冠军是同一个解（相关系数 r=%.2f）：这条在本机没咬人，别拿它去论证「必须写两个目标」。"
          % (corr if corr is not None else 0))
    NOBITE.append(("P10", "两个目标在本算例上 r=%.2f，冠军重合" % corr))
else:
    print("    互相差：按 makespan 选出来的解，平均完工比对方差 %s；按平均完工选出来的解，makespan 比对方差 %s"
          % (pct((A[3] - B[3]) / B[3]), pct((B[2] - A[2]) / A[2])))
oth = [p for p in POOL if p is not A]
B2 = min(oth, key=lambda p: p[3])
print("    退一步取平均完工的第二名（%s = %d / %.1f）：makespan 比冠军 %+d（%s），平均完工也还差 %s——"
      % (B2[0], B2[2], B2[3], B2[2] - A[2], pct((B2[2] - A[2]) / A[2]), pct((B2[3] - A[3]) / A[3])))
print("    两个指标在这批解里同向（r=%.2f）：换目标只是换个说法，真要打架得把交期或权重写进目标函数。"
      % (corr if corr is not None else 0))
print("    池里非被支配解 %d/%d 个：剩下 %d 个在两个指标上都被压着；只报一个指标时，它们会被当成「更好」端上台。"
      % (nd, len(POOL), len(POOL) - nd))
row("P10", "多目标写成一个", "r=%s，两个冠军%s；平均完工第二名在两个指标上都差 %s / %s"
    % ("NA" if corr is None else "%.2f" % corr, "重合" if A is B else "分家",
       pct((B2[2] - A[2]) / A[2]), pct((B2[3] - A[3]) / A[3])), 0)

# ---------------------------------------------------------------- [3] 集成/状态类
print()
print(W)
print("[3] 集成与状态类翻车：口径、幂等、超时、版本、回写")
print(W)

# ---- P11 冻结窗口口径错位
st_ref = starts(MAIN, DUR0, O_REF)
T_REL = 20
released = {op for op, s in st_ref.items() if s < T_REL}
rush11 = gen(1, M0, 777)[0]
J11 = [list(j) for j in MAIN] + [rush11]
_, ops11, d11 = make_eval(J11)
NOP11 = sum(len(j) for j in J11)
need_full = {}
for k, seq in O_REF.items():
    idxs = [idx for idx, op in enumerate(seq) if op in released]
    need_full[k] = max(idxs) + 1 if idxs else 0
print("  P11 冻结窗口口径错位（钉「机器前缀」而不是钉「开工时刻」）")
print("    基线 makespan %d；口径「开工时刻 < %d 小时 = 已开工」-> %d/%d 道工序（%.1f%%）"
      % (T_REF, T_REL, len(released), NOP, len(released) / NOP * 100))
print("  " + pad("    W", 7) + pad("钉住格数", 11) + pad("已开工覆盖率", 15) + pad("makespan", 10)
      + pad("时刻改动", 12) + pad("已开工被改", 14) + "钉住里被改")
rows11 = []
for Wn in (0, 3, 6):
    cut = {k: min(Wn, len(v)) for k, v in O_REF.items()}
    pinned = set()
    for k, seq in O_REF.items():
        pinned.update(seq[:cut[k]])
    v11, o11, ne11, rs11 = local_search(J11, seed=5, budget=200, base=O_REF, cut=cut, moves=2)
    st11 = starts(J11, d11, o11)
    ch_time = sum(1 for op in st11 if st11[op] != st_ref.get(op, 0))
    rel_moved = sum(1 for op in released if st11[op] != st_ref[op])
    pin_moved = sum(1 for op in released & pinned if st11[op] != st_ref[op])
    cov = len(released & pinned) / len(released) * 100
    rows11.append({"W": Wn, "cells": sum(cut.values()), "cov": cov, "v": v11, "ch": ch_time,
                   "rel": rel_moved, "pin": pin_moved, "npin": len(released & pinned),
                   "o": o11, "st": st11})
    print("  " + pad("    %d" % Wn, 7) + pad(sum(cut.values()), 11) + pad("%.0f%%" % cov, 15)
          + pad(v11, 10) + pad("%d/%d" % (ch_time, NOP11), 12)
          + pad("%d/%d" % (rel_moved, len(released)), 14) + str(pin_moved))
r6 = rows11[2]
NEED = sum(need_full.values())
print("    覆盖率：W=6 钉 %d 格 -> 盖住已开工 %d 个工序的 %.0f%%；W=3 钉 %d 格 -> 只有 %.0f%%（漏 %d 个）。"
      % (r6["cells"], len(released), r6["cov"], rows11[1]["cells"], rows11[1]["cov"],
         len(released) - rows11[1]["npin"]))
if r6["cov"] >= 100:
    print("    本算例 W=6 恰好盖满（按时刻口径只需钉 %s 合计 %d 格，前缀口径盖满就得钉 %d 格，多锁 %d 格）："
          % (list(need_full.values()), NEED, r6["cells"], r6["cells"] - NEED))
    print("    盖满时钉住确实有效（钉住集合里被改时刻 %d 个、已开工被改 %d 个），代价是全场仍有 %d/%d 个时刻要重算（%.0f%%）。"
          % (r6["pin"], r6["rel"], r6["ch"], NOP11, r6["ch"] / NOP11 * 100))
else:
    print("    盖不满：漏掉 %d 个已开工工序，其中 %d 个时刻被改；钉住集合本身被改 %d 个。"
          % (len(released) - r6["npin"], r6["rel"], r6["pin"]))
if r6["pin"] == 0 and rows11[1]["pin"] == 0:
    print("    两档前缀里被改时刻的都是 0 个：位置前缀锁得住，坏在口径——它按机器格数发牌，车间按开工时刻受害。")
else:
    print("    钉住集合里被改时刻的有 %d / %d 个（W=3 / W=6）：前缀本身就没锁住，得查 pin 的实现。"
          % (rows11[1]["pin"], r6["pin"]))
print("    钉满 vs 不钉：makespan %d -> %d（%s），但时刻改动 %d -> %d——冻结窗口换来的是稳定，不是更短。"
      % (rows11[0]["v"], r6["v"], pct((r6["v"] - rows11[0]["v"]) / rows11[0]["v"]),
         rows11[0]["ch"], r6["ch"]))
P11_REL, P11_CH = max(r["rel"] for r in rows11), rows11[0]["ch"]
row("P11", "冻结窗口口径错", "W=3 覆盖 %.0f%%（漏 %d 个）；W=6 盖满要多锁 %d 格，仍有 %d/%d 时刻重算"
    % (rows11[1]["cov"], len(released) - rows11[1]["npin"], r6["cells"] - NEED,
       r6["ch"], NOP11), 1)

# ---- P12 幂等重放
J12 = [list(j) for j in MAIN] + [list(j) for j in MAIN]
_, o12, d12, L12 = loads(J12)
n12a = M0 * len(MAIN) * (len(MAIN) - 1) // 2
n12b = M0 * len(J12) * (len(J12) - 1) // 2
o12d = dispatch(J12, d12, K_SPT, rnd=random.Random(11))
t12 = cmax(J12, d12, o12d)
uniq12 = len({tuple(j) for j in J12})
print("  P12 幂等重放（同一批工单被导入两次）")
print("    工单 %d -> %d，工序 %d -> %d；整单签名去重后剩 %d 条，说明该丢 %d 条"
      % (len(MAIN), len(J12), NOP, sum(len(j) for j in J12), uniq12, len(J12) - uniq12))
print("    析取变量 m*C(n,2)：%d -> %d（x%.2f，对 n 是二次）；同一规则排出的 makespan %d -> %d（%s）"
      % (n12a, n12b, n12b / n12a, T_SPT, t12, pct((t12 - T_SPT) / T_SPT)))
print("    负载翻倍而产能没翻倍（单机最忙 %d -> %d 小时）：多出来的不是产能是排队；重放不报错，只让模型自己变大。"
      % (max(L_true), max(L12)))
row("P12", "幂等重放", "析取变量 x%.2f（%d->%d）、makespan %s；整单签名可精确去重"
    % (n12b / n12a, n12a, n12b, pct((t12 - T_SPT) / T_SPT)), 1)

# ---- P13 求解器超时被当成无解
o13s = dispatch(MAIN, DUR0, K_ACT, rnd=random.Random(3))
t13s = cmax(MAIN, DUR0, o13s)
lad = []
print("  P13 求解器超时被当成「无解」（同一 seed，只改评估预算）")
print("    派工起点（ACTIVE）makespan = %d，平凡下界 = %d" % (t13s, LB0))
print("  " + pad("    预算", 10) + pad("makespan", 11) + pad("超下界", 11) + pad("比派工起点", 14)
      + pad("重启轮数", 11) + "返回 None")
for bd in (50, 200, 800, 3200):
    v13, o13, ne13, rs13 = local_search(MAIN, seed=3, budget=bd, moves=2)
    lad.append((bd, v13, ne13, rs13))
    print("  " + pad("    %d" % bd, 10) + pad(v13, 11) + pad(pct((v13 - LB0) / LB0), 11)
          + pad(pct((v13 - t13s) / t13s), 14) + pad(rs13, 11) + str(v13 is None))
n_none = sum(1 for x in lad if x[1] is None)
print("    四档 makespan %s，返回 None 的档数 = %d -> 超时交出的是次优解，不是无解。"
      % ([x[1] for x in lad], n_none))
print("    最省的一档（%d 次评估）就有 %d（比派工起点 %s）：把它当「算不出来」上报，等于把能用的方案扔掉。"
      % (lad[0][0], lad[0][1], pct((lad[0][1] - t13s) / t13s)))
print("    预算 x4（%d -> %d）只换来 %d 小时（%s）：这一段卡的是邻域，不是时间，加超时救不了质量。"
      % (lad[2][0], lad[3][0], lad[2][1] - lad[3][1], pct((lad[3][1] - lad[2][1]) / lad[2][1])))
nb13 = nbr_count(O_REF, {}, 2)
low = [x for x in lad if x[0] < nb13]
print("    一轮全场扫描要 %d 个邻居（交换+插入），前 %d 档预算（%s）连一轮都没走完，"
      % (nb13, len(low), "/".join(str(x[0]) for x in low)))
print("    重启轮数 %s -> 同一份预算买不到「更多局部最优」，只买到「同一个局部最优的不同进度」。"
      % sorted({x[3] for x in lad}))
row("P13", "超时当无解", "四档 %s，None 档数 %d；%d 次评估即有可用方案（比派工 %s）"
    % ("/".join(str(x[1]) for x in lad), n_none, lad[0][0], pct((lad[0][1] - t13s) / t13s)), 1)

# ---- P14 版本漂移（换 seed）
K_TIE = lambda s, p, i, k: p
drift = []
for tag, key in (("带工单号兜底 (p,i,k)", K_SPT), ("只按工时 (p,) 有并列", K_TIE)):
    tl = [0, 0]
    outs = {}
    for sd in range(6):
        sl = [0, 0]
        outs[sd] = dispatch(MAIN, DUR0, key, rnd=random.Random(sd), stats=sl)
        tl[0] += sl[0]
        tl[1] += sl[1]
    uniq = len({sig(outs[sd]) for sd in outs})
    mk = [cmax(MAIN, DUR0, outs[sd]) for sd in range(6)]
    lsv = [local_search(MAIN, seed=sd, budget=300, moves=2)[0] for sd in range(5)]
    drift.append((tag, tl[0], tl[1], uniq, mk, len(set(lsv)), lsv))
print("  P14 版本漂移（升级换了 random.Random(seed) 的种子）")
print("  " + pad("    派工 key", 30) + pad("打平/总次数", 15) + pad("6 个 seed 套数", 17)
      + pad("makespan 极差", 15) + "爬山 5 seed 值数")
for tag, tie, tot, uniq, mk, nls, lsv in drift:
    print("  " + pad("    " + tag, 30) + pad("%d/%d" % (tie, tot), 15) + pad(uniq, 17)
          + pad("%d" % (max(mk) - min(mk)), 15) + "%d" % nls)
tie_full, tot_full, tie_tie, tot_tie = drift[0][1], drift[0][2], drift[1][1], drift[1][2]
if tie_full == 0:
    print("    诚实结论：key 带工单号兜底时打平 0/%d 次 -> 换 seed 在这条链上根本没有入口，" % tot_full)
    print("    本机的漂移不来自随机种子，而来自墙钟预算（评估次数由机器当时忙不忙决定）。")
    NOBITE.append(("P14", "打平 0/%d 次，seed 无入口" % tot_full))
else:
    print("    key 带兜底仍有 %d/%d 次打平（%.1f%%）：seed 一换方案就换，漂移是真实的。"
          % (tie_full, tot_full, tie_full / tot_full * 100))
print("    把兜底去掉（key 只按工时）：打平升到 %d/%d（%.1f%%），6 个 seed 给 %d 套方案、makespan 极差 %d 小时；"
      % (tie_tie, tot_tie, tie_tie / tot_tie * 100, drift[1][3], max(drift[1][4]) - min(drift[1][4])))
print("    爬山在 5 个 seed 上给 %d 个不同值。要不要锁 seed，取决于打分是不是全序——这个能在本机数出来。"
      % drift[1][5])
row("P14", "版本漂移换 seed", "兜底 key 打平 %d/%d（无入口）；去掉兜底 %d/%d、极差 %d"
    % (tie_full, tot_full, tie_tie, tot_tie, max(drift[1][4]) - min(drift[1][4])), 2)

# ---- P15 状态回写失败
r0 = rows11[0]
O1, st1, t1 = r0["o"], r0["st"], r0["v"]
stale = {k: list(v) for k, v in O_REF.items()}
cut_stale = {k: len(v) for k, v in stale.items()}
t15, o15, ne15, rs15 = local_search(J11, seed=5, budget=250, base=stale, cut=cut_stale, moves=2)
st15 = starts(J11, d11, o15)
pos1, pos15 = {}, {}
for k, seq in O1.items():
    for idx, op in enumerate(seq):
        pos1[op] = (k, idx)
for k, seq in o15.items():
    for idx, op in enumerate(seq):
        pos15[op] = (k, idx)
rollback = sum(1 for op in pos15 if pos1.get(op) != pos15[op])
movable15 = sum(len(o15[k]) - cut_stale[k] for k in o15)
c_rush1 = max(st1[(24, x)] + d11[(24, x)] for x in range(len(rush11)))
c_rush15 = max(st15[(24, x)] + d11[(24, x)] for x in range(len(rush11)))
print("  P15 状态回写失败（方案下发后没写回，第二轮拿插单前的旧顺序当基线）")
print("    第一轮真实下发方案（插单后自由重排）makespan %d；第二轮以插单前的旧顺序为基线 -> %d（%s）"
      % (t1, t15, pct((t15 - t1) / t1)))
print("    两轮逐格比对：位置被挪动的工序 %d/%d（%.1f%%）；第二轮真正可动的格子只剩 %d 个（新活塞末尾）"
      % (rollback, NOP11, rollback / NOP11 * 100, movable15))
print("    插单工件的工序被贴到机器 %d 的第 %d 格：它的完工时刻从 %d 推到 %d（%+d 小时）"
      % (pos15[(24, 0)][0], pos15[(24, 0)][1], c_rush1, c_rush15, c_rush15 - c_rush1))
print("    两轮在日志里都写着「求解成功」：错的是输入基线，只有对比两份 order 才看得见。")
row("P15", "状态回写失败", "第二轮 %s（%d -> %d）；%d/%d 道工序位置被挪、可动格只剩 %d"
    % (pct((t15 - t1) / t1), t1, t15, rollback, NOP11, movable15), 2)

# ---------------------------------------------------------------- [4] 交付类
print()
print(W)
print("[4] 交付类翻车：数字没有分母、没有最差、没有闭环")
print(W)

# ---- P16 验收指标写「提升 X%」但没有分母
SM = gen(8, 3, 5)
m16, ops16, d16 = make_eval(SM)
lb16 = trivial_lb(SM)
t16, o16, ne16, rs16 = local_search(SM, seed=5, budget=800, moves=2)
rnd_vals, rnd_try = [], 0
r16 = random.Random(2026)
for _ in range(2000):
    oo = {k: r16.sample(ops16[k], len(ops16[k])) for k in ops16}
    vv = cmax(SM, d16, oo)
    rnd_try += 1
    if vv is not None:
        rnd_vals.append(vv)
rule16 = {}
for nm, key in KEYS:
    rule16[nm] = min(cmax(SM, d16, dispatch(SM, d16, key, rnd=random.Random(31 + sd))) for sd in (0, 1, 2))
best_r, worst_r = min(rule16.values()), max(rule16.values())
gs = []
if rnd_vals:
    gs.append(("随机可行解中位", (median(rnd_vals) - t16) / median(rnd_vals) * 100))
gs.append(("最差派工规则", (worst_r - t16) / worst_r * 100))
gs.append(("最好派工规则", (best_r - t16) / best_r * 100))
print("  P16 验收指标写「提升 X%」但没有分母")
print("    小算例 %d 工件 x %d 机器：抽 %d 组随机机器顺序，可行 %d 组（%.1f%%），其余直接成环"
      % (len(SM), m16, rnd_try, len(rnd_vals), len(rnd_vals) / rnd_try * 100))
print("    随机可行 makespan min/median/max = %s；四条规则 %d~%d；平凡下界 %d；本次爬山 %d"
      % ("%d/%.1f/%d" % (min(rnd_vals), median(rnd_vals), max(rnd_vals)) if rnd_vals else "无可行样本",
         best_r, worst_r, lb16, t16))
print("    注意分母本身：随机可行样本只有 %d 组，上面那个中位数就踩在这 %d 个数上。"
      % (len(rnd_vals), len(rnd_vals)))
print("    「比随机好 X%%」这类话，分母越薄数字越好看——真要写进验收，得先把 %d 条规则/搜索这套参照系说明白。"
      % len(KEYS))
gvals = [g for _, g in gs]
gpos = [g for g in gvals if g > 0]
ratio_txt = ("%.1f 倍" % (max(gpos) / min(gpos))) if len(gpos) > 1 else "倍率无从谈起（正提升只剩 1 个）"
print("    同一个解（makespan=%d）配 %d 个分母：%s"
      % (t16, len(gs), "、".join("比%s %+.1f%%" % (nm, g) for nm, g in gs)))
print("    最大与最小相差 %.1f 个百分点、倍率 %s——写进合同之前先问「相对谁」。"
      % (max(gvals) - min(gvals), ratio_txt))
print("    而它对平凡下界 %d 还高出 %s：所谓「提升」从来没有超过产能本身的下界。"
      % (lb16, pct((t16 - lb16) / lb16)))
row("P16", "提升没有分母", "同一个解三种说法 %s；随机顺序可行率 %.1f%%"
    % ("/".join("%+.1f%%" % g for _, g in gs), len(rnd_vals) / rnd_try * 100), 0)

# ---- P17 演示环境吞吐 != 生产环境
thr17 = {}
print("  P17「演示环境」吞吐 != 生产环境（本机评估吞吐，0.3 秒计时）")
print("  " + pad("    规模", 14) + pad("工序", 8) + pad("评估/秒", 13) + pad("相邻交换邻居", 16) + "扫完一轮")
for n, m in [(20, 4), (24, 6), (200, 15)]:
    jj = MAIN if (n, m) == (24, 6) else gen(n, m, 99)
    _, _, dd = make_eval(jj)
    bb = dispatch(jj, dd, K_ACT, rnd=random.Random(3))
    ev17 = Eval(jj, dd)
    tt = time.perf_counter()
    cc = 0
    while time.perf_counter() - tt < 0.30:
        ev17(bb)
        cc += 1
    rr = cc / (time.perf_counter() - tt)
    nb17 = nbr_count(bb, {}, 1)
    thr17[n * m] = (rr, nb17)
    print("  " + pad("    %d x %d" % (n, m), 14) + pad(n * m, 8) + pad("{:,.0f}".format(rr), 13)
          + pad("{:,}".format(nb17), 16)
          + ("%.0fms" % (nb17 / rr * 1000) if nb17 / rr < 1 else "%.1fs" % (nb17 / rr)))
sc = sorted(thr17)
r_small, r_big = thr17[sc[0]][0], thr17[sc[-1]][0]
print("    同一台机器、同一个内核：演示规模 %.0f 次/秒，生产规模 %.0f 次/秒，差 %.1f 倍（一次评估 ~ O(工序数)）"
      % (r_small, r_big, r_small / r_big))
print("    1 秒预算：演示规模够扫 %.1f 轮全场邻域，生产规模扫一轮要 %.1fs（同一轮扫描的代价差 %.0f 倍）——"
      % (r_small / thr17[sc[0]][1], thr17[sc[-1]][1] / r_big,
         (thr17[sc[-1]][1] / r_big) / (thr17[sc[0]][1] / r_small)))
print("    同一个「1 秒」在两种规模上是两个世界：演示里喊得出的「秒级重排」，在生产规模就是等不到的那一分钟。")
print("    边界说明：这里量的是本机内核吞吐随规模的变化，客户服务器的绝对值本机测不到，不编。")
row("P17", "演示吞吐", "%.0f vs %.0f 次/秒（x%.1f）；生产规模扫一轮 %s"
    % (r_small, r_big, r_small / r_big,
       "%.1fs" % (thr17[sc[-1]][1] / r_big)), 0)

# ---- P18 甘特图上的视觉欺骗
gaps18 = []
for k, seq in OPS0.items():
    srt = sorted(seq, key=lambda op: (st_ref[op], op))
    for a, b in zip(srt, srt[1:]):
        g0, g1 = st_ref[a] + DUR0[a], st_ref[b]
        if g1 > g0:
            gaps18.append((k, g0, g1))
idle_tot = sum(g1 - g0 for _, g0, g1 in gaps18)
idle_ge3 = sum(1 for _, g0, g1 in gaps18 if g1 - g0 >= 3)
jw_seg, jw_tot = 0, 0
for i, j in enumerate(MAIN):
    for o in range(1, len(j)):
        w = st_ref[(i, o)] - (st_ref[(i, o - 1)] + DUR0[(i, o - 1)])
        if w > 0:
            jw_seg += 1
            jw_tot += w
mrg = []
for a, b in sorted([st_ref[n], st_ref[n] + DUR0[n]] for n in st_ref):
    if mrg and a <= mrg[-1][1]:
        mrg[-1][1] = max(mrg[-1][1], b)
    else:
        mrg.append([a, b])
idle_work = sum(sum(max(0, min(g1, y) - max(g0, x)) for x, y in mrg) for _, g0, g1 in gaps18)
idle_dead = idle_tot - idle_work
util = 1 - idle_tot / (M0 * T_REF)
print("  P18 甘特图上的视觉欺骗（同一方案，按机器画 vs 按工件画）")
print("    按机器画：空档 %d 段、共 %d 小时，机器利用率 %.1f%%；阈值提到 >=3 小时，段数掉到 %d（-%.1f%%）"
      % (len(gaps18), idle_tot, util * 100, idle_ge3, (len(gaps18) - idle_ge3) / len(gaps18) * 100))
print("    按工件画：等待 %d 段、共 %d 小时——同一份方案，两种画法各自都能讲出「闲死了」或「堵死了」"
      % (jw_seg, jw_tot))
print("    空档里「工件还在别的机器上加工」%d 小时（工艺顺序挡着，不算浪费），全场无事可做的真空闲 %d 小时（%.1f%%）"
      % (idle_work, idle_dead, idle_dead / (M0 * T_REF) * 100))
if idle_dead == 0:
    print("    空档总量 %d 小时、可重叠 %d 小时（两者相等）：%d 段空白全都属于「活还在路上」，"
          % (idle_tot, idle_work, len(gaps18)))
    print("    也就是说这一屏的空白是画法造成的，不是产能浪费——这正是最容易被截图汇报骗的那种图。")
else:
    print("    真空闲占机器可用时间的 %.1f%%：这部分不是画法，是真的排空了，值得单独摆给计划员看。"
          % (idle_dead / (M0 * T_REF) * 100))
print("    视觉欺骗的量化就在段数那一栏：%d 段变 %d 段只改了画法，总空闲 %d 小时一分钟没少。"
      % (len(gaps18), idle_ge3, idle_tot))
row("P18", "甘特图视觉欺骗", "空档 %d 段/%d 小时（利用率 %.0f%%）；改阈值少 %.0f%% 段，真空闲 %d 小时"
    % (len(gaps18), idle_tot, util * 100, (len(gaps18) - idle_ge3) / len(gaps18) * 100, idle_dead), 2)

# ---- P19 指标只报平均不报最差
Cd = job_done(MAIN, DUR0, st_ref)
c_mean = sum(Cd) / len(Cd)
c_max, c_min = max(Cd), min(Cd)
i_max = Cd.index(c_max)
wait_i = [Cd[i] - sum(p for _, p in MAIN[i]) for i in range(len(MAIN))]
i_worst = wait_i.index(max(wait_i))
stA, stB = starts(MAIN, DUR0, A[1]), starts(MAIN, DUR0, B[1])
tail_a, tail_b = max(job_done(MAIN, DUR0, stA)), max(job_done(MAIN, DUR0, stB))
print("  P19 指标只报平均不报最差")
print("    工件完工时间：min %d / median %.1f / mean %.1f / max %d（max 是第 %d 号工件），max/mean = %.2f"
      % (c_min, median(Cd), c_mean, c_max, i_max, c_max / c_mean))
print("    在系统里待得最久的是第 %d 号：加工 %d 小时，等待 %d 小时，完工 %d"
      % (i_worst, sum(p for _, p in MAIN[i_worst]), wait_i[i_worst], Cd[i_worst]))
print("    平均完工冠军 %s -> 尾部工件完工 %d；makespan 冠军 %s -> %d（差 %+d 小时）"
      % (B[0], tail_b, A[0], tail_a, tail_b - tail_a))
if A is B:
    print("    本轮两个冠军是同一个解，这句比较退化成恒等，别当成「平均与最差同步」。")
if tail_b <= tail_a:
    print("    诚实说明：这一轮平均最优解的尾部没有更差（%d <= %d），「平均掩盖最差」在本算例上不成立，" % (tail_b, tail_a))
    print("    只能当成风险提醒，不能当成实测结论——要它成立得把工件间权重或交期写进目标。")
    NOBITE.append(("P19", "平均最优解的尾部没有更差（%d <= %d）" % (tail_b, tail_a)))
row("P19", "只报平均不报最差", "完工 max/mean=%.2f（%d vs %.1f）；待最久是第 %d 号，多待 %d 小时"
    % (c_max / c_mean, c_max, c_mean, i_worst, wait_i[i_worst]), 0)

# ---- P20 反馈闭环缺失
print("  P20 反馈闭环缺失（计划员手工改的方案没进训练/评测集）")
print("    本条无实测，只有流程要求：本机没有人在环，「改了几道工序、为什么改」测不出来，也不该编。")
print("    可测的代理量级：P11 一次插单重排会改 %d 个工序的时刻（其中已开工 %d 个），" % (P11_CH, P11_REL))
print("    P15 一次回写失败会挪 %d 道工序的顺序——人真正会碰的就是这些格子，它们就是该被采集的事件条数量级。"
      % rollback)
print("    流程要求：下发后的人工改动要回写成带时间戳的 diff 事件并进评测集，否则线上永远只评机器解。")
row("P20", "反馈闭环缺失", "无实测；代理量级 = 每次重排 %d~%d 个时刻/顺序改动（取自 P11/P15）"
    % (P11_REL, max(P11_CH, rollback)), 0)

# ---------------------------------------------------------------- [5] 一览
print()
print(W)
print("[5] 一览：20 条翻车的本机实测影响与检测难度")
print(W)
print("  检测难度口径：能否只靠这份数据自身（不看工艺卡、不看现场、不看人）在本地自检里抓到。")
wname = max(dw(r[1]) for r in ROWS) + 2
wimp = max(dw(r[2]) for r in ROWS) + 2
print("  " + pad("编号", 6) + pad("翻车", wname) + pad("实测影响", wimp) + "检测难度")
for pid, name, impact, kind in ROWS:
    print("  " + pad(pid, 6) + pad(name, wname) + pad(impact, wimp) + kind)
n_yes = sum(1 for r in ROWS if r[3] == "是")
n_no = sum(1 for r in ROWS if r[3] == "否")
n_part = sum(1 for r in ROWS if r[3] == "部分")
print("  纯本地自检能抓到 %d 条、抓不到 %d 条、介于两者 %d 条（共 %d 条）——抓不到的那些只能靠流程与外部对照。"
      % (n_yes, n_no, n_part, len(ROWS)))
if NOBITE:
    print("  没按预期咬人的条目（原样打印，不做包装）：%s" % "、".join(p for p, _ in NOBITE))
    for pid, why in NOBITE:
        print("    %s：%s" % (pid, why))
else:
    print("  本轮 20 条都在本机打出了非零影响，没有「测了个寂寞」的条目。")
el = time.perf_counter() - T_START
print("  全部数字出自本机现跑：算例 %d 工件 x %d 机器 = %d 工序（P16 用 %d x %d），随机种子写死；"
      % (len(MAIN), M0, NOP, len(SM), m16))
print("  只有 P17 那一栏是 wall-clock，换机器会变。本次运行 %.1f 秒，共 %d 条实测。" % (el, len(ROWS)))

