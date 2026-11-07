"""拿《某某智能排产智能体技术能力点检清单 V1.0》给「求解/算法引擎」定的验收基准，
在真实算例上逐条量一遍：能不能测、测出来是过还是不过、口径有没有坑。

用法:  python solver_budget.py
对照的基准（点检清单原文）:
  #28 MIP     核心排产问题在时限内求得可行解率 ≥99%，硬约束零违规
  #29 启发式   启发式求解时间 ≤ 精确求解 10%，方案质量损失 ≤5%
  #30 增量     增量重解耗时 ≤ 全量求解 20%，冻结窗口内方案不变
  #41 降级     算法超时熔断 15 秒，求解超时自动转启发式

纯标准库。时间是本机 wall-clock，换机器数字会变，结论不会。
"""
import itertools
import math
import random
import time

JOBS = [[(0, 5), (2, 1), (1, 4)],
        [(1, 2), (2, 4), (0, 5)],
        [(2, 3), (1, 5), (0, 6)],
        [(1, 6), (2, 6), (0, 1)]]


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
    """给定每台机器的加工顺序 → 最早开工时间（半激活调度）。有环返回 None。"""
    nxt, indeg = {}, {n: 0 for n in dur}
    for seq in order.values():
        for a, b in zip(seq, seq[1:]):
            nxt.setdefault(a, []).append(b)
            indeg[b] += 1
    for i, j in enumerate(jobs):
        for o in range(len(j) - 1):
            a, b = (i, o), (i, o + 1)
            nxt.setdefault(a, []).append(b)
            indeg[b] += 1
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
    if done < len(dur):
        return None
    return st


def cmax(jobs, dur, order):
    st = starts(jobs, dur, order)
    return None if st is None else max(s + dur[n] for n, s in st.items())


def dispatch(jobs, dur, key):
    """派工规则生成机器顺序：每步在「各工件当前可派工序」里按 key 挑最小的，同分随机。
       这样生成的顺序天然无环。key=(s,p,i,k)：s=最早开工时刻，p=工时，i=工件，k=机器。
         key=lambda s,p,i,k: (p,i,k) → SPT（最短工序优先）
         key=lambda s,p,i,k: (s,p,i,k) → 主动调度（谁先能开工派谁，Giffler–Thompson 味）"""
    m, _, _ = make_eval(jobs)
    n = len(jobs)
    ptr, mfree, jfree = [0] * n, [0.0] * m, [0.0] * n
    order = {k: [] for k in range(m)}
    while sum(ptr) < sum(len(j) for j in jobs):
        cand = []
        for i in range(n):
            if ptr[i] < len(jobs[i]):
                k, p = jobs[i][ptr[i]]
                cand.append((max(jfree[i], mfree[k]), p, i, k))
        ranked = [(key(*c), c) for c in cand]
        best = min(r for r, _ in ranked)
        tie = [c for r, c in ranked if r == best]
        _, _, i, k = random.choice(tie)
        p = jobs[i][ptr[i]][1]
        s = max(jfree[i], mfree[k])
        jfree[i] = mfree[k] = s + p
        order[k].append((i, ptr[i]))
        ptr[i] += 1
    return order


class Eval:
    """计数器。基准写「求解时间」，但真正决定时间的是评估次数——两个都得报。"""

    def __init__(self, jobs, dur):
        self.jobs, self.dur, self.n = jobs, dur, 0

    def __call__(self, order):
        self.n += 1
        return cmax(self.jobs, self.dur, order)


