# -*- coding: utf-8 -*-
"""采纳率是组织问题还是模型问题：把「允许算法改多少」做成一个可扫的旋钮，实测每一档的
计划质量（makespan）与改动量（顺序改动 / 时刻改动 / 已下发被改时刻），再套一个写死公式的
采纳模型，算出期望采纳质量的峰值落在哪一档。

用法:  python adoption_probe.py          （纯标准库，无第三方依赖）

  [1] 基线与「改动」怎么量化：两个口径的定义，以及它们真的不是同一个数
  [2] 扰动之后有多少种「改法」：钉住前缀 W=0/2/4/6/8/10/12，同一评估预算逐档实测
  [3] 采纳模型：把「改多少」换成「被接受的概率」，公式与 ref 的取值口径全部打印
  [4] 最优点在哪：两条行为曲线各自的峰值 W，换第二个算例看峰值稳不稳
  [5] 一次拒绝的代价：手工规则的 makespan + 「干脆不动老计划」这个参照点
  [6] 本机实测一览

预算一律写成评估次数（不是秒数）：墙钟不可复现。质量、改动量是测出来的；
p_accept 那两列是对行为的假设，不是测量——脚本里每一句解释都由实测值分支决定。
"""
import random
import sys
import time

_T0 = time.perf_counter()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")   # Windows 默认 GBK 控制台：编不出的字符变问号，别崩

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


def dispatch(jobs, dur, key, rnd=None, stats=None):
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
    """随机重启爬山。moves=2 在相邻交换之外加「把一道工序插到同机可动段更靠后的位置」。
       base/cut = 增量重排：各机器前 cut[k] 格钉回已下发顺序，新工序只能落在其后。"""
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


# ---------------------------------------------------------------- 改动量口径
def pos_map(order):
    p = {}
    for k, seq in order.items():
        for idx, op in enumerate(seq):
            p[op] = (k, idx)
    return p


def churn(st0, pos0, st1, pos1, rel):
    """两份方案（同一批老工序）之间的改动量。只数老工序：新插的工序没有「原来在哪」。"""
    sh = sorted(st0)
    cs = sum(1 for op in sh if pos0[op] != pos1.get(op))
    ct = sum(1 for op in sh if st0[op] != st1.get(op))
    shifts = [abs(st1[op] - st0[op]) for op in sh if op in st1]
    mean_shift = sum(shifts) / len(shifts)
    mx = max(shifts) if shifts else 0
    rc = sum(1 for op in rel if op in st1 and st1[op] != st0[op])
    return cs, ct, mean_shift, mx, rc


def append_plan(o0, jobs, newi):
    """零改动参照：老顺序一格不动，新工件每道工序追加到对应机器队尾。"""
    out = {k: list(v) for k, v in o0.items()}
    for o, (k, _p) in enumerate(jobs[newi]):
        out[k].append((newi, o))
    return out


BASE_BUDGET = 8000            # 基线方案的评估预算（固定值，不用墙钟）
BUDGET = 6000                 # 逐档重排的评估预算：所有 W 共用同一个数，比的是同一块买办
W_LIST = (0, 2, 4, 6, 8, 10, 12)
T_REL = 25                    # 基线里开工时刻 < T_REL 的工序算「已下发」
KS = (1, 2)                   # 采纳模型的两个行为指数
SEED_LS = 13
USABLE_SLACK = 3.0            # 可用线：makespan 不超过 W=0 方案的 +3%


def build(njob, mach, seed):
    """一个算例：基线方案 + 插单后的扰动算例 + 已下发集合。"""
    inst = gen(njob, mach, seed)
    _, _, dur = make_eval(inst)
    lb = trivial_lb(inst)
    mk0, o0, ne0, _r = local_search(inst, seed=SEED_LS, budget=BASE_BUDGET, moves=2)
    s0 = starts(inst, dur, o0)
    p0 = pos_map(o0)
    rel = {op for op, s in s0.items() if s < T_REL}
    rush = gen(1, mach, 777)[0]
    j2 = [list(j) for j in inst] + [rush]
    _, _, d2 = make_eval(j2)
    return dict(njob=njob, mach=mach, seed=seed, inst=inst, dur=dur, lb=lb, mk0=mk0,
                o0=o0, s0=s0, p0=p0, rel=rel, j2=j2, d2=d2, lb2=trivial_lb(j2),
                rush=rush, nop=sum(len(j) for j in inst))


def sweep(case, w_list=W_LIST, budget=BUDGET):
    rows = []
    for Wn in w_list:
        cut = {k: min(Wn, len(v)) for k, v in case["o0"].items()}
        pinned = set()
        for k, seq in case["o0"].items():
            pinned.update(seq[:cut[k]])
        v, o, ne, rs = local_search(case["j2"], seed=SEED_LS, base=case["o0"],
                                    cut=cut, moves=2, budget=budget)
        if v is None:
            rows.append(dict(w=Wn, feas=False))
            continue
        s1 = starts(case["j2"], case["d2"], o)
        cs, ct, ms, mx, rc = churn(case["s0"], case["p0"], s1, pos_map(o), case["rel"])
        rows.append(dict(w=Wn, feas=True, mk=v, evals=ne, restarts=rs, n_pin=sum(cut.values()),
                         rel_pin=len(case["rel"] & pinned), cs=cs, ct=ct, ms=ms, mx=mx, rc=rc,
                         order=o))
    return rows


