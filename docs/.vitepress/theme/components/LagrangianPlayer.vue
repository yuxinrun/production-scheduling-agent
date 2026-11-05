<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import LineChart from './LineChart.vue'

/*
 * 一个真的能算完的小例子：6 个工件、2 台设备，每台设备的可用工时是产能约束。
 * 原问题（每台设备 Σp ≤ T）难在「工件之间被产能耦合」；把产能约束用乘子 λ 放进目标函数后，
 * 子问题按工件完全可分解 —— 每个工件独立挑便宜的机器。这就是拉格朗日松弛的标准套路。
 */
const P = [
  [3, 5],
  [4, 3],
  [2, 4],
  [5, 3],
  [2, 4],
  [4, 2]
]
const C = [
  [4, 7],
  [5, 6],
  [3, 6],
  [6, 4],
  [3, 5],
  [5, 3]
]
const NAMES = ['J1', 'J2', 'J3', 'J4', 'J5', 'J6']
const M = 2

const props = withDefaults(
  defineProps<{ eyebrow?: string; title?: string; lead?: string; glow?: string; note?: string }>(),
  {}
)

const cap = ref(9)
const maxIter = 90
const iter = ref(0)
const playing = ref(false)
let timer: ReturnType<typeof setInterval> | undefined

/* 松弛子问题：给定 λ，逐工件 argmin_k (c + λ·p)，返回下界与产能占用 */
function relax(lam: number[], T: number) {
  let obj = 0
  const load = [0, 0]
  const assign: number[] = []
  for (let j = 0; j < NAMES.length; j++) {
    let bestK = 0
    let bestVal = Infinity
    for (let k = 0; k < M; k++) {
      const v = C[j][k] + lam[k] * P[j][k]
      if (v < bestVal) {
        bestVal = v
        bestK = k
      }
    }
    obj += bestVal
    assign.push(bestK)
    load[bestK] += P[j][bestK]
  }
  const dual = obj - lam[0] * T - lam[1] * T
  return { dual, load, assign, viol: [load[0] - T, load[1] - T] }
}

/* 穷举 2^6 = 64 种分配，拿到真最优 z*（只用于教学对照，真实项目里 64 会变成 640 亿） */
function exact(T: number) {
  let best = Infinity
  let bestMask = 0
  for (let mask = 0; mask < 1 << NAMES.length; mask++) {
    let l0 = 0
    let l1 = 0
    let cost = 0
    for (let j = 0; j < NAMES.length; j++) {
      const k = (mask >> j) & 1
      if (k === 0) l0 += P[j][0]
      else l1 += P[j][1]
      cost += C[j][k]
    }
    if (l0 <= T && l1 <= T && cost < best) {
      best = cost
      bestMask = mask
    }
  }
  return best === Infinity ? null : { cost: best, mask: bestMask }
}

/* 可行解修复：把超载机器上「挪走最划算」的工件搬到对面，直到两边都不超载 */
function repair(assign: number[], T: number) {
  const a = [...assign]
  for (let guard = 0; guard < 60; guard++) {
    const load = [0, 0]
    for (let j = 0; j < a.length; j++) load[a[j]] += P[j][a[j]]
    const over = load.map((v, k) => v - T)
    if (over[0] <= 0 && over[1] <= 0) {
      let cost = 0
      for (let j = 0; j < a.length; j++) cost += C[j][a[j]]
      return { cost, assign: a, load, feasible: true }
    }
    const from = over[0] > over[1] ? 0 : 1
    const to = 1 - from
    let bj = -1
    let bRatio = Infinity
    for (let j = 0; j < a.length; j++) {
      if (a[j] !== from) continue
      const delta = C[j][to] - C[j][from]
      const ratio = (delta + 1e-6) / (P[j][from] + 1e-6)
      if (ratio < bRatio) {
        bRatio = ratio
        bj = j
      }
    }
    if (bj < 0) break
    a[bj] = to
  }
  return { cost: Infinity, assign: a, load: [0, 0], feasible: false }
}

/*
 * 次梯度上升。两个细节：
 * 1) 有效下界是「历史最好的 θ」，不是当前 θ —— 因为 λ 会震荡，原始采样不是单调的；
 * 2) Polyak 步长需要一个上界 U 当靶子；还没有可行解时退化成 ρ/‖s‖ 的几何步长，否则 U=∞ 会把 λ 炸成 NaN。
 */
