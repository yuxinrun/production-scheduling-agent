# -*- coding: utf-8 -*-
"""把排产项目自己的排期当成一个调度问题来算：关键路径、资源受限工期、加人的收益、
逐个任务的延期敏感性，以及「先修数据还是先写内核」这两条路线的实测差距。

用法:  python roadmap_probe.py          （纯标准库，无第三方依赖）

  [1] 任务网络：15 个落地任务、依赖、所需角色——先把「分三期」换成一张 DAG
  [2] 关键路径（CPM）：无限资源下的最短工期、每个任务的最早/最晚、总松弛
  [3] 资源受限：每个角色只有 1 人时，工期涨到多少，瓶颈在哪个角色
  [4] 加人有用吗：瓶颈角色加到 2/3 人、把人推到无限，以及「砍任务」能不能换到周数
  [5] 延期敏感性：哪个任务拖 1 周会推后整体，哪些任务在 CPM 里「有松弛」但其实会疼
  [6] 三条路线：先修数据 / 算法不等数据 / UI 先上，工期差与返工面
  [7] 一次跑完的结论

这一页的数字全是结构量（周数、松弛、占用），不依赖机器速度，换机器不变。
"""
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

W = "=" * 74

# ------------------------------------------------------------------ 任务网络
# (id, 名称, 工期(周), 依赖, 角色)
TASKS = [
    ("T01", "现场调研 + 工艺数据采集", 3, [], "数据"),
    ("T02", "主数据清洗与数据字典", 4, ["T01"], "数据"),
    ("T03", "建模：工序/机器/日历", 3, ["T02"], "算法"),
    ("T04", "派工规则基线（4 条）", 2, ["T03"], "算法"),
    ("T05", "评估函数 + 平凡下界", 1, ["T03"], "算法"),
    ("T06", "爬山 / 元启发式", 3, ["T05"], "算法"),
    ("T07", "精确通道（CP/分支定界）", 3, ["T05"], "算法"),
    ("T08", "影子模式评测集", 2, ["T04", "T05"], "算法"),
    ("T09", "工作台 UI：甘特 + 拖拽", 5, ["T03"], "前端"),
    ("T10", "增量评估（闭包重算）", 3, ["T06", "T09"], "算法"),
    ("T11", "护栏与权限", 2, ["T03"], "后端"),
    ("T12", "审计与留痕", 2, ["T11"], "后端"),
    ("T13", "冻结窗口：按时刻钉", 2, ["T06"], "算法"),
    ("T14", "试运行 + 采纳跟踪", 4, ["T08", "T09", "T12"], "现场"),
    ("T15", "验收口径与回归基线", 2, ["T08"], "现场"),
]
DUR = {t[0]: t[2] for t in TASKS}
NAME = {t[0]: t[1] for t in TASKS}
DEPS = {t[0]: list(t[3]) for t in TASKS}
ROLE = {t[0]: t[4] for t in TASKS}
ORDER = [t[0] for t in TASKS]
ROLES = sorted({t[4] for t in TASKS})
LOAD = {r: sum(DUR[k] for k in ORDER if ROLE[k] == r) for r in ROLES}
TOT = sum(LOAD.values())


def dw(s):
    return sum(2 if ord(c) > 0x2E80 else 1 for c in str(s))


def pad(s, n):
    s = str(s)
    return s + " " * max(0, n - dw(s))


def succ_of(deps):
    s = {k: [] for k in ORDER}
    for k, ds in deps.items():
        for d in ds:
            s[d].append(k)
    return s


def cpm(deps=None, dur=None):
    """正向 ES/EF，反向 LS/LF，总松弛 = LS - ES。"""
    deps = deps or DEPS
    dur = dur or DUR
    es, ef = {}, {}
    for k in ORDER:                       # ORDER 本身已是拓扑序，删边不会破坏
        es[k] = max([ef[d] for d in deps[k]], default=0)
        ef[k] = es[k] + dur[k]
    T = max(ef.values())
    sc = succ_of(deps)
    lf, ls = {}, {}
    for k in reversed(ORDER):
        lf[k] = min([ls[s] for s in sc[k]], default=T)
        ls[k] = lf[k] - dur[k]
    slack = {k: ls[k] - es[k] for k in ORDER}
    return (es, ef, ls, lf, slack), T