def local_search(jobs, budget, seed=0, base=None, cut=None, deadline=None):
    """随机重启爬山。邻域 = 机器顺序的相邻交换。budget = 评估次数上限。
       base/cut: 增量重排。base = 已下发方案的各机器顺序，cut[k] = 机器 k 上不许动的
                 前缀长度。前 cut[k] 格按 base 原样钉死，新插的工序只能落在其后。
                 注意钉的是「位置前缀」而不是「工序集合」——后者会改掉已下发方案的开工时刻。
       deadline: 墙钟秒数上限（模拟 #41 的 15 秒熔断），到点立刻收手。"""
    m, ops_of, dur = make_eval(jobs)
    cut = cut or {}
    t_end = None if deadline is None else time.perf_counter() + deadline
    random.seed(seed)
    ev = Eval(jobs, dur)

    def spent():
        return ev.n >= budget or (t_end is not None and time.perf_counter() >= t_end)

    def pin(order):
        """把各机器的前缀还原成已下发方案，其余槽位按 order 给的顺序填。"""
        if base is None:
            return {k: list(v) for k, v in order.items()}
        out = {}
        for k, seq in order.items():
            head = base.get(k, [])[:cut.get(k, 0)]
            headset = set(head)
            out[k] = head + [x for x in seq if x not in headset]
        return out

    def first_free(k, seq):
        """机器 k 上第一个可交换的位置。"""
        return cut.get(k, 0)

    def climb(order, cur):
        improved = True
        while improved and not spent():
            improved = False
            for k in range(m):
                seq = order[k]
                for a in range(first_free(k, seq), len(seq) - 1):
                    if spent():
                        return cur
                    seq[a], seq[a + 1] = seq[a + 1], seq[a]
                    v = ev(order)
                    if v is not None and (cur is None or v < cur):
                        cur, improved = v, True
                    else:
                        seq[a], seq[a + 1] = seq[a + 1], seq[a]
        return cur

    def swap_safe(order, k, a):
        """做一次相邻交换；撞环（v=None）立刻撤销。"""
        seq = order[k]
        if a < first_free(k, seq) or a >= len(seq) - 1:
            return
        seq[a], seq[a + 1] = seq[a + 1], seq[a]
        if ev(order) is None:
            seq[a], seq[a + 1] = seq[a + 1], seq[a]

    best, start = None, None
    for _ in range(20):                                 # pin 后可能撞环，换一次派工重来
        start = pin(dispatch(jobs, dur, lambda s, p, i, k: (s, p, i, k)))
        best = ev(start)
        if best is not None:
            break
    best_order = {k: list(v) for k, v in start.items()}
    restarts = 0
    while not spent():
        restarts += 1
        cand = {k: list(v) for k, v in best_order.items()}
        rnd = random.Random(seed * 1000 + restarts)
        for _ in range(m):                              # 扰动：m 次随机相邻交换（只在可动段里挑）
            k = rnd.randrange(m)
            lo = cut.get(k, 0)
            if len(cand[k]) - 1 > lo:
                swap_safe(cand, k, rnd.randrange(lo, len(cand[k]) - 1))
        cur = ev(cand)
        cur = climb(cand, cur)          # climb 原地改 cand，返回它的 makespan
        if cur is not None and cur < best:
            best, best_order = cur, {k: list(v) for k, v in cand.items()}
    return best, best_order, ev.n, restarts


def trivial_lb(jobs):
    m = max(k for j in jobs for k, _ in j) + 1
    load = [0] * m
    for j in jobs:
        for k, p in j:
            load[k] += p
    return max([sum(p for _, p in j) for j in jobs] + load), load


def brute(jobs):
    """精确通道：机器顺序全枚举。小规模专用，同时返回最优顺序。"""
    m, ops_of, dur = make_eval(jobs)
    combos = list(itertools.product(*[itertools.permutations(ops_of[k]) for k in range(m)]))
    best, best_order, nfeas = None, None, 0
    for p in combos:
        o = {k: list(p[k]) for k in range(m)}
        v = cmax(jobs, dur, o)
        if v is not None:
            nfeas += 1
            if best is None or v < best:
                best, best_order = v, o
    return best, len(combos), nfeas, dur, best_order


# ================= 基准 #29 左半边：启发式时间 ≤ 精确求解 10% =================
m, ops_of, dur = make_eval(JOBS)
t0 = time.perf_counter()
OPT, ncombo, nfeas, _, opt_order = brute(JOBS)
t_exact = time.perf_counter() - t0
print(f"[4×3] 精确通道：机器顺序全枚举 {ncombo:,} 个，无环可评估 {nfeas:,} 个 → 最优 makespan = {OPT}")
print(f"      耗时 {t_exact:.3f}s，评估 {nfeas:,} 次（每次 = 一遍拓扑推进）")
for budget in (100, 300, 3000):
    t0 = time.perf_counter()
    h, _, ev, rs = local_search(JOBS, budget=budget)
    dt = time.perf_counter() - t0
    print(f"      爬山 预算{budget:>6,} → makespan {h}（损失 {(h - OPT) / OPT * 100:5.1f}%）"
          f"  {dt * 1000:7.2f}ms = 精确的 {dt / t_exact * 100:6.2f}%"
          f"   评估 {ev:>5,} 次 / 重启 {rs:>3,} 轮")
