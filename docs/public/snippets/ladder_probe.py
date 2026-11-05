# -*- coding: utf-8 -*-
"""求解器阶梯用同一种货币定价：在随机作业车间算例上，把六档求解器（先到先得/SPT、
主动调度、爬山+相邻交换、爬山+交换+插入、带随机重启、破坏-修复大邻域）放到同一把
尺子——「评估次数」——下逐档定价，量每一档到底买到多少边际改进。

用法:  python ladder_probe.py   （纯标准库，无第三方依赖）

  [1] 同一预算阶梯：60x8 上六档 x 四档评估预算，makespan、实际评估消耗、逐档边际改进与每次改进单价
  [2] 谁先撞墙：预算锁死换四个规模，看便宜档在哪一档规模上互相收敛、哪档烧满预算零改进
  [3] 邻域经济学：邻居数 x 每轮扫描代价 x 单位预算净改进，相邻交换 / 交换+插入 / 破坏重建按数据选赢家
  [4] 重启值不值：1/3/10 个起点分同一块总预算，切分在哪儿反而比一次长跑亏
  [5] 精确档能走多远：3x3/4x3/3x4 全枚举复核最优，5x3 实测验证外推，再把 6x3~10x3 折算成年
  [6] 可复现性自检：评估次数预算跑两次逐格比对，墙钟预算跑三次数评估次数
  [7] 一览：只复述上面算出来的数

除标注「本机吞吐 / 耗时 / 墙钟」的行外，全部输出只依赖种子，重跑逐字节相同。
"""
import itertools
import math
import random
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")   # Windows GBK 控制台：编不出变问号，别崩

W = "=" * 74
NL = 0


def p(*a):
    global NL
    if not a:
        print()
    else:
        print(*[s.rstrip() if isinstance(s, str) else s for s in a])
    NL += 1


def dw(s):
    return sum(2 if ord(c) > 0x2E80 else 1 for c in str(s))


def pad(s, n):
    s = str(s)
    return s + " " * max(0, n - dw(s))