def rcps(cap, deps=None, alpha=0.0):
    """串行调度生成方案（serial SGS）：每步只在「前置都已完成」的任务里挑优先级最高的。
       优先级 = (CPM 最早开始, -松弛)；同角色同时最多 cap[role] 个任务。
       同一任务在本角色的 cap 人之间平分：工期 = dur*(1+alpha*(n-1))/n，alpha=0 理想、0.3 Brooks。
       返回 (开始, 完成, 端到端周数, 消耗人周)。"""
    deps = deps or DEPS
    (es, ef, ls, lf, slack), _ = cpm(deps)
    busy = {r: [] for r in ROLES}
    st, fi = {}, {}
    cost = 0
    todo = set(ORDER)
    while todo:
        cand = [k for k in ORDER
                if k in todo and all(d not in todo for d in deps[k])]
        k = min(cand, key=lambda x: (es[x], -slack[x], x))
        todo.discard(k)
        r = ROLE[k]
        n = cap[r]
        if DUR[k] == 0:
            dur = 0
        else:
            dur = max(1, int(round(DUR[k] * (1 + alpha * (n - 1)) / n)))
        cost += dur * n
        t = max([fi[d] for d in deps[k]], default=0)

        def ok(x):
            return all(sum(1 for a, b in busy[r] if a <= y < b) < n for y in range(x, x + dur))
        while not ok(t):
            t += 1
        busy[r].append((t, t + dur))
        st[k], fi[k] = t, t + dur
    return st, fi, max(fi.values()), cost


# ---------------------------------------------------------------- [1] DAG
print()
print(W)
print("[1] 任务网络：先把「分三期」换成一张 DAG")
print(W)
print("  15 个任务、%d 条依赖边、%d 个角色；工期单位是周，不是「人月」。"
      % (sum(len(v) for v in DEPS.values()), len(ROLES)))
print("  " + pad("任务", 6) + pad("名称", 28) + pad("周", 4) + pad("角色", 6) + "前置")
for k in ORDER:
    print("  " + pad(k, 6) + pad(NAME[k], 28) + pad(DUR[k], 4) + pad(ROLE[k], 6)
          + ("—" if not DEPS[k] else ",".join(DEPS[k])))
print("  依赖边数 %d，任务 %d 个 -> 平均每个任务 %s 个前置。这张图不复杂，"
      "复杂的是「大家都想先做 T09 甘特图」，而它的前置只有 T03。"
      % (sum(len(v) for v in DEPS.values()), len(ORDER),
         "%.1f" % (sum(len(v) for v in DEPS.values()) / len(ORDER))))

# ---------------------------------------------------------------- [2] CPM
print()
print(W)
print("[2] 关键路径：资源无限时最快多少周")
print(W)
(es, ef, ls, lf, slack), T0 = cpm()
crit = [k for k in ORDER if slack[k] == 0]
print("  端到端最短工期（资源无限）= %d 周；关键任务 %d 个：%s" % (T0, len(crit), " -> ".join(crit)))
print("  " + pad("任务", 6) + pad("最早开始", 9) + pad("最早完成", 9) + pad("最晚开始", 9)
      + pad("最晚完成", 9) + pad("总松弛", 8) + "关键路径")
for k in ORDER:
    print("  " + pad(k, 6) + pad(es[k], 9) + pad(ef[k], 9) + pad(ls[k], 9) + pad(lf[k], 9)
          + pad(slack[k], 8) + ("是" if slack[k] == 0 else "否"))
print("  " + pad("角色", 8) + pad("任务数", 8) + pad("工作量(人周)", 13) + "占比")
for r in ROLES:
    print("  " + pad(r, 8) + pad(sum(1 for k in ORDER if ROLE[k] == r), 8)
          + pad(LOAD[r], 13) + "%.0f%%" % (LOAD[r] / TOT * 100))
print("  总量 %d 人周。资源无限的 %d 周没有意义——没有人是无限的。下一节每个角色只给 1 人。" % (TOT, T0))