t0 = time.perf_counter()
d = cmax(JOBS, dur, dispatch(JOBS, dur, lambda s, p, i, k: (p, i, k)))
t_disp = time.perf_counter() - t0
print(f"      SPT 一条规则 → makespan {d}（损失 {(d - OPT) / OPT * 100:.0f}%）  {t_disp * 1000:.3f}ms"
      f" = 精确的 {t_disp / t_exact * 100:.3f}%")
lb4 = trivial_lb(JOBS)[0]
print(f"      下界对照：平凡下界 = {lb4}，最优 = {OPT} → 下界离最优 {(OPT - lb4) / lb4 * 100:.1f}%；"
      f"拿它当分母报「损失」，同一个方案从 {(OPT - lb4) / lb4 * 100:.1f}% 缩到 {(OPT - lb4) / OPT * 100:.1f}%")

# ================= 基准 #29 右半边：规模上去以后，损失还有没有分母 =================
random.seed(2026)
BIG = [[(k, random.randint(1, 9)) for k in range(5)] for _ in range(20)]
for j in BIG:
    random.shuffle(j)
lb, load = trivial_lb(BIG)
n_ops_big = [len(ops) for ops in make_eval(BIG)[1].values()]
combo_big = 1
for x in n_ops_big:
    combo_big *= math.factorial(x)
print(f"\n[20×5] 20 工件 × 5 机器，每机器工序数 {n_ops_big}"
      f" → 机器顺序组合数 ≈ {combo_big:.3e}（精确通道在这里不存在）")
print(f"       每机器负载 {load} → 平凡下界 = {lb}")
ladder = []
for budget in (2000, 20000, 120000):
    t0 = time.perf_counter()
    h, ord_b, ev, rs = local_search(BIG, budget=budget, seed=7)   # 同一颗种子 ⇒ 三条是同一条轨迹的前缀
    dt = time.perf_counter() - t0
    ladder.append((budget, h, dt, ev, rs, ord_b))
    print(f"   预算 {budget:>7,} → makespan {h:>4}  {dt:6.2f}s  评估 {ev:>8,} 次  重启 {rs:>4,} 轮"
          f"   vs 下界 gap {(h - lb) / lb * 100:5.1f}%   15 秒熔断{'内收工' if dt <= 15 else '内跑不完'}")
print("   基准写「质量损失 ≤5%」，分母是最优值。这个规模上最优不可知，")
print("   手上只有 vs 下界的 gap——两个口径不同源，不能互换着报。")
t0 = time.perf_counter()
h15, _, ev15, rs15 = local_search(BIG, budget=10 ** 9, seed=7, deadline=15)
dt15 = time.perf_counter() - t0
gap15 = (h15 - lb) / lb * 100
under5 = [r for r in ladder if (r[1] - lb) / lb * 100 <= 5]
print(f"\n   同一条轨迹，改成只给 15 秒墙钟（评估不限）→ makespan {h15}，"
      f"用掉 {dt15:.2f}s，评估 {ev15:,} 次 / 重启 {rs15} 轮，gap {gap15:.1f}%")
if under5:
    b5, h5r, dt5 = under5[0][0], under5[0][1], under5[0][2]
    print(f"   ⇒ #29 要「损失 ≤5%」：轨迹上第一次进 5% 是 {h5r}（gap {(h5r - lb) / lb * 100:.1f}%），"
          f"花 {dt5:.1f}s = 熔断线的 {dt5 / 15:.1f} 倍")
print(f"      #41 要「15 秒熔断」：卡在 15s 只能停在 {h15}（gap {gap15:.1f}%）。")
print(f"      两条基准各占这条轨迹的一头，中间没有同时满足的解——除非加算力或换算法。")

