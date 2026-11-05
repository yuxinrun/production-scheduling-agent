---
title: 把车间写成数学：变量、约束、目标
description: 从现场术语到决策变量的映射表、四种变量化方案、MILP 与 CP 的两套完整写法，以及建模阶段最常见的十个 bug。
---

# 把车间写成数学：变量、约束、目标

建模不是「把问题写漂亮」，是**把现场的话翻译成能被剪枝的形状**。
同一个车间，两种建模方式的求解时间能差三个数量级——差的不是求解器，是变量选择。

这一页的结构是给你的工作流用的：

1. 一张**术语 → 数学对象**的映射表（拿去对着需求文档逐条填）
2. **四种变量化方案**，各自的规模与代价
3. MILP 与 CP 两套**能直接抄的完整写法**
4. 十个**建模阶段的经典 bug**（每一个都是别人踩过的）

---

## 一、术语 → 数学对象

拿到需求文档，第一件事不是选算法，是把每一句话归到下面四类之一。
**归不进去的句子，说明你还没问清楚。**

| 现场的话 | 数学对象 | 落在哪里 |
| --- | --- | --- |
| 工件 / 工单 `i` | 索引 `i ∈ J` | 集合 |
| 工序 `(i, j)`：工单 i 的第 j 道 | 操作 `o = (i,j)`，`j ∈ 0..n_i-1` | 集合 |
| 设备 / 工位 / 台架 / 炉子 `k` | 资源 `k ∈ M` | 集合 |
| 「这道工序要 6 小时」 | `p_{i,j}`（或 `p_{i,j,k}`：柔性时随机器变） | 参数 |
| 「这台机器周末不开」 | 资源日历 → 可行时窗集合 | 参数 + 预处理 |
| 「先粗车再精车」 | 紧前约束 `s_{i,j+1} ≥ s_{i,j} + p_{i,j}` | 硬约束 |
| 「一台机器同时只能干一件」 | 析取（disjunction）：要么 A 在 B 前，要么 B 在 A 前 | 硬约束 |
| 「同一台设备上的活不许重叠」 | `NoOverlap` / 析取 + big-M | 硬约束 |
| 「换型要 2 小时，A→B 和 B→A 不一样」 | 序列相关换型 `s_{k,a,b}` | 硬约束（CP 里用 `AddTransition`/automaton） |
| 「这批货周五前必须开工」 | `s_{i,0} ≥ r_i`；交期 `C_{i,last} ≤ d_i` | 分别是硬/软 |
| 「军品急件权重高」 | 目标里的 `w_i` | 目标函数 |
| 「热处理一炉能装 8 件，且必须一起进一起出」 | 批处理机：`p_batch = max(p)`，容量 `Σ size ≤ 8` | 硬约束（CP 里 `AddCumulative` + 辅助 0/1） |
| 「焊接完 20 天内必须进下道」 | 跨工序时间窗 `s_{i,j+1} ≤ s_{i,j} + p_{i,j} + 20` | **硬约束，且跨日历衰减** |
| 「无损检测合格率只有 60%」 | 随机加工时间 / 返工分支 | 不确定性，不是约束 |
| 「这道工序只有持证的 3 个人能做」 | 人员资质：`(i,j) → 允许的人员集合` | 耦合资源约束 |
| 「工装只有 4 套」 | 累计资源 `Cumulative(capacity=4)` | 硬约束 |
| 「夜班只有两个人值班」 | 时间窗内的累计人员约束 | 硬约束 |
| 「齐套了才能开工」 | `s_{i,0} ≥ t` 仅在 `kit_ok_i(t) = 1` 时 | 硬约束（布尔前置） |
| 「关键工序三定（定人定机定法）」 | 允许组合的**白名单** `(i,j,k,worker) ∈ A` | 硬约束（缺失时是 0 可行解） |
| 「尽量别加班」 | 目标项：超出标准工时的部分 | 软约束 / 目标 |
| 「炉子别空烧」 | 目标项：批次装载率 | 软约束 / 目标 |
| 「这个方案要能解释」 | 不是目标，是**输出契约**：解 + 触发的约束编号 | 系统设计 |