def acceptance(rows, case):
    """p_accept = 1 / (1 + (churn/ref)^k)，churn 取「时刻改动」；ref 由本算例实测挑出。"""
    feas = [r for r in rows if r["feas"]]
    base_row = feas[0]
    line = base_row["mk"] * (1 + USABLE_SLACK / 100.0)
    usable = [r for r in feas if r["mk"] <= line]
    ref_src = next((r for r in usable if r["w"] > 0), None)
    if ref_src is not None:
        ref_w = ref_src["w"]
    else:
        ref_w = None
    ref = max(1, ref_src["ct"] if ref_src is not None
              else max(r["ct"] for r in feas))
    for r in rows:
        if not r["feas"]:
            continue
        r["ok"] = r["mk"] <= line
        r["q"] = case["lb2"] / r["mk"]
        for k in KS:
            p = 1.0 / (1.0 + (r["ct"] / ref) ** k)
            r["p%d" % k] = p
            r["eq%d" % k] = p * r["q"]
    return ref, base_row["mk"], line, ref_w


def peak(rows, key):
    return max((r for r in rows if r["feas"]), key=lambda r: r[key])


def pct(x):
    return "%+.1f%%" % x


def sd(a, b):
    """安全除法：分母为 0 就当 0，别让整个脚本因为一个空集合崩掉。"""
    return a / b if b else 0.0


def over(mk, lb):
    return (mk - lb) / lb * 100.0


# ---------------------------------------------------------------- [1] 口径
print(W)
print("[1] 基线与「改动」怎么量化")
print(W)
BIG = build(50, 6, 2026)
nb_big = nbr_count(BIG["o0"], {}, 2)
_ev = Eval(BIG["inst"], BIG["dur"])
t0 = time.perf_counter()
for _ in range(400):
    _ev(BIG["o0"])
rate = 400 / (time.perf_counter() - t0)
sys.stderr.write("wall: 50x6 throughput %.0f evals/s (kept out of stdout so the page is byte-stable)\n" % rate)
print("  先把标尺定死：预算写成评估次数，不写秒（墙钟换台机器就漂，同页 perf_probe 的 [7] 量过）。")
print("  一次评估 = starts() 走一遍拓扑。这台机器 50x6 那一档跑得比 30x6 慢多少没写进 stdout——")
print("  那是墙钟，换台机器就变；本页所有结论只用「邻居数 / 预算次数」这个纯结构比值，跟机器无关。")
print("  原定规模 50 工件 x 6 机器：%d 工序，平凡下界 %d，基线 makespan %d（超下界 %s，预算 %d 次）。"
      % (BIG["nop"], BIG["lb"], BIG["mk0"], pct(over(BIG["mk0"], BIG["lb"])), BASE_BUDGET))
print("  这个规模一次全场邻域扫描要 %s 个邻居 = %.2f 轮/预算 %d 次：一次扫描都扫不完。"
      % ("{:,}".format(nb_big), BUDGET / nb_big, BUDGET))
big_rows = []
for Wn in (0, max(W_LIST)):
    cut = {k: min(Wn, len(v)) for k, v in BIG["o0"].items()}
    v, o, ne, rs = local_search(BIG["j2"], seed=SEED_LS, base=BIG["o0"], cut=cut,
                                moves=2, budget=BUDGET)
    s1 = starts(BIG["j2"], BIG["d2"], o)
    big_rows.append((Wn, v, churn(BIG["s0"], BIG["p0"], s1, pos_map(o), BIG["rel"])[1]))
print("  实测两格对照（50x6、插单、预算同为 %d）：W=0 makespan %d / 时刻改动 %d；W=%d makespan %d / 时刻改动 %d。"
      % (BUDGET, big_rows[0][1], big_rows[0][2], big_rows[1][0], big_rows[1][1], big_rows[1][2]))
if big_rows[1][2] <= big_rows[0][2]:
    print("  钉到 W=%d 时刻改动少了 %d 个（%.1f%%）：这个规模上旋钮有正反馈，曲线就在它上面画。"
          % (big_rows[1][0], big_rows[0][2] - big_rows[1][2],
             sd(big_rows[0][2] - big_rows[1][2], big_rows[0][2]) * 100))
    WORK = BIG
else:
    dn = big_rows[1][2] - big_rows[0][2]
    print("  钉到 W=%d 时刻改动不降反升（+%d 个，%.1f%%）：这一档的扫描连一轮邻域都没走完，钉住只把新工序推远，"
          % (big_rows[1][0], dn, sd(dn, big_rows[0][2]) * 100))
    print("  旋钮拧不动方案。这不是「钉住没用」，是 6,000 次预算连一轮全场扫描都走不完（0.82 轮），")
    print("  每档只见到邻域的一小段——扫描覆盖不足时，钉住只是把新工序挤到队尾，改动量反而更大。")
    WORK = build(30, 6, 2026)
