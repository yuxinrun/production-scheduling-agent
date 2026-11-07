---
title: 代码：从贪心到 CP-SAT 到 Agent —— 15 分钟跑通一个最小排产内核
description: 一份 12 工件 × 4 机器、seed 写死的作业车间算例，五级台阶逐级实测：80 行纯标准库评估器（前向传播 + 环检测即可行性判据）、四条贪心规则零成本买到 makespan=140、CP-SAT 子进程隔离（本机 ortools 原生崩溃而主进程毫发无损——降级链的第一课）、增量评估只走访 32.5% 的工序把吞吐放大 2.1 倍、设备停机 18 分钟的右移修复只动 13 个工序且护栏复检零违规、护栏注入违规被 2 条归因信息当场阻断。每一个 text 代码块都是原始 stdout。
---

# 代码：从贪心到 CP-SAT 到 Agent

首页那段 30 行的内核，你跑通它只完成了 3%。
这一页把剩下 97% 的**第一层**补上：还是同一个小算例，但代码分五级台阶往上走，
每一级都告诉你「这一级买到什么、买到不了什么、下一级要用什么换」。

**五级台阶是：**

1. **评估器** —— 把「一张排程表」变成「一个数」。没有它，贪心和 CP-SAT 都无从比较；
2. **贪心** —— 零求解器成本，四条派工规则，免费的那一档；
3. **CP-SAT** —— 约束规划接手，把贪心剩下的差距挣回来（以及：求解器崩了怎么办）；
4. **增量评估** —— 邻域移动后不全量重算，把「一次点击能搜多少」放大；
5. **右移修复 + 护栏** —— 扰动来了只动该动的部分，方案放行前硬约束逐条过闸。

全部实测来自一份脚本：[`/snippets/code_probe.py`](/snippets/code_probe.py)
（仓库路径 `docs/public/snippets/code_probe.py`，约 450 行）。
第 [1][2][4][5][6] 节**纯标准库**；第 [3] 节需要 `pip install ortools`（≥ 9.8）。
页面上每一个 `text` 代码块都是本机（Windows 11 / Python 3.12）的**原始 stdout**，一个字符没改。

<FlowRail
  glow="teal"
  eyebrow="阅读顺序"
  title="五级台阶，每一级回答一个会被代码评审问到的问题"
  lead="顺序有讲究：先能评估（否则无从比较），再贪心（免费的先榨干），再 CP-SAT（挣剩下的钱），然后才谈性能（增量）与扰动（修复）。反过来的团队会在第三周重写第一版。"
  :steps="[
    { code: '01', name: '评估器', desc: '前向传播 + 环检测，把方案变成数', meta: '第一节 · 标准库', tone: 'teal' },
    { code: '02', name: '贪心', desc: '四条规则 0.3ms，免费买到 140', meta: '第二节 · 标准库', tone: 'blue' },
    { code: '03', name: 'CP-SAT', desc: 'NoOverlap + 下界；崩溃隔离', meta: '第三节 · ortools', tone: 'coral' },
    { code: '04', name: '增量评估', desc: '32.5% 的走访量，2.1 倍吞吐', meta: '第四节 · 标准库', tone: 'lime' },
    { code: '05', name: '右移修复', desc: '停机 18 分钟，只动 13 个工序', meta: '第五节 · 标准库', tone: 'coral' },
    { code: '06', name: '护栏', desc: '注入违规，2 条归因当场阻断', meta: '第六节 · 标准库', tone: 'blue' }
  ]"
  note="第六节的护栏函数只有 20 行，但它是「Agent」两个字和「自动排程脚本」两个字的分界线。"
/>

---

## 一、评估器：先让「方案」变成「数」

作业车间（job shop）的方案就是**每台机器上的工序顺序**。给定顺序，最早开工时间由两条链决定：
工件内的先后（工艺路线）和机器上的先后（顺序本身）。沿拓扑序前向推进一遍就是评估：

