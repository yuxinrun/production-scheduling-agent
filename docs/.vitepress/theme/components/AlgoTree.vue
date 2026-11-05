<script setup lang="ts">
import { computed, reactive } from 'vue'

type Algo = { id: string; name: string; en: string; tone: string; why: string; cost: string }
type Opt = { label: string; hint: string; w: Record<string, number> }

const props = withDefaults(
  defineProps<{ eyebrow?: string; title?: string; lead?: string; glow?: string; note?: string }>(),
  {}
)

const algos: Algo[] = [
  {
    id: 'exact',
    name: '数学规划 + 分支定界',
    en: 'MILP / B&B / 割平面',
    tone: 'teal',
    why: '唯一能给出「这就是最优」和「证明给你看」的路线。松弛下界还能拿来剪枝。',
    cost: '规模一上去就指数爆炸；非线性目标（利用率、换型矩阵）很难写进去。'
  },
  {
    id: 'cp',
    name: '约束规划',
    en: 'CP / CP-SAT / no_overlap',
    tone: 'blue',
    why: '排产事实上的主力。时序逻辑约束写得像人话，传播器（edge-finding）会自动砍掉大半搜索空间。',
    cost: '整数变量多时内存吃紧；商用求解器要授权，开源 CP-SAT 免费但对超大图也吃力。'
  },
  {
    id: 'lag',
    name: '拉格朗日松弛',
    en: 'Lagrangian relaxation',
    tone: 'lime',
    why: '把「耦合工件的那条产能约束」松弛进目标，子问题立刻按工件分解、可以并行；给你一个能拿去剪枝的下界。',
    cost: '有对偶间隙；次梯度要调步长、会震荡；解出来的松弛解通常不可行，还得配修复启发式。'
  },
  {
    id: 'mh',
    name: '元启发式',
    en: 'GA / SA / TS / ALNS / 移瓶颈',
    tone: 'coral',
    why: '什么都能装：换型矩阵、能耗、加班、特殊过程窗口，全塞进适应度函数就行。中等规模性价比最高。',
    cost: '没有最优性保证，同一份数据两次跑结果不同；参数一调就得重测，验收时会很难看。'
  },
  {
    id: 'rule',
    name: '调度规则派单',
    en: 'SPT / EDD / CR / WSPT / ATC',
    tone: 'ink',
    why: '毫秒级、零授权费、计划员看得懂、现场肯用。单台机器上还有可证最优性。',
    cost: '多机耦合就失效；只会「派单」不会「规划」，跨工序齐套与批量优化无能为力。'
  },
  {
    id: 'rl',
    name: '强化学习 / GNN 策略',
    en: 'RL for JSP/FJSP',
    tone: 'blue',
    why: '训练一次、推理极快，天生适合事件驱动的实时重排；能把「过去怎么排得好」学进策略。',
    cost: '样本贵、泛化差（换一批订单就掉点）、不可解释；军工场景里「为什么这样排」答不上来就上不了线。'
  },
  {
    id: 'llm',
    name: 'LLM 编排 + 求解器执行',
    en: 'LLM as orchestrator',
    tone: 'lime',
    why: '不是让大模型排产，是让它读懂人话、拆任务、挑工具、解释结果 —— 取数和寻优交给确定性内核。',
    cost: '模型不能碰数值真相；必须做降级（模型不可用时排产照常跑）与留痕，否则审计过不了。'
  }
]

