# -*- coding: utf-8 -*-
"""一次拖拽到底要重算多少东西：在随机作业车间算例上实测「影响闭包」的大小与分布、
闭包增量重算 vs 全场重算的吞吐与加速比、以及 <16ms / <100ms / <1s 三档体感预算判定，
为调度员工作台（/build/workbench，拖拽式排产 UI）的产品形态（实时拖拽 / 点一下等一下 / 夜算）给出数字依据。

用法:  python workbench_probe.py          （纯标准库，无第三方依赖）

  [1] 闭包有多深：相邻交换后「图上闭包」与「实际时刻变化」随规模的分布
  [2] 全场重算 vs 闭包重算：先过正确性门（逐格相同），再测吞吐与加速倍数
  [3] 拖一下的体感预算：一次鼠标抬起按规模判 是/否
  [4] 长尾：闭包大小分位数与「最坏一次拖拽」的代价
  [5] 机器维度：哪台机器「动不得」，锁掉它全场影响降多少
  [6] 本机实测一览

时间是本机 wall-clock，换机器数字会变；闭包大小、占比与结论不会。
"""
import itertools
import math
import random
import sys
import textwrap
import time
from collections import defaultdict

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


# ---------------------------------------------------------------- 闭包内核
def swap_order(order, k, a):
    """机器 k 上第 a 格与第 a+1 格相邻交换，返回新顺序（原顺序不动）。"""
    new = {kk: list(vv) for kk, vv in order.items()}
    s = new[k]
    s[a], s[a + 1] = s[a + 1], s[a]
    return new


def succ_map(jobs, order):
    """和 starts() 完全同款的后续表：机器紧邻边 + 工件工艺链边。"""
    nxt = {}
    for seq in order.values():
        for a, b in zip(seq, seq[1:]):
            nxt.setdefault(a, []).append(b)
    for i, j in enumerate(jobs):
        for o in range(len(j) - 1):
            nxt.setdefault((i, o), []).append((i, o + 1))
    return nxt


def forward_closure(nxt, roots):
    seen, stack = set(roots), list(roots)
    while stack:
        n = stack.pop()
        for c in nxt.get(n, []):
            if c not in seen:
                seen.add(c)
                stack.append(c)
    return seen


def closure_size(jobs, dur, order, op):
    """把 op 在其机器上往后挪一格（相邻交换）。返回 (新顺序, 图上闭包集合, 交换的两个工序)。
       op 已在该机最后一格（挪不动）时返回 None。闭包 = 交换后图上从被移动工序出发的前向可达集。"""
    i, o = op
    k = jobs[i][o][0]
    seq = order[k]
    a = seq.index(op)
    if a + 1 >= len(seq):
        return None
    x, y = seq[a], seq[a + 1]
    new_order = swap_order(order, k, a)
    roots = {x, y}
    return new_order, forward_closure(succ_map(jobs, new_order), roots), roots


def starts_partial(jobs, dur, order, fixed_st, roots):
    """只重算闭包内的最早开工时刻：闭包外沿用 fixed_st，闭包内做受限拓扑推进。
       正确性前提（代码保证）：闭包对后继边封闭，故闭包外任何工序的前驱都不在闭包内。
       返回 (完整时刻字典, 闭包集合)；字典与全场 starts() 逐格相同（[2] 里有门）。"""
    pos = {}
    for seq in order.values():
        for idx, x in enumerate(seq):
            pos[x] = idx

    def mach_succ(x):
        seq = order[jobs[x[0]][x[1]][0]]
        p = pos[x]
        return seq[p + 1] if p + 1 < len(seq) else None

    def mach_pred(x):
        seq = order[jobs[x[0]][x[1]][0]]
        p = pos[x]
        return seq[p - 1] if p > 0 else None

    C, stack = set(roots), list(roots)
    while stack:
        n = stack.pop()
        if n[1] + 1 < len(jobs[n[0]]):
            c = (n[0], n[1] + 1)
            if c not in C:
                C.add(c)
                stack.append(c)
        c = mach_succ(n)
        if c is not None and c not in C:
            C.add(c)
            stack.append(c)

    st = dict(fixed_st)
    cnt, base = {}, {}
    for n in C:
        k_in, b = 0, 0
        if n[1] > 0:
            p = (n[0], n[1] - 1)
            if p in C:
                k_in += 1
            else:
                b = max(b, fixed_st[p] + dur[p])
        p = mach_pred(n)
        if p is not None:
            if p in C:
                k_in += 1
            else:
                b = max(b, fixed_st[p] + dur[p])
        cnt[n], base[n] = k_in, b
    for n in C:
        st[n] = base[n]
    ready = [n for n in C if cnt[n] == 0]
    while ready:
        n = ready.pop()
        end = st[n] + dur[n]
        succs = []
        if n[1] + 1 < len(jobs[n[0]]):
            succs.append((n[0], n[1] + 1))
        c = mach_succ(n)
        if c is not None:
            succs.append(c)
        for c in succs:
            if c in C:
                if st[c] < end:
                    st[c] = end
                cnt[c] -= 1
                if cnt[c] == 0:
                    ready.append(c)
    return st, C


def quant(xs, q):
    xs = sorted(xs)
    p = (len(xs) - 1) * q
    lo = int(p)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (p - lo)


def median(xs):
    return quant(xs, 0.5)


# ---------------------------------------------------------------- 公共测量准备
T0 = time.perf_counter()