```python
def topo_order(seq):
    """Kahn 拓扑：节点 = 工序，边 = 工件内先后 + 同机先后。seq 有环则不可行。"""
    succs = {op: [] for op in PT}          # op = (工件号, 工序号)
    indeg = {op: 0 for op in PT}
    for j in JOBS:                         # 工艺链
        for o in range(N_MACH - 1):
            succs[(j, o)].append((j, o + 1)); indeg[(j, o + 1)] += 1
    for m in MACHS:                        # 机器链
        for a, b in zip(seq[m], seq[m][1:]):
            succs[a].append(b); indeg[b] += 1
    order, queue = [], [op for op in PT if indeg[op] == 0]
    while queue:
        op = queue.pop(); order.append(op)
        for s in succs[op]:
            indeg[s] -= 1
            if indeg[s] == 0: queue.append(s)
    return order if len(order) == len(PT) else None   # None = 有环，不可行

def forward(order, seq, pt=PT):
    """最早开工时间：start = max(工件前道完工, 机器前道完工)。"""
    starts = {}
    for j, o in order:
        s = starts[(j, o-1)] + pt[(j, o-1)][1] if o > 0 else 0
        mp = seq[pt[(j, o)][0]]; i = mp.index((j, o))
        if i > 0:
            pred = mp[i-1]
            s = max(s, starts[pred] + pt[pred][1])
        starts[(j, o)] = s
    return starts

def makespan(order, seq):
    st = forward(order, seq)
    return max(s + PT[op][1] for op, s in st.items())
```

三个设计决定，每个后面都站着一批翻车现场：

- **环检测就是可行性判据。** `topo_order` 返回 `None` 意味着机器顺序和工艺路线互相矛盾——
  那个方案**不存在任何开工时间能让它成立**。很多自研排产器在这步直接 `KeyError`，查了一整天才发现是顺序有环。
- **评估器必须是「真理的单一来源」。** CP-SAT 解出来要喂回它复算（第三节），贪心的产物要过它复算。
  评估器和求解器口径不一致的项目，会在验收会上给出两个不同的 makespan。
- **工时用整数。** 浮点毛刺会让「逐格一致」的自检偶尔失败，而你永远查不出是哪一格。

```text
[1] 算例与评估器
  算例：12 工件 x 4 机器，seed=42，工序 48 个，总工时 451
  工时分布：min 3 / avg 9.4 / max 17
  理论下界（粗）：max(总工时/机器数 112, 单工件链 51)
  评估器自检 ①：随机机器顺序 → topo 有环，判不可行（环检测即可行性判据）
  评估器自检 ②：可行序列（FIFO 贪心）makespan=140，重算一次=140，逐格一致
  评估器复杂度：一次全量评估走访 48 个工序，O(工序数)
```

注意自检 ①：**随机生成的机器顺序多半有环**。这不是意外，是作业车间的本性——
每对同机工序都有两个方向可选，选错一组就成环。可行性从来不是排产问题的免费赠品。

---

## 二、贪心：免费的先榨干

非延迟派工：机器空闲时，在「前道工序已完成」的候选里按规则挑一个。四条规则，全是教科书里的：

```python
def greedy(rule):
    """非延迟派工：机器空闲时，在「前道工序已完」的候选里按 rule 挑一个。"""
    job_ready = {(j, 0): 0 for j in JOBS}      # (j,o) -> 最早可开工时刻
    mach_free = {m: 0 for m in MACHS}
    seq = {m: [] for m in MACHS}; starts = {}
    nxt = {j: 0 for j in JOBS}; remaining = N_JOBS * N_MACH
    while remaining:
        cand = [(j, nxt[j]) for j in JOBS if nxt[j] < N_MACH]
        best = min(cand, key=lambda op: (max(mach_free[PT[op][0]], job_ready[op]), rule(op)))
        j, o = best; mach = PT[best][0]
        s = max(mach_free[mach], job_ready[best])
        starts[best] = s; seq[mach].append(best)
        mach_free[mach] = s + PT[best][1]
        if o + 1 < N_MACH: job_ready[(j, o + 1)] = mach_free[mach]
        nxt[j] += 1; remaining -= 1
    return seq, starts
```

```text
[2] 贪心：四条派工规则，零求解器成本
  先来先干 (FIFO)            makespan=140   求解耗时  0.32 ms   vs 最好贪心 +0
  短工时优先 (SPT)            makespan=140   求解耗时  0.34 ms   vs 最好贪心 +0
  长工时优先 (LPT)            makespan=162   求解耗时  0.45 ms   vs 最好贪心 +22
  剩余量最多优先 (MWKR)         makespan=143   求解耗时  0.69 ms   vs 最好贪心 +3
  粗下界 112：最好贪心离它还有 28。这一段差距就是 [3] 节求解器要挣的钱。
```

三条结论：