::: warning 一句话对应两个对象时，先问清优先级
「试车不合格要重新装配再试车」这句话同时给了三样东西：
一条**回边**（工艺路线成环）、一个**随机时长**（合格率 60%）、一个**产能消耗**（返工占用台架）。
把它们塞进一个字段（比如 `is_rework: bool`）的项目，后期一定要重写数据模型。
:::

---

## 二、四种变量化方案

同一批数据，四种写法。选错方案的代价是**永远算不出来**。

| 方案 | 决策变量 | 变量数 | 适合 | 代价 |
| --- | --- | --- | --- | --- |
| **时刻变量**（disjunctive） | `s_o` 整数开始时刻 | `O(操作数)` | CP / CP-SAT、分支定界析取树 | 时间域要离散化；大 M 版在 MILP 里数值性差 |
| **顺序 0/1** | `y_{o1,o2}` = 同机上谁先 | `O(同机对数)` ≈ `Σ_k n_k²/2` | 单机子问题、割平面、Shifting Bottleneck | 对称性严重，剪枝困难 |
| **指派 0/1** | `z_{o,k}` = 这道工序给哪台机 | `O(操作 × 候选机)` | 柔性车间 FJSP、并行机 | 只决定「谁做」不决定「何时」，必须叠一层排序 |
| **时间索引** | `x_{o,k,t}` = o 在 k 上 t 时刻开工 | `O(操作 × 机 × 时段)` | LP 松弛最紧、能源/人员耦合约束好写 | 规模爆炸：1000 工序 × 20 机 × 500 时段 = 10⁷ 变量 |

**经验法则**：

- 约束复杂、日历麻烦、要给现场解释 → **时刻变量 + CP**。这是今天 90% 的新项目该走的路。
- 需要连续量（成本、库存、运输）和排产一起解 → **MILP + big-M 或时间索引**。
- 时间索引只在**时段粒度粗**（按班次/按天）时用。按分钟做时间索引的模型，光 LP 松弛就解不动。
- 「指派 + 排序」两层分开（先解机器分配，再固定路线排序）就是经典的 **Shifting Bottleneck** 思路，快但会丢最优。

---

## 三、写法 A：MILP（big-M，Manne 1960）

作业车间 `Jm | | C_max`。变量：`s_{i,j}` 开始时刻，`C_{i,j}` 完工时刻，
`y_{(i,j),(k,l)}` ∈ {0,1} 表示同机器上 `(i,j)` 排在 `(k,l)` 之前。

```text
min  C_max

s.t.  C_{i,j} = s_{i,j} + p_{i,j}                          ∀ i, j          # 完工定义
      s_{i,j+1} ≥ C_{i,j}                                  ∀ i, j < n_i-1  # 工艺路线
      s_{i,0} ≥ r_i                                        ∀ i             # 可用时刻
      ── 同一台机器不许重叠（big-M 析取）──
      s_{k,l} ≥ C_{i,j} − M (1 − y_{(i,j),(k,l)})           ∀ 同机 m 上的对
      s_{i,j} ≥ C_{k,l} − M · y_{(i,j),(k,l)}              ∀ 同机 m 上的对
      C_max ≥ C_{i,n_i−1}                                  ∀ i             # makespan 下压
      y ∈ {0,1}, s ≥ 0
```

三行代码之外的三个坑：

1. **M 取多大。** 取 `M = Σ全部加工时间` 是安全的但松得要死；LP 松弛几乎不剪枝。
   正确做法：M 用**这台机器上该操作的最早可能开始与最晚可能完工**分别收紧，或直接换析取约束求解。
2. **对称性**。`y` 的两个方向是对偶的，交换机器顺序不改变目标——分支树里全是等价解。
   要加 symmetry breaking（比如同机上工序 1 与工序 2 若 `p` 相同、路线无关，强制字典序）。
3. **`C = s + p` 写成 `≥`。** 目标是最小化时会自动收紧，但如果你把目标换成别的（比如人员利用率），
   `≥` 会让 `C` 停在错误的地方。**能用等号就用等号。**