def bench(fn, target=0.10, cap=4000):
    """先 5 次粗测，再按 target 秒定次数实测；返回 (单次秒, 次数)。"""
    t0 = time.perf_counter()
    for _ in range(5):
        fn()
    per = (time.perf_counter() - t0) / 5.0
    reps = max(5, min(cap, int(target / max(per, 1e-9))))
    t0 = time.perf_counter()
    for _ in range(reps):
        fn()
    return (time.perf_counter() - t0) / reps, reps


SIZES = [(20, 4), (40, 6), (60, 8), (100, 10), (200, 15)]
NSAMP = 50
inst = {}
for n, m in SIZES:
    jobs = gen(n, m, 20261129 + n)
    mm, _, dur = make_eval(jobs)
    order = dispatch(jobs, dur, lambda s, p, i, k: (s, p, i, k), rnd=random.Random(11 + n))
    inst[(n, m)] = {"jobs": jobs, "dur": dur, "order": order, "st": starts(jobs, dur, order),
                    "ops": len(dur), "m": mm}

# ---------------------------------------------------------------- [0] 一例解剖
print(W)
print("[0] 一例解剖：把一台机器上相邻两格对调，甘特图上到底动了谁")
print(W)
mn = 6
mjobs = gen(mn, 3, 777, lo=2, hi=9)
_, _, mdur = make_eval(mjobs)
morder = dispatch(mjobs, mdur, lambda s, p, i, k: (s, p, i, k), rnd=random.Random(3))
mst = starts(mjobs, mdur, morder)
NM = len(mdur)
tok = lambda op: "%d.%d" % op
print("  小算例：%d 个工件 × 3 台机器 = %d 道工序，工时 2~9，固定种子；顺序 = 最早开工派工规则一次生成。" % (mn, NM))
print("  目的：[1] 之后所有结论都是成千上万道工序上的统计，这一节只给一格「看得见」的样本——")
print("        一次对调之后，哪些工序的时刻真的变了、哪些只是拓扑上够得着却没变。")
cyc0 = 0
movable = 0
for k in range(3):
    for a in range(len(morder[k]) - 1):
        movable += 1
        if starts(mjobs, mdur, swap_order(morder, k, a)) is None:
            cyc0 += 1
print("  可动的相邻交换位 %d 个，其中 %d 个一对调依赖图就成环（starts() 返回 None）——这种拖拽前端必须当场拒绝。"
      % (movable, cyc0))
best = None
for k in range(3):
    for a in range(len(morder[k]) - 1):
        new = swap_order(morder, k, a)
        st_new = starts(mjobs, mdur, new)
        if st_new is None:
            continue
        C = forward_closure(succ_map(mjobs, new), {morder[k][a], morder[k][a + 1]})
        if best is None or len(C) > len(best[4]):
            best = (k, a, new, st_new, C)
bk, ba, border, bst, bC = best
changed = sorted(n for n in bst if bst[n] != mst[n])
idle = sorted(n for n in bC if bst[n] == mst[n])
print("  选「闭包最大」的那一格来解剖：机器 %d 第 %d 格与第 %d 格对调（%s ↔ %s）。"
      % (bk, ba, ba + 1, tok(morder[bk][ba]), tok(morder[bk][ba + 1])))
print("  每台机器的加工顺序（工序@开工时刻+工期）：")
print("  " + pad("机器", 7) + pad("拖之前", 60) + "拖之后")
for k in range(3):
    print("  " + pad(k, 7)
          + pad(" ".join("%s@%d+%d" % (tok(x), mst[x], mdur[x]) for x in morder[k]), 60)
          + " ".join("%s@%d+%d" % (tok(x), bst[x], mdur[x]) for x in border[k]))
print("  " + pad("工序", 8) + pad("机器", 6) + pad("工期", 6) + pad("原开工", 9)
      + pad("新开工", 9) + pad("变化", 7) + "在闭包内")
for k in range(3):
    for x in border[k]:
        print("  " + pad(tok(x), 8) + pad(k, 6) + pad(mdur[x], 6) + pad(mst[x], 9) + pad(bst[x], 9)
              + pad(("+%d" % (bst[x] - mst[x])) if bst[x] > mst[x] else ("-" + str(mst[x] - bst[x]) if bst[x] < mst[x] else "不动"), 7)
              + ("是" if x in bC else "否"))
cm0 = max(mst[n] + mdur[n] for n in mdur)
cm1 = max(bst[n] + mdur[n] for n in mdur)
mc0 = sum(mst[n] + mdur[n] for n in mdur) / NM
mc1 = sum(bst[n] + mdur[n] for n in mdur) / NM
print("  这一次拖拽：图上闭包 %d 道工序（占全场 %.1f%%），时刻真变了 %d 道，白算 %d 道（%.0f%%）。"
      % (len(bC), len(bC) / NM * 100, len(changed), len(idle), len(idle) / len(bC) * 100))
print("  闭包外的 %d 道工序时刻一格没动——这就是「闭包对后继边封闭」能当增量重算边界的理由。" % (NM - len(bC)))
print("  时刻变了的 %d 道：%s。" % (len(changed), "、".join(tok(n) for n in changed)))
idle_txt = " ".join("%s@%d" % (tok(n), mst[n]) for n in idle)
print("  白算名单（在闭包内、时刻没变；写成 工序@原开工时刻）——列出来是为了看清「拓扑上够得着」和「时刻真的会改」是两件事：")
for _ln in textwrap.wrap(idle_txt, 74, initial_indent=" " * 10, subsequent_indent=" " * 10):
    print(_ln)
