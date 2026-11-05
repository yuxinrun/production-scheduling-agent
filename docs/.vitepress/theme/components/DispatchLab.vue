<script setup lang="ts">
import { computed, reactive, ref } from 'vue'

type Job = { name: string; r: number; p: number; d: number; w: number; tone?: string }

const props = withDefaults(
  defineProps<{
    eyebrow?: string
    title?: string
    lead?: string
    glow?: string
    jobs?: Job[]
    note?: string
  }>(),
  {
    jobs: () => [
      { name: 'J1', r: 0, p: 6, d: 12, w: 3, tone: 'teal' },
      { name: 'J2', r: 0, p: 3, d: 8, w: 1, tone: 'coral' },
      { name: 'J3', r: 2, p: 8, d: 26, w: 2, tone: 'blue' },
      { name: 'J4', r: 4, p: 4, d: 14, w: 5, tone: 'lime' },
      { name: 'J5', r: 6, p: 7, d: 20, w: 1, tone: 'teal' },
      { name: 'J6', r: 8, p: 2, d: 10, w: 4, tone: 'coral' }
    ]
  }
)

const rules = [
  { id: 'FIFO', cn: '先到先排', formula: '按 r↑（到达顺序）', blurb: '车间里的默认做法：谁先来谁先干。它不问交期，所以长任务会把短任务堵死。' },
  { id: 'SPT', cn: '最短加工时间', formula: 'p↑', blurb: '最小化平均流程时间的最优单台规则。代价：交期远的短件插队，急件可能等死。' },
  { id: 'EDD', cn: '最早交期', formula: 'd↑', blurb: '最小化最大延期 Lmax 的最优单台规则。代价：不管任务大小，一个长件能拖垮一排。' },
  { id: 'CR', cn: '关键比', formula: '((d − t)/p)↑', blurb: '把「还剩多少时间」除以「还要干多久」。随时间滚动重算，是车间里最常用的动态规则。' },
  { id: 'WSPT', cn: '加权最短', formula: '(w/p)↑', blurb: '最小化 Σ w·C 的最优单台规则。给关键件、军品件更高权重就靠它。' },
  { id: 'ATC', cn: '老化指数', formula: 'e^((t−r)/h) · (d−p−t)/p ↑', blurb: '在关键比上乘一个「等久了就加分」的老化因子，避免长件永远被短件插队饿死。' }
]

const tones: Record<string, string> = {
  teal: 'var(--accent)',
  coral: 'var(--coral)',
  blue: 'var(--blue)',
  lime: 'var(--lime)'
}

const jobs = reactive<Job[]>(props.jobs.map((j, i) => ({ ...j, tone: j.tone ?? Object.keys(tones)[i % 4] })))
const seed = props.jobs.map((j) => ({ ...j }))
const active = ref('CR')

function keyFor(id: string, j: Job, t: number, h: number) {
  switch (id) {
    case 'FIFO':
      return j.r * 1000 + j.p
    case 'SPT':
      return j.p
    case 'EDD':
      return j.d
    case 'CR':
      return (j.d - t) / Math.max(j.p, 0.01)
    case 'WSPT':
      return -j.w / Math.max(j.p, 0.01)
    case 'ATC': {
      const aging = Math.exp((t - j.r) / Math.max(h, 1))
      return -aging * ((j.d - j.p - t) / Math.max(j.p, 0.01))
    }
    default:
      return 0
  }
}