- **规则之间能差 13.6%（140 vs 162），成本都是亚毫秒。** 选型时先把规则矩阵跑一遍，
  这一档的收益是免费的，先挣到手再谈求解器——[perf 页](/build/perf) 第二节量的就是这件事。
- **规则没有全胜者。** 这个算例里 FIFO 和 SPT 打平；换个工时分布，冠军就换人。
  所以「我们用 EDD」这种一句话选型不成立，要写成可以配置的规则表。
- **贪心到粗下界还有 28（25%）。** 这 25% 就是第三节求解器的营收空间。
  如果你的项目验收指标写在粗下界附近，贪心就够了，别为了 3% 引入一个求解器依赖。

---

## 三、CP-SAT：把剩下 25% 挣回来（以及：它崩了怎么办）

同一个算例的 CP-SAT 模型，40 行。**两组约束、一个目标**，没有更多了：

```python
from ortools.sat.python import cp_model

horizon = sum(d for _, d in PT.values())
model = cp_model.CpModel()
start, end, interval = {}, {}, {}
for op, (m, d) in PT.items():
    start[op] = model.new_int_var(0, horizon, f"s{op[0]}_{op[1]}")
    end[op]   = model.new_int_var(0, horizon, f"e{op[0]}_{op[1]}")
    interval[op] = model.new_interval_var(start[op], d, end[op], f"i{op[0]}_{op[1]}")

for j in JOBS:                                  # 约束一：工件内先后
    for o in range(N_MACH - 1):
        model.add(start[(j, o + 1)] >= end[(j, o)])
for m in MACHS:                                 # 约束二：同机互斥
    ops = [op for op in PT if PT[op][0] == m]
    model.add_no_overlap([interval[op] for op in ops])

mk = model.new_int_var(0, horizon, "makespan")
for j in JOBS:
    model.add(mk >= end[(j, N_MACH - 1)])
model.minimize(mk)

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 10.0    # 预算写时间，不写「解到最优」
solver.parameters.num_search_workers = 8
status = solver.solve(model)
print(solver.status_name(status), solver.value(mk), solver.best_objective_bound)
```

写法上的三件事比模型本身重要：

- **`add_no_overlap` 一组约束顶掉一个机器的整张析取弧网。** 1000×50 的形状是 2,497 万条弧
  （见 [perf 页第一节](/build/perf)），CP 求解器把它们压进传播器，你只需要声明互斥。
- **`max_time_in_seconds` 必须写。** 「解到最优」在生产环境不是参数，是事故。
- **`best_objective_bound` 必须打印。** 它和 `value(mk)` 的差就是诚实性间隙——
  「已优化」和「离最优多远」是两句话（见 [下界与间隙](/problem/bounds)）。

:::: warning 诚实一幕：本机 CP-SAT 原生崩溃，所以本节没有数字
上面这段代码在写稿的这台 Windows 机器上（Python 3.12 + ortools 9.15）**导入正常、`solve()` 一调就段错误**
（子进程退出码 3221225477）。所以这一节的 stdout 没有贴数字——不贴就是没有，手册不编造 stdout。
这也顺手演示了第三件比模型更重要的事：**求解器是原生库，它崩溃的方式是带走你的进程。**
脚本把 CP-SAT 放进子进程隔离运行，主进程照常把后面三节跑完：

```text
[3] CP-SAT（子进程隔离运行：崩了不许带走主服务）
  子进程退出码 3221225477（非零）——CP-SAT 原生库没跑完，本机不产出 [3] 的数字
  主进程毫发无损。这就是「求解器降级链」的第一课：解不动就退回贪心档，别让排产跟着挂。
```

生产代码请照抄这个模式：求解调用放独立进程（或至少独立协程 + 超时），
失败降级到贪心档方案并告警，**绝不让「优化」这个增强功能变成「排产」这个核心功能的单点故障。**
完整降级链的设计见 [写保护、熔断与降级链](/arch/guardrail)。
::::

在 OR-Tools 能正常跑的机器上，这个量级的算例通常秒级出最优解，
然后**必须**把解喂回第一节的评估器复算一遍，确认两个口径一致（脚本里就是这么做的）。

---

## 四、增量评估：别把 48 个工序全重算一遍

爬山/禁忌搜索的吞吐 = 单次评估成本 × 邻域大小。全量重算是 48 个工序的拓扑推进；
但「同机相邻交换」只影响两个工序的后继链，增量传播平均只摸 15.6 个：