print("  换完顺序的目标函数：makespan %d → %d（%+d），平均完工 %.2f → %.2f（%+.2f）。"
      % (cm0, cm1, cm1 - cm0, mc0, mc1, mc1 - mc0))
print("  工作台上一条硬规矩：拖拽的「代价」不是那根条移动了几格，是上面这两行——用户要知道自己把全局推远了多远。")

print("  同一个算例里 15 个可动位各自的图上闭包（按机器、从第 0 格起）——「哪些格子值得让用户拖」可以按这个数上色：")
allc = []
mach_c = {}
for k in range(3):
    row = []
    mach_c[k] = []
    for a in range(len(morder[k]) - 1):
        new = swap_order(morder, k, a)
        st_new = starts(mjobs, mdur, new)
        if st_new is None:
            row.append("环")
            continue
        c = len(forward_closure(succ_map(mjobs, new), {morder[k][a], morder[k][a + 1]}))
        allc.append(c)
        mach_c[k].append(c)
        row.append(str(c))
    print("    机器 %d  " % k + " ".join(pad(v, 5) for v in row))
allc.sort()
print("  15 个位里成环 %d 个；剩下 %d 个的闭包：最小 %d、中位 %d、最大 %d（全场 %d 道工序）。"
      % (movable - len(allc), len(allc), allc[0], median(allc), allc[-1], NM))
_sp = {k: (min(v), max(v)) for k, v in mach_c.items() if v}
_wk = max(_sp, key=lambda k: _sp[k][1] / max(1, _sp[k][0]))
if _sp[_wk][1] > _sp[_wk][0]:
    print("  同一台机器内部就能差很多：机器 %d 的各位闭包从 %d 到 %d（%.1f 倍）——拖拽上色要按「位」算，不是按「机器」算。"
          % (_wk, _sp[_wk][0], _sp[_wk][1], _sp[_wk][1] / max(1, _sp[_wk][0])))
else:
    print("  这个算例里每台机器内部各位闭包相同（%s）；真实工厂数据上通常不会这么齐，上色仍然按位算。"
          % "、".join("%d:%d" % (k, v[0]) for k, v in sorted(_sp.items())))

# ---------------------------------------------------------------- [1] 闭包有多深
print(W)
print("[1] 一次拖拽的闭包有多大：挪一格，多少道工序的开工时刻会跟着动")
print(W)
print("  做法：在当前顺序里随机挑 NSAMP=%d 个可动的相邻交换位（= 工作台上一次拖拽），得新顺序后两种数法：" % NSAMP)
print("        图上闭包 = 交换后从被挪工序出发的全部后继（保守上界，增量实现真正要重算的集合）；")
print("        实际变化 = 新顺序全场重推后，开工时刻确实不同的工序数（真实波及）。")
print("  算例：gen() 稠密路线（每工件走完全部 m 台），工时 1~9，每档固定种子；基准顺序 = 最早开工派工规则一次生成。")
print("  图上闭包按交换后的图算，实际变化按同一新顺序全场重推算——两个数同源，差值可信。")
print("  两种数法必须分开：增量实现按图上闭包重算，用户眼睛看到的是实际变化——它们的差就是「白算」。")
print("  " + pad("n x m", 10) + pad("工序数", 8) + pad("图闭包均值", 12) + pad("中位", 7)
      + pad("P90", 6) + pad("最大", 7) + pad("实际变化均值", 13) + pad("闭包占比", 9)
      + pad("白算均值", 9) + "环")
g1 = {}
for n, m in SIZES:
    D = inst[(n, m)]
    jobs, dur, order, st_old, NOPS = D["jobs"], D["dur"], D["order"], D["st"], D["ops"]
    moves_all = [(k, a) for k in range(m) for a in range(len(order[k]) - 1)]
    rnd = random.Random(5 + n)
    gs, ac, cyc, overflow = [], [], 0, 0
    samples = []
    for (k, a) in rnd.sample(moves_all, min(NSAMP, len(moves_all))):
        x, y = order[k][a], order[k][a + 1]
        new = swap_order(order, k, a)
        st_new = starts(jobs, dur, new)
        if st_new is None:
            cyc += 1
            continue
        C = forward_closure(succ_map(jobs, new), {x, y})
        na = sum(1 for nn in st_new if st_new[nn] != st_old[nn])
        gs.append(len(C))
        ac.append(na)
        overflow += 1 if na > len(C) else 0
        samples.append((k, a, {x, y}))
    g1[(n, m)] = {"gs": gs, "ac": ac, "samples": samples, "cyc": cyc, "overflow": overflow}
    print("  " + pad("%d x %d" % (n, m), 10) + pad(NOPS, 8)
          + pad("%.1f" % (sum(gs) / len(gs)), 12) + pad("%.1f" % median(gs), 7)
          + pad("%.0f" % quant(gs, 0.9), 6) + pad(max(gs), 7)
          + pad("%.1f" % (sum(ac) / len(ac)), 13)
          + pad("%.1f%%" % (sum(gs) / len(gs) / NOPS * 100), 9)
          + pad("%.1f" % (sum(gs) / len(gs) - sum(ac) / len(ac)), 9)
          + str(cyc))