/* 单台机器的列表调度：每个决策时刻只在「已到达且未完成」里挑优先级最高的一件 */
function simulate(id: string, list: Job[]) {
  const left = list.map((j, i) => ({ ...j, idx: i }))
  const out: { name: string; s: number; e: number; d: number; w: number; tone: string }[] = []
  const done: Record<string, number> = {}
  let t = Math.min(...left.map((j) => j.r))
  let guard = 0
  while (left.length && guard++ < 400) {
    const avail = left.filter((j) => j.r <= t)
    if (!avail.length) {
      t = Math.min(...left.map((j) => j.r))
      continue
    }
    const h = avail.reduce((a, j) => a + j.p, 0) / avail.length
    const pick = avail.reduce((best, j) => (keyFor(id, j, t, h) < keyFor(id, best, t, h) ? j : best))
    out.push({ name: pick.name, s: t, e: t + pick.p, d: pick.d, w: pick.w, tone: pick.tone ?? 'teal' })
    done[pick.name] = t + pick.p
    t += pick.p
    left.splice(left.indexOf(pick), 1)
  }
  return { out, done }
}

const metrics = computed(() => {
  const map: Record<string, any> = {}
  for (const r of rules) {
    const { out, done } = simulate(r.id, jobs)
    let sumT = 0;
    let sumWT = 0;
    let sumFlow = 0;
    let tardy = 0;
    let lmax = -1e9;
    for (const j of jobs) {
      const c = done[j.name]
      if (c == null) continue
      const t = Math.max(0, c - j.d)
      sumT += t
      sumWT += t * j.w
      sumFlow += c - j.r
      if (t > 0) tardy++
      lmax = Math.max(lmax, c - j.d)
    }
    map[r.id] = {
      seq: out.map((o) => o.name).join(' → '),
      gantt: out,
      cmax: out.length ? out[out.length - 1].e : 0,
      sumT,
      sumWT,
      tardy,
      lmax: Math.max(0, lmax),
      flow: jobs.length ? sumFlow / jobs.length : 0
    }
  }
  return map
})

const cur = computed(() => metrics.value[active.value])
const best = computed(() => {
  const ids = rules.map((r) => r.id)
  const pick = (f: (m: any) => number) => {
    let id = ids[0]
    for (const x of ids) if (f(metrics.value[x]) < f(metrics.value[id])) id = x
    return id
  }
  return {
    sumT: pick((m) => m.sumT),
    lmax: pick((m) => m.lmax),
    flow: pick((m) => m.flow),
    cmax: pick((m) => m.cmax)
  }
})

const horizon = computed(() => Math.max(...Object.values(metrics.value).map((m) => m.cmax), 1) + 2)
const ruleMeta = computed(() => Object.fromEntries(rules.map((r) => [r.id, r])))

function reset() {
  jobs.splice(0, jobs.length, ...seed.map((j, i) => ({ ...j, tone: props.jobs[i]?.tone ?? Object.keys(tones)[i % 4] })))
}
</script>

