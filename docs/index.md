---
layout: home
hero:
  name: 排产 Agent 手册
  text: 从 NP-hard 到车间现场
  tagline: 写给要做 production-scheduling-agent 的程序员 —— 数学怎么建模、算法怎么选、架构怎么搭、坑在哪、以及一个航空发动机厂的真实数字。
  image:
    ariaLabel: 三级智能体分层图与一张五行迷你甘特图
  actions:
    - theme: brand
      text: 15 分钟跑通一个最小排产内核
      link: /build/code
    - theme: alt
      text: 先搞清「排产」到底指什么
      link: /what-is
    - theme: alt
      text: 实战案例：LISA（黎阳）
      link: /case/background
features:
  - title: 问题本身是强 NP-hard
    details: 100 道工序的车间，光「每台设备内部的先后顺序」就有约 10³¹⁵⁹ 种候选，可观测宇宙只有 10⁸⁰ 个原子。任何承诺「一键最优」的界面都在撒谎 —— 该问的是「离下界多远」。
    link: /problem/np-hard
    linkText: 为什么无解
  - title: 拉格朗日不是装饰
    details: 弱对偶定理保证：只要乘子 λ ≥ 0，θ(λ) 永远不超过真最优。所以它可以安全地拿去分支定界里剪枝。手册里有个可以按步播放的次梯度迭代器。
    link: /problem/lagrangian
    linkText: 亲手跑一遍
  - title: CP 才是排产的主力
    details: 约束规划不是在搜索，而是在排除。no_overlap + edge-finding 传播器能把 (n!)^m 的搜索空间砍到能算。ft10 的 930 卡了运筹学界三十年。
    link: /problem/exact
    linkText: 精确算法地图
  - title: 算法选型没有标准答案
    details: 规模、精度要求、约束形状、重排频率、数据成熟度 —— 五个问题答完，排序自己会变。手册给的是一个可以点的选型器，不是一句「用强化学习」。
    link: /problem/heuristic
    linkText: 打开选型器
  - title: 三级智能体，不是一个大模型
    details: 原子级 Copilot 只读建议、分子级编排器跨工序仲裁、化合物级总控写基线前必须人工终审。权限是架构的一部分，不是提示词里的礼貌请求。
    link: /arch/three-level
    linkText: 看权限阶梯
  - title: LLM 是翻译，不是搬运工
    details: 2026 年的实测：只用大模型解 40 个 LP，60 分钟做好 16 个；大模型 + 求解器 6 分钟全做；纯求解器 8.17 秒全做。数值真相必须由确定性内核产出。
    link: /problem/learning
    linkText: 边界在哪
  - title: 采纳率是组织问题
    details: 现场调研里 APS 采纳率只有 20~30%，客户把 ≥85% 写进验收 KPI。缺的不是算法，是白盒归因、冻结窗口、影子模式和「别把标注负担加给计划员」。
    link: /build/adoption
    linkText: 怎么被接受
  - title: 20 个真实翻车现场
    details: 把「有限产能检查」包装成优化排程、齐套导了表却没生效、次梯度步长炸成 NaN、模型不可用时排产跟着挂 —— 每一条都有对应的护栏写法。
    link: /build/pitfalls
    linkText: 避坑清单
---

<div class="psa-home-sec">

## 一、先说清楚：这本手册不讲「AI 改变制造业」

讲的是一个具体的工程问题：**怎么让程序替计划员决定「哪张工单、在哪台设备、从几点到几点、干什么」**，
并且这个决定在真实现场能被执行、能被追责、能被回放。

它同时是一个**数学问题**（强 NP-hard、对偶、多目标、随机扰动）和一个**软件问题**（数据口径、系统集成、权限、审计、UI）。
只学一边的人在这种项目里一定会翻车：只懂运筹的写不出能接 MES 的服务，只懂后端的会以为换个更大的模型就能解决交期违约。

</div>

<div class="psa-home-sec">

## 二、15 分钟能跑通什么

下面这段代码不含任何框架，是整本手册的最小可运行内核：**有限产能 + 工艺顺序 + 一条硬约束检查 + 一个可解释的输出**。
先让它跑起来，再回头看为什么它不够用。

```python
# 30 行：单设备、有限产能、带归因的排产内核
from dataclasses import dataclass

@dataclass
class Op:
    order: str        # 工单号
    seq: int          # 第几道工序
    minutes: int      # 标准工时
    due_day: int      # 交期（第几天 24:00 前）

def schedule(ops, day_minutes=960, workdays=6):
    ops = sorted(ops, key=lambda o: (o.due_day, o.seq))   # EDD：最小化最大延期的最优单台规则
    clock, plan, late = 0, [], []
    for o in ops:
        start, clock = clock, clock + o.minutes            # 串行排队 = 有限产能的本体
        finish_day = start // day_minutes + 1
        if clock > o.due_day * day_minutes * workdays / 6:
            late.append(f"{o.order}-{o.seq} 预计 {finish_day} 天完工 > 交期 {o.due_day} 天")
        plan.append((o.order, o.seq, start, o.minutes))
    return plan, late
```

