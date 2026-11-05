import itertools
import random
import statistics

JOBS = [[(0, 5), (2, 1), (1, 4)],
        [(1, 2), (2, 4), (0, 5)],
        [(2, 3), (1, 5), (0, 6)],
        [(1, 6), (2, 6), (0, 1)]]
M, N = 3, len(JOBS)

# ---- 1. 平凡下界 ----
job_paths = [sum(p for _, p in j) for j in JOBS]
load = [0] * M
for j in JOBS:
    for k, p in j:
        load[k] += p
job_lb, mac_lb = max(job_paths), max(load)
trivial = max(job_lb, mac_lb)
print("每机器负载 =", load, " 每工件链长 =", job_paths)
print("LB1 工件链 =", job_lb, " LB2 机器负载 =", mac_lb, " 平凡下界 =", trivial)

# ---- 2. 析取图全枚举求最优 ----
ops_of = {k: [] for k in range(M)}
for i, j in enumerate(JOBS):
    for o, (k, p) in enumerate(j):
        ops_of[k].append((i, o))


def longest_path(order):
    """给定每台机器的加工顺序，返回关键路径长度（=该排序下的最早可能完工时间）。
    若析取图有环，说明这组顺序互相矛盾，返回 None。"""
    succ = {}
    for i, j in enumerate(JOBS):
        for o in range(len(j) - 1):
            succ.setdefault((i, o), []).append((i, o + 1))
    for seq in order.values():
        for a, b in zip(seq, seq[1:]):
            succ.setdefault(a, []).append(b)
    memo, on_stack = {}, set()

    def tail(node):
        if node in memo:
            return memo[node]
        if node in on_stack:
            raise ValueError("cycle")
        on_stack.add(node)
        i, o = node
        v = JOBS[i][o][1] + max([tail(x) for x in succ.get(node, [])] or [0])
        on_stack.discard(node)
        memo[node] = v
        return v

    try:
        return max(tail((i, 0)) for i in range(N))
    except ValueError:
        return None


combos = list(itertools.product(*[itertools.permutations(ops_of[k]) for k in range(M)]))
best, how_many, infeasible = None, 0, 0
for perm in combos:
    c = longest_path({k: list(perm[k]) for k in range(M)})
    if c is None:
        infeasible += 1
        continue
    if best is None or c < best:
        best, how_many = c, 1
    elif c == best:
        how_many += 1
OPT = best
print("排序组合数 =", len(combos), " 其中互相矛盾(成环) =", infeasible)
print("最优 makespan =", OPT, " 并列最优的排序组数 =", how_many)

# ---- 3. 机器分解界：每台机器解 1|r_j,q_j|Cmax，取 max ----
ES, TAIL = {}, {}
for i, j in enumerate(JOBS):
    t = 0
    for o, (k, p) in enumerate(j):
        ES[(i, o)] = t
        t += p
    t = 0
    for o in reversed(range(len(j))):
        TAIL[(i, o)] = t
        t += j[o][1]

vals = {}
for k in range(M):
    cand = []
    for perm in itertools.permutations(ops_of[k]):
        e, z = 0, 0
        for node in perm:
            s = max(e, ES[node])
            e = s + JOBS[node[0]][node[1]][1]
            z = max(z, e + TAIL[node])
        cand.append(z)
    vals[k] = min(cand)
mb = max(vals.values())
print("每台机器 1|rj,qj|Cmax 精确值 =", vals, " 机器分解界 =", mb)

# ---- 4. 三种 gap 口径 ----
for SOL in (OPT + 2, 32):
    print(f"手里的解 = {SOL}   vs 平凡下界 {(SOL - trivial) / trivial * 100:5.1f}%"
          f"   vs 分解界 {(SOL - mb) / mb * 100:5.1f}%   vs 真实最优 {(SOL - OPT) / OPT * 100:5.1f}%")
print("下界自己离最优:", f"{(OPT - trivial) / trivial * 100:.1f}%", "->", f"{(OPT - mb) / mb * 100:.1f}%")

# ---- 5. 「人工计划」上界：机器上按工件号排 ----
naive = longest_path({k: sorted(ops_of[k]) for k in range(M)})
print("按工件号顺序的朴素计划 makespan =", naive, " 比最优差", f"{(naive - OPT) / OPT * 100:.1f}%")