# ---------------------------------------------------------------- [3] 资源受限
print()
print(W)
print("[3] 资源受限：每角色 1 人，工期涨到多少")
print(W)
cap1 = {r: 1 for r in ROLES}
st1, fi1, T1, _c1 = rcps(cap1)
print("  每角色 1 人的串行调度：端到端 %d 周，比资源无限多 %d 周（+%.0f%%）"
      % (T1, T1 - T0, (T1 - T0) / T0 * 100))
print("  " + pad("任务", 6) + pad("CPM最早", 9) + pad("实际开始", 9) + pad("实际完成", 9)
      + pad("被推迟", 8) + pad("角色", 6) + "名称")
for k in sorted(ORDER, key=lambda x: (st1[x], x)):
    print("  " + pad(k, 6) + pad(es[k], 9) + pad(st1[k], 9) + pad(fi1[k], 9)
          + pad(st1[k] - es[k], 8) + pad(ROLE[k], 6) + NAME[k])
delay = {r: sum(st1[k] - es[k] for k in ORDER if ROLE[k] == r) for r in ROLES}
bn = max(delay, key=lambda r: delay[r])
print("  累计推迟最多的是「%s」：%d 周·任务（该角色 %d 个任务 / %d 人周）。"
      % (bn, delay[bn], sum(1 for k in ORDER if ROLE[k] == bn), LOAD[bn]))
print("  算法角色占 %d/%d 个任务、%d/%d 人周（%.0f%% / %.0f%%）——"
      % (sum(1 for k in ORDER if ROLE[k] == "算法"), len(ORDER), LOAD["算法"], TOT,
         sum(1 for k in ORDER if ROLE[k] == "算法") / len(ORDER) * 100, LOAD["算法"] / TOT * 100))
print("    瓶颈不是「人手不够」这个形容词，是「同一个角色同时要干几件事」这个队列。")
last = max(ORDER, key=lambda k: fi1[k])
print("  最晚完成的实际任务是 %s（%s，第 %d~%d 周）；它在 CPM 关键路径上吗 = %s。"
      % (last, NAME[last], st1[last], fi1[last], "是" if slack[last] == 0 else "否"))
print("  关键路径任务里，实际开始时间被推迟最多的：%s。"
      % max(crit, key=lambda k: st1[k] - es[k]))
print("  各角色在这 %d 周里真的干了几周（区间取并，一个人不能同时干两件事）：" % T1)
print("  " + pad("角色", 8) + pad("忙(周)", 8) + pad("空档(周)", 9) + pad("最长连续", 10)
      + pad("利用率", 9) + "空档在哪")
runs = []
for r in ROLES:
    iv = sorted((st1[k], fi1[k]) for k in ORDER if ROLE[k] == r)
    busy = len(set(x for a, b in iv for x in range(a, b)))
    best_run = run = 0
    gaps = []
    prev = 0
    for a, b in iv:
        if a > prev:
            gaps.append("%d~%d" % (prev, a))
            run = 0
        run += b - a
        best_run = max(best_run, run)
        prev = max(prev, b)
    if prev < T1:
        gaps.append("%d~%d" % (prev, T1))
    runs.append((r, busy, T1 - busy, best_run))
    print("  " + pad(r, 8) + pad(busy, 8) + pad(T1 - busy, 9) + pad(best_run, 10)
          + pad("%.0f%%" % (busy / T1 * 100), 9) + (" ".join(gaps) or "没有空档"))
idle = [x for x in runs if x[1] / T1 < 0.9 and x[2] > 0]
tight = max(runs, key=lambda x: x[3])
print("  最长连续不断工的是「%s」：%d 周里连轴转 %d 周；其余角色最长按 %d 个连续周计。"
      % (tight[0], T1, tight[3], max(x[3] for x in runs if x[0] != tight[0])))
print("  「连续 %d 周一天不停」就是瓶颈的定义——不是任务数最多，是一周空隙都没有。" % tight[3])
print("  反过来，前端只有 1 个任务、5 周活，在 %d 周的项目里空 %d 周：%s。"
      % (T1, [x for x in runs if x[0] == "前端"][0][2],
         "给前端加人、提前给前端排活，都换不到工期"))