const steps: { q: string; help: string; options: Opt[] }[] = [
  {
    q: '这道题多大？',
    help: '按同时在排的「工序数」估，不是订单数。',
    options: [
      { label: '≤ 30 工序', hint: '一个工位的一天', w: { exact: 3, cp: 3, rule: 1, lag: 2 } },
      { label: '30 – 300', hint: '一个车间一个班次', w: { cp: 3, exact: 2, mh: 2, lag: 2 } },
      { label: '300 – 3000', hint: '全厂一日计划', w: { mh: 3, lag: 3, cp: 2, rule: 1 } },
      { label: '> 3000', hint: '多厂 / 月台计划', w: { lag: 3, mh: 2, rule: 2, rl: 1, cp: 1 } }
    ]
  },
  {
    q: '要多准？',
    help: '「准」的定义决定成本：要证明最优，还是要个能执行的方案。',
    options: [
      { label: '必须最优，要能证明', hint: '验收/审计要看间隙', w: { exact: 4, cp: 3, lag: 3, mh: -2, rule: -3 } },
      { label: '比人工好 5% 就行', hint: '最常见的真实要求', w: { cp: 3, mh: 3, lag: 2, exact: 1 } },
      { label: '分钟内出可用方案', hint: '调度会上就要拍板', w: { rule: 4, mh: 2, rl: 2, cp: 1, exact: -3 } },
      { label: '别违反硬约束就好', hint: '先求可行，再求好', w: { rule: 3, cp: 2, mh: 1 } }
    ]
  },
  {
    q: '约束长什么样？',
    help: '约束的形状比数量更决定选型。',
    options: [
      { label: '线性产能 + 交期', hint: 'Σp ≤ T、C ≤ d 这类', w: { exact: 4, lag: 3, cp: 1 } },
      { label: '大量时序逻辑', hint: '不相交、时窗、必须先/后、间隔', w: { cp: 5, mh: 1, exact: -2 } },
      { label: '工序可选多台设备', hint: 'FJSP：柔性带来组合爆炸', w: { mh: 3, cp: 3, rl: 2 } },
      { label: '跨工序链式 + 外协', hint: '转运时窗、凑批等待', w: { lag: 3, mh: 2, cp: 2, llm: 2 } }
    ]
  },
  {
    q: '多久重排一次？',
    help: '重排频率是隐形的规模放大器：夜里跑一次和每次扰动跑一次，是两个量级。',
    options: [
      { label: '夜间全量重排', hint: '1~2 小时窗口', w: { exact: 2, cp: 2, mh: 3, lag: 2 } },
      { label: '班次级局部重排', hint: '≤30 分钟', w: { rule: 3, cp: 2, mh: 2, lag: 1 } },
      { label: '事件驱动，分钟级', hint: '设备一停就得改', w: { rule: 4, rl: 4, cp: 1, exact: -4, mh: -1 } },
      { label: '周滚动，锁 3 天', hint: '冻结窗口内不改', w: { exact: 2, cp: 3, mh: 1, llm: 1 } }
    ]
  },
  {
    q: '数据和规则成熟吗？',
    help: '这一问决定「现在能不能上」，而不是「理论上谁最好」。',
    options: [
      { label: '工时/日历/BOM 都准，规则已签署', hint: '理想态', w: { exact: 3, cp: 3, lag: 3, rl: 2 } },
      { label: '规则还在老师傅脑子里', hint: '先显性化，别先优化', w: { rule: 3, llm: 3, mh: 1, exact: -3 } },
      { label: '数据缺口大、报工不回流', hint: '没有实绩就没有闭环', w: { rule: 4, llm: 2, rl: -3, exact: -4 } },
      { label: '有 3 年以上实绩数据', hint: '可以拿来学', w: { rl: 4, mh: 2, exact: 1, llm: 2 } }
    ]
  }
]

const answers = reactive<Record<number, number>>({})

function pick(si: number, oi: number) {
  answers[si] = answers[si] === oi ? -1 : oi
}
function clearAll() {
  for (const k of Object.keys(answers)) delete answers[Number(k)]
}

const scored = computed(() => {
  const sum: Record<string, number> = Object.fromEntries(algos.map((a) => [a.id, 0]))
  for (const [si, oi] of Object.entries(answers)) {
    if (oi == null || oi < 0) continue
    const w = steps[Number(si)].options[oi].w
    for (const [k, v] of Object.entries(w)) if (sum[k] != null) sum[k] += v
  }
  const answered = Object.values(answers).filter((v) => v >= 0).length
  return {
    answered,
    ranked: algos
      .map((a) => ({ ...a, score: Math.max(0, sum[a.id]) }))
      .sort((x, y) => y.score - x.score),
    max: Math.max(1, ...Object.values(sum))
  }
})