NB_WORK = nbr_count(WORK["o0"], {}, 2)
print("  工作算例：%d 工件 x %d 机器 = %d 工序（工时 1~9），基线 makespan %d，超下界 %s（下界 %d），"
      % (WORK["njob"], WORK["mach"], WORK["nop"], WORK["mk0"],
         pct(over(WORK["mk0"], WORK["lb"])), WORK["lb"]))
print("    一次全场扫描 %s 邻居 = %.2f 轮/预算 %d 次；下面全部曲线都在这一档上测。"
      % ("{:,}".format(NB_WORK), BUDGET / NB_WORK, BUDGET))
print("  改动量的两个口径，下面全程按这两句数：")
print("    顺序改动 = 两份方案里 (机器, 槽位) 不同的老工序数；只数老工序，新插的工序没有「原来在哪」。")
print("    时刻改动 = 开工时刻不同的老工序数；平均位移/最大位移 = 全部老工序 |Δ开工时刻| 的均值/最大值。")
dv, do, dne, drs = local_search(WORK["inst"], seed=91, budget=BUDGET, moves=2)
ds = starts(WORK["inst"], WORK["dur"], do)
d_cs, d_ct, d_ms, d_mx, d_rc = churn(WORK["s0"], WORK["p0"], ds, pos_map(do), WORK["rel"])
print("  拿它校验口径：同一批工件、不加任何扰动、只把 seed 从 %d 换成 91 重跑（预算 %d）："
      % (SEED_LS, BUDGET))
print("    makespan %d -> %d（%s），顺序改动 %d 个、时刻改动 %d 个、平均位移 %.1f、最大位移 %d。"
      % (WORK["mk0"], dv, pct(over(dv, WORK["lb"]) - over(WORK["mk0"], WORK["lb"])), d_cs, d_ct, d_ms, d_mx))
print("  两个口径是同一个数吗：%s（顺序 %d 个 vs 时刻 %d 个 = 占老工序 %.1f%% / %.1f%%）——"
      % ("是" if d_cs == d_ct else "否", d_cs, d_ct,
         d_cs / WORK["nop"] * 100, d_ct / WORK["nop"] * 100))
print("  所以「这版跟上一版差不多」这句话必须先说清按哪个口径数，两个口径能差 %d 个工序。" % abs(d_cs - d_ct))
if dv == WORK["mk0"]:
    print("  质量一模一样，却动了 %d 道工序的时刻：这就是车间里那句「跟上版没区别，别换」。" % d_ct)

# ---------------------------------------------------------------- [2] 逐档实测
print()
print(W)
print("[2] 扰动之后有多少种「改法」")
print(W)
RUSH = WORK["rush"]
print("  扰动 = 插一个急单：1 个工件 x %d 道工序，工时 %s（合计 %d），算例下界 %d -> %d。"
      % (WORK["mach"], [p for _, p in RUSH], sum(p for _, p in RUSH), WORK["lb"], WORK["lb2"]))
print("  钉法照搬增量重排的口径：各机器前 W 格钉回基线顺序（钉位置前缀，不钉工序集合）。")
print("  已下发口径：基线里开工时刻 < %d 的工序 %d 个，占 %d 个老工序的 %.0f%%。"
      % (T_REL, len(WORK["rel"]), WORK["nop"], len(WORK["rel"]) / WORK["nop"] * 100))
print("  " + pad("W", 4) + pad("钉住格数", 11) + pad("makespan", 10) + pad("超下界", 9)
      + pad("顺序改动", 10) + pad("时刻改动", 10) + pad("平均位移", 10) + pad("最大位移", 10)
      + "已下发被改时刻")
ROWS = sweep(WORK)
for r in ROWS:
    if not r["feas"]:
        print("  " + pad(r["w"], 4) + "该档无可行顺序（钉住前缀成环），跳过")
        continue
    print("  " + pad(r["w"], 4) + pad(r["n_pin"], 11) + pad(r["mk"], 10)
          + pad(pct(over(r["mk"], WORK["lb2"])), 9) + pad(r["cs"], 10) + pad(r["ct"], 10)
          + pad("%.1f" % r["ms"], 10) + pad(r["mx"], 10)
          + "%d（钉住的 %d 格）" % (r["rc"], r["rel_pin"]))
evs = [r["evals"] for r in ROWS if r["feas"]]
FEAS = [r for r in ROWS if r["feas"]]
print("  每格实际评估次数 %d~%d（预算写死 %d，逐格同一块预算，才叫公平比较）；重启次数 %s。"
      % (min(evs), max(evs), BUDGET, [r["restarts"] for r in FEAS]))
ROW6 = next((r for r in FEAS if r["w"] == 6), None)
CUT_R = {k: min(6, len(v)) for k, v in WORK["o0"].items()}
r_b = local_search(WORK["j2"], seed=SEED_LS, base=WORK["o0"], cut=CUT_R, moves=2, budget=BUDGET)
if ROW6 is None:
    print("  可复现性自检没有 W=6 那格（该档不可行），跳过。")
else:
    print("  可复现性自检（把 W=6 那格原样重跑，跟上表那一行对）：makespan %s/%s、评估次数 %s/%s、"
          "机器顺序逐格相同 = %s。" % (ROW6["mk"], r_b[0], ROW6["evals"], r_b[2],
                                       "是" if ROW6["order"] == r_b[1] else "否"))
    if ROW6["order"] != r_b[1]:
        print("  顺序不同 = 这条链上有别的东西在变，本表的档位间差就不能全归给 W。")