跑通它你只完成了 3%。剩下 97% 是：**多设备怎么分、齐套不满足怎么办、设备突然停了要不要重排、
计划员凭什么信你、以及出了问题谁签字。** 这五件事一件都不在算法里，但每一件都能让项目死掉。

</div>

<DispatchLab
  eyebrow="互动 · 单台设备派单"
  title="六种调度规则，没有一种在所有指标上全胜"
  lead="改改工时和交期，看每条规则把哪个指标做优、把哪个指标做坏。这是理解「排产是权衡」最快的一节课。"
/>

<div class="psa-home-sec">

## 三、地图：一个问题从车间走到屏幕，要穿过几层

</div>

<LayerStack
  eyebrow="七层底座"
  title="每一层都在解决一个具体的失败模式"
  lead="少任何一层，项目都会以一种可预测的方式死掉。手册按层拆，每层给出「少了它会怎样」。"
  :layers="[
    { code: 'L6', name: '人机协同层', sub: '甘特差分 · 白盒归因 · 电子签名', tone: 'lime', items: ['计划员看得懂', '改得动', '愿意签字'], tag: '决定采纳率' },
    { code: 'L5', name: '评测治理层', sub: '双模评测 · 影子运行 · 月度升降档', tone: 'coral', items: ['硬约束零违规', '采纳率 ≥85%', '出得去观察期'], tag: '决定能不能上线' },
    { code: 'L4', name: '权限安全层', sub: 'ABAC · 写入熔断 · 密级 · 审计双链', tone: 'blue', items: ['谁能动', '动了留痕', '越权即断'], tag: '军工准入门' },
    { code: 'L3', name: '工具层', sub: '求解器 · 工艺算法沙箱 · 系统适配器', tone: 'teal', items: ['COPT / CP-SAT', 'ERP/MES/WMS/QMS', '降级链'], tag: '数值真相来源' },
    { code: 'L2', name: '记忆层', sub: '工作记忆 · 案例库 · 实绩回流', tone: 'teal', items: ['历史组批拆单', '人机分歧集', '工时基线自学习'], tag: '决定会不会越来越准' },
    { code: 'L1', name: '本体层', sub: '结构本体 + 4M 插拔 · SHACL 护栏 · PROV-O 血缘', tone: 'blue', items: ['工艺路线 DAG', '设备能力拓扑', '硬约束校验'], tag: '决定方案可不可执行' },
    { code: 'L0', name: '编排层', sub: 'SOP 总线 · 状态机 · 检查点回滚', tone: 'ink', items: ['长事务', '断点续跑', '跨日审批'], tag: '决定稳不稳' }
  ]"
  note="L0 数据五维点检（订单 / 工序 / 资源 / 日历 / 约束）达标率 ≥90% 是所有智能体的上线门禁 —— 数据失真会把准确率上限直接封顶在 60~70%。"
/>

<ChainRipple
  eyebrow="互动 · 扰动涟漪"
  title="点一个异常，看它怎么顺着工艺链往下传"
  lead="缓冲是唯一的堤坝。这台「涟漪直觉训练器」只算一阶传播，但它能教会你为什么热处理的缓冲要给 10 小时而不是 3 小时。"
/>

<div class="psa-home-sec">

## 四、算法选型：五个问题问完，答案自己变

别问「排产用什么算法」。要问「我这批订单、这几台设备、这个重排频率，配得上哪种算法」。

</div>

<AlgoTree
  eyebrow="互动 · 选型器"
  title="把「用什么算法」拆成五个可回答的问题"
  lead="规模、精度、约束形状、重排频率、数据成熟度。五问全选完，右侧的排序会实时变化 —— 注意它经常在「规则派单」和「CP」之间反复横跳，这才是真实情况。"
/>

<ExplosionChart
  eyebrow="为什么必须近似"
  title="工序数每加 2，搜索空间加一个数量级"
  lead="条长按 log₁₀ 画。下面选一个工件数，看看「穷举」这两个字在现场值多少钱。"
/>

<div class="psa-home-sec">

## 五、真实案例：一个航空发动机厂的排产 Agent（LISA）