def sci(x):
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
        return "%.0f 分钟" % (secs // 60)
    if secs < 86400:
        return "%.1f 小时" % (secs / 3600)
    if secs < 3.15e7:
        return "%.1f 天" % (secs / 86400)
    return sci(secs / 3.15e7) + " 年"


# T6 破坏-修复的调参常量（页面上出现的 8 与 3 就是这两个值）
KDESTROY = 8            # 每轮摘掉的工序数
NPOS_SHALLOW = 3        # 浅重插每个工序试的位置数（头/中/尾）


# ---------------------------------------------------------------- JSP 内核（数组版）
def build_ctx(jobs):
    """n 工件 x m 机器、每工件走完全部机器。工序编号 oid = i*m + o。"""
    n = len(jobs)
    m = len(jobs[0])
    mach = [0] * (n * m)
    dur = [0] * (n * m)
    for i, j in enumerate(jobs):
        assert len(j) == m
        for o, (k, p_) in enumerate(j):
            mach[i * m + o] = k
            dur[i * m + o] = p_
    indeg_base = [1 if o > 0 else 0 for i in range(n) for o in range(m)]
    return {"n": n, "m": m, "mach": mach, "dur": dur, "indeg_base": indeg_base}


def sched(ctx, order):
    """给定每台机器的加工顺序 -> 半激活最早开工 makespan；有环返回 None。
       一次「评估」= 此函数跑一遍。六档阶梯全部用它计价，与机器快慢无关。"""
    dur, m = ctx["dur"], ctx["m"]
    N = ctx["n"] * m
    mnext = [-1] * N
    indeg = ctx["indeg_base"].copy()
    for seq in order:
        prev = -1
        for a in seq:
            if prev >= 0:
                mnext[prev] = a
                indeg[a] += 1
            prev = a
    st = [0] * N
    q = [oid for oid in range(N) if indeg[oid] == 0]
    head, done = 0, 0
    while head < len(q):
        u = q[head]
        head += 1
        done += 1
        e = st[u] + dur[u]
        v = u + 1
        if v % m != 0:                        # 工艺弧：同工件下一道工序
            if st[v] < e:
                st[v] = e
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
        w = mnext[u]                          # 机器弧：同机下一个工序
        if w >= 0:
            if st[w] < e:
                st[w] = e
            indeg[w] -= 1
            if indeg[w] == 0:
                q.append(w)
    if done < N:
        return None
    return max(st[i * m + m - 1] + dur[i * m + m - 1] for i in range(ctx["n"]))


class Eval:
    """共享评估器：预算 = 评估次数上限，不是秒表。六档全用同一个类、同一个 sched()。"""

    def __init__(self, ctx):
        self.ctx, self.n = ctx, 0

    def __call__(self, order):
        self.n += 1
        return sched(self.ctx, order)

    def out(self, budget):
        return self.n >= budget


def dispatch(ctx, key, rnd=None):
    """派工规则生成机器顺序：每步在「各工件当前可派工序」里按 key 挑最小的，同分用 rnd 挑。"""
    n, m = ctx["n"], ctx["m"]
    mach, dur = ctx["mach"], ctx["dur"]
    ptr = [0] * n
    mfree = [0] * m
    jfree = [0] * n
    order = [[] for _ in range(m)]
    done = 0
    while done < n * m:
        cand = []
        for i in range(n):
            if ptr[i] < m:
                oid = i * m + ptr[i]
                k = mach[oid]
                cand.append((jfree[i] if jfree[i] > mfree[k] else mfree[k], dur[oid], i, k))
        keys = [key(*c) for c in cand]
        best = min(keys)
        tie = [c for c, kk in zip(cand, keys) if kk == best]
        s, pu, i, k = tie[0] if rnd is None else rnd.choice(tie)
        ptr[i] += 1
        jfree[i] = mfree[k] = s + pu
        order[k].append(i * m + ptr[i] - 1)
        done += 1
    return order


def trivial_lb(ctx):
    n, m, mach, dur = ctx["n"], ctx["m"], ctx["mach"], ctx["dur"]
    load = [0] * m
    for oid in range(n * m):
        load[mach[oid]] += dur[oid]
    return max([sum(dur[i * m:(i + 1) * m]) for i in range(n)] + load)


def gen(n, m, seed, lo=1, hi=9):
    r = random.Random(seed)
    out = []
    for _ in range(n):
        route = list(range(m))
        r.shuffle(route)
        out.append([(k, r.randint(lo, hi)) for k in route])
    return out


KEY_SPT = lambda s, pu, i, k: (pu, i, k)              # T1 先到先得/SPT：最短工序先派
KEY_ACT = lambda s, pu, i, k: (s, pu, i, k)           # T2 主动调度：先能开工的先派


def first_improve(ctx, ev, budget, order, cur, moves, acc):
    """首改进爬山：从头扫邻域，见到第一个变好的就走一步，再从头扫；扫干净 = 收敛。
       moves=1 只相邻交换；moves=2 再加「把工序往本机更靠后的位置插」。"""
    while not ev.out(budget):
        moved = False
        for k in range(ctx["m"]):
            seq = order[k]
            L = len(seq)
            for a in range(L - 1):
                for b in ([a + 1] if moves == 1 else range(a + 1, L)):
                    if ev.out(budget):
                        return cur, False
                    x = seq.pop(a)
                    seq.insert(b, x)
                    v = ev(order)
                    if v is not None and v < cur:
                        cur = v
                        acc[0] += 1
                        moved = True
                        break
                    seq.pop(b)
                    seq.insert(a, x)
                if moved:
                    break
            if moved:
                break
        if not moved:
            return cur, True
    return cur, False


def climb_tier(ctx, budget, order, moves):
    """T3/T4：从给定起点爬山。返回 (makespan, 实际评估, 改进次数, 是否收敛)。"""
    ev = Eval(ctx)
    cur = ev(order)
    acc = [0]
    cur, conv = first_improve(ctx, ev, budget, order, cur, moves, acc)
    assert cur is not None and ev.n <= budget
    return cur, ev.n, acc[0], conv


def restart_tier(ctx, budget, base_order, base_val, rnd, slice_b=3000, stagn_limit=4):
    """T5：多起点 + 保留最优。起点 = 随机优先派工（起点真的各不相同），每个起点最多烧
       slice_b 次评估；连续 stagn_limit 个起点没刷新全局最优就收摊。"""
    ev = Eval(ctx)
    best, best_order = base_val, [list(s) for s in base_order]
    starts = stagn = acc0 = 0
    while not ev.out(budget) and stagn < stagn_limit:
        starts += 1
        o = dispatch(ctx, lambda s, pu, i, k: (rnd.random(), i), rnd)
        cur = ev(o)
        slice_end = budget if ev.n + slice_b > budget else ev.n + slice_b
        acc = [0]
        cur, conv = first_improve(ctx, ev, slice_end, o, cur, 2, acc)
        assert cur is not None
        acc0 += acc[0]
        if cur < best:
            best, stagn, best_order = cur, 0, [list(s) for s in o]
        else:
            stagn += 1
    assert ev.n <= budget
    return best, best_order, ev.n, starts, acc0, ev.n < budget


def destroy_tier(ctx, budget, base_order, base_val, rnd, k=KDESTROY, stagn_limit=6, deep=False):
    """T6：破坏-修复（ALNS 味的一步）。随机摘掉 k 个工序，按随机顺序逐个贪心插回其机器
       上的位置（deep=试全部位置；浅=只试头/中/尾 3 个），补一小段爬山，只接受变好。"""
    N = ctx["n"] * ctx["m"]
    mach = ctx["mach"]
    ev = Eval(ctx)
    best, best_order = base_val, [list(s) for s in base_order]
    rounds = stagn = acc0 = 0
    while not ev.out(budget) and stagn < stagn_limit:
        rounds += 1
        o = [list(s) for s in best_order]
        removed = rnd.sample(range(N), k)
        for oid in removed:
            o[mach[oid]].remove(oid)
        dead = False
        for oid in rnd.sample(removed, k):
            seq = o[mach[oid]]
            L = len(seq)
            cand = range(L + 1) if deep else [0, L // 2, L][:NPOS_SHALLOW]
            bv = bp = None
            for pos in cand:
                if ev.out(budget):
                    dead = True
                    break
                seq.insert(pos, oid)
                v = ev(o)
                seq.pop(pos)
                if v is not None and (bv is None or v < bv):
                    bv, bp = v, pos
            if dead:
                break
            if bp is None:
                bp = min(len(seq), 1)
            seq.insert(bp, oid)
        if dead:
            break
        cur = ev(o)
        if cur is None:
            stagn += 1
            continue
        acc = [0]
        cur, conv = first_improve(ctx, ev, budget, o, cur, 2 if deep else 1, acc)
        acc0 += acc[0]
        if cur < best:
            best, stagn, best_order = cur, 0, [list(s) for s in o]
        else:
            stagn += 1
    assert ev.n <= budget
    return best, best_order, ev.n, rounds, acc0, ev.n < budget


def nbr_count(order, moves):
    c = 0
    for seq in order:
        L = len(seq)
        c += L - 1
        if moves >= 2:
            c += L * (L - 1) // 2 - (L - 1)
    return c


SEED = 2026
BUDGETS = [500, 2000, 10000, 50000]
TNAME = ["T1 SPT派工", "T2 主动调度", "T3 交换爬山", "T4 +插入", "T5 +重启", "T6 +破坏"]
COLW = 10

# ================================================================ [1] 同一预算阶梯
INST1 = gen(60, 8, SEED)
CTX1 = build_ctx(INST1)
LB1 = trivial_lb(CTX1)
NOPS1 = CTX1["n"] * CTX1["m"]

t0 = time.perf_counter()
_probe = Eval(CTX1)
_act0 = dispatch(CTX1, KEY_ACT, random.Random(7))
while time.perf_counter() - t0 < 0.12:
    _probe(_act0)
THR1 = _probe.n / (time.perf_counter() - t0)          # 本机吞吐，只上这一行


def ladder_run(budget):
    ev1 = Eval(CTX1)
    v1 = ev1(dispatch(CTX1, KEY_SPT, random.Random(7)))
    ev2 = Eval(CTX1)
    o2 = dispatch(CTX1, KEY_ACT, random.Random(7))
    v2 = ev2(o2)
    assert v1 >= LB1 and v2 >= LB1 and v2 <= v1
    r3 = climb_tier(CTX1, budget, [list(s) for s in o2], 1)
    r4 = climb_tier(CTX1, budget, [list(s) for s in o2], 2)
    r5 = restart_tier(CTX1, budget, o2, v2, random.Random(501))
    r6 = destroy_tier(CTX1, budget, o2, v2, random.Random(502))
    # 每档：(makespan, 实际评估, 相对上一档改进, 改进次数, 备注)
    return [(v1, 1, None, 0, "派工"),
            (v2, 1, v1 - v2, 0, "派工"),
            (r3[0], r3[1], v2 - r3[0], r3[2], "收敛" if r3[3] else "烧满"),
            (r4[0], r4[1], r3[0] - r4[0], r4[2], "收敛" if r4[3] else "烧满"),
            (r5[0], r5[2], r4[0] - r5[0], r5[4], "%d起点%s" % (r5[3], "收摊" if r5[5] else "烧满")),
            (r6[0], r6[2], r5[0] - r6[0], r6[4], "%d轮%s" % (r6[3], "收摊" if r6[5] else "烧满"))]


LAD = {E: ladder_run(E) for E in BUDGETS}
for E in BUDGETS:
    assert all(x[1] <= E for x in LAD[E])
    assert all(x[0] >= LB1 for x in LAD[E])

p(W)
p("[1] 同一预算阶梯：六档求解器放在同一把尺（评估次数）上定价")
p(W)
p("  算例：60 工件 x 8 机器 = %d 工序（seed=%d），平凡下界 LB=%d。货币 = 评估次数，不是秒。" % (NOPS1, SEED, LB1))
p("  T1/T2 各花 1 次评估（派工本身不评估，评估才计价）；T3~T6 上限 E，收敛/收摊即停，不烧满预算。")
p("  1 次评估 = %d 个工序的拓扑推进；本机实测 %s 评估/秒（本行随机器负载漂），满额 50,000 次约 %.0f 秒。"
  % (NOPS1, "{:,.0f}".format(THR1), 50000 / THR1))
p("  " + pad("预算E", 9) + "".join(pad(t.split()[0], COLW) for t in TNAME) + pad("烧满档数", 10) + "同值尾段")
for E in BUDGETS:
    burn = sum(1 for t in (2, 3, 4, 5) if LAD[E][t][1] >= E)
    run = 1
    for t in range(4, 1, -1):
        if LAD[E][t][0] == LAD[E][5][0]:
            run += 1
        else:
            break
    p("  " + pad("{:,}".format(E), 9) + "".join(pad(LAD[E][t][0], COLW) for t in range(6))
      + pad("%d/4" % burn, 10) + ("T%d~T6 同值" % (7 - run) if run >= 2 else "尾段仍分胜负"))
p("  " + pad("预算E", 9) + pad("T3用", COLW + 4) + pad("T4用", COLW + 4) + pad("T5用", COLW + 4)
  + pad("T6用", COLW + 4) + "实际评估次数与预算占用")
for E in BUDGETS:
    p("  " + pad("{:,}".format(E), 9) + "".join(pad("{:,}".format(LAD[E][t][1]), COLW + 4) for t in range(2, 6))
      + "占用 %s" % " / ".join("%.0f%%" % (LAD[E][2 + t][1] / E * 100) for t in range(4)))
p("  " + pad("预算E", 9) + pad("T2-T1", COLW + 2) + pad("T3-T2", COLW + 2) + pad("T4-T3", COLW + 2)
  + pad("T5-T4", COLW + 2) + pad("T6-T5", COLW + 2) + "边际改进（正=买到，0=白买，负=倒贴）")
for E in BUDGETS:
    p("  " + pad("{:,}".format(E), 9) + pad("%+d" % LAD[E][1][2], COLW + 2)
      + "".join(pad("%+d" % LAD[E][t][2], COLW + 2) for t in range(2, 6))
      + "T6 超下界 %+.1f%%" % ((LAD[E][5][0] - LB1) / LB1 * 100))
p("  " + pad("预算E", 9) + pad("T3 单价", 10) + pad("T4 单价", 10) + pad("T5 单价", 10)
  + pad("T6 单价", 10) + "每次改进单价=评估/接受步数；「无改进」=没有步可摊；行尾=四档收摊状态")
for E in BUDGETS:
    cells = ""
    for t in range(2, 6):
        v, ne, d, ac, note = LAD[E][t]
        cells += pad("无改进" if ac == 0 else "{:,.0f}".format(ne / ac), 10)
    p("  " + pad("{:,}".format(E), 9) + cells + " / ".join(LAD[E][t][4] for t in range(2, 6)))
z500 = [TNAME[t] for t in range(2, 6) if LAD[500][t][2] == 0]
z50k = [TNAME[t] for t in range(2, 6) if LAD[50000][t][2] == 0]
p("  预算 500 时白买的档：%s。预算 50,000 时白买的档：%s。"
  % ("、".join(z500) if z500 else "无", "、".join(z50k) if z50k else "无"))
neg = [(E, t) for E in BUDGETS for t in range(2, 6) if LAD[E][t][2] < 0]
if neg:
    p("  出现倒贴（本档比上一档更差）：%s——同一预算下多起点把长爬坡切碎了，档位高不等于解好。"
      % "、".join("E=%s %s %+d" % ("{:,}".format(E), TNAME[t], LAD[E][t][2]) for E, t in neg))
else:
    p("  没有出现倒贴：每一档都不差于上一档；但「不差于」不等于「买到了」——看上面一堆 0 的格。")
p("  50,000 预算处 T5 实际烧 %s 次（占 %.0f%%）后收摊，还停在 %d；T4 用 %s 次摸到 %d：贵的档不等于好的档。"
  % ("{:,}".format(LAD[50000][4][1]), LAD[50000][4][1] / 50000 * 100, LAD[50000][4][0],
     "{:,}".format(LAD[50000][3][1]), LAD[50000][3][0]))

# ================================================================ [2] 谁先撞墙
E2 = 1500
SIZES = [(20, 4), (40, 6), (60, 8), (100, 10)]
LAD2 = {}
for (n, m) in SIZES:
    ctx = build_ctx(gen(n, m, 99))
    lb = trivial_lb(ctx)
    v1 = Eval(ctx)(dispatch(ctx, KEY_SPT, random.Random(7)))
    ev2 = Eval(ctx)
    o2 = dispatch(ctx, KEY_ACT, random.Random(7))
    v2 = ev2(o2)
    r3 = climb_tier(ctx, E2, [list(s) for s in o2], 1)
    r4 = climb_tier(ctx, E2, [list(s) for s in o2], 2)
    r5 = restart_tier(ctx, E2, o2, v2, random.Random(501))
    r6 = destroy_tier(ctx, E2, o2, v2, random.Random(502))
    LAD2[(n, m)] = (lb, [v1, v2, r3[0], r4[0], r5[0], r6[0]],
                    [(r3[1], r3[2]), (r4[1], r4[2]), (r5[2], r5[4]), (r6[2], r6[4])])

p()
p(W)
p("[2] 谁先撞墙：预算锁死 %s 次评估，换算例规模" % "{:,}".format(E2))
p(W)
p("  评估次数这把尺与机器快慢无关：四个规模拿到的次数一样，差别全在每次评估摊多少工序。")
p("  " + pad("规模", 10) + pad("LB", 6) + "".join(pad(t.split()[0], COLW) for t in TNAME) + pad("T1/T6 超下界", 14) + "同值尾段")
conv_from = None
for (n, m) in SIZES:
    lb, vs, _ = LAD2[(n, m)]
    first = None
    for t in range(2, 5):
        if all(vs[u] == vs[t] for u in range(t, 6)):
            first = t
            break
    if first is not None and conv_from is None and first <= 3:
        conv_from = (n, m, first)
    p("  " + pad("%d x %d" % (n, m), 10) + pad(lb, 6) + "".join(pad(v, COLW) for v in vs)
      + pad("+%.0f%%/%+.0f%%" % ((vs[0] - lb) / lb * 100, (vs[5] - lb) / lb * 100), 14)
      + ("T%d~T6 同值" % (first + 1) if first is not None else "尾段仍分胜负"))
p("  " + pad("规模", 10) + pad("T3 用/改进", 15) + pad("T4 用/改进", 15) + pad("T5 用/改进", 15)
  + "T6 用/改进（预算都是 %s 次）" % "{:,}".format(E2))
for (n, m) in SIZES:
    _, _, cons = LAD2[(n, m)]
    p("  " + pad("%d x %d" % (n, m), 10) + "".join(pad("%s / %+d" % ("{:,}".format(ne), ac), 15) for ne, ac in cons))
p("  注：/后是爬山接受步数——随机重启的爬坡步未必净赚过 T2 基线，净收益看上面那张表各档差值。")
burn0 = [(n, m, ["T3", "T4", "T5", "T6"][i]) for (n, m) in SIZES
         for i, (ne, ac) in enumerate(LAD2[(n, m)][2]) if ne >= E2 and ac == 0]
if burn0:
    p("  烧满预算却 0 改进的档：%s——评估次数花完，解一步没动，这就是撞墙的形状。"
      % "、".join("%dx%d %s" % b for b in burn0))
rev = [(n, m, t, LAD2[(n, m)][1][t + 1] - LAD2[(n, m)][1][t]) for (n, m) in SIZES for t in range(2, 5)
       if LAD2[(n, m)][1][t + 1] > LAD2[(n, m)][1][t]]
if rev:
    p("  倒挂（后一档反而比前一档差）共 %d 处——小预算下贵档把爬坡切碎，阶梯不单调：" % len(rev))
    for (n, m, t, d) in rev:
        p("    %d x %d：T%d %d -> T%d %d（反而差 %d）"
          % (n, m, t + 1, LAD2[(n, m)][1][t], t + 2, LAD2[(n, m)][1][t + 1], d))
cheap_win = [(n, m, LAD2[(n, m)][1][5] - LAD2[(n, m)][1][2]) for (n, m) in SIZES
             if LAD2[(n, m)][1][2] < LAD2[(n, m)][1][5]]
if cheap_win:
    p("  最便宜档反而赢的规模：%s——在这些格上，「升级算法」的正确答案是把钱花回评估次数本身。"
      % "、".join("%d x %d（T3 比 T6 好 %d）" % (n, m, d) for (n, m, d) in cheap_win))
if conv_from:
    n0, m0, t0_ = conv_from
    p("  便宜档互相收敛的最小规模：%d x %d——从 T%d 起 %d 档同值（%d）：再往下争论贵算法没有意义，"
      % (n0, m0, t0_ + 1, 6 - t0_, LAD2[(n0, m0)][1][t0_]))
    p("  先撞的墙是本规模的局部最优，不是算法选型。")
else:
    p("  四个规模上四档都没有完全同值：即便 20x4，贵档在 %s 次评估内还在买到东西。" % "{:,}".format(E2))
gap_tie = sum(1 for (n, m) in SIZES if LAD2[(n, m)][1][5] == LAD2[(n, m)][1][2])
gap_worse = max(((n, m, LAD2[(n, m)][1][5] - LAD2[(n, m)][1][2]) for (n, m) in SIZES), key=lambda g: g[2])
if gap_worse[2] > 0:
    p("  最贵档 vs 最省档：%d 个规模上 T6=T3、其余 T6 更差，最大倒差在 %d x %d（T3 %d vs T6 %d，贵 %d）——"
      % (gap_tie, gap_worse[0], gap_worse[1], LAD2[(gap_worse[0], gap_worse[1])][1][2],
         LAD2[(gap_worse[0], gap_worse[1])][1][5], gap_worse[2]))
    p("  在 %s 次评估这一档预算上，大邻域没买到任何东西，只买到更多评估。" % "{:,}".format(E2))
elif gap_tie == len(SIZES):
    p("  四个规模上 T6 与 T3 全部同值：%s 次评估的预算买不出大邻域的差价，它只配在更高预算处答辩。" % "{:,}".format(E2))
else:
    p("  各规模上 T6 都不比 T3 差，但也没买到更多（最大差 %d）：这一档预算下大邻域纯属陪标。" % gap_worse[2])

# ================================================================ [3] 邻域经济学
E3 = [500, 2000, 10000]
NB = [("相邻交换", 1), ("交换+插入", 2), ("破坏重建(浅)", 0), ("破坏重建(全位)", 3)]
ev2x = Eval(CTX1)
o2x = dispatch(CTX1, KEY_ACT, random.Random(7))
v2x = ev2x(o2x)
NBRES = {}
for label, mv in NB:
    row = []
    for E in E3:
        if mv in (1, 2):
            r = climb_tier(CTX1, E, [list(s) for s in o2x], mv)
            row.append((r[0], r[1], r[2]))
        elif mv == 0:
            r = destroy_tier(CTX1, E, o2x, v2x, random.Random(601), deep=False)
            row.append((r[0], r[2], r[4]))
        else:
            r = destroy_tier(CTX1, E, o2x, v2x, random.Random(602), deep=True)
            row.append((r[0], r[2], r[4]))
    NBRES[label] = row
SWAP_N = nbr_count(o2x, 1)
INS_N = nbr_count(o2x, 2)

p()
p(W)
p("[3] 邻域经济学：邻居数 x 每轮扫描代价 x 单位预算净改进")
p(W)
p("  还是 60x8（LB=%d，T2 起点 %d）。相邻交换一轮 %d 个邻居；加插入变 %s 个（x%.1f）——不是更多选择，是更贵的扫描。"
  % (LB1, v2x, SWAP_N, "{:,}".format(INS_N), INS_N / SWAP_N))
p("  扫完一轮的标价就是邻居数：交换 %d 次评估、交换+插入 %s 次（贵 %.1f 倍）；破坏重建一轮重插评估：浅 %dx%d=%d 次、全位约 %dx%d=%d 次（每机 %d 个工序 + 1 个插入位），后面再接一小段爬山。"
  % (SWAP_N, "{:,}".format(INS_N), INS_N / SWAP_N,
     KDESTROY, NPOS_SHALLOW, KDESTROY * NPOS_SHALLOW,
     KDESTROY, NOPS1 // CTX1["m"] + 1, KDESTROY * (NOPS1 // CTX1["m"] + 1), NOPS1 // CTX1["m"]))
unscan = [E for E in E3 if INS_N > E]
if len(unscan) == len(E3):
    acc_t4 = NBRES["交换+插入"][2][2]
    p("  %s 三档预算都给不起插入邻域的完整一轮（%s > %s）：T4 的改进全是扫描半路撞上的（最大预算处接受 %d 步），不是扫出来的。"
      % ("/".join("{:,}".format(E) for E in E3), "{:,}".format(INS_N), "{:,}".format(max(E3)), acc_t4))
p("  " + pad("邻域", 15) + pad("接受步数峰值", 14) + "".join(pad("E=%s" % "{:,}".format(E), 16) for E in E3))
for label, mv in NB:
    row = NBRES[label]
    p("  " + pad(label, 15) + pad(max(r[2] for r in row), 14)
      + "".join(pad("%d（%s）" % (r[0], "{:,}".format(r[1])), 16) for r in row))
for i, E in enumerate(E3):
    bv = min(NBRES[label][i][0] for label, _ in NB)
    ws = [label for label, _ in NB if NBRES[label][i][0] == bv]
    cheap = min(ws, key=lambda lb_2: NBRES[lb_2][i][1])
    p("  E=%-6s 赢家：%s（makespan=%d；评估最省的 %s 用 %s 次）"
      % ("{:,}".format(E), "、".join(ws), bv, cheap, "{:,}".format(NBRES[cheap][i][1])))
dd = NBRES["破坏重建(全位)"][2][0] - NBRES["破坏重建(浅)"][2][0]
ee = NBRES["破坏重建(全位)"][2][1] - NBRES["破坏重建(浅)"][2][1]
if dd < 0:
    p("  全位重插比浅重插多烧 %s 评估换来 %+d（接受步数 %d -> %d）：贵邻域只在爬不动的时候才值。"
      % ("{:,}".format(ee), dd, NBRES["破坏重建(浅)"][2][2], NBRES["破坏重建(全位)"][2][2]))
elif dd == 0:
    p("  全位重插比浅重插多烧 %s 评估，makespan 一分没变（都停在 %d；接受步数 %d vs %d）——"
      % ("{:,}".format(ee), NBRES["破坏重建(浅)"][2][0], NBRES["破坏重建(浅)"][2][2], NBRES["破坏重建(全位)"][2][2]))
    p("  在这里，把每个工序试遍全部位置只是买了更多次评估，没买到解。")
else:
    p("  全位重插比浅重插多烧 %s 评估还多差 %d（接受步数 %d vs %d）：贵邻域在这一档预算下是负资产。"
      % ("{:,}".format(ee), dd, NBRES["破坏重建(浅)"][2][2], NBRES["破坏重建(全位)"][2][2]))
tie_all = all(len([l for l, _ in NB if NBRES[l][i][0] == min(NBRES[q][i][0] for q, _ in NB)]) == 4 for i in range(2))
if tie_all:
    p("  注意 E<=2,000 时四种邻域全部交不出改进：输赢要到 E=10,000 才开始分家——预算不够时，邻域选型是空谈。")

# ================================================================ [4] 重启值不值
E4 = 6000
RS = [1, 3, 10]
R4 = {}
for (n, m) in [(40, 6), (60, 8)]:
    ctx = build_ctx(gen(n, m, 99))
    lb = trivial_lb(ctx)
    row = []
    for r in RS:
        if r == 1:
            t = climb_tier(ctx, E4, [list(s) for s in dispatch(ctx, KEY_ACT, random.Random(7))], 2)
            row.append((t[0], t[1]))
        else:
            rnd = random.Random(700 + r)
            ev2 = Eval(ctx)
            o_act2 = [list(s) for s in dispatch(ctx, KEY_ACT, random.Random(7))]
            cur = ev2(o_act2)
            cur, conv = first_improve(ctx, ev2, min(E4, ev2.n + E4 // r), o_act2, cur, 2, [0])
            best = cur
            for _ in range(r - 1):
                if ev2.out(E4):
                    break
                oo = dispatch(ctx, lambda s, pu, i, k: (rnd.random(), i), rnd)
                cur = ev2(oo)
                slice_end = min(E4, ev2.n + E4 // r)
                cur, conv = first_improve(ctx, ev2, slice_end, oo, cur, 2, [0])
                if cur < best:
                    best = cur
            assert ev2.n <= E4
            row.append((best, ev2.n))
    R4[(n, m)] = (lb, row)

p()
p(W)
p("[4] 重启值不值：总预算 %s 次评估切成 1/3/10 个起点" % "{:,}".format(E4))
p(W)
p("  重启不是免费午餐：每个起点要先付一次全场评估 + 一段爬山，起点越多、每段越短（r=10 时每段只有 %d 次）。" % (E4 // 10))
p("  " + pad("规模", 10) + pad("LB", 6) + "".join(pad("r=%d 起点" % r, 18) for r in RS) + "切分盈亏")
for (n, m) in [(40, 6), (60, 8)]:
    lb, row = R4[(n, m)]
    bv = min(v for v, _ in row)
    ib = [i for i, x in enumerate(row) if x[0] == bv][0]
    cells = "".join(pad("%d（%s）" % (v, "{:,}".format(ne)), 18) for v, ne in row)
    if ib == 0:
        others = [v for v, _ in row[1:]]
        if min(others) == row[0][0]:
            vtxt = "一次长跑已是最优（最好切分并列于 %d）" % row[0][0]
        else:
            vtxt = "一次长跑最优（最好切分 %d，还差 %d）" % (min(others), min(others) - row[0][0])
    else:
        vtxt = "切分买到 %+d：赢家 r=%d（%d），长跑 %d" % (row[0][0] - bv, RS[ib], bv, row[0][0])
    p("  " + pad("%d x %d" % (n, m), 10) + pad(lb, 6) + cells + vtxt)
row60 = R4[(60, 8)][1]
row40 = R4[(40, 6)][1]
if row60[0][0] <= min(x[0] for x in row60):
    p("  60x8 上 r=1（从 T2 起点一次长爬坡 %s 次评估到 %d）不输给任何切分：这里切分买到的只有心理安慰。"
      % ("{:,}".format(row60[0][1]), row60[0][0]))
else:
    p("  60x8 上切分确实赢：%d -> %d（赢家 r=%d），代价是每个起点只能烧 %d 次左右评估。"
      % (row60[0][0], min(x[0] for x in row60),
         RS[[i for i, x in enumerate(row60) if x[0] == min(v for v, _ in row60)][0]], E4 // 10))
if max(x[0] for x in row40) > min(x[0] for x in row40):
    p("  40x6 上三个结果 %s 并不全同：r=%d 的切分反而比 r=%d 差 %d——重启值不值，看的是局部最优地形，不能靠信仰。"
      % ("/".join(str(x[0]) for x in row40),
        RS[[i for i, x in enumerate(row40) if x[0] == max(v for v, _ in row40)][0]],
        RS[[i for i, x in enumerate(row40) if x[0] == min(v for v, _ in row40)][0]],
        max(x[0] for x in row40) - min(x[0] for x in row40)))

# ================================================================ [5] 精确档能走多远
p()
p(W)
p("[5] 精确档能走多远：全枚举机器顺序（组合数 = (n!)^m）")
p(W)
p("  tiny 算例与站点性能页同源（seed=11），最优 25/33/29 在这里直接重算复核，不是抄来的。")
ENUM = {}
p("  " + pad("规模", 10) + pad("组合数", 12) + pad("可行(无环)", 12) + pad("最优", 8) + pad("LB", 7) + "实测耗时")
tot_t = 0.0
tot_c = 0
for (n, m) in [(3, 3), (4, 3), (3, 4)]:
    ctx = build_ctx(gen(n, m, 11))
    lb = trivial_lb(ctx)
    combos = math.factorial(n) ** m
    ops_on = [[] for _ in range(m)]
    for oid in range(n * m):
        ops_on[ctx["mach"][oid]].append(oid)
    perms = [list(itertools.permutations(s)) for s in ops_on]
    t0 = time.perf_counter()
    best, nfeas = None, 0
    evn = Eval(ctx)
    for pr in itertools.product(*perms):
        v = evn([list(pr[k]) for k in range(m)])
        if v is not None:
            nfeas += 1
            if best is None or v < best:
                best = v
    dt = time.perf_counter() - t0
    tot_t += dt
    tot_c += combos
    ENUM[(n, m)] = (best, lb, nfeas, combos, dt)
    assert best >= lb and evn.n == combos
    p("  " + pad("%d x %d" % (n, m), 10) + pad("{:,}".format(combos), 12) + pad("{:,}".format(nfeas), 12)
      + pad(best, 8) + pad(lb, 7) + "%.3f 秒（随负载漂）" % dt)
assert ENUM[(3, 3)][0] == 25 and ENUM[(4, 3)][0] == 33 and ENUM[(3, 4)][0] == 29, "最优须与站点已复核值一致"
enum_rate = tot_c / tot_t
ctx = build_ctx(gen(5, 3, 11))
combos5 = math.factorial(5) ** 3
ops_on = [[] for _ in range(3)]
for oid in range(15):
    ops_on[ctx["mach"][oid]].append(oid)
perms5 = [list(itertools.permutations(s)) for s in ops_on]
t0 = time.perf_counter()
best5, feas5 = None, 0
ev5 = Eval(ctx)
for pr in itertools.product(*perms5):
    v = ev5([list(pr[k]) for k in range(3)])
    if v is not None:
        feas5 += 1
        if best5 is None or v < best5:
            best5 = v
dt5 = time.perf_counter() - t0
lb5 = trivial_lb(ctx)
p("  再拿 5x3 把外推验证一遍：%s 组合全枚举跑穿：最优 %d（LB=%d，可行 %s 个 = %.1f%%）——%s"
  % ("{:,}".format(combos5), best5, lb5, "{:,}".format(feas5), feas5 / combos5 * 100,
     "最优正好压住下界，这格是算出来的，不是猜的。" if best5 == lb5
     else "最优比下界高 %d，这格是算出来的，不是猜的。" % (best5 - lb5)))
enum_rate5 = combos5 / dt5
ratio5 = (combos5 / enum_rate) / dt5
dev5 = abs(ratio5 - 1) * 100
p("  这一跑本机耗时 %.2f 秒；按 4x3 吞吐（%s 组合/秒）外推应是 %.1f 秒（本行随机器漂）：%s"
  % (dt5, "{:,.0f}".format(enum_rate), combos5 / enum_rate,
     ("外推与实测差 %.1f%%：同一量级的账可以当数。" % dev5) if dev5 < 50
     else ("外推与实测差 %.1f%%：只当量级参考，别当秒表。" % dev5)))
p("  可行比例（无环/全组合）：%d/%d=%.0f%%、%s/%s=%.0f%%、%d/%s=%.0f%%——乱序组合大多直接成环，被 sched() 判 None。"
  % (ENUM[(3, 3)][2], ENUM[(3, 3)][3], ENUM[(3, 3)][2] / ENUM[(3, 3)][3] * 100,
     "{:,}".format(ENUM[(4, 3)][2]), "{:,}".format(ENUM[(4, 3)][3]), ENUM[(4, 3)][2] / ENUM[(4, 3)][3] * 100,
     ENUM[(3, 4)][2], "{:,}".format(ENUM[(3, 4)][3]), ENUM[(3, 4)][2] / ENUM[(3, 4)][3] * 100))
p("  再往外的大额账按 5x3 实测吞吐 %s 组合/秒折算（本行起随机器漂）：" % "{:,.0f}".format(enum_rate5))
p("  " + pad("规模", 10) + pad("组合数", 16) + pad("折算秒", 16) + "换成")
for (n, m) in [(6, 3), (8, 3), (10, 3)]:
    combos = math.factorial(n) ** m
    secs = combos / enum_rate5
    p("  " + pad("%d x %d" % (n, m), 10) + pad(sci(combos), 16) + pad(sci(secs), 16) + human_time(secs))
p("  换算出来的实话：10 x 3（才 30 个工序）按本机枚举吞吐要 %s；生产规模的 %d x %d 想都别想。"
  % (human_time(math.factorial(10) ** 3 / enum_rate5), 60, 8))
p("  所以精确档的岗位是裁判不是前锋：%s 个组合以内当场对答案（比如复核爬山有没有命中最优），全场交给阶梯的低档去打。"
  % "{:,}".format(combos5))

# ================================================================ [6] 可复现性自检
p()
p(W)
p("[6] 可复现性自检：预算写成评估次数 vs 写成秒")
p(W)
tw1 = restart_tier(CTX1, 2000, o2x, v2x, random.Random(501))
tw2 = restart_tier(CTX1, 2000, o2x, v2x, random.Random(501))
same_o = all(a == b for a, b in zip(tw1[1], tw2[1])) and tw1[0] == tw2[0] and tw1[2] == tw2[2]
td1 = destroy_tier(CTX1, 2000, o2x, v2x, random.Random(502))
td2 = destroy_tier(CTX1, 2000, o2x, v2x, random.Random(502))
same_d = all(a == b for a, b in zip(td1[1], td2[1])) and td1[0] == td2[0]
tc1 = climb_tier(CTX1, 2000, [list(s) for s in o2x], 2)
tc2 = climb_tier(CTX1, 2000, [list(s) for s in o2x], 2)
same_c = tc1[0] == tc2[0] and tc1[1] == tc2[1]
assert same_o and same_d and same_c, "评估次数预算下两次必须逐格相同，否则 RNG 漏了时钟"
p("  同一算例（60x8）、同一 seed、评估次数上限 2,000，连续跑两遍：")
p("  " + pad("档", 9) + pad("makespan", 14) + pad("评估次数", 14) + "结果比对")
p("  " + pad("T4爬山", 9) + pad("%d / %d" % (tc1[0], tc2[0]), 14)
  + pad("%s / %s" % ("{:,}".format(tc1[1]), "{:,}".format(tc2[1])), 14) + ("「相同」" if same_c else "「不同」"))
p("  " + pad("T5重启", 9) + pad("%d / %d" % (tw1[0], tw2[0]), 14)
  + pad("%s / %s" % ("{:,}".format(tw1[2]), "{:,}".format(tw2[2])), 14) + ("「相同」" if same_o else "「不同」"))
p("  " + pad("T6破坏", 9) + pad("%d / %d" % (td1[0], td2[0]), 14)
  + pad("%s / %s" % ("{:,}".format(td1[2]), "{:,}".format(td2[2])), 14) + ("「相同」" if same_d else "「不同」"))
wall = []
for _ in range(3):
    evw = Eval(CTX1)
    o = [list(s) for s in o2x]
    cur = evw(o)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 0.5:
        cur, conv = first_improve(CTX1, evw, evw.n + 200, o, cur, 2, [0])
        if conv:
            break
    wall.append((cur, evw.n))
uniq_w = len({w[1] for w in wall})
p("  预算改写成墙钟 0.5 秒、同 seed 跑三次（本行起随机器负载漂）：")
p("    评估次数 %s -> 三次相同 = %s；makespan %s -> 相同 = %s"
  % (str([w[1] for w in wall]), "是" if uniq_w == 1 else "否", str([w[0] for w in wall]),
     "是" if len({w[0] for w in wall}) == 1 else "否"))
p("    口径提醒：这段墙钟循环是每 200 次评估切一片再对表，次数已经被量化到片长上；")
if uniq_w == 1:
    p("    这一轮被切齐了才「相同」，别把它当可复现——站点性能页 [7] 不切片、同 0.3 秒三次跑出过 [444, 445, 442]。")
    p("    秒本来就是机器忙不忙的函数，别把「碰巧稳」当「复现」；写验收就写评估次数，别写秒。")
else:
    p("    即使被切齐到片长，同样 0.5 秒仍跑出 %d 种不同的评估次数（%s）——搜索深度随负载漂。"
      % (uniq_w, str([w[1] for w in wall])))
    p("    站点性能页 [7] 不切片时同 0.3 秒三次跑出过 [444, 445, 442]：写成秒的验收没法复验，写次数才写得动。")
p("    对照：评估次数预算两跑逐格比对 T4=%s、T5=%s、T6=%s（T4 无随机、T5 含 %d 个随机起点、T6 含 %d 轮破坏的 RNG）。"
  % ("「相同」" if same_c else "「不同」", "「相同」" if same_o else "「不同」", "「相同」" if same_d else "「不同」",
     tw1[3], td1[3]))
p("  阶梯的整条定价（[1]~[4] 所有表）都建立在评估次数这把尺上：换台机器跑，次数、解、表结构不变，只有秒变。")

# ================================================================ [7] 一览
p()
p(W)
p("[7] 一览：只复述上面算出来的数")
p(W)
p("  阶梯（60x8，LB=%d）：T1 %d -> T2 %d（T2-T1 %+d 是规则白送的）；预算 50,000 处 T3~T6 = %s。"
  % (LB1, LAD[50000][0][0], LAD[50000][1][0], LAD[50000][1][2], [x[0] for x in LAD[50000][2:]]))
w50k = [t for t in range(2, 6) if LAD[50000][t][2] > 0]
p("  预算 500 处 T3~T6 的边际改进：%s——%d 档白买；50,000 处还在买东西的只剩 %s。档位不是信仰。"
  % ("/".join("%+d" % LAD[500][t][2] for t in range(2, 6)), len(z500),
     "、".join("%s（%+d）" % (TNAME[t], LAD[50000][t][2]) for t in w50k) if w50k else "没有档位"))
p("  撞墙：%s。烧满 %s 次却 0 改进的组合：%s。"
  % (("T%d~T6 同值从 %d x %d 开始" % (conv_from[2] + 1, conv_from[0], conv_from[1])) if conv_from else "四档在四个规模上都没完全同值",
     "{:,}".format(E2), "、".join("%dx%d %s" % b for b in burn0) if burn0 else "无"))
p("  重启：E=%s 下 40x6 赢家 r=%d、60x8 赢家 r=%d；邻域：E=10,000 赢家 %s。"
  % ("{:,}".format(E4),
     RS[[i for i, x in enumerate(R4[(40, 6)][1]) if x[0] == min(v for v, _ in R4[(40, 6)][1])][0]],
     RS[[i for i, x in enumerate(R4[(60, 8)][1]) if x[0] == min(v for v, _ in R4[(60, 8)][1])][0]],
     "、".join(l for l, _ in NB if NBRES[l][2][0] == min(NBRES[q][2][0] for q, _ in NB))))
p("  精确：3x3/4x3/3x4 重算最优 %s（与站点复核值一致）；5x3 全枚举 %s 组合跑穿，最优 %d%s；6x3 起要按 [5] 的折算表读。"
  % ("/".join(str(ENUM[k][0]) for k in [(3, 3), (4, 3), (3, 4)]), "{:,}".format(combos5), best5,
     "（等于下界，无解可改进）" if best5 == trivial_lb(build_ctx(gen(5, 3, 11))) else "（高于下界 %d）" % trivial_lb(build_ctx(gen(5, 3, 11)))))
p("  复现：评估次数预算两跑逐格比对 T4/T5/T6 = %s；墙钟 0.5s 三跑评估次数 %s。"
  % ("三档全「相同」" if (same_c and same_o and same_d) else "有档「不同」（见 [6]）", str([w[1] for w in wall])))
p("  本页 stdout 共 %d 行，每个数字都出自上面跑出来的表。争论「哪个算法」之前，" % (NL + 2))
p("  先把预算写成评估次数、把每档的边际改进算出来——表里那些 0 和负数就是答案。")