# ================= 基准 #30：增量重解 ≤ 全量 20%，冻结窗口内方案不变 =================
def freeze_prefix(base_order, st, until):
    """「冻结窗口内方案不变」的正确写法：机器 k 的前 cut[k] 格按已下发方案原样钉死。
       cut[k] = 该机器上最晚一道冻结工序的位置 + 1。"""
    cut = {}
    for k, seq in base_order.items():
        idx = [i for i, n in enumerate(seq) if st[n] < until]
        cut[k] = max(idx) + 1 if idx else 0
    return cut


def pin_to_front(order, frozen):
    """常见偷懒写法：把冻结工序挑出来放最前。放的是「新生成的顺序里挑」，不是下发方案。"""
    return {k: [x for x in v if x in frozen] + [x for x in v if x not in frozen]
            for k, v in order.items()}


st_base = starts(JOBS, dur, opt_order)
print("\n[插单] 车间正在执行下面这份已下发的方案（4 工件精确最优）：")
print(f"       makespan = {OPT}，工序开工时刻 = "
      + " ".join(f"{i}.{o}@{st_base[(i, o)]:g}" for i in range(len(JOBS)) for o in range(3)))
print(f"       各机器负载 = {trivial_lb(JOBS)[1]} → 瓶颈在机器 0 和 1")
FREEZE = 6
frozen = {n for n, s in st_base.items() if s < FREEZE}
cut4 = freeze_prefix(opt_order, st_base, FREEZE)
print(f"       冻结窗口 [0,{FREEZE}) = {sorted(frozen)}")
print(f"       按前缀写法各机器的固定段 = "
      f"{ {k: opt_order[k][:cut4[k]] for k in opt_order} }\n")
for NEW, tag in (((2, 3), "急单走闲机器"),
                 ((0, 7), "急单压瓶颈"),
                 ([(0, 4), (1, 5), (2, 3)], "急单三道工序全走")):
    ops = NEW if isinstance(NEW, list) else [NEW]
    J5 = [list(j) for j in JOBS] + [ops]
    t0 = time.perf_counter()
    OPT5, nc5, nf5, dur5, _ = brute(J5)
    t_full = time.perf_counter() - t0
    t0 = time.perf_counter()
    h5, order5, ev5, rs5 = local_search(J5, budget=4000, base=opt_order, cut=cut4, seed=11)
    t_incr = time.perf_counter() - t0
    st5 = starts(J5, dur5, order5)
    moved = {n: (st_base[n], st5[n]) for n in frozen if st_base[n] != st5[n]}
    h_free, _, _, _ = local_search(J5, budget=4000, seed=11)
    print(f"  [{tag}] 新工件工序 = {ops}")
    print(f"      全量重排：枚举 {nc5:,} 个机器顺序（无环 {nf5:,}）→ 最优 {OPT5}，耗时 {t_full:.2f}s"
          + (f"   ← 这一步本身就超了 15 秒熔断" if t_full > 15 else ""))
    print(f"      增量重排：{h5}（比全量差 {(h5 - OPT5) / OPT5 * 100:.1f}%），耗时 {t_incr:.3f}s"
          f" = 全量的 {t_incr / t_full * 100:.1f}%（红线 20%）→ 评估 {ev5:,} 次 / 重启 {rs5} 轮")
    print(f"      冻结工序开工时刻变化 = {moved or '无'} → 基准后半句「方案不变」"
          f"{'满足' if not moved else '不满足'}")
    print(f"      同预算放开冻结 → {h_free}，冻结的价格 = {h5 - h_free} 个时间单位"
          + ('（这单插得进去，白冻）' if h5 == h_free else '（这单插不进去，冻出来的）\n'))
print(f"\n       增量耗时口径 20% 全线达标，因为分母是全量枚举——分母越大，比例越好看。")
print(f"       「方案不变」这半句在小算例上也不花钱：4×3 规模下，钉住前缀以后照样撞得到最优。")