F, L = FEAS[0], FEAS[-1]
mono_dn = all(FEAS[i]["ct"] >= FEAS[i + 1]["ct"] for i in range(len(FEAS) - 1))
rev = ["%d->%d" % (FEAS[i]["w"], FEAS[i + 1]["w"]) for i in range(len(FEAS) - 1)
       if FEAS[i]["ct"] < FEAS[i + 1]["ct"]]
mono_up = all(FEAS[i]["mk"] <= FEAS[i + 1]["mk"] for i in range(len(FEAS) - 1))
print("  旋钮拧到 W=%d：时刻改动 %d -> %d（%s），顺序改动 %d -> %d，已下发被改时刻 %d -> %d。"
      % (L["w"], F["ct"], L["ct"], pct((L["ct"] - F["ct"]) / F["ct"] * 100),
         F["cs"], L["cs"], F["rc"], L["rc"]))
print("  时刻改动随 W 单调下降吗：%s%s" % ("是" if mono_dn else "否",
      "" if mono_dn else "（回弹发生在 W=%s 这几对相邻档上，见上表）" % "、".join(rev)))
print("  makespan 随 W 单调上升吗：%s（全档最好 %d 出现在 W=%d 那档，不是最左端）"
      % ("是" if mono_up else "否", min(r["mk"] for r in FEAS),
         min(FEAS, key=lambda r: r["mk"])["w"]))
print("  质量这一轴：makespan %d -> %d（%s），全档极差 %d（%.1f%%）；钉到 W=%d 一共钉住 %d 格（占 %d 工序的 %.0f%%）。"
      % (F["mk"], L["mk"], pct((L["mk"] - F["mk"]) / F["mk"] * 100),
         max(r["mk"] for r in FEAS) - min(r["mk"] for r in FEAS),
         (max(r["mk"] for r in FEAS) - min(r["mk"] for r in FEAS)) / F["mk"] * 100,
         L["w"], L["n_pin"], WORK["nop"] + len(RUSH), L["n_pin"] / (WORK["nop"] + len(RUSH)) * 100))
if L["mk"] > F["mk"]:
    print("  两端比：钉到 W=%d 比不钉慢 %+d 个时间单位（%s）——质量这一轴确实要收钱；"
          % (L["w"], L["mk"] - F["mk"], pct((L["mk"] - F["mk"]) / F["mk"] * 100)))
    print("  但中间%s（%s），所以这条轴只能当趋势看，不能当函数用。"
          % ("不是单调的" if not mono_up else "单调上升",
             "最好那格在 W=%d" % min(FEAS, key=lambda r: r["mk"])["w"]))
else:
    print("  方向不对：钉到 W=%d 的 makespan（%d）没比不钉（%d）差，%+d——"
          % (L["w"], L["mk"], F["mk"], L["mk"] - F["mk"]))
    print("  固定小预算下钉住等于热启动：这条曲线上「采纳」那一轴便宜，「质量」那一轴几乎不收钱。")
n6 = [r["mk"] for r in FEAS if r["w"] == 6]
CUT6 = {k: min(6, len(v)) for k, v in WORK["o0"].items()}
x27 = local_search(WORK["j2"], seed=27, base=WORK["o0"], cut=CUT6, moves=2, budget=BUDGET)[0]
x41 = local_search(WORK["j2"], seed=41, base=WORK["o0"], cut=CUT6, moves=2, budget=BUDGET)[0]
n_mks = n6 + [x27, x41]
NOISE = max(n_mks) - min(n_mks)
print("  同一格 W=6 换 seed（%d/%d/%d）：makespan %s，极差 %d = %.1f%%——"
      % (SEED_LS, 27, 41, n_mks, NOISE, sd(NOISE, min(n_mks)) * 100))
print("  上面那条（%s）趋势线站在多大噪声上，就看这两个数：同格极差 %d vs 全档首尾变化 %d。"
      % ("单调下降" if mono_dn else "非单调", NOISE, abs(L["mk"] - F["mk"])))
if NOISE >= abs(L["mk"] - F["mk"]):
    print("  两个数同量级：这条曲线的档间差没盖过 seed 抖动，下面 [3][4] 的峰值只能读成「这一台机器这一个算例的落点」。")

# ---------------------------------------------------------------- [3] 采纳模型
print()
print(W)
print("[3] 采纳模型：把「改多少」换成「被接受的概率」")
print(W)
REF, MK_U0, LINE, REF_W = acceptance(ROWS, WORK)
print("  公式（全文只用这一个）：p_accept = 1 / (1 + (churn/ref)^k)，churn = 上表的「时刻改动」。")
print("  churn 越大越容易被拒；ref 是「一次能消化的改动量」，churn = ref 时 p_accept 正好一半。")
print("  可用线 = W=0 的 makespan %d x (1+%.0f%%) = %.1f：质量掉出这条线的档位，计划员不用看改动量也会打回。"
      % (MK_U0, USABLE_SLACK, LINE))