const run = computed(() => {
  const T = cap.value
  const hist: { raw: number; dual: number; ub: number | null; lam0: number; lam1: number }[] = []
  let lam = [0, 0]
  let bestDual = -Infinity
  let ub = Infinity
  let beta = 2
  let rho = 2.5
  let stale = 0
  const truth = exact(T)
  for (let k = 0; k <= maxIter; k++) {
    const r = relax(lam, T)
    const rp = repair(r.assign, T)
    if (rp.feasible) ub = Math.min(ub, rp.cost)
    if (r.dual > bestDual) bestDual = r.dual
    hist.push({ raw: r.dual, dual: bestDual, ub: Number.isFinite(ub) ? ub : null, lam0: lam[0], lam1: lam[1] })
    if (k === maxIter) break
    const prev = hist[hist.length - 2]
    if (prev && r.dual <= prev.dual + 1e-9) stale++
    else stale = 0
    if (stale > 10) {
      beta *= 0.6
      rho *= 0.85
      stale = 0
    }
    const s = r.viol
    const norm2 = s[0] * s[0] + s[1] * s[1]
    if (norm2 < 1e-12) break
    const step = Number.isFinite(ub) ? (beta * (ub - r.dual)) / norm2 : rho / Math.sqrt(norm2)
    lam = [Math.max(0, lam[0] + step * s[0]), Math.max(0, lam[1] + step * s[1])]
    if (!Number.isFinite(ub) && lam[0] + lam[1] > 60) break
  }
  while (hist.length <= maxIter) hist.push({ ...hist[hist.length - 1] })
  return { hist, truth }
})

const at = computed(() => run.value.hist[Math.min(iter.value, run.value.hist.length - 1)])
const finalAssign = computed(() => {
  const T = cap.value
  const lam = [at.value.lam0, at.value.lam1]
  return relax(lam, T)
})

const series = computed(() => {
  const out: any[] = [
    { tone: 'teal', label: '下界 θ* = 历史最好的 θ(λ)', points: run.value.hist.map((h, i) => [i, h.dual]) },
    { tone: 'ink', label: 'θ(λ) 原始采样（会震荡）', points: run.value.hist.map((h, i) => [i, h.raw]), dashed: true }
  ]
  const ubPts = run.value.hist.map((h, i) => [i, h.ub ?? (h.dual as number)])
  if (run.value.hist.some((h) => h.ub != null)) {
    out.push({ tone: 'blue', label: '上界 U：修复后的可行方案代价', points: ubPts, dashed: true })
  }
  if (run.value.truth) {
    out.push({ tone: 'coral', label: `真最优 z* = ${run.value.truth.cost}（穷举 2⁶=64 种）`, points: run.value.hist.map((h, i) => [i, run.value.truth!.cost]), dashed: true })
  }
  return out
})

const marks = computed(() => [{ x: iter.value, y: at.value.dual, label: `k=${iter.value}`, tone: 'teal' }])

const chartMin = computed(() => Math.min(...run.value.hist.map((h) => h.raw), ...run.value.hist.map((h) => h.dual)))

watch(cap, () => {
  iter.value = 0
})

function toggle() {
  playing.value = !playing.value
  if (playing.value) {
    timer = setInterval(() => {
      if (iter.value >= run.value.hist.length - 1) {
        toggle()
        return
      }
      iter.value++
    }, 130)
  } else if (timer) clearInterval(timer)
}
function step(n: number) {
  playing.value = false
  if (timer) clearInterval(timer)
  iter.value = Math.max(0, Math.min(run.value.hist.length - 1, iter.value + n))
}
</script>