# ---------------------------------------------------------------- [4] 加人
print()
print(W)
print("[4] 加人有用吗：瓶颈角色加到 2 人 / 3 人，再算砍任务")
print(W)
print("  两个模型（第二个是「关于协作的假设」，不是测量，所以两个都印出来对照）：")
print("    共同假设：一个任务能在本角色的人之间平分，同角色同时最多 cap 个任务。")
print("    理想：n 人做同一任务，工期 = dur/n")
print("    Brooks：工期 = dur x (1 + 0.3 x (n-1)) / n  ->  2 人 0.65x，3 人 0.533x")
print("    「占用」= 人头 x 端到端周数（项目把人占掉的人周，这才是预算付的东西；"
      "工作量另外算，本项目 %d 人周）。" % TOT)
print("  " + pad("配置", 22) + pad("理想(周)", 9) + pad("Brooks(周)", 12) + pad("人头", 7)
      + pad("占用(人·周)", 12) + "省下（理想/Brooks 周）")
rows4 = []
Tb = T1
for label, cap in (("每角色 1 人（基线）", {r: 1 for r in ROLES}),
                   ("算法 2 人", {**cap1, "算法": 2}),
                   ("算法 + 前端 2 人", {**cap1, "算法": 2, "前端": 2}),
                   ("算法 3 人，其余 1", {**cap1, "算法": 3}),
                   ("算法 + 现场 2 人", {**cap1, "算法": 2, "现场": 2}),
                   ("全员 2 人", {r: 2 for r in ROLES}),
                   ("全员 3 人", {r: 3 for r in ROLES})):
    _, _, i, _ = rcps(cap)
    _, _, b, _ = rcps(cap, alpha=0.3)
    heads = sum(cap.values())
    rows4.append((label, cap, i, b, heads, heads * b))
    print("  " + pad(label, 22) + pad(i, 9) + pad(b, 12) + pad(heads, 7) + pad(heads * b, 12)
          + "%+d / %+d 周" % (i - Tb, b - Tb))
best = min(rows4, key=lambda r: r[3])
cheap = min(rows4, key=lambda r: r[5])
base_occ = rows4[0][5]
print("  周数最少：%s（Brooks %d 周，占用 %d 人·周）；占用最少：%s（占用 %d 人·周，%d 周）。"
      % (best[0], best[3], best[5], cheap[0], cheap[5], cheap[3]))
print("  「最快」和「最省占用」%s同一个配置——先定目标函数，再谈排期。"
      % ("是" if best[0] == cheap[0] else "不是"))
print("  每提前 1 周，占用往哪边走（Brooks 口径，基线 %d 周 / %d 人·周）：" % (rows4[0][3], base_occ))
for label, cap, i, b, heads, occ in rows4[1:]:
    w = Tb - b
    d = occ - base_occ
    if w <= 0:
        tail = "周数没换到，纯多付 %d 人·周" % d if d else "周数没换到，占用还涨了"
    elif d < 0:
        tail = "时间和占用一起省（项目早收工，这种不用纠结）"
    else:
        tail = "开始用占用买时间：每买 1 周 +%.1f 人·周" % (d / w)
    print("    %s 提前 %d 周，占用 %+d 人·周 -> %s" % (pad(label, 20), w, d, tail))
floor_i = rcps({r: 99 for r in ROLES})[2]
ones = cpm(DEPS, {k: 1 for k in ORDER})[1]
print("  把 cap 推到 99（人要多少给多少）：端到端 %d 周，和「每个任务只占 1 周时的最长链」%d 周相等——"
      % (floor_i, ones))
print("    因为模型不许一个任务压到 1 周以下。到这一步再加人一点用没有，"
      "能动的只有「链上有几个任务」，也就是下面那张砍任务表。")
print("  砍任务对照（工期置 0，其余不变）：加速的另一条路，量一量它到底省几周。")
print("  " + pad("砍掉", 6) + pad("名称", 28) + pad("省人周", 8) + pad("理想省", 8)
      + pad("资源受限省", 11) + "换到的是")
drops = []
for k in ORDER:
    old = DUR[k]
    DUR[k] = 0
    dT0 = T0 - cpm()[1]
    _, _, dTr, dCost = rcps(cap1)
    DUR[k] = old
    drops.append((k, T1 - dTr, dT0, old))
