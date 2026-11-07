<script setup lang="ts">
import { computed, ref, watch } from 'vue'

type Stage = { name: string; en: string; finish: number; buffer: number; orders: number; tone: string; frozen: boolean }

const props = withDefaults(
  defineProps<{
    eyebrow?: string
    title?: string
    lead?: string
    glow?: string
    note?: string
    stages?: Stage[]
    events?: { id: string; name: string; hits: number; base: number; kind: string; desc: string }[]
  }>(),
  {
    stages: () => [
      { name: '锻造', en: 'A-01', finish: 12, buffer: 6, orders: 4, tone: 'teal', frozen: false },
      { name: '机加工', en: 'A-02', finish: 26, buffer: 4, orders: 9, tone: 'blue', frozen: true },
      { name: '表面热处理', en: 'A-03', finish: 38, buffer: 10, orders: 7, tone: 'coral', frozen: true },
      { name: '装配', en: 'A-05', finish: 52, buffer: 3, orders: 12, tone: 'lime', frozen: true },
      { name: '试车', en: 'A-06', finish: 62, buffer: 8, orders: 5, tone: 'teal', frozen: false }
    ],
    events: () => [
      { id: 'brk', name: '五轴设备故障', hits: 1, base: 8, kind: '设备', desc: '瓶颈设备停机：备件到货 + 复位 + 首件检验。机加是五轴独此一家，没有替代路径。' },
      { id: 'rush', name: '军品急件插入', hits: 1, base: 6, kind: '插单', desc: 'P0 急件要挤进机加队列。插单优先级评分卡未签署时，这一步只能靠计划员拍脑袋。' },
      { id: 'nib', name: '探伤不合格返工', hits: 2, base: 12, kind: '质量', desc: 'X 射线探伤不合格 → 补焊 → 复检。返工是概率事件，缓冲必须按合格率分布来给。' },
      { id: 'sub', name: '外协件延误', hits: 3, base: 24, kind: '供应', desc: '外协钣金件没到，装配工位等米下锅。外协进度是黑箱，通常当天才发现。' },
      { id: 'furn', name: '热处理炉检修超时', hits: 2, base: 10, kind: '设备', desc: '炉子提前检修或检修拖期，组批窗口整体后移，满炉率随之下降。' }
    ]
  }
)

const picked = ref(props.events[0].id)
const shock = ref(0)
const maxBuffer = ref(false)

const cur = computed(() => props.events.find((e) => e.id === picked.value)!)
const impact = computed(() => (maxBuffer.value ? 48 : cur.value.base + shock.value))

/*
 * 涟漪传播：冲击只从出事那一段进入链条；每段先用自己缓冲吃，吃不下的往下一段传。
 * 缓冲是唯一的堤坝 —— 缓冲为 0 的那一段，就是把洪水往下游倒的那一段。
 */
const ripple = computed(() => {
  const k0 = cur.value.hits
  let carry = 0
  const rows: { st: Stage; absorb: number; pass: number; hit: boolean; slip: number }[] = []
  for (let i = 0; i < props.stages.length; i++) {
    const st = props.stages[i]
    if (i === k0) carry += impact.value
    const absorb = Math.min(carry, st.buffer)
    const pass = carry - absorb
    rows.push({ st, absorb, pass, hit: i === k0, slip: carry })
    carry = pass
  }
  return rows
})

const totalAffected = computed(() =>
  ripple.value.filter((r) => r.slip > 0.001).reduce((a, r) => a + r.st.orders, 0)
)
const endDelay = computed(() => ripple.value[ripple.value.length - 1].slip)
const frozenBreached = computed(() => ripple.value.some((r) => r.slip > 0.001 && r.st.frozen))

watch(picked, () => {
  shock.value = 0
  maxBuffer.value = false
})

const worst = computed(() => Math.max(1, ...ripple.value.map((r) => r.slip)))
</script>