手册里的每个架构决策都对照一个真实项目验证过。这家厂的计划口径是「周滚动，3 锁 1、下发 3、展望 3」，
交付目标里有一条很硬：**硬物理约束违背率 = 0**，另一条很软也很要命：**人工采纳率 ≥85%**。

</div>

<BarsCompare
  eyebrow="案例 · 客户明码标价的数字"
  title="现状 → 验收，中间隔着 12 个月"
  unit=""
  :max="100"
  :series="[
    { tone: 'ink', label: '现状' },
    { tone: 'teal', label: '一期目标' },
    { tone: 'coral', label: '验收 KPI' }
  ]"
  :rows="[
    { label: 'APS 方案人工采纳率', hint: '计划员愿意直接用', values: [25, 60, 85], display: ['20~30%', '≥60%', '≥85%'] },
    { label: '装配齐套率', hint: '9 项要素逐项判定', values: [60, 80, 100] },
    { label: '试车日计划达成率', hint: '到料不可视是根因', values: [50, 70, 90] },
    { label: '瓶颈设备有效负荷', values: [50, 47, 45], display: ['40~60%', '45~50%', '45~50%'] }
  ]"
  note="最后一行是反直觉的：排产优化不把瓶颈拉满当目标。瓶颈利用率拉满 = 在制品堆积 + 现场抵触（Little 定律），采纳率反而掉。数字出自《业务调研》与《问题提炼与目标对齐清单》。"
/>

<MatrixGrid
  eyebrow="案例 · 14 个智能体"
  title="三级矩阵：谁只读、谁能仲裁、谁能写基线"
  :cols="['原子级 ×7<br/>Copilot', '分子级 ×5<br/>Orchestrator', '化合物级 ×2<br/>战略中枢']"
  :rows="[
    { label: '数据可见范围', cells: [ { s: 'ok', t: '本工序只读' }, { s: 'ok', t: '跨工序链只读' }, { s: 'ok', t: '全厂 + 跨厂脱敏' } ] },
    { label: '输出可执行方案', cells: [ { s: 'soft', t: '带归因建议' }, { s: 'hard', t: '协调解 + 暂存锁定' }, { s: 'block', t: '终审后才生效' } ] },
    { label: '系统写入权', cells: [ { s: 'na', t: '无' }, { s: 'na', t: '无下发权' }, { s: 'warn', t: '验签回写 + 熔断' } ] },
    { label: '跨工序干预', cells: [ { s: 'block', t: '禁止' }, { s: 'ok', t: '冲突仲裁' }, { s: 'ok', t: '瓶颈资源分配' } ] },
    { label: '失败时的样子', cells: [ { s: 'weak', t: '退回人工排产' }, { s: 'soft', t: '升级至总控' }, { s: 'hard', t: '厂部调度中心兜底' } ] }
  ]"
  note="化合物级无论准确率多高都保留「厂部调度中心终审后生效」，不进入全自动下发 —— 这是形态表里的硬条件，不是保守。"
/>

<div class="psa-home-sec">

## 六、几个我希望你记住的判断

</div>

<div class="psa-claims">

### 「报告最优性间隙，而不是报告最优」

元启发式只给你上界。`abz8` 的最好调度 665、最好的下界 645 —— 3% 的雾从 1988 年飘到今天没人驱得散。
你的界面如果只显示「已优化 12%」而不显示「离下界多远」，那就是一个没有速度表的速度限制。

### 「CP 在搜索之前先排除」

`(100!)²⁰` 个候选不需要真的枚举。传播器（edge-finding、timetable-energetic）会从时窗里推出大量必然的先后关系，
把问题缩小到能搜的范围。**先写约束，再谈启发式** —— 顺序反了的项目都在调参数。

### 「重排策略要分层，别一上来全厂重排」

右移（冻结 + 顺延）最便宜，局部修复居中，全量重排最贵也最容易引发「计划 nervousness」。
触发机制分周期滚动和事件驱动两种，LISA 的口径是：局部重排 ≤30 分钟、夜间全量重排 1~2 小时、跨厂异步协同 ≤2 小时。

### 「大模型不该碰数值真相」

它该做的是：听懂「周三前把这三张军品件插进去，别动已领料的那批」，翻成任务、挑工具、解释结果、把拒绝的原因说清楚。
取数走只读 MCP 面，寻优走求解器，护栏走 SHACL —— 全在模型外面。

</div>

<div class="psa-home-sec">

## 七、生态与现状：一个数字提醒你别乐观