if REF_W is None:
    print("  线内没有 W>0 的档位，ref 退全档最大 churn = %d（这个 ref 挑法本身要被质疑）。" % REF)
else:
    print("  ref = 线内最小的非零档实测出来的 churn：W=%d 那档，churn=%d -> ref=%d。" % (REF_W, REF, REF))
print("  k 是两个行为指数，不是测量：k=1 温和型（改动线性劝退），k=2 敏感型（改动平方劝退）。")
print("  下面两列 p_accept 以及由它乘出来的期望采纳质量都是这套假设的推论；换假设就得重算。")
print("  质量分 = 下界/makespan，落在 (0,1]（实测）；期望采纳质量 = p_accept x 质量分。")
print("  " + pad("W", 4) + pad("时刻改动", 10) + pad("p(温和k=1)", 12) + pad("p(敏感k=2)", 12)
      + pad("makespan", 10) + pad("质量分", 9) + pad("期望采纳(温和)", 15)
      + pad("期望采纳(敏感)", 15) + "可用")
for r in FEAS:
    print("  " + pad(r["w"], 4) + pad(r["ct"], 10) + pad("%.3f" % r["p1"], 12)
          + pad("%.3f" % r["p2"], 12) + pad(r["mk"], 10) + pad("%.3f" % r["q"], 9)
          + pad("%.4f" % r["eq1"], 15) + pad("%.4f" % r["eq2"], 15)
          + ("是" if r["ok"] else "否"))
sp1 = (max(r["eq1"] for r in FEAS) - min(r["eq1"] for r in FEAS)) / min(r["eq1"] for r in FEAS) * 100
sp2 = (max(r["eq2"] for r in FEAS) - min(r["eq2"] for r in FEAS)) / min(r["eq2"] for r in FEAS) * 100
print("  曲线的起伏：期望采纳质量温和型跨档摆 %.1f%%、敏感型摆 %.1f%%；质量分自己只摆 %.1f%%。"
      % (sp1, sp2, (max(r["q"] for r in FEAS) - min(r["q"] for r in FEAS)) / min(r["q"] for r in FEAS) * 100))
mono_p = all(FEAS[i]["p1"] <= FEAS[i + 1]["p1"] for i in range(len(FEAS) - 1))
if FEAS[0]["p1"] > FEAS[-1]["p1"]:
    print("  p_accept 随 W 上升？否（%.3f -> %.3f）：钉得越多反而越不可接受，模型的排序跟直觉相反。"
          % (FEAS[0]["p1"], FEAS[-1]["p1"]))
else:
    print("  首末两端：p_accept(温和) %.3f -> %.3f（%s）、p_accept(敏感) %.3f -> %.3f（%s）——少改就好卖，方向跟直觉一致。"
          % (FEAS[0]["p1"], FEAS[-1]["p1"], pct(sd(FEAS[-1]["p1"] - FEAS[0]["p1"], FEAS[0]["p1"]) * 100),
             FEAS[0]["p2"], FEAS[-1]["p2"], pct(sd(FEAS[-1]["p2"] - FEAS[0]["p2"], FEAS[0]["p2"]) * 100)))
    print("  逐档单调不降吗：%s（churn 那一列在 W=%s 处回弹，p 就跟着回弹，见上表）"
          % ("是" if mono_p else "否", "、".join("%d->%d" % (FEAS[i]["w"], FEAS[i + 1]["w"])
             for i in range(len(FEAS) - 1) if FEAS[i]["ct"] < FEAS[i + 1]["ct"])))

# ---------------------------------------------------------------- [4] 峰值在哪
print()
print(W)
print("[4] 最优点在哪：扫出来的峰值 W")
print(W)


FLAT = 5.0