<template>
  <figure class="psa-fig" :class="glow ? 'glow-' + glow : ''">
    <p v-if="eyebrow" class="psa-eyebrow">{{ eyebrow }}</p>
    <p v-if="title" class="psa-h">{{ title }}</p>
    <p v-if="lead" class="psa-lead">{{ lead }}</p>

    <div class="cr-picks">
      <button
        v-for="e in events"
        :key="e.id"
        type="button"
        class="psa-btn"
        :class="{ 'is-on': e.id === picked }"
        @click="picked = e.id"
      >
        {{ e.name }}
      </button>
    </div>

    <div class="cr-kicker">
      <span class="cr-kind">{{ cur.kind }}</span>
      <p class="cr-desc">{{ cur.desc }}</p>
      <label class="cr-shock">
        <span>冲击再加</span>
        <input v-model.number="shock" type="range" min="0" max="36" step="2" />
        <b>+{{ shock }}h</b>
      </label>
      <button type="button" class="psa-btn" :class="{ 'is-on': maxBuffer }" @click="maxBuffer = !maxBuffer">
        压满缓冲 48h
      </button>
    </div>

    <div class="cr-chain">
      <template v-for="(r, i) in ripple" :key="r.st.name">
        <div class="cr-node" :class="{ 'is-hit': r.hit, 'is-hot': r.slip > 0.001 && !r.hit, 'is-frozen': r.st.frozen }">
          <p class="cr-code">{{ r.st.en }} · 计划完工 {{ r.st.finish }}h</p>
          <p class="cr-name">{{ r.st.name }}</p>
          <div class="cr-nums">
            <p><span>波及</span><b>{{ r.slip.toFixed(0) }}h</b></p>
            <p><span>缓冲吃掉</span><b class="ok">{{ r.absorb.toFixed(0) }}h</b></p>
            <p><span>传给下道</span><b :class="{ bad: r.pass > 0 }">{{ r.pass.toFixed(0) }}h</b></p>
          </div>
          <div class="cr-meter">
            <i class="cr-abs" :style="{ width: (r.absorb / worst) * 100 + '%' }" />
            <i class="cr-pass" :style="{ width: (r.pass / worst) * 100 + '%' }" />
          </div>
          <p class="cr-meta">
            缓冲池 {{ r.st.buffer }}h · 波及工单 {{ r.slip > 0.001 ? r.st.orders : 0 }} 张
            <em v-if="r.st.frozen" class="cr-frz">冻结窗口内</em>
          </p>
        </div>
        <div v-if="i < ripple.length - 1" class="cr-arrow" :class="{ flowing: ripple[i + 1].slip > 0.001 }">
          <span>{{ ripple[i + 1].slip > 0.001 ? ripple[i + 1].slip.toFixed(0) + 'h' : '止' }}</span>
        </div>
      </template>
    </div>

    <div class="cr-verdict">
      <div>
        <span class="cr-vlabel">源头注入</span>
        <b>{{ impact }}h</b>
        <em>{{ cur.name }} @ {{ stages[cur.hits].name }}</em>
      </div>
      <div>
        <span class="cr-vlabel">传到试车尾端</span>
        <b :class="{ bad: endDelay > 0 }">{{ endDelay.toFixed(0) }}h</b>
        <em>缓冲总共拦下 {{ (impact - endDelay).toFixed(0) }}h</em>
      </div>
      <div>
        <span class="cr-vlabel">受影响工单</span>
        <b>{{ totalAffected }}</b>
        <em>张（含源头工序）</em>
      </div>
      <div>
        <span class="cr-vlabel">要不要升级</span>
        <b :class="{ bad: frozenBreached }">{{ frozenBreached ? '要审批' : '局部消化' }}</b>
        <em>{{ frozenBreached ? '触碰冻结窗口 → 走审批卡片' : '未碰冻结区 → 局部重排即可' }}</em>
      </div>
    </div>

    <p v-if="note" class="psa-note">{{ note }}</p>
    <p v-else class="psa-note">
      这是一个「一阶」涟漪模型：只沿工艺链正向传，不算并行设备抢产能、不看换型矩阵。
      真实系统里这一步靠工艺路线 DAG + 设备能力拓扑做拓扑传播（某某项目用图谱引擎做，验收 KPI 是 ≤15 分钟出影响面）。
      把它当直觉训练器用：先看清「缓冲是唯一的堤坝」，再去啃真图。
    </p>
  </figure>
</template>

<style scoped>
.cr-picks { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }

.cr-kicker {
  display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px;
  padding: 12px 15px; margin-bottom: 20px; border-radius: 11px;
  border: 1px solid var(--line); border-left: 3px solid var(--coral); background: var(--panel-2);
}
.cr-kind {
  font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .12em; text-transform: uppercase;
  padding: 3px 9px; border-radius: 999px; background: var(--coral); color: #fff;
}
html.dark .cr-kind { color: #1b0703; }
.cr-desc { margin: 0; flex: 1 1 320px; font-size: 12.5px; line-height: 1.72; color: var(--muted); }
.cr-shock { display: inline-flex; align-items: center; gap: 8px; font-family: var(--font-mono); font-size: 10px; color: var(--muted); }
.cr-shock b { color: var(--coral); font-size: 11.5px; }
.cr-shock input { width: 96px; accent-color: var(--coral); }

.cr-chain {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(0, 1fr);
  gap: 0;
  align-items: stretch;
}
.cr-node {
  min-width: 0;
  padding: 12px 12px 10px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel-2);
  transition: border-color .2s var(--ease), transform .2s var(--ease);
}
.cr-node.is-hot { border-color: var(--blue); }
.cr-node.is-hit { border-color: var(--coral); background: var(--bg); box-shadow: 0 10px 26px -18px var(--coral); }
.cr-node.is-frozen { border-style: dashed; }
.cr-code {
  margin: 0 0 3px; font-family: var(--font-mono); font-size: 8.8px; letter-spacing: .1em;
  text-transform: uppercase; color: var(--faint);
}
.cr-name { margin: 0 0 9px; font-size: 13.5px; font-weight: 720; letter-spacing: -.01em; color: var(--ink); }
.cr-nums { display: flex; flex-direction: column; gap: 2px; margin-bottom: 9px; }
.cr-nums p { margin: 0; display: flex; justify-content: space-between; gap: 6px; font-family: var(--font-mono); font-size: 9.6px; color: var(--faint); }
.cr-nums b { color: var(--ink-2); font-weight: 600; }
.cr-nums b.ok { color: var(--accent); }
.cr-nums b.bad { color: var(--coral); }
.cr-meter { display: flex; height: 8px; border-radius: 3px; overflow: hidden; background: var(--panel); border: 1px solid var(--line); }
.cr-abs { display: block; height: 100%; background: var(--accent); }
.cr-pass { display: block; height: 100%; background: var(--coral); }
.cr-meta { margin: 8px 0 0; font-family: var(--font-mono); font-size: 9px; line-height: 1.6; color: var(--faint); }
.cr-frz { font-style: normal; color: var(--blue); }

.cr-arrow {
  display: flex; align-items: center; justify-content: center; width: 100%; min-width: 34px;
  font-family: var(--font-mono); font-size: 9.5px; color: var(--faint); position: relative;
}
.cr-arrow::before { content: ''; position: absolute; left: 4px; right: 4px; top: 50%; border-top: 1px dashed var(--line-strong); }
.cr-arrow span { position: relative; z-index: 1; padding: 1px 5px; border-radius: 4px; background: var(--panel); }
.cr-arrow.flowing span { color: var(--coral); border: 1px solid var(--coral); }
.cr-arrow.flowing::before { border-top-style: solid; border-top-color: var(--coral); }

.cr-verdict {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1px;
  margin-top: 20px; background: var(--line); border: 1px solid var(--line); border-radius: 12px; overflow: hidden;
}
.cr-verdict div { background: var(--panel); padding: 11px 14px; display: flex; flex-direction: column; gap: 2px; }
.cr-vlabel { font-family: var(--font-mono); font-size: 9px; letter-spacing: .12em; text-transform: uppercase; color: var(--faint); }
.cr-verdict b { font-family: var(--font-mono); font-size: 1.14rem; font-weight: 600; color: var(--ink); }
.cr-verdict b.bad { color: var(--coral); }
.cr-verdict em { font-style: normal; font-size: 10.5px; color: var(--muted); }

@media (max-width: 960px) {
  .cr-chain { grid-auto-flow: row; grid-auto-columns: auto; gap: 4px 0; }
  .cr-arrow { min-width: 0; height: 26px; }
  .cr-arrow::before { top: 50%; left: 24%; right: 24%; }
  .cr-desc { flex-basis: 100%; }
}
</style>