# ---- 6. 随机「工序序列编码」构造可行解 ----
random.seed(7)
seen = set()
for _ in range(20000):
    genes = [i for i in range(N) for _ in JOBS[i]]
    random.shuffle(genes)
    ptr, job_free, mach_free = [0] * N, [0] * N, [0] * M
    order = {k: [] for k in range(M)}
    for i in genes:
        o = ptr[i]
        k, p = JOBS[i][o]
        s = max(job_free[i], mach_free[k])
        job_free[i] = mach_free[k] = s + p
        ptr[i] += 1
        order[k].append((i, o))
    seen.add(longest_path(order))
print("随机 20000 个可行解的 makespan 取值 =", sorted(seen))
print("随机最好 =", min(seen), " 随机最差 =", max(seen))

# ---- 7. 两目标：(makespan, 总完工时间) 的下界是「向量」，而且角点不可达 ----
acyclic = []
for perm in combos:
    c = longest_path({k: list(perm[k]) for k in range(M)})
    if c is not None:
        acyclic.append(c)
print()
print("无环排序组数 =", len(acyclic), " 其中达到最优的占比 =",
      f"{sum(1 for c in acyclic if c == OPT) / len(acyclic) * 100:.2f}%")
print("无环排序的 makespan: 平均", f"{statistics.mean(acyclic):.1f}",
      " 中位", statistics.median(acyclic), " 最差", max(acyclic))


def starts(order):
    """给定无环的机器顺序，算每个工序的最早开工时间（从 0 起单调上推的不动点迭代）。"""
    st = {(i, o): 0 for i, j in enumerate(JOBS) for o in range(len(j))}
    for _ in range(N * M + 2):
        changed = False
        for k, seq in order.items():
            prev = None
            for node in seq:
                i, o = node
                lo = st[(i, o - 1)] + JOBS[i][o - 1][1] if o else 0
                if prev is not None:
                    lo = max(lo, st[prev] + JOBS[prev[0]][prev[1]][1])
                if st[node] != lo:
                    st[node] = lo
                    changed = True
                prev = node
        if not changed:
            break
    return st


sched = set()
for perm in combos:
    order = {k: list(perm[k]) for k in range(M)}
    cmax = longest_path(order)
    if cmax is None:
        continue
    st = starts(order)
    assert max(s + JOBS[i][o][1] for (i, o), s in st.items()) == cmax, "不动点没收敛"
    sum_c = sum(st[(i, len(JOBS[i]) - 1)] + JOBS[i][-1][1] for i in range(N))
    sched.add((cmax, sum_c))

pts = sorted(sched)
def dominates(p, q):
    """q 支配 p：q 的每个目标都不比 p 差，且至少一个严格更好。"""
    return all(b <= a for a, b in zip(p, q)) and q != p
front = [p for p in pts if not any(dominates(p, q) for q in pts)]
print("两目标不重复解点 =", len(pts), " 个，Pareto 前沿 =", front)
lb_cmax = trivial
lb_sumc = sum(sum(p for _, p in j) for j in JOBS)
print("下界向量 = (Cmax", lb_cmax, ", sumC", lb_sumc, ")  这个角点可达吗？",
      (lb_cmax, lb_sumc) in sched)
print("前沿里 sumC 最小 =", min(f[1] for f in front),
      "  Cmax 最小 =", min(f[0] for f in front))

# ---- 8. 换成「总拖期」：单目标最优落在不同的解上 ----
chain = [sum(p for _, p in j) for j in JOBS]
DUE = [10, 12, 15, 14]
sched2 = set()
for perm in combos:
    order = {k: list(perm[k]) for k in range(M)}
    cmax = longest_path(order)
    if cmax is None:
        continue
    st = starts(order)
    c_i = [st[(i, len(JOBS[i]) - 1)] + JOBS[i][-1][1] for i in range(N)]
    sched2.add((cmax, sum(max(0, c - d) for c, d in zip(c_i, DUE))))
pts2 = sorted(sched2)
front2 = [p for p in pts2 if not any(dominates(p, q) for q in pts2)]
print("工件链长 =", chain, " 交期 =", DUE)
print("(Cmax, 总拖期) 不重复解点 =", len(pts2), " 前沿 =", front2)
print("各自单目标最优: Cmax =", min(p[0] for p in pts2),
      " 总拖期 =", min(p[1] for p in pts2))