tot_ops = [inst[s]["ops"] for s in SIZES]
pcts = [sum(g1[s]["gs"]) / len(g1[s]["gs"]) / inst[s]["ops"] * 100 for s in SIZES]
apcts = [sum(g1[s]["ac"]) / len(g1[s]["ac"]) / inst[s]["ops"] * 100 for s in SIZES]
ratios = [(sum(g1[s]["gs"]) / len(g1[s]["gs"])) / max(sum(g1[s]["ac"]) / len(g1[s]["ac"]), 1) for s in SIZES]
print("  有效样本合计 %d 个（每档 %d~%d 个，相邻交换成环的样本已剔除，环列合计 %d）。"
      % (sum(len(v["gs"]) for v in g1.values()), min(len(v["gs"]) for v in g1.values()),
         max(len(v["gs"]) for v in g1.values()), sum(v["cyc"] for v in g1.values())))
print("  实际变化越过图上闭包的样本总数 = %d（应为 0：闭包是后继封闭集，凡是时刻变了的必然在闭包内）。"
      % sum(v["overflow"] for v in g1.values()))
print("  实际变化占比随规模：%s——眼睛真正看到的波及约是闭包的 %.0f%%~%.0f%%。"
      % ("、".join("%dx%d:%.1f%%" % (s[0], s[1], p) for s, p in zip(SIZES, apcts)),
         min(a / p for a, p in zip(apcts, pcts)) * 100,
         max(a / p for a, p in zip(apcts, pcts)) * 100))
print("  占比（中位口径）：%s。" % "、".join("%dx%d:%.1f%%" % (s[0], s[1], median(g1[s]["gs"]) / inst[s]["ops"] * 100) for s in SIZES))
max_pcts = [max(g1[s]["gs"]) / inst[s]["ops"] * 100 for s in SIZES]
tail_cnt = sum(1 for s, mp in zip(SIZES, max_pcts) if mp > 50)
print("  占比（最大口径）：%s——%d/%d 档的单次最大波及超过全场一半。"
      % ("、".join("%dx%d:%.1f%%" % (s[0], s[1], p) for s, p in zip(SIZES, max_pcts)), tail_cnt, len(SIZES)))
print("  闭包/实际变化 均值比 %s：按图上闭包做的增量重算里，约 %.1f%%~%.1f%% 是「时刻没变但拓扑够得着」的白算。"
      % ("、".join("%.2fx" % r for r in ratios),
         (1 - 1 / min(ratios)) * 100, (1 - 1 / max(ratios)) * 100))
print("  闭包占比随规模：%s——%s" % ("、".join("%dx%d:%.1f%%" % (s[0], s[1], p) for s, p in zip(SIZES, pcts)),
      "基本持平，闭包与全场同阶" if pcts[-1] <= pcts[0] * 1.2 else
      ("单调走高：规模越大越躲不开全网波及" if pcts[-1] > pcts[0] else "反而走低：小算例里一次挪动占比更高")))
print("  读法：占比这列就是增量评估的天花板——平均 %.0f%%~%.0f%% 的占比意味着闭包重算最多把每次代价砍一半左右，"
      % (min(pcts), max(pcts)))
print("  省不出量级。图上闭包比实际变化平均多 %.1f~%.1f 个工序（各档），增量实现仍必须整闭包重推才逐格正确。"
      % (min(sum(g1[s]["gs"]) / len(g1[s]["gs"]) - sum(g1[s]["ac"]) / len(g1[s]["ac"]) for s in SIZES),
         max(sum(g1[s]["gs"]) / len(g1[s]["gs"]) - sum(g1[s]["ac"]) / len(g1[s]["ac"]) for s in SIZES)))

# ---------------------------------------------------------------- [2] 全场 vs 闭包重算
print()
print(W)
print("[2] 一次全场重推 vs 一次闭包重推：先过正确性门，再谈时间")
print(W)
print("  正确性门：对每档全部有效样本，starts_partial(闭包) 与 starts(全场) 的结果字典逐格 ==，全过才计时。")
print("  " + pad("n x m", 10) + pad("验证", 10) + pad("全场次/秒", 11) + pad("闭包次/秒", 11)
      + pad("加速倍数", 9) + pad("闭包单次ms", 12) + "计时次数")
gate_all, rate_f, rate_p, ms_p, ms_f = {}, {}, {}, {}, {}
for n, m in SIZES:
    D = inst[(n, m)]
    jobs, dur, order, st_old = D["jobs"], D["dur"], D["order"], D["st"]
    ok_moves = g1[(n, m)]["samples"][:8]
    ok = True
    ncmp = 0
    for (k, a, roots) in g1[(n, m)]["samples"]:
        new = swap_order(order, k, a)
        st_full = starts(jobs, dur, new)
        st_part, _ = starts_partial(jobs, dur, new, st_old, roots)
        ncmp += 1
        if st_part != st_full:
            ok = False
    gate_all[(n, m)] = (ok, ncmp)
    assert ok, "闭包重算与全场重算失配：%dx%d，禁止在未验证的实现上计时" % (n, m)
    tf, nf, tp, np_ = 0.0, 0, 0.0, 0
    for (k, a, roots) in ok_moves:
        new = swap_order(order, k, a)
        dt, r = bench(lambda nn=new: starts(jobs, dur, nn))
        tf += dt * r
        nf += r
        dt, r = bench(lambda nn=new, rr=roots: starts_partial(jobs, dur, nn, st_old, rr)[0])
        tp += dt * r
        np_ += r
    rate_f[(n, m)], rate_p[(n, m)] = nf / tf, np_ / tp
    ms_f[(n, m)], ms_p[(n, m)] = tf / nf * 1000, tp / np_ * 1000
    print("  " + pad("%d x %d" % (n, m), 10)
          + pad("OK %d/%d" % (ncmp if ok else -1, ncmp) if ok else "失配", 10)
          + pad("%.0f" % rate_f[(n, m)], 11) + pad("%.0f" % rate_p[(n, m)], 11)
          + pad("%.2fx" % (rate_p[(n, m)] / rate_f[(n, m)]), 9)
          + pad("%.2f" % ms_p[(n, m)], 12) + str(nf))