<template>
  <figure class="psa-fig" :class="glow ? 'glow-' + glow : ''">
    <p v-if="eyebrow" class="psa-eyebrow">{{ eyebrow }}</p>
    <p v-if="title" class="psa-h">{{ title }}</p>
    <p v-if="lead" class="psa-lead">{{ lead }}</p>

    <div class="dl-rules">
      <button
        v-for="r in rules"
        :key="r.id"
        type="button"
        class="psa-btn"
        :class="{ 'is-on': r.id === active }"
        :aria-pressed="r.id === active"
        @click="active = r.id"
      >
        {{ r.id }}
      </button>
      <button type="button" class="psa-btn dl-reset" @click="reset">↺ 重置数据</button>
    </div>

    <div class="dl-rule-meta">
      <span class="dl-tag">{{ active }}</span>
      <span class="dl-cn">{{ ruleMeta[active].cn }}</span>
      <code class="dl-formula">{{ ruleMeta[active].formula }}</code>
      <p class="dl-blurb">{{ ruleMeta[active].blurb }}</p>
    </div>

    <div class="dl-grid">
      <div class="dl-edit">
        <p class="dl-cap">工件台账（改工时 / 交期，实时重算）</p>
        <table class="dl-table">
          <thead>
            <tr><th>件</th><th>到达 r</th><th>工时 p</th><th>交期 d</th><th>权重 w</th></tr>
          </thead>
          <tbody>
            <tr v-for="(j, i) in jobs" :key="j.name">
              <td class="dl-name"><i :style="{ background: tones[j.tone ?? 'teal'] }" />{{ j.name }}</td>
              <td class="dl-locked">{{ j.r }}</td>
              <td><input v-model.number="jobs[i].p" type="number" min="1" max="30" step="1" /></td>
              <td><input v-model.number="jobs[i].d" type="number" min="1" max="60" step="1" /></td>
              <td><input v-model.number="jobs[i].w" type="number" min="1" max="9" step="1" /></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="dl-kpi">
        <p class="dl-cap">本次排出来的结果</p>
        <div class="dl-kpi-row"><b>{{ cur.cmax }}</b><span>makespan C<sub>max</sub></span><em v-if="best.cmax === active">最优</em></div>
        <div class="dl-kpi-row"><b>{{ cur.sumT }}</b><span>总延期 ΣT<sub>j</sub></span><em v-if="best.sumT === active">最优</em></div>
        <div class="dl-kpi-row"><b>{{ cur.lmax }}</b><span>最大延期 L<sub>max</sub></span><em v-if="best.lmax === active">最优</em></div>
        <div class="dl-kpi-row"><b>{{ cur.flow.toFixed(1) }}</b><span>平均流程时间</span><em v-if="best.flow === active">最优</em></div>
        <div class="dl-kpi-row"><b>{{ cur.tardy }}/{{ jobs.length }}</b><span>延期件数</span><em v-if="cur.tardy === 0">全准时</em></div>
        <div class="dl-kpi-row"><b>{{ cur.sumWT }}</b><span>加权延期 Σw·T</span><em />
        </div>
      </div>
    </div>

    <div class="dl-gantt">
      <div v-for="r in rules" :key="'g' + r.id" class="dl-grow" :class="{ 'is-active': r.id === active }">
        <span class="dl-glabel">{{ r.id }}</span>
        <span class="dl-gtrack">
          <span
            v-for="(b, i) in metrics[r.id].gantt"
            :key="i"
            class="dl-gbar"
            :style="{
              left: (b.s / horizon) * 100 + '%',
              width: ((b.e - b.s) / horizon) * 100 + '%',
              background: tones[b.tone]
            }"
            :title="`${b.name} ${b.s}→${b.e}（交期 ${b.d}）`"
          >{{ b.name }}</span>
          <span
            v-for="j in jobs"
            :key="'d' + j.name"
            class="dl-gdue"
            :style="{ left: (j.d / horizon) * 100 + '%' }"
            :title="`${j.name} 交期 ${j.d}`"
          />
        </span>
        <span class="dl-gseq">{{ metrics[r.id].seq }}</span>
      </div>
    </div>

    <p v-if="note" class="psa-note">{{ note }}</p>
    <p v-else class="psa-note">
      同一批工件、同一条规则集，六种规则没有一种在所有指标上全胜 —— 这就是「调度规则是权衡，不是答案」。
      红线是各工件交期；ATC 的老化因子让等得久的工件加分，所以它很少把长件饿死。
      单台机器上 SPT 对 ΣC、EDD 对 L<sub>max</sub>、WSPT 对 ΣwC 有可证最优性；上了多机（JSP/FJSP）这些结论全部失效。
    </p>
  </figure>
</template>

<style scoped>
.dl-rules { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 16px; }
.dl-reset { margin-left: auto; font-size: 10px; }