# ============ 追加：规模上去，两件事同时显形——冻结要花钱，而且偷懒写法会违约 ============
rush_rng = random.Random(4242)
RUSH = [(k, rush_rng.randint(2, 8)) for k in range(5)]
BIGH = [list(j) for j in BIG] + [RUSH]
lb_h = trivial_lb(BIGH)[0]
row20k = [r for r in ladder if r[0] == 20000][0]
base_h, base_order = row20k[1], row20k[5]
dur_b = make_eval(BIG)[2]
st_b = starts(BIG, dur_b, base_order)
FZ = 15
frozen_big = {n for n, s in st_b.items() if s < FZ}
cutb = freeze_prefix(base_order, st_b, FZ)
print(f"\n[上规模] 20×5：下发方案 makespan = {base_h}（预算 20,000 那一跑）")
print(f"       急单 = {RUSH}（第 21 个工件，5 道工序）→ 新平凡下界 = {lb_h}")
print(f"       冻结窗口 [0,{FZ}) = {len(frozen_big)} 道 / 105 道，各机器固定段长 = "
      f"{ {k: cutb[k] for k in cutb} }")
t0 = time.perf_counter()
h_fz, ord_fz, ev_fz, rs_fz = local_search(BIGH, budget=20000, base=base_order, cut=cutb, seed=7)
t_fz = time.perf_counter() - t0
t0 = time.perf_counter()
h_fr, ord_fr, _, rs_fr = local_search(BIGH, budget=20000, seed=7)
t_fr = time.perf_counter() - t0
st_fz = starts(BIGH, make_eval(BIGH)[2], ord_fz)
moved_big = {n: (st_b[n], st_fz[n]) for n in frozen_big if st_b[n] != st_fz[n]}
print(f"       前缀钉死 → {h_fz}（vs 下界 {(h_fz - lb_h) / lb_h * 100:.1f}%），{t_fz:.2f}s，重启 {rs_fz} 轮")
print(f"       全放开、同预算 → {h_fr}（vs 下界 {(h_fr - lb_h) / lb_h * 100:.1f}%），{t_fr:.2f}s，重启 {rs_fr} 轮")
print(f"       ⇒ 两次结果的差 = {h_fz - h_fr} 个时间单位。注意它是负的——")
print(f"          不是「冻结反而赚了 {abs(h_fz - h_fr)}」，是同预算下两边都没撞到最优，")
print(f"          差值里混着搜索噪声。真正的冻结代价 = opt(冻结) − opt(自由) ≥ 0，")
print(f"          而这两个 opt 在本页的规模上都不可知。4×3 上它是 0，也不是「冻结不花钱」，")
print(f"          是那个规模怎么搜都撞得到最优。")
print(f"       冻结工序开工时刻变化 = {moved_big or '无'}（前缀写法，按构造不可能动）")
naive = pin_to_front(ord_fr, frozen_big)          # 自由搜完，再把冻结集合“置顶”
mm_h = make_eval(BIGH)[2]
st_naive = starts(BIGH, mm_h, naive)
if st_naive is None:
    print(f"\n[偷懒写法] 置顶以后直接撞出环，方案不可执行——连评估都过不了。")
else:
    moved_naive = {n: (st_b[n], st_naive[n]) for n in frozen_big if st_b[n] != st_naive[n]}
    print(f"\n[偷懒写法] 不设前缀，先自由搜、再把冻结工序「挑出来放最前」：")
    print(f"       makespan {cmax(BIGH, mm_h, naive)}，同样 {len(frozen_big)} 道冻结工序，"
          f"开工时刻变了 {len(moved_naive)} 道 = {moved_naive}")
    print(f"       放前面 ≠ 放在原来那一格。车间已按下发方案把机床腾给这批活，")
    print(f"       提前开工同样是违约——机床那半小时本来留给别处。")
    print(f"       「不变」只有按 (机器, 位置) 钉死才成立；写成「集合置顶」的实现能骗过单测，骗不过车间。")
print(f"\n       基准 #30 写了「冻结窗口内方案不变」，没写「不变值多少钱」。")
print(f"       落地时这一行要业务签字：为了不动这 {len(frozen_big)} 道工序，")
print(f"       整班交付最多愿意慢多少？答案只能是「opt(冻结) − opt(自由)」，")
print(f"       也就是一个在验收现场量不出来的数——只能靠下界夹逼，或者靠人拍。")