print("  闭包重算与全场重算逐格相同（每档全部有效样本）：%s"
      % "、".join("%dx%d=%s" % (s[0], s[1], gate_all[s][0]) for s in SIZES))
print("  合计 %d 次比较（每档 49~50 个样本的完整时刻字典逐格 ==），计时只发生在全部 True 之后。"
      % sum(v[1] for v in gate_all.values()))
sp_big = rate_p[(200, 15)] / rate_f[(200, 15)]
sp_all = [rate_p[s] / rate_f[s] for s in SIZES]
print("  两列计时用同一方法（5 次预热 + 固定时长内重复），差别只有被测函数——加速比的可比性由门保证。")
cov_pct = sum(g1[(200, 15)]["gs"]) / len(g1[(200, 15)]["gs"]) / inst[(200, 15)]["ops"] * 100
cov8 = {s: sum(g1[s]["gs"][:8]) / 8 / inst[s]["ops"] * 100 for s in SIZES}
print("  全场单次 %.2f~%.2fms、闭包单次 %.2f~%.2fms（从 %d 工序到 %d 工序），两列都随工序数近线性——"
      % (min(ms_f.values()), max(ms_f.values()), min(ms_p.values()), max(ms_p.values()),
         inst[SIZES[0]]["ops"], inst[SIZES[-1]]["ops"]))
print("  计时样本（每档 8 个移动）的闭包覆盖率：%s。" % "、".join("%dx%d:%.1f%%" % (s[0], s[1], cov8[s]) for s in SIZES))
print("  加速倍数各档 %s；最大档（200x15）闭包平均覆盖 %.1f%% 的工序。"
      % ("、".join("%.2fx" % v for v in sp_all), cov_pct))
s_lo = min(SIZES, key=lambda s: cov8[s])
s_hi = max(SIZES, key=lambda s: cov8[s])
print("  覆盖最低档 %dx%d（%.1f%%）加速 %.2fx，覆盖最高档 %dx%d（%.1f%%）加速 %.2fx——%s"
      % (s_lo[0], s_lo[1], cov8[s_lo], rate_p[s_lo] / rate_f[s_lo],
         s_hi[0], s_hi[1], cov8[s_hi], rate_p[s_hi] / rate_f[s_hi],
         "低覆盖率不一定换来高加速：位置表与字典拷贝仍是 O(工序数)，量级省不掉"
         if rate_p[s_lo] / rate_f[s_lo] <= rate_p[s_hi] / rate_f[s_hi]
         else "覆盖率越低、加速越猛，方向符合预期"))
print("  加速倍数与闭包覆盖放同一把尺子：覆盖 c% 的「纯比例」预期加速 = 100/c（少碰多少工序，就该少花多少时间），"
      "实测低于预期的那截就是增量实现自身的固定开销。")
gaps = {}
for s in SIZES:
    exp = 100.0 / cov8[s]
    gaps[s] = rate_p[s] / rate_f[s] - exp
    print("    %dx%d  覆盖 %.1f%%  比例预期 %.2fx  实测 %.2fx  差 %+.2fx"
          % (s[0], s[1], cov8[s], exp, rate_p[s] / rate_f[s], gaps[s]))
wg = min(SIZES, key=lambda s: gaps[s])
print("  最不给力的一档是 %dx%d：实测加速 %.2fx，比自己的比例预期低 %.2fx（全档 %.2fx~%.2fx）——"
      % (wg[0], wg[1], rate_p[wg] / rate_f[wg], -gaps[wg], min(sp_all), max(sp_all)))
print("  该档闭包单次 %.2fms，固定开销在这个量级上压不下来：闭包实现自身仍要 O(工序数) 建位置表、"
      % ms_p[wg])
print("  整字典拷贝闭包外时刻——省下的是常数，不是量级。五档里 %d 档低于比例预期；其余 %d 档反而快过比例预期，平均高 %.2fx"
      "（闭包重推连全场字典重建和全图扫描一起省掉了，不只是少碰几道工序）。"
      % (sum(1 for s in SIZES if gaps[s] < 0), sum(1 for s in SIZES if gaps[s] >= 0),
         sum(gaps[s] for s in SIZES if gaps[s] >= 0) / max(1, sum(1 for s in SIZES if gaps[s] >= 0))))
if sp_big < 1.5:
    print("  实话：最大档 %.2fx 的加速不算好看，闭包平均要碰 %.1f%% 的工序，增量与全场的差距天然被封死在一半附近。"
          % (sp_big, cov_pct))
else:
    print("  加速 %.2fx：闭包只碰 %.1f%% 的工序，省下的是一次全场字典重建与全图拓扑推进。" % (sp_big, cov_pct))
print("  但注意上限：加速 %.2fx 意味着一次联动的代价仍有全场的 %.0f%%——「闭包重算」不是免费的魔法，"
      % (sp_big, 100 / sp_big))