```python
# PuLP 版：单机 ΣwjCj，验证 Smith 比率规则（p/w 升序）
import pulp

jobs = [(1, 3, 5), (2, 2, 8), (3, 4, 2), (4, 1, 4)]   # (name, p, w)
m = pulp.LpProblem("1||sum_wjCj", pulp.LpMinimize)
y = {(a, b): pulp.LpVariable(f"y_{a[0]}_{b[0]}", cat="Binary")
     for a in jobs for b in jobs if a[0] < b[0]}      # a 在 b 前？
C = {j[0]: pulp.LpVariable(f"C_{j[0]}", lowBound=0) for j in jobs}
P = sum(j[1] for j in jobs)

m += pulp.lpSum(j[2] * C[j[0]] for j in jobs)
for j in jobs:
    m += C[j[0]] >= j[1]                               # 不早于自身加工时间
for a in jobs:
    for b in jobs:
        if a[0] < b[0]:
            m += C[a[0]] <= C[b[0]] - b[1] + P * (1 - y[(a, b)])   # a 先
            m += C[b[0]] <= C[a[0]] - a[1] + P * y[(a, b)]         # b 先
m.solve(pulp.PULP_CBC_CMD(msg=0))
print("最优 ΣwjCj =", round(pulp.value(m.objective), 3),
      "顺序 =", sorted(jobs, key=lambda j: -j[2] / j[1]))           # 按 w/p 降序 = Smith
```

---

## 四、写法 B：CP-SAT（今天默认该用这个）

同样两个约束，CP 用**全局约束**表达，剪枝靠推理引擎而不是 LP 松弛。
`NoOverlap` 内部会跑 disjunctive reasoning 与 edge-finding，毫秒级排除掉的分支比 LP 剪的多。

```python
# 柔性作业车间（FJSP）最小化 makespan：指派 + 排序一起解
from ortools.sat.python import cp_model

# ops[i] = [(machine, proc_time), ...]；工艺路线顺序 = 列表顺序
ops = {
    0: [(0, 3), (1, 2), (2, 2)],
    1: [(1, 4), (0, 1), (2, 3)],
    2: [(2, 2), (0, 3), (1, 1)],
    3: [(0, 2), (2, 4), (1, 3)],
    4: [(1, 3), (2, 1), (0, 2)],
}
machines = [m for j in ops for (m, _) in ops[j]]
HORIZON = sum(max(p for (_, p) in ops[j]) for j in ops) + 10

model = cp_model.CpModel()
x = {}      # x[j,o,m] = 工序 o 是否交给机器 m
s = {}      # s[j,o]    = 开始时刻
e = {}      # e[j,o]    = 完工时刻
pres = {}   # pres[j,o][m] = optional interval，NoOverlap 用

for j in ops:
    for o, cand in enumerate(ops[j]):
        x[j, o] = {m: model.NewBoolVar(f"x_{j}_{o}_{m}") for m, _ in cand}
        s[j, o] = model.NewIntVar(0, HORIZON, f"s_{j}_{o}")
        e[j, o] = model.NewIntVar(0, HORIZON, f"e_{j}_{o}")
        for m, p in cand:
            present = x[j, o][m]
            interval = model.NewOptionalIntervalVar(s[j, o], p, e[j, o], present, f"iv_{j}_{o}_{m}")
            pres[j, o, m] = interval
            # 只有选中这台机器时，工时才等于 p
            model.Add(e[j, o] == s[j, o] + p).OnlyEnforceIf(present)
        model.Add(sum(x[j, o].values()) == 1)                    # 必须且只能一台
        if o:
            model.Add(s[j, o] >= e[j, o - 1])                   # 工艺路线

for m in set(machines):
    model.AddNoOverlap([pres[j, o, m] for j in ops
                        for o in range(len(ops[j])) if (j, o, m) in pres])

makespan = model.NewIntVar(0, HORIZON, "makespan")
for j in ops:
    model.Add(makespan >= e[j, len(ops[j]) - 1])
model.Minimize(makespan)

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 30      # ← 这行才是排产系统真正的核心
solver.parameters.num_search_workers = 8
st = solver.Solve(model)
if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    print("makespan =", solver.Value(makespan),
          "bound =", solver.BestObjectiveBound(),          # ← 下界，报告 gap 用
          "gap = %.1f%%" % (100 * (solver.Value(makespan) - solver.BestObjectiveBound())
                            / max(1, solver.Value(makespan))))
```