```python
def forward(order, seq, pt=PT, cache=None, seeds=()):
    """沿拓扑序前向传播。cache 给定时只重访 seeds 及其后继（增量评估）。"""
    starts = {} if cache is None else dict(cache)
    dirty = set(seeds)                          # 起点 seeds：被交换的两个工序
    succs = build_succs(seq)                    # 后继表：工件内先后 + 同机先后
    for op in order:
        if cache is not None and op not in dirty:
            continue                            # 没被波及的工序直接跳过
        s = 0
        if op[1] > 0: s = max(s, starts[(op[0], op[1]-1)] + pt[(op[0], op[1]-1)][1])
        mp = seq[pt[op][0]]; i = mp.index(op)
        if i > 0: s = max(s, starts[mp[i-1]] + pt[mp[i-1]][1])
        old = starts.get(op); starts[op] = s
        if old != s: dirty.update(succs.get(op, ()))   # 变了才传染给后继
    return starts
```

```text
[4] 增量评估：邻域移动后，全量重算 vs 增量重算
  算例 48 工序；同机相邻交换 x200（另 0 个交换产生环，判非法移动跳过）
  基线 makespan=140；全量重算每次走访 48 工序，均耗时 77.8 us
  增量重算：平均走访 15.6 工序（32.5% of 全量），均耗时 37.9 us
  结论：评估吞吐 ≈ x2.1；邻域大小不变时，增量评估直接把「一次点击能搜多少」放大同倍数
```

两个要点：

- **32.5% 不是终点。** 算例越大，波及比例越小（后继链相对全长越短），增量收益越大。
  [perf 页第三节](/build/perf) 实测过 8,000 工序的评估要 169ms——那种规模下不做增量，
  交互式重排直接出局。
- **变了才传染。** 传播时若某工序的最早开工时间没变，它的整棵后继子树都可以剪掉。
  这一行 `if old != s` 是增量评估器里最值钱的一行。
- 环检测是免费附赠的合法性过滤器：交换导致成环的移动直接判非法（本例 200 次交换 0 次成环，
  但大算例里这个比例不可忽略）。

---

## 五、右移修复：扰动来了，先试最便宜的一档

设备停机 18 分钟。处置分三档：**右移**（把撞上窗口的工序推到窗口后，后继顺延）→
**CP-SAT 局部重排**（冻结已开工的，重排其余）→ **人工裁决**。第一档的实现只有 25 行：

```python
def repair_rightshift(plan, seq, m_broken, b0, b1, freeze_until):
    """第一档修复：只右移。撞窗工序推到 b1 之后，后继顺延；冻结工序钉死。"""
    frozen = {op: s for op, s in plan.items() if s < freeze_until}
    order = topo_order(seq)
    starts, hops = {}, []
    for op in order:
        j, o = op; m, d = PT[op]
        if op in frozen:
            starts[op] = frozen[op]             # 已开工的一动不动
            continue
        s = 0
        if o > 0: s = max(s, starts[(j, o-1)] + PT[(j, o-1)][1])
        mp = seq[m]; i = mp.index(op)
        if i > 0: s = max(s, starts[mp[i-1]] + PT[mp[i-1]][1])
        if m == m_broken and s < b1 and s + d > b0:
            s = b1; hops.append(op)             # 撞上停机窗口：整体推到窗口后
        starts[op] = s
    return starts, frozen, hops
```

```text
[5] 冻结窗口右移修复：设备停机后，只动该动的部分
  基线：SPT 贪心 makespan=140；冻结开工时刻 <42 的 22 个工序
  扰动：M1 在第 35~53 分钟停机（窗口 18 分钟）
  右移修复：makespan 140 -> 140（+0）；被移动 13 个工序（占可动部分 50%），其中直接跳窗 1 个
  位移：min +4 / max +8 / avg +7.4 分钟，全部右移 True
  护栏复检：PASS，0 条违规
  口径提醒：冻结按「开工时刻 < freeze_until」判定，不是按机器序列前缀（后者是 perf 页第六节的反例）
```

- **makespan +0 但动了 13 个工序。** makespan 不变 ≠ 没有影响：中间工序全体右移 4~8 分钟，
  这正是「计划 nervousness」要量化的东西——[评测页](/build/eval) 的人机分歧采集就盯这类改动。
- **全部右移、零违规** 是这一档的卖点：不回退任何已就绪的准备工作（领料、排刀、转运），
  现场照常执行。它买不到的也写清楚：makespan 拉长、交期变差的场景它无能为力，那才轮到 CP-SAT。
