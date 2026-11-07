<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    eyebrow?: string
    title?: string
    lead?: string
    glow?: string
    series: { tone: string; label: string; points: number[][]; dashed?: boolean; dots?: boolean; area?: boolean }[]
    xTicks: { v: number; label: string }[]
    yTicks?: { v: number; label: string }[]
    xMin?: number
    xMax?: number
    yMin?: number
    yMax?: number
    bands?: { x0?: number; x1?: number; y0?: number; y1?: number; tone?: string; label?: string }[]
    marks?: { x: number; y: number; label: string; tone?: string }[]
    xLabel?: string
    yLabel?: string
    note?: string
    height?: number
  }>(),
  { height: 300, series: () => [], xTicks: () => [] }
)

const W = 760
const padL = 58
const padR = 22
const padT = 18
const padB = 46
const H = computed(() => props.height)
const plotW = W - padL - padR
const plotH = () => H.value - padT - padB

// Markdown 里若把 :yMin="0" 写成 yMin="0"，静态属性进 props 就是字符串，
// 会让 fmt() 的 v.toFixed 抛错、整页 SSR 失败，所以这里统一归一化成数字。
const num = (v: unknown) => {
  if (v === null || v === undefined || v === '') return undefined
  const n = Number(v)
  return Number.isFinite(n) ? n : undefined
}

const bounds = computed(() => {
  const all = props.series.flatMap((s) => s.points)
  const xs = all.map((p) => p[0])
  const ys = all.map((p) => p[1])
  return {
    x0: num(props.xMin) ?? Math.min(...xs),
    x1: num(props.xMax) ?? Math.max(...xs),
    y0: num(props.yMin) ?? Math.min(0, ...ys),
    y1: num(props.yMax) ?? Math.max(...ys) * 1.08
  }
})

const sx = (x: number) => padL + ((x - bounds.value.x0) / (bounds.value.x1 - bounds.value.x0 || 1)) * plotW
const sy = (y: number) => H.value - padB - ((y - bounds.value.y0) / (bounds.value.y1 - bounds.value.y0 || 1)) * plotH()

const line = (pts: number[][]) => pts.map((p, i) => `${i ? 'L' : 'M'}${sx(p[0]).toFixed(1)} ${sy(p[1]).toFixed(1)}`).join('')
const area = (pts: number[][]) =>
  `${line(pts)}L${sx(pts[pts.length - 1][0]).toFixed(1)} ${sy(bounds.value.y0).toFixed(1)}L${sx(pts[0][0]).toFixed(1)} ${sy(bounds.value.y0).toFixed(1)}Z`

const yTicks = computed(() => {
  const fmt = (v: number) => {
    if (v >= 10000) return (v / 1000).toFixed(0) + 'k'
    const span = bounds.value.y1 - bounds.value.y0
    if (span < 20) return v.toFixed(1)
    if (span < 200) return v.toFixed(v >= 100 ? 0 : 1)
    return v.toFixed(0)
  }
  if (Array.isArray(props.yTicks) && props.yTicks.length) return props.yTicks
  const b = bounds.value
  const n = 4
  return Array.from({ length: n + 1 }, (_, i) => {
    const v = b.y0 + ((b.y1 - b.y0) * i) / n
    return { v, label: fmt(v) }
  })
})
</script>