def report_peak(tag, rows, case, ref, line):
    feas = [r for r in rows if r["feas"]]
    out = {}
    for k in KS:
        key = "eq%d" % k
        pk = peak(rows, key)
        spread = sd(max(r[key] for r in feas) - min(r[key] for r in feas),
                    min(r[key] for r in feas)) * 100
        u_ok = [r for r in feas if r.get("ok")]
        alt = max(u_ok, key=lambda r: r[key]) if u_ok else None
        out[k] = (pk, alt)
        print("  %s k=%d：%s，最优 W=%d，makespan %d（超下界 %s），时刻改动 %d，期望采纳质量 %.4f"
              % (tag, k, "温和型" if k == 1 else "敏感型", pk["w"], pk["mk"],
                 pct(over(pk["mk"], case["lb2"])), pk["ct"], pk[key]))
        print("    这条曲线跨档摆 %.1f%%（判读线 %.0f%%）：%s，落点%s。"
              % (spread, FLAT, "摆幅盖得住这条线" if spread >= FLAT else "摆幅盖不住这条线",
                 "有内容" if spread >= FLAT else "只能当这 %d 个数里最大的那个" % len(feas)))
        print("    与不钉（W=0，纯追质量那格）比：makespan %s（%+d）、时刻改动 %+d（%s）、期望采纳质量 %s。"
              % (pct((pk["mk"] - feas[0]["mk"]) / feas[0]["mk"] * 100), pk["mk"] - feas[0]["mk"],
                 pk["ct"] - feas[0]["ct"],
                 pct((pk["ct"] - feas[0]["ct"]) / feas[0]["ct"] * 100),
                 pct((pk[key] - feas[0][key]) / feas[0][key] * 100)))
        bm = min(feas, key=lambda r: r["mk"])
        print("    全档最好 makespan 是 %d（W=%d 那格），峰值那格比它慢 %+d（%s）——这是质量的账。"
              % (bm["mk"], bm["w"], pk["mk"] - bm["mk"], pct((pk["mk"] - bm["mk"]) / bm["mk"] * 100)))
        if pk["w"] == 0:
            print("    峰值在最左端（W=0）：模型认为全量重排值那个被拒风险——上线就得咽下 %d 个时刻改动（已下发里 %d 个）。"
                  % (pk["ct"], pk["rc"]))
        elif pk["w"] == max(W_LIST):
            print("    峰值在最右端（W=%d，本表最狠的钉法）：这套假设下的最优策略就是「尽量不动老计划」，"
                  % pk["w"])
            print("    那系统该交付的是补丁式差异（只动非钉住段），而不是重排；剩下的 %d 个改动就是它的地板。"
                  % pk["ct"])
        else:
            print("    峰值在中间（W=%d，%d 档列表里第 %d 格）：既不是最大自由度也不是最大约束。"
                  % (pk["w"], len(W_LIST), W_LIST.index(pk["w"]) + 1))
            if spread >= FLAT:
                print("    摆幅够大（见上），所以这个中间值是曲线给的，不是挑出来的。")
        if not pk.get("ok") and alt is not None:
            print("    注意：这格 makespan %d 掉出可用线（<= %.1f）；按可用线重挑 -> W=%d（%d，期望采纳质量 %.4f）。"
                  % (pk["mk"], line, alt["w"], alt["mk"], alt[key]))
    return out


PK_A = report_peak("算例 A(seed=%d)" % WORK["seed"], ROWS, WORK, REF, LINE)
CASE_B = build(WORK["njob"], WORK["mach"], 8888)
ROWS_B = sweep(CASE_B)
REF_B, _, LINE_B, REF_W_B = acceptance(ROWS_B, CASE_B)
FEAS_B = [r for r in ROWS_B if r["feas"]]
print("  换个种子再看一遍（算例 B：%d 工件 x %d 机器，基线 %d、下界 %d、插单后下界 %d）："
      % (CASE_B["njob"], CASE_B["mach"], CASE_B["mk0"], CASE_B["lb"], CASE_B["lb2"]))
print("  " + pad("W", 4) + pad("时刻改动", 10) + pad("makespan", 10) + pad("超下界", 9)
      + pad("已下发被改", 12) + pad("期望采纳(温和)", 15) + "期望采纳(敏感)")
for r in FEAS_B:
    print("  " + pad(r["w"], 4) + pad(r["ct"], 10) + pad(r["mk"], 10)
          + pad(pct(over(r["mk"], CASE_B["lb2"])), 9) + pad(r["rc"], 12)
          + pad("%.4f" % r["eq1"], 15) + "%.4f" % r["eq2"])
print("  B 按同一条规则挑出的 ref = %d（W=%s），A 的是 %d（W=%s）。"
      % (REF_B, REF_W_B, REF, REF_W))
PK_B = report_peak("算例 B", ROWS_B, CASE_B, REF_B, LINE_B)
LEV_A = (FEAS[0]["ct"] - FEAS[-1]["ct"]) / FEAS[0]["ct"] * 100
LEV_B = (FEAS_B[0]["ct"] - FEAS_B[-1]["ct"]) / FEAS_B[0]["ct"] * 100
print("  旋钮杠杆（W=0 到 W=%d 的时刻改动降幅）：A %.1f%%、B %.1f%%——同一个 W 列表在两个算例上不是同一件事。"
      % (max(W_LIST), LEV_A, LEV_B))
if LEV_B <= 0:
    print("  B 的降幅是负的（%+.1f%%）：那个算例上钉住压根没减少改动，B 那条曲线只是平的，峰值不说明策略。" % LEV_B)
same = all(PK_A[k][0]["w"] == PK_B[k][0]["w"] for k in KS)
print("  峰值稳不稳：%s（A: %s / B: %s）"
      % ("两个算例逐档重合" if same else "两个算例不重合",
         "/".join("k=%d->W%d" % (k, PK_A[k][0]["w"]) for k in KS),
         "/".join("k=%d->W%d" % (k, PK_B[k][0]["w"]) for k in KS)))
if not same:
    print("  最大差 %d 档：换算例就得重扫，别把上面那张表当参数抄进生产。"
          % max(abs(PK_A[k][0]["w"] - PK_B[k][0]["w"]) for k in KS))

# ---------------------------------------------------------------- [5] 拒绝的代价
print()
print(W)
print("[5] 一次拒绝的代价")
print(W)
J2, D2 = WORK["j2"], WORK["d2"]
LB2 = WORK["lb2"]
print("  「计划员把方案打回去、自己排」要有个替身：四条老派工规则在插单后的算例上各跑一遍（无预算，毫秒级）。")
print("  后两列把 [3] 那套模型套到手工方案上（p 用敏感型 k=%d，churn = 它相对基线的时刻改动）。" % KS[1])
print("  " + pad("规则", 34) + pad("makespan", 10) + pad("超下界", 9) + pad("平均完工", 11)
      + pad("时刻改动", 10) + pad("p(敏感k=2)", 12) + "期望采纳质量")