const topIds = computed(() => scored.value.ranked.filter((a) => a.score >= 0 && a.score >= scored.value.max * 0.55).slice(0, 3))
</script>

<template>
  <figure class="psa-fig" :class="glow ? 'glow-' + glow : ''">
    <p v-if="eyebrow" class="psa-eyebrow">{{ eyebrow }}</p>
    <p v-if="title" class="psa-h">{{ title }}</p>
    <p v-if="lead" class="psa-lead">{{ lead }}</p>

    <div class="at-grid">
      <div class="at-qs">
        <div v-for="(s, si) in steps" :key="si" class="at-q">
          <p class="at-qh">
            <span class="at-idx">{{ String(si + 1).padStart(2, '0') }}</span>
            {{ s.q }}
          </p>
          <p class="at-help">{{ s.help }}</p>
          <div class="at-opts">
            <button
              v-for="(o, oi) in s.options"
              :key="o.label"
              type="button"
              class="at-opt"
              :class="{ 'is-on': answers[si] === oi }"
              @click="pick(si, oi)"
            >
              <b>{{ o.label }}</b>
              <span>{{ o.hint }}</span>
            </button>
          </div>
        </div>
        <div class="at-foot">
          <span class="at-count">已答 {{ scored.answered }} / {{ steps.length }}</span>
          <button type="button" class="psa-btn" @click="clearAll">↺ 清空</button>
        </div>
      </div>

      <div class="at-out">
        <p class="at-cap">选型建议（随点随算）</p>
        <div v-if="scored.answered === 0" class="at-idle">
          左边五问全选完，这里会给出排序。<em>没有万能算法，只有对得上约束形状的那一个。</em>
        </div>
        <ol v-else class="at-rank">
          <li v-for="a in scored.ranked" :key="a.id" :class="{ 'is-top': topIds.includes(a.id), 'is-bad': a.score <= 0 }">
            <span class="at-rank-head">
              <i :class="'dot-' + a.tone" />
              <b>{{ a.name }}</b>
              <span class="at-en">{{ a.en }}</span>
              <em v-if="topIds.includes(a.id)" class="at-pick">推荐</em>
            </span>
            <span class="at-rank-bar">
              <i :class="'bar-' + a.tone" :style="{ width: Math.min(100, (a.score / scored.max) * 100) + '%' }" />
            </span>
            <span v-if="topIds.includes(a.id)" class="at-rank-why">
              <b>为什么：</b>{{ a.why }}
              <br />
              <b>代价：</b>{{ a.cost }}
            </span>
          </li>
        </ol>
        <p v-if="scored.answered > 0" class="at-warn">
          分数是「这五个回答对各路线的适配度」，不是性能排名。任何一条路线都要先在你的黄金集上跑一次才算数。
        </p>
      </div>
    </div>

    <p v-if="note" class="psa-note">{{ note }}</p>
    <p v-else class="psa-note">
      工业界的真实答案几乎永远是「组合拳」：规则派单兜住实时性，CP 或 MILP 做局部最优，松弛下界判断「已经够好了」，
      元启发式负责把大范围搜完，LLM 只在最外层做人话接口 —— 数值真相必须由确定性内核产出。
    </p>
  </figure>
</template>