print("  只是把同样的活干得更省；[3] 用毫秒判定它到底够不够格做实时联动。")

# ---------------------------------------------------------------- [3] 体感预算
print()
print(W)
print("[3] 拖一下的体感预算：一次鼠标抬起（闭包重算）能不能追上 60fps / 点击 / 1 秒")
print(W)
print("  一次拖拽的前端代价按本档实测「闭包单次」与「全场单次」毫秒计，判定由这两个数算出，不是手写。")
print("  三档预算线：16.7ms = 60fps 一帧（拖拽跟手）、100ms = 点击无感、1000ms = 转圈可接受。")
print("  " + pad("n x m", 10) + pad("闭包ms", 9) + pad("全场ms", 9) + pad("闭包<16ms", 10)
      + pad("闭包<100ms", 10) + pad("闭包<1s", 8) + pad("全场<100ms", 10) + "全场<1s")
verdict = {}
no_cnt = 0
for n, m in SIZES:
    yes_p16 = ms_p[(n, m)] < 16
    yes_p100 = ms_p[(n, m)] < 100
    yes_p1s = ms_p[(n, m)] < 1000
    no_cnt += sum(1 for v in (yes_p16, yes_p100, yes_p1s, ms_f[(n, m)] < 100, ms_f[(n, m)] < 1000) if not v)
    verdict[(n, m)] = (yes_p16, yes_p100, yes_p1s)
    print("  " + pad("%d x %d" % (n, m), 10) + pad("%.2f" % ms_p[(n, m)], 9)
          + pad("%.2f" % ms_f[(n, m)], 9)
          + pad("是" if yes_p16 else "否", 10) + pad("是" if yes_p100 else "否", 10)
          + pad("是" if yes_p1s else "否", 8)
          + pad("是" if ms_f[(n, m)] < 100 else "否", 10)
          + ("是" if ms_f[(n, m)] < 1000 else "否"))
big = SIZES[-1]
print("  判定表共 %d 格，「否」出现 %d 格；最快档 %.2fms、最慢档 %.2fms，工序数差 %.1fx 而耗时差 %.1fx（耗时按表内两位小数值相除）。"
      % (5 * len(SIZES), no_cnt,
         min(ms_p.values()), max(ms_p.values()),
         inst[big]["ops"] / inst[SIZES[0]]["ops"],
         round(max(ms_p.values()), 2) / max(round(min(ms_p.values()), 2), 0.01)))
print("  拖拽流判定（拖动中每秒做 30 次抬起级重算，占用 = 30 x 单次毫秒，跟得上与否由实测次数/秒判）：")
print("  " + pad("n x m", 10) + pad("闭包次/秒", 11) + pad("闭包占用", 10)
      + pad("全场次/秒", 11) + pad("全场占用", 10) + "闭包判定")
for s in SIZES:
    print("  " + pad("%d x %d" % s, 10) + pad("%.0f" % rate_p[s], 11)
          + pad("%.1f%%" % (30 * ms_p[s] / 1000 * 100), 10)
          + pad("%.0f" % rate_f[s], 11) + pad("%.1f%%" % (30 * ms_f[s] / 1000 * 100), 10)
          + ("跟得上" if rate_p[s] >= 30 else "跟不上"))
if verdict[big][2]:
    if verdict[big][0]:
        form = "实时拖拽：最大档闭包重算 %.2fms，一帧 16.7ms 装得下" % ms_p[big]
    elif verdict[big][1]:
        form = "点一下等一下：最大档 %.2fms，拖拽跟手做不到，抬起后 100ms 内给结果可行" % ms_p[big]
    else:
        form = "夜算/批量：最大档闭包重算 %.2fms 已过 1 秒线，同步联动没戏" % ms_p[big]
else:
    form = "夜算/批量：最大档闭包重算 %.2fs，UI 不能同步等" % (ms_p[big] / 1000)
print("  本机判定：%s。" % form)
print("  同档全场重算 %.2fms，判定 %s——增量与否在毫秒量级上没改变结论，改变的是余量（%.1f 倍）。"
      % (ms_f[big], "同样是实时" if ms_f[big] < 16 else "拖不到实时但点击可等" if ms_f[big] < 100 else "点击也要等",
         ms_f[big] / ms_p[big]))
fr_pct = ms_p[big] / 16.7 * 100
print("  余量换成占用率：最大档一次闭包重算吃掉一帧的 %.1f%%；拖动中按每秒 30 次抬起级重算节流，"
      % fr_pct)
print("  CPU 占用 = 30 x %.2fms = %.1f%%（实测吞吐 %d 次/秒，%s 30/秒的要求）；全场重算同样节流则占用 %.1f%%。"
      % (ms_p[big], 30 * ms_p[big] / 1000 * 100,
         rate_p[big], "满足" if rate_p[big] >= 30 else "不满足", 30 * ms_f[big] / 1000 * 100))

# ---------------------------------------------------------------- [4] 长尾
print()
print(W)
print("[4] 闭包是不是长尾：「平均很快」能不能写进产品承诺")
print(W)
n, m = 200, 15
gs, ac = g1[(n, m)]["gs"], g1[(n, m)]["ac"]
D = inst[(n, m)]
print("  200x15（%d 工序，%d 次有效拖拽样本）闭包大小分位数：" % (D["ops"], len(gs)))
print("  样本只有 %d 个：P95/P99 已在第 %.0f~%.0f 个顺序统计量间插值，高分位不稳，尾部判定把 P90 与 max 并着看。"
      % (len(gs), 0.95 * (len(gs) - 1) + 1, 0.99 * (len(gs) - 1) + 1))