三个必须记住的细节：

- **`max_time_in_seconds` 不是兜底，是产品定义。** 超时时返回的是 FEASIBLE，不是「失败」。你的代码要按 FEASIBLE 走完整条链路。
- **`BestObjectiveBound()` 免费送你一个下界。** 上面那段代码顺手打印了 gap。
  这一行日志以后会成为你和计划员之间最重要的信任来源。见 [下界与间隙](/problem/bounds)。
- **`OptionalIntervalVar` 是柔性车间的钥匙。** 机器不确定时，用「可选区间」而不是大 M。

---

## 五、把方案画出来：解的可视化

求解器给你的是一堆整数。现场能看懂的是一张甘特。
`start`/`duration`/`machine` 三元组直接映射到行与条：

<GanttView
  eyebrow="解的形状"
  title="同一批工序，四种资源占用"
  lead="设备是行，时间（小时）是列。实心条是被排进去的活，虚线条是因为产能挤不进、只能推到视野外的部分。"
  :horizon="72"
  :tick="12"
  tick-unit="H"
  :now-at="18"
  :legend="[
    { tone: 'teal', label: '正常占用' },
    { tone: 'coral', label: '违反硬约束' },
    { tone: 'blue', label: '等待 / 转序' },
    { tone: 'lime', label: '瓶颈资源' }
  ]"
  :rows="[
    { name: '五轴 A-02', sub: '独生子 · 瓶颈', bars: [
      { s: 0, d: 8, tone: 'lime', label: 'W12-车' },
      { s: 8, d: 3, tone: 'blue', label: '换型' },
      { s: 11, d: 14, tone: 'lime', label: 'W07-车' },
      { s: 25, d: 6, tone: 'teal' },
      { s: 34, d: 10, tone: 'teal', label: 'W19' },
      { s: 48, d: 12, tone: 'teal', ghost: true }
    ] },
    { name: '数控车 A-04', sub: '平行机 3 台', bars: [
      { s: 0, d: 10, tone: 'teal', label: 'W03' },
      { s: 12, d: 9, tone: 'teal', label: 'W15' },
      { s: 24, d: 4, tone: 'blue', label: '待料' },
      { s: 28, d: 12, tone: 'teal', label: 'W21' },
      { s: 44, d: 16, tone: 'teal', ghost: true }
    ] },
    { name: '热处理炉 A-03', sub: '批处理 · 满炉率', bars: [
      { s: 6, d: 12, tone: 'coral', label: '3/8 装载 · 违规' },
      { s: 22, d: 16, tone: 'teal', label: '合炉 8/8' },
      { s: 40, d: 14, tone: 'blue', label: '等齐套' }
    ] },
    { name: '试车台架 A-06', sub: '窗口极窄', bars: [
      { s: 0, d: 6, tone: 'teal', label: '台架保养' },
      { s: 18, d: 10, tone: 'lime', label: 'W07 首试' },
      { s: 34, d: 8, tone: 'blue', label: '等检测' },
      { s: 46, d: 10, tone: 'coral', label: '两装两试 · 再试', ghost: true }
    ] }
  ]"
  note="红色条是被 SHACL / 硬校验拦下来的那种解：装载 3/8 的炉子数学上完全可行，现场是违法的。这就是为什么「约束写完」比「目标写对」更重要——你的求解器不会替你把这条红线加进模型。"
/>

---

## 六、建模阶段的十个 bug

这些 bug 的共性是：**求解器不报错，结果不可用**。