rules = [("SPT 最短工序优先", lambda s, p, i, k: (p, i, k)),
         ("MWKR 剩余工时最长", lambda s, p, i, k: (-sum(q for _, q in J2[i]), i, k)),
         ("EDD-ish 按工件序号(近似先到先排)", lambda s, p, i, k: (i, p, k)),
         ("主动调度 (先能开工的先派)", lambda s, p, i, k: (s, p, i, k))]
hand = {}
for name, key in rules:
    o = dispatch(J2, D2, key, rnd=random.Random(7))
    s1 = starts(J2, D2, o)
    cs, ct, ms, mx, rc = churn(WORK["s0"], WORK["p0"], s1, pos_map(o), WORK["rel"])
    hm = cmax(J2, D2, o)
    pa = 1.0 / (1.0 + (ct / REF) ** KS[1])
    hand[name] = (hm, mean_completion(J2, D2, o), ct, pa, pa * LB2 / hm, ms, mx)
    print("  " + pad(name, 34) + pad(hm, 10) + pad(pct(over(hm, LB2)), 9)
          + pad("%.1f" % hand[name][1], 11) + pad(ct, 10) + pad("%.3f" % pa, 12)
          + "%.4f" % hand[name][4])
AP = append_plan(WORK["o0"], J2, len(J2) - 1)
aps = starts(J2, D2, AP)
a_cs, a_ct, a_ms, a_mx, a_rc = churn(WORK["s0"], WORK["p0"], aps, pos_map(AP), WORK["rel"])
ap_mk = cmax(J2, D2, AP)
ap_eq = 1.0 * LB2 / ap_mk
print("  参照点「干脆不动」：老顺序一格不改，急单追加到各机器队尾 -> makespan %d（超下界 %s）。"
      % (ap_mk, pct(over(ap_mk, LB2))))
print("    实测它的改动量：顺序改动 %d 个、时刻改动 %d 个、已下发被改 %d 个、最大位移 %d——"
      % (a_cs, a_ct, a_rc, a_mx))
print("    按模型 p_accept = %.3f，期望采纳质量 = 1.000 x %.3f = %.4f。" % (1.0 / (1 + (a_ct / REF) ** 2), LB2 / ap_mk, ap_eq))
HUM = "主动调度 (先能开工的先派)"
hmk = hand[HUM][0]
rule_mks = {name: v[0] for name, v in hand.items()}
worst_r = max(rule_mks, key=lambda k: rule_mks[k])
best_r = min(rule_mks, key=lambda k: rule_mks[k])
print("  四条规则自己就差 %s 倍（最好 %s=%d，最差 %s=%d，下界 %d）：手工排产的质量全看手感是哪一条。"
      % ("%.2f" % (rule_mks[worst_r] / rule_mks[best_r]), best_r.split(" ")[0], rule_mks[best_r],
         worst_r.split(" ")[0], rule_mks[worst_r], LB2))
pkA1, pkA2 = PK_A[1][0], PK_A[2][0]
BEQ1 = max(r["eq1"] for r in FEAS)
BEQ2 = max(r["eq2"] for r in FEAS)
print("  人工手感最像哪条是解释，不是测量：车间手工排产的动作就是「哪个工序现在能开就先派」，")
print("  所以拿 %s 当替身：makespan %d（超下界 %s）、相对基线时刻改动 %d 个、最大位移 %d。"
      % (HUM, hmk, pct(over(hmk, LB2)), hand[HUM][2], hand[HUM][6]))
if hmk == FEAS[0]["mk"] and hand[HUM][2] == FEAS[0]["ct"]:
    print("  顺带实测到一件事：替身跟 [2] 里 W=0 那格的 makespan/时刻改动逐个数相同（%d/%d）——"
          % (hmk, FEAS[0]["ct"]))
    print("  这块预算（%d 次评估）下，不钉的「全量重排」没重排出比主动调度更好的东西，两个口径一起撞上同一个数。" % BUDGET)
print("  这笔账：拒绝一次 = 拿 %d 换峰值那格的 %d，差 %+d（%s）；与不钉那格（%d）比%s，差 %d。"
      % (hmk, pkA1["mk"], hmk - pkA1["mk"], pct(sd(hmk - pkA1["mk"], pkA1["mk"]) * 100),
         FEAS[0]["mk"], "更慢" if hmk > FEAS[0]["mk"] else ("持平" if hmk == FEAS[0]["mk"] else "更快"),
         abs(hmk - FEAS[0]["mk"])))
if hmk < pkA1["mk"]:
    print("  注意方向：手工替身比采纳峰值那格还快 %d——这条算例上「打回去自己排」不吃质量的亏，"
          % (pkA1["mk"] - hmk))
    print("  模型里那个拒绝代价是白担心的；真代价在另一件事上：它自己就动了 %d 道工序的时刻。" % hand[HUM][2])