<template>
  <figure class="psa-fig" :class="glow ? 'glow-' + glow : ''">
    <p v-if="eyebrow" class="psa-eyebrow">{{ eyebrow }}</p>
    <p v-if="title" class="psa-h">{{ title }}</p>
    <p v-if="lead" class="psa-lead">{{ lead }}</p>

    <div class="lp-bar">
      <button type="button" class="psa-btn" :class="{ 'is-on': playing }" @click="toggle">
        {{ playing ? '⏸ 暂停' : '▶ 跑次梯度' }}
      </button>
      <button type="button" class="psa-btn" @click="step(-1)">← 一步</button>
      <button type="button" class="psa-btn" @click="step(1)">一步 →</button>
      <button type="button" class="psa-btn" @click="step(999)">→→ 收敛</button>
      <label class="lp-cap">
        <span>每台设备可用工时 T</span>
        <input v-model.number="cap" type="range" min="8" max="16" step="1" />
        <b>{{ cap }}h</b>
      </label>
    </div>

    <div class="lp-stats">
      <div><span>迭代 k</span><b>{{ iter }}</b></div>
      <div><span>λ（设备 1）</span><b>{{ at.lam0.toFixed(3) }}</b></div>
      <div><span>λ（设备 2）</span><b>{{ at.lam1.toFixed(3) }}</b></div>
      <div><span>下界 θ</span><b class="t-teal">{{ at.dual.toFixed(2) }}</b></div>
      <div><span>上界 U</span><b class="t-blue">{{ at.ub ?? '—' }}</b></div>
      <div><span>间隙 U − θ</span><b class="t-coral">{{ at.ub == null ? '—' : (at.ub - at.dual).toFixed(2) }}</b></div>
    </div>

    <LineChart
      eyebrow="收敛过程"
      title="下界往上爬，间隙往里收"
      :series="series"
      :marks="marks"
      :x-ticks="[{ v: 0, label: '0' }, { v: 20, label: '20' }, { v: 40, label: '40' }, { v: 60, label: '60' }, { v: 80, label: '80' }, { v: 90, label: 'k' }]"
      :y-min="chartMin - 1.2"
      :y-max="run.truth ? run.truth.cost + 1 : undefined"
      :bands="at.ub == null ? [] : [{ x0: 0, x1: 90, y0: at.dual, y1: at.ub, tone: 'coral', label: '对偶间隙' }]"
      x-label="次梯度迭代次数 k"
      y-label="代价"
      :height="260"
      note="弱对偶定理保证：只要 λ ≥ 0，θ(λ) 永远 ≤ 真最优 —— 所以下界可以放心拿去剪枝，它不会骗你。上界来自修复出的可行解，永远 ≥ 真最优。"
    />

    <div class="lp-tables">
      <div>
        <p class="lp-cap2">当前 λ 下的松弛解（工件各自挑便宜的机器）</p>
        <table class="lp-tb">
          <thead><tr><th>工件</th><th>p 设备1</th><th>p 设备2</th><th>调整后代价</th><th>选中</th></tr></thead>
          <tbody>
            <tr v-for="(j, i) in NAMES" :key="j">
              <td>{{ j }}</td>
              <td>{{ P[i][0] }}h</td>
              <td>{{ P[i][1] }}h</td>
              <td class="lp-mono">
                {{ (C[i][0] + at.lam0 * P[i][0]).toFixed(1) }} / {{ (C[i][1] + at.lam1 * P[i][1]).toFixed(1) }}
              </td>
              <td :class="'lp-pick tone-' + (finalAssign.assign[i] === 0 ? 'm1' : 'm2')">
                {{ finalAssign.assign[i] === 0 ? '设备 1' : '设备 2' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div>
        <p class="lp-cap2">产能占用（超了就把 λ 推高，让它下次不敢选这边）</p>
        <div v-for="(l, k) in finalAssign.load" :key="k" class="lp-load">
          <span class="lp-load-name">设备 {{ k + 1 }}</span>
          <span class="lp-load-track">
            <span
              class="lp-load-bar"
              :class="{ over: l > cap }"
              :style="{ width: Math.min(100, (l / Math.max(cap, 1)) * 100) + '%' }"
            />
            <span class="lp-load-capline" />
          </span>
          <span class="lp-load-val" :class="{ over: l > cap }">{{ l }}h / {{ cap }}h</span>
        </div>
        <p class="lp-verdict">
          <template v-if="finalAssign.load[0] <= cap && finalAssign.load[1] <= cap">
            松弛解本身就可行 → 它同时是原问题最优解，间隙为 0
          </template>
          <template v-else>
            松弛解不可行 → 必须修复才能下发；θ 与 U 之间留着整数性间隙
          </template>
        </p>
        <p class="lp-truth">
          穷举全部 2<sup>6</sup> = 64 种分配，真最优 z* =
          <b>{{ run.truth ? run.truth.cost : '无可行解（T 太紧，两台设备都塞不下）' }}</b>
          <span v-if="run.truth && at.ub != null && run.truth.cost - at.dual > 0.01">
            · θ 收敛到 {{ at.dual.toFixed(2) }}，比 z* 低 {{ (run.truth.cost - at.dual).toFixed(2) }} —— 这就是对偶间隙（整数性间隙）
          </span>
          <span v-else-if="run.truth && at.ub != null">
            · θ 已经追平 z*：这次松弛是「精确」的，可惜一般问题不会这么便宜
          </span>
        </p>
      </div>
    </div>

    <p v-if="note" class="psa-note">{{ note }}</p>
    <p v-else class="psa-note">
      次梯度法只有次梯度方向，不是下降方向，所以 λ 会震荡 —— 图上看得见。工程上因此配上「候选解池 + 步长折半 +
      固定 λ 求多组解」三件套（bundle 方法 / 次梯度聚合），而不是一路裸跑。
      把 T 拖小：产能一紧，间隙立刻变大，这正是排产项目里「松弛下界不能直接当方案」的原因。
    </p>
  </figure>
</template>

<style scoped>
.lp-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 16px; }
.lp-cap {
  display: inline-flex; align-items: center; gap: 9px; margin-left: auto;
  font-family: var(--font-mono); font-size: 10px; letter-spacing: .06em; color: var(--muted);
}
.lp-cap b { color: var(--coral); font-size: 12px; }
.lp-cap input { width: 104px; accent-color: var(--coral); }

.lp-stats {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(104px, 1fr)); gap: 1px;
  background: var(--line); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; margin-bottom: 8px;
}
.lp-stats div { background: var(--panel); padding: 9px 12px; display: flex; flex-direction: column; gap: 3px; }
.lp-stats span {
  font-family: var(--font-mono); font-size: 9px; letter-spacing: .1em; text-transform: uppercase; color: var(--faint);
}
.lp-stats b { font-family: var(--font-mono); font-size: 14px; font-weight: 600; color: var(--ink); }
.t-teal { color: var(--accent) !important; }
.t-blue { color: var(--blue) !important; }
.t-coral { color: var(--coral) !important; }