<style scoped>
.at-grid { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 24px; }
.at-qs { display: flex; flex-direction: column; gap: 16px; }
.at-qh {
  margin: 0 0 2px; display: flex; align-items: baseline; gap: 8px;
  font-size: 13px; font-weight: 720; letter-spacing: -.01em; color: var(--ink);
}
.at-idx {
  font-family: var(--font-mono); font-size: 9.5px; color: var(--accent);
  border: 1px solid var(--accent); border-radius: 4px; padding: 1px 4px;
}
.at-help { margin: 0 0 8px; font-family: var(--font-mono); font-size: 9.6px; color: var(--faint); letter-spacing: .01em; }
.at-opts { display: flex; flex-direction: column; gap: 6px; }
.at-opt {
  display: flex; flex-direction: column; align-items: flex-start; gap: 1px; text-align: left;
  padding: 8px 12px; border: 1px solid var(--line-strong); border-radius: 9px; background: var(--panel-2);
  cursor: pointer; transition: all .16s var(--ease);
}
.at-opt:hover { border-color: var(--accent); transform: translateX(2px); }
.at-opt.is-on { border-color: var(--accent); background: var(--bg); box-shadow: inset 3px 0 0 var(--accent); }
.at-opt b { font-size: 12.5px; font-weight: 680; color: var(--ink); }
.at-opt span { font-family: var(--font-mono); font-size: 9.5px; color: var(--faint); }
.at-opt.is-on span { color: var(--muted); }
.at-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 2px; }
.at-count { font-family: var(--font-mono); font-size: 10px; letter-spacing: .1em; color: var(--muted); }

.at-out { border-left: 1px dashed var(--line-strong); padding-left: 22px; }
.at-cap {
  margin: 0 0 10px; font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .14em;
  text-transform: uppercase; color: var(--faint);
}
.at-idle { font-size: 12.5px; line-height: 1.8; color: var(--muted); }
.at-idle em { display: block; font-style: normal; margin-top: 8px; color: var(--faint); font-family: var(--font-mono); font-size: 10.5px; }
.at-rank { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 9px; }
.at-rank li { padding: 8px 10px; border-radius: 9px; border: 1px solid transparent; }
.at-rank li.is-top { border-color: var(--line-strong); background: var(--panel-2); }
.at-rank li.is-bad { opacity: .42; }
.at-rank-head { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; }
.dot-teal, .dot-coral, .dot-blue, .dot-lime, .dot-ink { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
.dot-teal { background: var(--accent); } .dot-coral { background: var(--coral); }
.dot-blue { background: var(--blue); } .dot-lime { background: var(--lime); } .dot-ink { background: var(--ink-2); }
.at-rank-head b { font-size: 12.5px; font-weight: 700; color: var(--ink); }
.at-en { font-family: var(--font-mono); font-size: 9.5px; color: var(--faint); }
.at-pick {
  font-style: normal; font-family: var(--font-mono); font-size: 8.6px; letter-spacing: .1em; text-transform: uppercase;
  padding: 1px 6px; border-radius: 999px; background: var(--ink); color: var(--bg);
}
html.dark .at-pick { background: var(--accent); color: var(--accent-ink); }
.at-rank-bar { display: block; height: 6px; margin: 6px 0 0; border-radius: 3px; background: var(--panel); border: 1px solid var(--line); overflow: hidden; }
.at-rank-bar i { display: block; height: 100%; transition: width .3s var(--ease); }
.bar-teal { background: var(--accent); } .bar-coral { background: var(--coral); }
.bar-blue { background: var(--blue); } .bar-lime { background: var(--lime); } .bar-ink { background: var(--ink-2); }
.at-rank-why { display: block; margin-top: 7px; font-size: 11.8px; line-height: 1.72; color: var(--muted); }
.at-rank-why b { color: var(--ink-2); font-weight: 680; font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .08em; text-transform: uppercase; }
.at-warn {
  margin: 14px 0 0; padding-top: 12px; border-top: 1px dashed var(--line-strong);
  font-family: var(--font-mono); font-size: 10px; line-height: 1.7; color: var(--faint);
}

@media (max-width: 900px) {
  .at-grid { grid-template-columns: minmax(0, 1fr); }
  .at-out { border-left: 0; padding-left: 0; padding-top: 18px; border-top: 1px dashed var(--line-strong); }
}
</style>