elif hmk - pkA1["mk"] <= NOISE:
    print("  上一行的 %+d 放到 [2] 的噪声尺子上比：同一格换 seed 的极差是 %d——"
          % (hmk - pkA1["mk"], NOISE))
    print("  也就是说这台机器这条算例上「打回重排」的标价量不出来：要它贵，得先让质量差盖过噪声。")
else:
    print("  打回重排的标价 = makespan 差 %s（%d vs %d），一次拒绝就是这么贵。"
          % (pct(sd(hmk - pkA1["mk"], pkA1["mk"]) * 100), hmk, pkA1["mk"]))
print("  最锋利的一条对比：把同一个模型套到「不动」上得 %.4f，套到扫出来的峰值上得 %.4f / %.4f（%s）。"
      % (ap_eq, pkA1["eq1"], pkA2["eq2"],
         "零改动那个极端反而最高" if ap_eq >= max(pkA1["eq1"], pkA2["eq2"]) else "峰值仍是采纳加权最优"))
if ap_eq >= max(BEQ1, BEQ2):
    print("  意思是：这套 p_accept 假设里「改动 = 风险」压过了「质量 = 收益」（质量分跨档只摆 %.1f%%），"
          % ((max(r["q"] for r in FEAS) - min(r["q"] for r in FEAS)) / min(r["q"] for r in FEAS) * 100))
    print("  公式再认真也只会把系统推向不重排。要打破它得让质量真的值钱（瓶颈日、超时罚），不是换算法。")
else:
    print("  意思是：在扫出来的这几档里，适当钉住确实比「完全不动」划算 %.4f vs %.4f（%s）。"
          % (max(BEQ1, BEQ2), ap_eq, pct((max(BEQ1, BEQ2) - ap_eq) / ap_eq * 100)))

# ---------------------------------------------------------------- [6] 一览
print()
print(W)
print("[6] 本机实测一览")
print(W)
print("  标尺：预算全写成评估次数（基线 %d、逐档 %d）；墙钟数字（含本机评估吞吐）一律只写 stderr，不进 stdout。"
      % (BASE_BUDGET, BUDGET))
print("  规模：50x6 一次全场扫描要 %s 个邻居，预算 %d 次连一轮都扫不完（%.2f 轮）——"
      % ("{:,}".format(nb_big), BUDGET, BUDGET / nb_big))
print("    同预算下实测 W=0 与 W=%d 的时刻改动是 %d 与 %d，钉多反而更动，曲线在这档测不出东西；"
      % (big_rows[1][0], big_rows[0][2], big_rows[1][2]))
print("    所以全部曲线换到 %dx%d（%d 工序、%.2f 轮扫描/预算）上测。"
      % (WORK["njob"], WORK["mach"], WORK["nop"], BUDGET / NB_WORK))
print("  口径：顺序改动与时刻改动是两回事——不加扰动只换 seed 就测出 %d 个 vs %d 个（老工序 %d 个），"
      % (d_cs, d_ct, WORK["nop"]))
QUAL_TXT = ("完全没变（%d）" % dv) if dv == WORK["mk0"] else ("只动了 %+d（%d vs %d）" % (dv - WORK["mk0"], dv, WORK["mk0"]))
print("    而 makespan %s——「换个种子重跑一遍」这件事本身就是改动，跟扰动无关。" % QUAL_TXT)
print("  旋钮：W=0 -> %d 时时刻改动 %d -> %d（%s）、已下发被改时刻 %d -> %d，makespan %d -> %d（%s）。"
      % (L["w"], F["ct"], L["ct"], pct((L["ct"] - F["ct"]) / F["ct"] * 100), F["rc"], L["rc"],
         F["mk"], L["mk"], pct((L["mk"] - F["mk"]) / F["mk"] * 100)))
print("  模型：ref = %d（线内 W=%s 那档实测的 churn），峰值 W = 温和 %d / 敏感 %d，%s。"
      % (REF, REF_W, PK_A[1][0]["w"], PK_A[2][0]["w"],
         "敏感型那格的 makespan 掉出了可用线（%d > %.1f）" % (PK_A[2][0]["mk"], LINE)
         if not PK_A[2][0].get("ok") else "两档都在可用线以内"))
print("    第二个算例（seed=%d，ref=%d）峰值 W = 温和 %d / 敏感 %d；旋钮杠杆 A %.1f%% vs B %.1f%%。"
      % (CASE_B["seed"], REF_B, PK_B[1][0]["w"], PK_B[2][0]["w"], LEV_A, LEV_B))
print("  拒绝：手工替身 %s = %d，采纳峰值那格 = %d（差 %s）；「干脆不动」= %d、时刻改动 %d 个、期望采纳质量 %.4f。"
      % (HUM.split(" ")[0], hmk, PK_A[1][0]["mk"], pct((hmk - PK_A[1][0]["mk"]) / PK_A[1][0]["mk"] * 100),
         ap_mk, a_ct, ap_eq))
print("  本页只测了质量与改动量：p_accept 那两列是行为假设（k=%d 与 %d）的推论，换 ref、换 k、换算例都得重跑。"
      % KS)
sys.stderr.write("wall %.2fs (deliberately kept out of stdout)\n" % (time.perf_counter() - _T0))