print("  " + pad("分位", 10) + "".join(pad(t, 8) for t in ["P50", "P75", "P90", "P95", "P99", "最大"]))
print("  " + pad("图闭包", 10) + "".join(pad("%.0f" % quant(gs, q), 8) for q in [.5, .75, .9, .95, .99, 1.0]))
print("  " + pad("实际变化", 10) + "".join(pad("%.0f" % quant(ac, q), 8) for q in [.5, .75, .9, .95, .99, 1.0]))
ratio = max(gs) / max(median(gs), 1)
ratio_ac = max(ac) / max(median(ac), 1)
mean_med = (sum(gs) / len(gs)) / max(median(gs), 1)
wi = gs.index(max(gs))
kw, aw, rootsw = g1[(n, m)]["samples"][wi]
neww = swap_order(D["order"], kw, aw)
dt_pw, _ = bench(lambda: starts_partial(D["jobs"], D["dur"], neww, D["st"], rootsw)[0], target=0.03, cap=200)
dt_fw, _ = bench(lambda: starts(D["jobs"], D["dur"], neww), target=0.03, cap=200)
print("  最大/中位 = %.2fx（均值/中位 = %.2fx）；P99 %.0f 对 P50 %.0f；实际变化列最大/中位 %.2fx。"
      % (ratio, mean_med, quant(gs, .99), quant(gs, .5), ratio_ac))
print("  最坏一次拖拽：机器 %d 第 %d 格，闭包 %d 工序（占全场 %.1f%%），闭包重算 %.2fms，全场重算 %.2fms。"
      % (kw, aw, max(gs), max(gs) / D["ops"] * 100, dt_pw * 1000, dt_fw * 1000))
print("  最坏一次覆盖全场 %.1f%%，均值覆盖 %.1f%%：增量重算消灭不了「牵一发动全身」，只让它变便宜。"
      % (max(gs) / D["ops"] * 100, cov_pct))
print("  中位口径：实际变化 %.0f 个 vs 图闭包 %.0f 个——用户看到的波及恒不大于重算的波及（闭包是上界）。"
      % (median(ac), median(gs)))
if dt_pw > dt_fw:
    print("  且这最坏一次闭包重算 %.2fms 反而慢于全场 %.2fms：闭包≈全场时，增量实现的建表拷贝开销全暴露——"
          % (dt_pw * 1000, dt_fw * 1000))
    print("  「平均 %.1f 个工序、%.2fms」可以写进监控看板，不能写进产品承诺；"
          % (sum(gs) / len(gs), ms_p[(n, m)]))
    print("  承诺要按分位数写（P90 闭包 %.0f 个），并把最坏 %.2fms 明确留在页面上。"
          % (quant(gs, 0.9), dt_pw * 1000))
else:
    print("  这最坏一次闭包重算 %.2fms 仍快于全场 %.2fms：即便闭包覆盖 %.1f%%，增量实现也没输。"
          % (dt_pw * 1000, dt_fw * 1000, max(gs) / D["ops"] * 100))
    print("  但均值 %.2fms 对最坏 %.2fms 差 %.1f 倍——产品承诺按分位数写，不按均值写。"
          % (ms_p[(n, m)], dt_pw * 1000, dt_pw * 1000 / max(ms_p[(n, m)], 1e-9)))
if ratio >= 2.0:
    print("  按 max/中位 >= 2 的尺子，长尾坐实（%.2fx）：一次拖拽的代价可以从 %.0f 跳到 %.0f 个工序。"
          % (ratio, median(gs), max(gs)))
else:
    print("  按 max/中位 < 2 的尺子，分布不算长尾（%.2fx）：均值 %.1f 有代表性；"
          % (ratio, sum(gs) / len(gs)))
    print("  真正的风险不在倍率而在绝对覆盖——中位数就占全场 %.1f%%，一半的拖拽都要碰上千道工序。"
          % (median(gs) / D["ops"] * 100))

# ---------------------------------------------------------------- [5] 机器维度
print()
print(W)
print("[5] 哪台机器「动不得」：按机器聚合闭包，看锁定关键设备值多少")
print(W)
n, m = 200, 15
D = inst[(n, m)]
jobs, dur, order, st_old = D["jobs"], D["dur"], D["order"], D["st"]
rnd = random.Random(77)
per_mac = defaultdict(list)
ntried = 0
for k in range(m):
    pairs = list(range(len(order[k]) - 1))
    for a in rnd.sample(pairs, min(8, len(pairs))):
        x, y = order[k][a], order[k][a + 1]
        new = swap_order(order, k, a)
        if starts(jobs, dur, new) is None:
            continue
        C = forward_closure(succ_map(jobs, new), {x, y})
        per_mac[k].append(len(C))
        ntried += 1