for k, save_r, save_i, old in sorted(drops, key=lambda x: (-x[1], -x[2], -x[3])):
    if save_r == 0 and save_i == 0:
        continue
    if save_r > 0 and save_i > 0:
        tag = "两个口径都提前"
    elif save_r > 0:
        tag = "只有资源受限口径提前（CPM 看不出来）"
    else:
        tag = "纸面提前，队列里换不到"
    print("  " + pad(k, 6) + pad(NAME[k], 28) + pad(old, 8)
          + pad("-%d周" % save_i if save_i else "不动", 8)
          + pad("-%d周" % save_r if save_r else "不动", 11) + tag)
silent = [x for x in drops if x[1] == 0]
hard = [x for x in drops if x[1] == 0 and x[2] == 0]
print("  按资源受限口径，砍掉 %d 个任务交付一周都不动（%s）——"
      % (len(silent), " ".join(x[0] for x in silent)))
print("    其中 %d 个连 CPM 口径也不动，省下的 %d 人周叫减范围，不叫加速。"
      % (len(hard), sum(x[3] for x in hard)))
print("    工期只认关键链，不认「我们少干点活吧」这个意愿。")

# ---------------------------------------------------------------- [5] 敏感性
print()
print(W)
print("[5] 延期敏感性：谁拖一周会推后整体，谁拖了没人发现")
print(W)
print("  口径：把单个任务工期 +1 周，分别看资源无限（CPM）与资源受限（每角色 1 人）的端到端变化。")
print("  " + pad("任务", 6) + pad("名称", 28) + pad("松弛", 6) + pad("CPM影响", 9)
      + pad("资源受限影响", 13) + "判读")
sens = []
for k in ORDER:
    old = DUR[k]
    DUR[k] = old + 1
    T2 = cpm()[1]
    T2r = rcps(cap1)[2]
    DUR[k] = old
    sens.append((k, T2 - T0, T2r - T1))
for k, d1, d2 in sens:
    if d1 > 0 and d2 > 0:
        tag = "两个口径都晚一周"
    elif d1 > 0:
        tag = "纸面关键，队列里被吸收"
    elif d2 > 0:
        tag = "CPM 说没关系，实际晚一周"
    else:
        tag = "整体不受影响"
    print("  " + pad(k, 6) + pad(NAME[k], 28) + pad(slack[k], 6) + pad("+%d周" % d1, 9)
          + pad("+%d周" % d2, 13) + tag)
hot = [x for x in sens if x[1] > 0]
cold = [x for x in sens if x[1] == 0]
queue = [x for x in sens if x[1] == 0 and x[2] > 0]
both = [x for x in sens if x[1] > 0 and x[2] > 0]
ghost = [x for x in sens if x[1] > 0 and x[2] == 0]
none = [x for x in sens if x[1] == 0 and x[2] == 0]
print("  两个口径都躲不掉的（%d 个）：%s" % (len(both), " ".join(x[0] for x in both)))
print("  只有资源受限会晚的（%d 个）：%s" % (len(queue), " ".join(x[0] for x in queue)))
print("    这些任务在 CPM 里有松弛，PM 说「没关系」；每角色只有 1 人时，它一拖，交付就拖。")
print("    「PM 说这个有松弛」和「实际拖了没关系」是两句话。差别就是这一行。")
print("  纸面关键、实际被队列吸收的（%d 个）：%s"
      % (len(ghost), " ".join(x[0] for x in ghost) or "无"))
print("  两边都不敏感的（%d 个）：%s" % (len(none), " ".join(x[0] for x in none)))