| # | Bug | 症状 | 修法 |
| --- | --- | --- | --- |
| 1 | **日历没进模型** | 排出来周末开工、保养时段占用 | 把 `available(k, t)` 预处理成时窗列表，用 `AddIntervalVar` 域约束，或 `AddForbiddenIntervals` |
| 2 | **把换型当常数** | 现场说「你这个顺序根本换不过来」 | 序列相关换型：`s_next ≥ end_prev + setup[machine][prev][next]`；CP 用 `AddAutomaton` / transition 表 |
| 3 | **M 取全局总工时** | B&B 跑 3 小时不收敛，LP 松弛一塌糊涂 | 每个约束单独收紧 M；或改用析取/可选区间 |
| 4 | **时间单位混用** | 分钟和小时在同一约束里相加，结论差 60 倍 | 全模型只用一个整数单位（分钟），入口处换算一次，写进常量 |
| 5 | **工件级 C 与工序级 C 混用** | makespan 莫名其妙偏小 | 明确 `C_i = C_{i,n_i−1}`，别复用同一个变量名 |
| 6 | **软约束写成大罚权重** | 求解器「理性地」违反了资质约束 | 法规、安全、军检类约束必须是**硬**的；只有产能、加班、换型损失可以是软的 |
| 7 | **忽略累计资源（人、工装、能源）** | 方案里同一班 3 个人在干 5 件事 | `AddCumulative(intervals, demands, capacity, name)`。人效是典型累计资源 |
| 8 | **把并行工序写成串行** | 产能凭空少 30%，计划员一眼看出假 | 工艺路线要是 DAG 不是链。同一工单可并行分支时，用前置集合而不是 `j+1` |
| 9 | **交期用自然日、日历用工作日** | OTD 数字永远比现场好 | 统一走日历函数；跨节假日的有效期衰减（20 天是自然日）单列一个字段 |
| 10 | **把随机加工时间当确定值** | 每次重排结果都在剧烈变化 | 均值进模型 + 缓冲按方差给；或走鲁棒/场景。见 [不确定性](/problem/uncertainty) |

::: tip 「模型对不对」怎么验证
拿三张**历史周计划**做离线复算：把你的模型跑在同一批数据上，
检查两件事——
① 人工计划在你模型里是不是**可行解**（不是的话，你的硬约束一定写错了，因为人工计划每天都在执行）；
② 你的解比人工计划好在哪个指标上，那个指标是不是计划员真正在乎的。
第 ① 条是最便宜的模型校验，能一次性抓出 70% 的过度约束。
:::

---

## 七、建模四步 Checklist

按这个顺序做，不要跳步：

1. **集合与索引**：工单、工序、设备、人员、工装、批次。先把主数据表建出来，编码映射对上（图号 ↔ 物料号 ↔ 工序号）。
2. **参数**：`p`、`r`、`d`、`w`、日历、换型矩阵、容量。**每个参数标注来源与置信度**——现场参数里有一半是估的。
3. **硬约束**：紧前、不重叠、资质、有效期、齐套门禁、白名单。**写完先只求可行不求最优**（`model.Add(makespan <= 人工计划的 Cmax)` 然后只 `Solve()`）。可行解都出不来，谈不上优化。
4. **目标**：先单目标跑通，再谈多目标。**先问「你们最痛的是哪个数」**，别一上来就 `multi`。

::: warning 第 3 步和建模工具的选型顺序反了会怎样
很多项目从「选求解器」开始，最后发现真正的问题在**参数拿不到**：
换型矩阵没有实测、日历在 MES 的另一个库里、人员资质是张 Excel。
排产项目的工期分布大致是 60% 数据、25% 建模、10% 求解、5% 算法。
这个数字来自 LISA 项目复盘，样本量 = 1，但方向和几乎所有现场工程师的说法一致。
:::

---

## 下一步

- [拉格朗日松弛与对偶定理](/problem/lagrangian) —— 约束太多写不下时，怎么把它们放进目标函数并拿到下界
- [精确算法：分支定界、割平面、约束传播](/problem/exact) —— 求解器内部到底在干什么
- [多目标：Pareto、ε-约束、字典序](/problem/multiobjective) —— 「交期、成本、加班都要」这句话的数学后果