avg = {k: sum(v) / len(v) for k, v in per_mac.items() if v}
best_k = max(avg, key=lambda k: avg[k])
worst_k = min(avg, key=lambda k: avg[k])
allg = [g for v in per_mac.values() for g in v]
mean_all = sum(allg) / len(allg)
mean_excl = sum([g for k, v in per_mac.items() if k != best_k for g in v]) / max(1, len(allg) - len(per_mac[best_k]))
print("  每台机器随机 %d 个相邻交换位，图上闭包均值（按机器）：" % 8)
print("  口径：本节按机器分层采样（保证每台都有样本，共 %d 次有效移动），与 [1] 的全局随机样本相互独立。" % ntried)
print("  " + pad("机器", 7) + pad("闭包均值", 10) + pad("闭包最大", 9) + pad("占全场", 8) + "标记")
for k in sorted(avg, key=lambda x: -avg[x]):
    tag = "动不得" if k == best_k else ("最皮实" if k == worst_k else "")
    print("  " + pad(k, 7) + pad("%.1f" % avg[k], 10) + pad(max(per_mac[k]), 9)
          + pad("%.1f%%" % (avg[k] / D["ops"] * 100), 8) + tag)
print("  口径：机器号从 0 起；「动不得」按图上闭包均值取最大台，「最皮实」同口径取最小台。")
print("  全场平均闭包 %.1f 个工序；禁止拖动机器 %d 后降到 %.1f 个，少 %.1f%%。"
      % (mean_all, best_k, mean_excl, (mean_all - mean_excl) / mean_all * 100))
drop_pct = (mean_all - mean_excl) / mean_all * 100
cheapest3 = sorted(avg, key=lambda k: avg[k])[:3]
mean_c3 = sum([g for k, v in per_mac.items() if k not in cheapest3 for g in v]) / \
          max(1, len(allg) - sum(len(per_mac[k]) for k in cheapest3))
print("  若锁掉波及最小的 %d 台（%s），全场平均闭包反而升到 %.1f（%.1f%%）——能拖的只剩高波及机器。"
      % (len(cheapest3), "、".join(str(k) for k in cheapest3), mean_c3,
         (mean_c3 - mean_all) / mean_all * 100))
load = {k: sum(dur[op] for op in order[k]) for k in range(m)}
load_rank = sorted(range(m), key=lambda k: -load[k]).index(best_k) + 1
print("  「动不得」机器 %d：总负荷 %d（15 台里第 %d 重）；波及最皮实机器 %d 总负荷 %d。"
      % (best_k, load[best_k], load_rank, worst_k, load[worst_k]))
if load_rank <= m // 2:
    print("  负荷与波及方向一致：动不得机器 %d 负荷排第 %d 重、落在前一半——按负荷选「关键设备」能命中它。"
          % (best_k, load_rank))
else:
    print("  负荷与波及方向不一致：动不得机器 %d 负荷只排第 %d 重——按负荷锁定关键设备会选错机器。"
          % (best_k, load_rank))
if drop_pct >= 10:
    print("  锁一台机器就能把平均波及面砍 %.1f%%——工作台上的「锁定关键设备」按钮值得做。" % drop_pct)
else:
    print("  锁一台只省 %.1f%%：波及面不是单台机器决定的，「锁定关键设备」按钮优先级可以放低，" % drop_pct)
    print("  （各机器闭包均值 %.1f~%.1f，同为一次拖拽代价却差 %.1fx——真正的旋钮在闭包重算本身，见 [2]）。"
          % (min(avg.values()), max(avg.values()), max(avg.values()) / max(min(avg.values()), 1)))

# ---------------------------------------------------------------- [6] 一览
print()
print(W)
print("[6] 本机实测一览（全部复述 [0]~[5] 测到的数）")
print(W)
for s in SIZES:
    D = inst[s]
    gmed = median(g1[s]["gs"])
    print("  %-8s %4d 工序：闭包中位 %.0f（%.1f%% 全场），全场重算 %.0f 次/秒，闭包重算 %.0f 次/秒（%.2fx），"
          % ("%dx%d" % s, D["ops"], gmed, gmed / D["ops"] * 100, rate_f[s], rate_p[s], rate_p[s] / rate_f[s])
          + "拖拽跟手 " + ("是" if verdict[s][0] else "否"))
print("  正确性门：闭包重算 == 全场重算，%d 次逐格比较全部相同（%s）。"
      % (sum(v[1] for v in gate_all.values()),
         "、".join("%s" % v[0] for v in gate_all.values())))
print("  实际变化占比（[1]）：%s——图上闭包是其上界，增量按上界重算才逐格正确。"
      % "、".join("%dx%d:%.1f%%" % (s[0], s[1], p) for s, p in zip(SIZES, apcts)))
print("  闭包占比（[1]）：%s——增量评估的天花板就压在这一列上。"
      % "、".join("%dx%d:%.1f%%" % (s[0], s[1], p) for s, p in zip(SIZES, pcts)))
print("  最坏一次拖拽（[4]）：闭包 %d 工序（覆盖 %.1f%%）、%.2fms；机器维度（[5]）：锁定机器 %d 只使平均闭包降 %.1f%%。"
      % (max(gs), max(gs) / D["ops"] * 100, dt_pw * 1000, best_k, drop_pct))
print("  拖拽流换算（[3]）：最大档闭包重算实测 %d 次/秒，%s每秒 30 次抬起级重算的要求。"
      % (rate_p[big], "满足" if rate_p[big] >= 30 else "不满足"))
print("  产品形态判定（[3]，按本机 %dx%d 实测 %.2fms）：%s" % (big[0], big[1], ms_p[big], form.split("：")[0]))
print("  时间是本机 wall-clock：本次全程 %s，毫秒与次数列换机器会变；[0][1][4][5] 的闭包计数、占比与验证结果由固定种子生成，换机器一个数字都不动。"
      % human_time(time.perf_counter() - T0))