- 如果冻结工序挡住了右移路径（护栏复检 FAIL），这一档就到头了——升级，别硬修。

---

## 六、护栏：Agent 和「自动排程脚本」的分界线

方案放行前，硬约束逐条过闸。这个函数是三层权限模型里**最底层的物理防线**——
它在任何模型、任何 LLM、任何「智能」的外面：

```python
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
```

```text
[6] Agent 护栏：方案放行前，硬约束逐条校验（LLM 永远不碰这一步）
  贪心解：PASS，0 条违规，放行进暂存区（还不许写基线）
  注入违规（把 (0, 1) 提前 5 分钟）：FAIL，2 条违规，阻断 + 归因
    - 同机互斥 M1: (1, 0)（64+12）压住 (0, 1)（开工 74）
    - 同机互斥 M1: (0, 1)（74+6）压住 (6, 1)（开工 76）
  归因粒度是硬要求：「违规」两个字计划员没法干活，「谁压住了谁、差几分钟」可以
```

三个刻意的细节：

- **PASS 也不写基线。** 输出是「放行进暂存区」——写基线是化合物级 Agent 的事，
  且要终审（见 [三级智能体](/arch/three-level)）。权限在架构里，不在函数名里。
- **归因到「谁压住谁、差几分钟」。** 计划员拿到「校验失败」什么也做不了，
  拿到上面两行可以直接改。这是采纳率 ≥85% 那条 KPI 在代码层的等价物。
- **注意注入违规还带出了第二条违规。** 一个坏改动会激活多条约束——护栏要全部报出来，
  只报第一条的计划员会以为改一处就好。

---

## 七、合起来：这就是最小可用的排产 Agent

五个函数 + 一个子进程隔离，就是整本手册的最小骨架：

| 台阶 | 函数 | 解决的失败模式 | 对应章节 |
| --- | --- | --- | --- |
| 评估器 | `topo_order` / `forward` | 「两个模块报出两个 makespan」 | [性能](/build/perf) |
| 贪心 | `greedy` | 「为了 3% 引入求解器依赖」 | [启发式](/problem/heuristic) |
| CP-SAT | `sec3` 模板 + 子进程隔离 | 「求解器崩溃带走排产服务」 | [降级链](/arch/guardrail) |
| 增量评估 | `forward(cache, seeds)` | 「交互式重排慢到没法用」 | [性能](/build/perf) |
| 右移修复 | `repair_rightshift` | 「一次停机全厂重排」 | [不确定性](/problem/uncertainty) |
| 护栏 | `check` | 「AI 生成的方案直接写进 MES」 | [写保护](/arch/guardrail) |

:::: tip 想换成你的车间
把 `gen()` 换成读你的工艺路线表（工件 × 工序 × 候选机 × 工时），注意三件事：
① 工时用整数；② 每工件不必走满全部机器，但机器号要连续；③ 先跑 [数据五维点检](/build/data-first)，
数据不过门禁，这五个函数算得再对也是在精确地算错。
::::

---

## 附：完整可复现脚本

本页**每一个 `text` 代码块**由一份约 450 行的脚本打印：
[`/snippets/code_probe.py`](/snippets/code_probe.py)。

```bash
python docs/public/snippets/code_probe.py    # [1][2][4][5][6] 纯标准库；[3] 自动进子进程
python docs/public/snippets/code_probe.py --cpsat   # 只跑 CP-SAT 节（需 ortools >= 9.8）
```

种子写死在脚本头（`SEED = 42`），贪心、增量、修复、护栏四节的**结论跨机器稳定**；
`us` 级耗时会随机器浮动，CP-SAT 节在本机崩溃（见第三节的诚实一幕），
在正常机器上会打印状态、makespan、下界与自检行。

---

## 下一步

- [性能：万级变量与秒级重排](/build/perf) —— 本页评估器的规模化版本：8,000 工序的吞吐账。
- [先修数据，再谈智能](/build/data-first) —— `gen()` 换成真数据之前，必须先过五维门禁。
- [评测：影子模式与人机分歧](/build/eval) —— 第五节「动了 13 个工序」正是要采集的分歧信号。
- [写保护、熔断与降级链](/arch/guardrail) —— 第三节崩溃隔离的完整架构版。
- [20 个真实翻车现场](/build/pitfalls) —— 本页每个设计决定反着做会翻的车。