# ---------------------------------------------------------------- [6] 两条路线
print()
print(W)
print("[6] 三条路线：先修数据、算法不等数据、UI 先上")
print(W)
print("  路线 A（本手册的建议）：调研 -> 清洗 -> 建模 -> 其余全挂在这条链上。")
print("    资源无限 %d 周，资源受限 %d 周。" % (T0, T1))
d_b = {k: list(DEPS[k]) for k in ORDER}
d_b["T03"] = [x for x in d_b["T03"] if x != "T02"]        # 算法组不等数据
(esb, efb, lsb, lfb, slb), Tb2 = cpm(d_b)
Tbr = rcps(cap1, d_b)[2]
print("  路线 B（很常见）：算法不等数据，用假数据先把内核做完 = 删掉 T02->T03 这条边。")
print("    资源无限 %d 周（省 %d），资源受限 %d 周（省 %d）。" % (Tb2, T0 - Tb2, Tbr, T1 - Tbr))
d_c = {k: list(DEPS[k]) for k in ORDER}
d_c["T09"] = []                                            # UI 不等建模
(esc, efc, lsc, lfc, slc), Tc = cpm(d_c)
Tcr = rcps(cap1, d_c)[2]
print("  路线 C（更常见）：UI 先画甘特 = 把 T09 的前置摘掉。")
print("    资源无限 %d 周（省 %d），资源受限 %d 周（省 %d）。" % (Tc, T0 - Tc, Tcr, T1 - Tcr))
print("  工期差距其实很小：最多省 %d 周（理想）/%d 周（资源受限）。"
      % (max(T0 - Tb2, T0 - Tc), max(T1 - Tbr, T1 - Tcr)))


def downstream(root, deps=None):
    deps = deps or DEPS
    sc = succ_of(deps)
    seen, stack = set(), list(sc[root])
    while stack:
        x = stack.pop()
        if x in seen:
            continue
        seen.add(x)
        stack.extend(sc[x])
    return seen


for tag, root, deps in (("A", "T02", DEPS), ("B", "T02", d_b), ("C", "T03", DEPS)):
    ds = downstream(root, deps)
    print("  %s：从 %s 出发，下游有 %d 个任务依赖它的产出（占 %d 个任务的 %.0f%%）。"
          % (tag, root, len(ds), len(ORDER), len(ds) / len(ORDER) * 100))
ds_b2 = downstream("T02", DEPS)
ds_b = downstream("T02", d_b)
print("  摘掉 T02->T03 之后，T02 的下游闭包从 %d 个缩到 %d 个——"
      % (len(downstream("T02", DEPS)), len(downstream("T02", d_b))))
print("    省下的 %d 周是账面的；账下的是「建模改一次，下游 %d 个任务返工一次」。"
      % (T0 - Tb2, len(ds_b2)))
print("  本手册为什么把「先修数据，再谈智能」放在落地第一篇：%d 个下游任务里，"
      "有 %d 个的最终产出直接取决于清洗质量（算法/现场角色）。"
      % (len(downstream("T02", DEPS)),
         sum(1 for k in downstream("T02", DEPS) if ROLE[k] in ("算法", "现场"))))

# ---------------------------------------------------------------- [7] 一览
print()
print(W)
print("[7] 一次跑完的结论")
print(W)
print("  任务：%d 个、%d 条依赖边、%d 个角色、总工作量 %d 人周（算法占 %.0f%%）。"
      % (len(ORDER), sum(len(v) for v in DEPS.values()), len(ROLES), TOT, LOAD["算法"] / TOT * 100))
print("  工期：资源无限 %d 周 -> 每角色 1 人 %d 周（+%d 周，+%.0f%%）。"
      % (T0, T1, T1 - T0, (T1 - T0) / T0 * 100))
print("  关键路径：%s（%d 个任务，松弛全为 0）。" % (" -> ".join(crit), len(crit)))
print("  加人（Brooks 口径）：周数最少 %s -> %d 周；占用最少 %s -> %d 人·周（基线 %d）。"
      % (best[0], best[3], cheap[0], cheap[5], base_occ))
print("  敏感性：拖一周就晚交付的，CPM 口径 %d 个、资源受限口径 %d 个；"
      "其中 %d 个只有资源模型会疼，%d 个两边都不敏感。"
      % (len(hot), len([x for x in sens if x[2] > 0]), len(queue), len(none)))
print("  砍任务：%d 个砍下去交付不动（其中 %d 个连纸面都不动，白省 %d 人周），%d 个真能缩短交付。"
      % (len(silent), len(hard), sum(x[3] for x in hard), len([x for x in drops if x[1] > 0])))
print("  路线：不等数据省 %d 周（资源受限省 %d 周），但 T02 的下游有 %d 个任务。"
      % (T0 - Tb2, T1 - Tbr, len(ds_b2)))