<template>
  <figure class="psa-fig" :class="glow ? 'glow-' + glow : ''">
    <p v-if="eyebrow" class="psa-eyebrow">{{ eyebrow }}</p>
    <p v-if="title" class="psa-h">{{ title }}</p>
    <p v-if="lead" class="psa-lead">{{ lead }}</p>

    <div class="psa-legend">
      <span v-for="s in series" :key="s.label">
        <i :class="'sw-' + s.tone" :style="s.dashed ? { background: 'none', borderTop: '2px dashed var(--sw)' } : {}" />
        {{ s.label }}
      </span>
    </div>

    <svg :viewBox="`0 0 ${W} ${H}`" class="lc" role="img" :aria-label="title || '折线图'">
      <defs>
        <pattern id="lcgrid" width="26" height="26" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r="1" fill="currentColor" opacity=".06" />
        </pattern>
      </defs>
      <rect :x="padL" :y="padT" :width="plotW" :height="plotH()" fill="url(#lcgrid)" class="lc-grid-bg" />

      <g v-for="(bd, i) in bands || []" :key="'b' + i">
        <rect
          v-if="bd.x0 != null"
          :x="sx(bd.x0)" :y="padT" :width="sx(bd.x1!) - sx(bd.x0)" :height="plotH()"
          :class="'lc-band lc-band-' + (bd.tone || 'teal')"
        />
        <rect
          v-else
          :x="padL" :y="sy(bd.y1!)" :width="plotW" :height="Math.abs(sy(bd.y0!) - sy(bd.y1!))"
          :class="'lc-band lc-band-' + (bd.tone || 'teal')"
        />
        <text v-if="bd.label" :x="padL + 8" :y="sy(bd.y1 ?? bounds.y1) + 14" class="lc-band-label" :class="'tx-' + (bd.tone || 'teal')">
          {{ bd.label }}
        </text>
      </g>

      <g v-for="t in yTicks" :key="'y' + t.v">
        <line :x1="padL" :x2="W - padR" :y1="sy(t.v)" :y2="sy(t.v)" class="lc-rule" />
        <text :x="padL - 8" :y="sy(t.v) + 3.5" class="lc-tick" text-anchor="end">{{ t.label }}</text>
      </g>

      <g v-for="t in xTicks" :key="'x' + t.v">
        <line :x1="sx(t.v)" :x2="sx(t.v)" :y1="H - padB" :y2="H - padB + 4" class="lc-rule" />
        <text :x="sx(t.v)" :y="H - padB + 18" class="lc-tick" text-anchor="middle">{{ t.label }}</text>
      </g>

      <line :x1="padL" :x2="W - padR" :y1="H - padB" :y2="H - padB" class="lc-axis" />
      <line :x1="padL" :x2="padL" :y1="padT" :y2="H - padB" class="lc-axis" />

      <path v-for="s in series.filter((x) => x.area)" :key="'a' + s.label" :d="area(s.points)" :class="'lc-area lc-' + s.tone" />
      <path
        v-for="s in series"
        :key="'l' + s.label"
        :d="line(s.points)"
        :class="['lc-line', 'lc-' + s.tone, { dashed: s.dashed }]"
        fill="none"
      />
      <g v-for="s in series.filter((x) => x.dots)" :key="'d' + s.label">
        <circle v-for="(p, i) in s.points" :key="i" :cx="sx(p[0])" :cy="sy(p[1])" r="3.6" :class="'lc-dot lc-' + s.tone" />
      </g>

      <g v-for="(m, i) in marks || []" :key="'m' + i">
        <line :x1="sx(m.x)" :x2="sx(m.x)" :y1="sy(m.y)" :y2="H - padB" class="lc-drop" :class="'tx-' + (m.tone || 'coral')" />
        <circle :cx="sx(m.x)" :cy="sy(m.y)" r="4.5" :class="'lc-dot lc-' + (m.tone || 'coral')" />
        <text :x="sx(m.x) + 8" :y="sy(m.y) - 7" class="lc-mark" :class="'tx-' + (m.tone || 'coral')">{{ m.label }}</text>
      </g>

      <text v-if="xLabel" :x="W - padR" :y="H - 6" class="lc-axis-label" text-anchor="end">{{ xLabel }}</text>
      <text v-if="yLabel" :x="14" :y="padT + 4" class="lc-axis-label">{{ yLabel }}</text>
    </svg>

    <p v-if="note" class="psa-note">{{ note }}</p>
  </figure>
</template>

<style scoped>
.lc { width: 100%; height: auto; display: block; }
.lc-grid-bg { color: var(--ink); }
.lc-rule { stroke: var(--line); stroke-width: 1; stroke-dasharray: 3 5; }
.lc-axis { stroke: var(--line-strong); stroke-width: 1; }
.lc-tick, .lc-axis-label { font-family: var(--font-mono); font-size: 9.5px; fill: var(--faint); letter-spacing: .04em; }
.lc-axis-label { font-size: 9px; letter-spacing: .12em; text-transform: uppercase; fill: var(--muted); }
.lc-line { stroke-width: 2.4; stroke-linejoin: round; stroke-linecap: round; }
.lc-line.dashed { stroke-dasharray: 6 5; stroke-width: 2; }
.lc-area { opacity: .12; stroke: none; }
.lc-teal { stroke: var(--accent); fill: var(--accent); }
.lc-coral { stroke: var(--coral); fill: var(--coral); }
.lc-blue { stroke: var(--blue); fill: var(--blue); }
.lc-lime { stroke: var(--lime); fill: var(--lime); }
.lc-ink { stroke: var(--ink-2); fill: var(--ink-2); }
.lc-dot { stroke: var(--panel); stroke-width: 1.5; }
.lc-drop { stroke-width: 1; stroke-dasharray: 2 4; }
.lc-mark { font-family: var(--font-mono); font-size: 10px; }
.lc-band { opacity: .1; }
.lc-band-teal { fill: var(--accent); } .lc-band-coral { fill: var(--coral); }
.lc-band-blue { fill: var(--blue); } .lc-band-lime { fill: var(--lime); }
.lc-band-label { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .08em; }
.tx-teal { fill: var(--accent); color: var(--accent); } .tx-coral { fill: var(--coral); color: var(--coral); }
.tx-blue { fill: var(--blue); color: var(--blue); }
.tx-ink { fill: var(--ink-2); color: var(--ink-2); }
.sw-teal { --sw: var(--accent); } .sw-coral { --sw: var(--coral); }
.sw-blue { --sw: var(--blue); } .sw-lime { --sw: var(--lime); } .sw-ink { --sw: var(--ink-2); }
</style>