.lp-tables {
  display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 22px;
  margin-top: 6px; padding-top: 18px; border-top: 1px dashed var(--line-strong);
}
.lp-cap2 {
  margin: 0 0 8px; font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .12em;
  text-transform: uppercase; color: var(--faint);
}
.lp-tb { width: 100%; border-collapse: collapse; font-size: 11.5px; }
.lp-tb th {
  text-align: left; padding: 4px 6px; font-family: var(--font-mono); font-size: 9px; letter-spacing: .06em;
  text-transform: uppercase; color: var(--faint); border-bottom: 1px solid var(--line-strong); font-weight: 560;
}
.lp-tb td { padding: 4px 6px; border-bottom: 1px dashed var(--line); color: var(--ink-2); }
.lp-mono { font-family: var(--font-mono); font-size: 10.5px; color: var(--muted); }
.lp-pick { font-family: var(--font-mono); font-size: 10px; }
.lp-pick.tone-m1 { color: var(--accent); } .lp-pick.tone-m2 { color: var(--blue); }

.lp-load { display: grid; grid-template-columns: 52px minmax(0, 1fr) 74px; align-items: center; gap: 10px; margin-bottom: 7px; }
.lp-load-name { font-family: var(--font-mono); font-size: 10px; color: var(--muted); }
.lp-load-track { position: relative; height: 13px; border: 1px solid var(--line); border-radius: 4px; background: var(--panel-2); }
.lp-load-bar { position: absolute; inset: 1px auto 1px 1px; border-radius: 3px; background: var(--accent); transition: width .25s var(--ease); }
.lp-load-bar.over { background: var(--coral); }
.lp-load-capline { position: absolute; right: 0; top: -3px; bottom: -3px; width: 1px; background: var(--ink-2); opacity: .6; }
.lp-load-val { font-family: var(--font-mono); font-size: 10.5px; text-align: right; color: var(--muted); }
.lp-load-val.over { color: var(--coral); font-weight: 600; }

.lp-verdict { margin: 12px 0 4px; font-size: 12px; line-height: 1.7; color: var(--ink-2); }
.lp-truth { margin: 0; font-family: var(--font-mono); font-size: 10.5px; line-height: 1.7; color: var(--faint); }
.lp-truth b { color: var(--coral); }

@media (max-width: 860px) {
  .lp-tables { grid-template-columns: minmax(0, 1fr); gap: 18px; }
  .lp-cap { margin-left: 0; width: 100%; }
}
</style>
