<script setup lang="ts">
withDefaults(
  defineProps<{
    eyebrow?: string
    title?: string
    lead?: string
    horizon?: number
    tick?: number
    tickUnit?: string
    glow?: string
    rows: { name: string; sub?: string; bars: { s: number; d: number; tone?: string; label?: string; ghost?: boolean }[] }[]
    legend?: { tone: string; label: string }[]
    ghostLabel?: string
    note?: string
    nowAt?: number
  }>(),
  { horizon: 96, tick: 24, tickUnit: 'D', legend: () => [
    { tone: 'teal', label: '正常占用' },
    { tone: 'coral', label: '冲突 / 违规' },
    { tone: 'blue', label: '等待与缓冲' },
    { tone: 'lime', label: '瓶颈资源' }
  ], ghostLabel: '虚线 = 被产能挤掉的部分' }
)

const ticks = (props: number, horizon: number) => Array.from({ length: Math.floor(horizon / props) + 1 }, (_, i) => i)
</script>

<template>
  <figure class="psa-fig" :class="glow ? 'glow-' + glow : ''">
    <p v-if="eyebrow" class="psa-eyebrow">{{ eyebrow }}</p>
    <p v-if="title" class="psa-h">{{ title }}</p>
    <p v-if="lead" class="psa-lead">{{ lead }}</p>
    <div class="psa-legend">
      <span v-for="l in legend" :key="l.label"><i :class="'sw-' + l.tone" />{{ l.label }}</span>
      <span><i class="sw-ghost" />{{ ghostLabel }}</span>
    </div>

    <div class="gv">
      <div class="gv-head">
        <span class="gv-corner">资源 / 工序</span>
        <div class="gv-axis">
          <span v-for="i in ticks(tick, horizon)" :key="i" class="gv-tick" :style="{ left: (i * tick / horizon) * 100 + '%' }">
            {{ tickUnit }}{{ i * tick }}
          </span>
        </div>
      </div>

      <div v-for="(r, ri) in rows" :key="r.name" class="gv-row" :class="{ alt: ri % 2 }">
        <div class="gv-label">
          <strong>{{ r.name }}</strong>
          <span v-if="r.sub">{{ r.sub }}</span>
        </div>
        <div class="gv-track">
          <span
            v-for="i in ticks(tick, horizon)"
            :key="'g' + i"
            class="gv-grid"
            :style="{ left: (i * tick / horizon) * 100 + '%' }"
          />
          <div
            v-for="(b, bi) in r.bars"
            :key="bi"
            class="gv-bar"
            :class="['gv-' + (b.tone || 'teal'), { ghost: b.ghost }]"
            :style="{ left: (b.s / horizon) * 100 + '%', width: Math.max(b.d / horizon * 100, 1.2) + '%' }"
            :title="b.label || `${r.name} · ${b.s}→${b.s + b.d}`"
          >
            <em v-if="b.label">{{ b.label }}</em>
          </div>
          <div v-if="nowAt != null" class="gv-now" :style="{ left: (nowAt / horizon) * 100 + '%' }" />
        </div>
      </div>
    </div>

    <p v-if="note" class="psa-note">{{ note }}</p>
  </figure>
</template>

<script lang="ts">
export default { name: 'GanttView' }
</script>

<style scoped>
.gv { border: 1px dashed var(--line-strong); border-radius: 14px; padding: 10px 12px 12px; }
.gv-head, .gv-row { display: grid; grid-template-columns: 168px 1fr; gap: 14px; align-items: center; }
.gv-head { margin-bottom: 8px; }
.gv-corner { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--faint); }
.gv-axis { position: relative; height: 16px; }
.gv-tick {
  position: absolute; top: 0; transform: translateX(-50%);
  font-family: var(--font-mono); font-size: 9.5px; color: var(--faint); white-space: nowrap;
}
.gv-row { padding: 4px 0; border-top: 1px dashed var(--line); }
.gv-row.alt .gv-track { background: var(--panel-2); }
.gv-label strong { display: block; font-size: 12.5px; font-weight: 650; color: var(--ink); }
.gv-label span { font-family: var(--font-mono); font-size: 9.5px; color: var(--faint); }
.gv-track { position: relative; height: 34px; border-radius: 8px; }
.gv-grid { position: absolute; top: 4px; bottom: 4px; width: 1px; background: var(--line); }
.gv-bar {
  position: absolute; top: 7px; height: 20px; border-radius: 6px;
  background: var(--fill); opacity: .9;
  display: flex; align-items: center; overflow: hidden;
  transition: transform 0.18s var(--ease);
}
.gv-bar:hover { transform: translateY(-2px); }
.gv-bar em { font-style: normal; padding: 0 6px; font-family: var(--font-mono); font-size: 9.5px; color: #fffdf8; white-space: nowrap; text-shadow: 0 1px 2px rgba(0,0,0,.35); }
.gv-teal { --fill: var(--accent); }
.gv-coral { --fill: var(--coral); }
.gv-blue { --fill: var(--blue); }
.gv-lime { --fill: var(--lime); }
.gv-lime em { color: var(--ink); text-shadow: none; }
.gv-bar.ghost {
  background: repeating-linear-gradient(135deg, transparent 0 4px, var(--fill) 4px 6px);
  opacity: .45;
}
.gv-now { position: absolute; top: 2px; bottom: 2px; width: 2px; background: var(--coral); border-radius: 1px; }
.sw-teal { --sw: var(--accent); } .sw-coral { --sw: var(--coral); }
.sw-blue { --sw: var(--blue); } .sw-lime { --sw: var(--lime); }
.sw-ghost { --sw: var(--line-strong); background: repeating-linear-gradient(135deg, transparent 0 3px, var(--line-strong) 3px 5px); }

@media (max-width: 760px) {
  .gv-head, .gv-row { grid-template-columns: 92px 1fr; gap: 8px; }
  .gv-label strong { font-size: 11px; }
  .gv-bar em { display: none; }
  .gv-tick { font-size: 8.5px; }
}
</style>
