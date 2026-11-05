<script setup lang="ts">
withDefaults(
  defineProps<{
    eyebrow?: string
    title?: string
    lead?: string
    unit?: string
    max?: number
    glow?: string
    series: { tone: string; label: string }[]
    rows: { label: string; hint?: string; values: number[]; display?: string[] }[]
    note?: string
  }>(),
  { max: 100, unit: '%' }
)

const pct = (v: number, max: number) => Math.max(0, Math.min(100, (v / max) * 100))
</script>

<template>
  <figure class="psa-fig" :class="glow ? 'glow-' + glow : ''">
    <p v-if="eyebrow" class="psa-eyebrow">{{ eyebrow }}</p>
    <p v-if="title" class="psa-h">{{ title }}</p>
    <p v-if="lead" class="psa-lead">{{ lead }}</p>
    <div class="psa-legend">
      <span v-for="s in series" :key="s.label"><i :class="'sw-' + s.tone" />{{ s.label }}</span>
    </div>
    <div class="bc">
      <div v-for="(r, i) in rows" :key="r.label" class="bc-row">
        <div class="bc-label">
          <strong>{{ r.label }}</strong>
          <span v-if="r.hint">{{ r.hint }}</span>
        </div>
        <div class="bc-bars">
          <div v-for="(v, si) in r.values" :key="si" class="bc-line">
            <div class="bc-track">
              <div
                class="bc-fill"
                :class="'bc-' + series[si].tone"
                :style="{ width: pct(v, max) + '%' }"
              />
            </div>
            <span class="bc-val" :class="'tx-' + series[si].tone">{{ r.display?.[si] ?? v + unit }}</span>
          </div>
        </div>
      </div>
    </div>
    <p v-if="note" class="psa-note">{{ note }}</p>
  </figure>
</template>

<style scoped>
.bc { display: grid; gap: 4px; }
.bc-row {
  display: grid; grid-template-columns: 190px 1fr; gap: 18px; align-items: center;
  padding: 10px 0; border-top: 1px dashed var(--line);
}
.bc-row:first-child { border-top: 0; }
.bc-label strong { display: block; font-size: 13px; font-weight: 650; color: var(--ink); }
.bc-label span { font-family: var(--font-mono); font-size: 9.5px; color: var(--faint); letter-spacing: .04em; }
.bc-bars { display: grid; gap: 6px; }
.bc-line { display: grid; grid-template-columns: 1fr 74px; align-items: center; gap: 10px; }
.bc-track { height: 12px; border-radius: 6px; background: var(--panel-3); overflow: hidden; }
.bc-fill { height: 100%; border-radius: 6px; background: var(--fill); transition: width .5s var(--ease); }
.bc-val { font-family: var(--font-mono); font-size: 10.5px; text-align: right; color: var(--muted); white-space: nowrap; }
.bc-teal { --fill: var(--accent); } .bc-coral { --fill: var(--coral); }
.bc-blue { --fill: var(--blue); } .bc-lime { --fill: var(--lime); }
.bc-ink { --fill: var(--ink-2); }
.tx-teal { color: var(--accent); } .tx-coral { color: var(--coral); }
.tx-blue { color: var(--blue); } .tx-lime { color: var(--lime); } .tx-ink { color: var(--muted); }
.sw-teal { --sw: var(--accent); } .sw-coral { --sw: var(--coral); }
.sw-blue { --sw: var(--blue); } .sw-lime { --sw: var(--lime); } .sw-ink { --sw: var(--ink-2); }
@media (max-width: 760px) {
  .bc-row { grid-template-columns: 1fr; gap: 8px; }
  .bc-line { grid-template-columns: 1fr 66px; }
}
</style>