- 中国 APS 软件市场 2025 年收入约 **27.3 亿元**、同比 **+21.8%**（IDC 口径，经第三方转载）；另一口径为 2024 年 25.11 亿元、+23.45%（智研咨询）。市场在长，但**买过软件 ≠ 排得出计划**。
- 信通院《制造业数字化转型发展报告(2025)》：**规上工业企业数字化改造比例已达 89.6%**。可是同一批企业的计划员还在偷偷用 Excel —— 因为系统里的 BOM、工时、日历不可信。
- 政策端明确加码：八部门《「人工智能+制造」专项行动实施意见》要求 2027 年打造 **1000 个高水平工业智能体**；工信部《智能制造典型场景参考指引（2025 年版）》40 个场景里直接列了「车间智能排产」「生产动态调度」。
- 求解器国产化在提速：杉数 COPT、华为天筹（中铝瑞闽冷轧案例：1500 订单 × 10 余工序 × 40+ 组辊组炉组刀规则，**按时交货率 94.1% → 98%+**）。开源侧 OR-Tools/CP-SAT、HiGHS、SCIP（8.0.3 起 Apache-2.0）都够你起步。
- 行业里最诚实的一句泼冷水来自联友科技：**「单靠大模型排产是幻觉」** —— 必须 LLM 交互 + 求解器寻优 + 规则引擎校验分层。这句话基本概括了这本手册的架构章节。

</div>

<QuizSelf
  eyebrow="自测 · 12 题"
  title="看完首页就能做的部分，先测一下"
  lead="这 12 题覆盖复杂度、对偶、CP、排产语义、MCP 权限、脱敏与落地。答错的每一题都对应真实项目里翻过一次的车。"
/>

<div class="psa-home-sec">

## 八、怎么读这本手册

</div>

<MatrixGrid
  eyebrow="路线"
  title="三条读法，按你是谁选"
  :cols="['只想知道能不能做', '要写代码', '要写方案']"
  :rows="[
    { label: '认知', sub: '/what-is · /not-aps', cells: [ { s: 'ok', t: '必读' }, { s: 'ok', t: '必读' }, { s: 'ok', t: '必读' } ] },
    { label: '数学与算法', sub: '/problem/*', cells: [ { s: 'weak', t: '跳' }, { s: 'hard', t: '精读 + 跑代码' }, { s: 'soft', t: '读结论' } ] },
    { label: '系统架构', sub: '/arch/*', cells: [ { s: 'na', t: '—' }, { s: 'hard', t: '必读' }, { s: 'hard', t: '必读' } ] },
    { label: '实战案例 LISA', sub: '/case/*', cells: [ { s: 'soft', t: '看数字' }, { s: 'ok', t: '对照实现' }, { s: 'hard', t: '当模板抄' } ] },
    { label: '工程落地', sub: '/build/*', cells: [ { s: 'na', t: '—' }, { s: 'hard', t: '必读' }, { s: 'ok', t: '必读' } ] }
  ]"
  note="所有数字都标了出处：运筹学结论给论文/教材，案例数字给黎阳项目的调研与需求文档，行业数字给公开报道并注明「未能核实」的那部分照写不误 —— 口径不一致本身就是排产项目的头号坑。"
/>

<div class="psa-home-sec">

## 九、一个诚实的声明

这本手册里的案例数字来自项目文档，而**项目文档自己就有口径冲突**：规则条数一处写 68 条、另一处数出来是 56 条；
约束总数一处写 137 条、按可数条目累加是 132 条；问题清单有 37 项版和 28 项版两份。
我没有替它们抹平，而是在对应页面上把两份口径都写出来并标注出处 —— 因为你在真实项目里遇到的第一件事就是这个。

**排产 Agent 的第一号坑不是算法，是「同一个指标，三个部门三套数」。** 手册里所有的架构图都会告诉你哪一层负责把口径钉死。

</div>

<style>
.psa-home-sec { max-width: 1152px; margin: 44px auto 0; padding: 0 24px; }
.psa-home-sec h2 {
  font-size: 1.42rem; font-weight: 760; letter-spacing: -.028em; border: 0; padding: 0; margin: 0 0 14px;
}
.psa-home-sec h2 + p, .psa-home-sec p { max-width: 74ch; }
.psa-claims {
  max-width: 1152px; margin: 30px auto 0; padding: 0 24px;
  display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px;
}
.psa-claims h3 {
  font-size: 13.5px; font-weight: 720; letter-spacing: -.01em; border: 0; padding: 14px 0 0; margin: 0;
  border-top: 2px solid var(--accent); color: var(--ink);
}
.psa-claims p { font-size: 13.2px; line-height: 1.78; color: var(--muted); margin: 8px 0 0; }
.psa-claims strong { color: var(--ink-2); }
@media (max-width: 760px) {
  .psa-home-sec { padding: 0 16px; }
  .psa-claims { padding: 0 16px; gap: 4px; }
}
</style>