.dl-rule-meta {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px;
  padding: 11px 14px; margin-bottom: 18px;
  border: 1px solid var(--line); border-left: 3px solid var(--accent); border-radius: 10px;
  background: var(--panel-2);
}
.dl-tag { font-family: var(--font-mono); font-size: 11px; font-weight: 600; color: var(--accent); letter-spacing: .08em; }
.dl-cn { font-size: 12.5px; font-weight: 680; color: var(--ink); }
.dl-formula {
  font-family: var(--font-mono); font-size: 10.5px; padding: 2px 8px;
  border: 1px dashed var(--line-strong); border-radius: 5px; color: var(--muted); background: transparent;
}
.dl-blurb { margin: 0; width: 100%; font-size: 12.5px; line-height: 1.72; color: var(--muted); }

.dl-grid { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 20px; margin-bottom: 20px; }
.dl-cap {
  margin: 0 0 8px; font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .14em;
  text-transform: uppercase; color: var(--faint);
}
.dl-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.dl-table th {
  text-align: left; padding: 5px 6px; font-family: var(--font-mono); font-size: 9.5px;
  letter-spacing: .08em; text-transform: uppercase; color: var(--faint);
  border-bottom: 1px solid var(--line-strong); font-weight: 560;
}
.dl-table td { padding: 4px 6px; border-bottom: 1px dashed var(--line); color: var(--ink-2); }
.dl-name { display: flex; align-items: center; gap: 7px; font-family: var(--font-mono); font-size: 11px; }
.dl-name i { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
.dl-locked { font-family: var(--font-mono); color: var(--faint); }
.dl-table input {
  width: 100%; height: 26px; padding: 0 6px; text-align: right;
  border: 1px solid var(--line-strong); border-radius: 6px;
  background: var(--bg); color: var(--ink);
  font-family: var(--font-mono); font-size: 11.5px;
}
.dl-table input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

.dl-kpi { display: flex; flex-direction: column; gap: 6px; }
.dl-kpi-row {
  display: grid; grid-template-columns: 74px minmax(0, 1fr) 52px; align-items: center; gap: 10px;
  padding: 7px 12px; border: 1px solid var(--line); border-radius: 9px; background: var(--panel-2);
}
.dl-kpi-row b { font-family: var(--font-mono); font-size: 1.02rem; font-weight: 600; color: var(--ink); }
.dl-kpi-row span { font-size: 11.5px; color: var(--muted); }
.dl-kpi-row em {
  font-family: var(--font-mono); font-size: 9px; font-style: normal; letter-spacing: .1em;
  text-transform: uppercase; color: var(--accent); text-align: right;
}

.dl-gantt { display: flex; flex-direction: column; gap: 7px; }
.dl-grow {
  display: grid; grid-template-columns: 54px minmax(0, 1fr); gap: 4px 12px; align-items: center;
  padding: 5px 8px; border-radius: 9px; border: 1px solid transparent;
}
.dl-grow.is-active { border-color: var(--line-strong); background: var(--panel-2); }
.dl-glabel { font-family: var(--font-mono); font-size: 10px; letter-spacing: .08em; color: var(--muted); }
.dl-grow.is-active .dl-glabel { color: var(--accent); font-weight: 600; }
.dl-gtrack { position: relative; height: 22px; border-radius: 5px; background: var(--panel-2); border: 1px solid var(--line); overflow: hidden; }
.dl-grow.is-active .dl-gtrack { background: var(--bg); }
.dl-gbar {
  position: absolute; top: 2px; bottom: 2px; display: flex; align-items: center; justify-content: center;
  font-family: var(--font-mono); font-size: 9px; color: #04120f; font-weight: 600;
  border-radius: 3px; overflow: hidden; white-space: nowrap;
}
.dl-gdue { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--coral); opacity: .55; }
.dl-gseq {
  grid-column: 2; font-family: var(--font-mono); font-size: 9.5px; color: var(--faint);
  letter-spacing: .02em; margin-top: 2px;
}

@media (max-width: 860px) {
  .dl-grid { grid-template-columns: minmax(0, 1fr); }
  .dl-kpi-row { grid-template-columns: 64px minmax(0, 1fr) 46px; }
  .dl-gbar { font-size: 8px; }
}
</style>
