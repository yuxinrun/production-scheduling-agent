<script setup lang="ts">
withDefaults(
  defineProps<{
    eyebrow?: string
    title?: string
    lead?: string
    glow?: string
    cols: string[]
    rows: { label: string; sub?: string; cells: { s: string; t?: string }[] }[]
    note?: string
  }>(),
  { rows: () => [], cols: () => [] }
)

const marks: Record<string, string> = {
  ok: '●', hard: '◆', soft: '◐', weak: '○', na: '—', block: '✕', warn: '▲', missing: '◌'
}
</script>

<template>
  <figure class="psa-fig" :class="glow ? 'glow-' + glow : ''">
    <p v-if="eyebrow" class="psa-eyebrow">{{ eyebrow }}</p>
    <p v-if="title" class="psa-h">{{ title }}</p>
    <p v-if="lead" class="psa-lead">{{ lead }}</p>

    <div class="mg-scroll">
      <div class="mg" :style="{ gridTemplateColumns: `minmax(140px, 1.3fr) repeat(${cols.length}, minmax(52px, 1fr))` }">
        <div class="mg-cell mg-th mg-corner">约束 ＼ 场景</div>
        <div v-for="c in cols" :key="c" class="mg-cell mg-th">{{ c }}</div>

        <template v-for="(r, ri) in rows" :key="r.label">
          <div class="mg-cell mg-rh" :class="{ alt: ri % 2 }">
            <strong>{{ r.label }}</strong>
            <span v-if="r.sub">{{ r.sub }}</span>
          </div>
          <div
            v-for="(cell, ci) in r.cells"
            :key="ci"
            class="mg-cell mg-c"
            :class="['mg-' + cell.s, { alt: ri % 2 }]"
            :title="cell.t || r.label + ' / ' + cols[ci]"
          >
            <span class="mg-mark">{{ marks[cell.s] || '?' }}</span>
            <em v-if="cell.t">{{ cell.t }}</em>
          </div>
        </template>
      </div>
    </div>

    <div class="mg-legend">
      <span><i class="mgk-ok" />满足 / 硬适用</span>
      <span><i class="mgk-soft" />软约束（可违反，计入惩罚）</span>
      <span><i class="mgk-warn" />预警</span>
      <span><i class="mgk-block" />阻断</span>
      <span><i class="mgk-na" />无关</span>
    </div>

    <p v-if="note" class="psa-note">{{ note }}</p>
  </figure>
</template>

<style scoped>
.mg-scroll { overflow-x: auto; }
.mg { display: grid; gap: 4px; min-width: 560px; }
.mg-cell {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
  padding: 8px 6px; border-radius: 9px;
}
.mg-th {
  font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .06em;
  color: var(--faint); text-align: center;
  background: var(--panel-2);
}
.mg-corner { align-items: flex-start; text-align: left; }
.mg-rh { align-items: flex-start; }
.mg-rh strong { font-size: 12px; font-weight: 650; color: var(--ink); line-height: 1.4; }
.mg-rh span { font-family: var(--font-mono); font-size: 9.5px; color: var(--faint); }
.mg-c { background: var(--panel-2); border: 1px solid var(--line); }
.mg-c.alt { background: var(--panel); }
.mg-c em { font-style: normal; font-family: var(--font-mono); font-size: 9px; color: var(--muted); }
.mg-mark { font-size: 13px; line-height: 1; color: var(--mk); }
.mg-ok { --mk: var(--accent); }
.mg-hard { --mk: var(--accent); }
.mg-soft { --mk: var(--blue); }
.mg-weak { --mk: var(--faint); }
.mg-warn { --mk: #b7791f; }
.mg-block { --mk: var(--coral); }
.mg-missing { --mk: var(--coral); }
.mg-na { --mk: var(--line-strong); }
.mg-legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 14px; }
.mg-legend span {
  display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--font-mono); font-size: 9.5px; color: var(--muted);
}
.mg-legend i { width: 9px; height: 9px; border-radius: 3px; background: var(--k); }
.mgk-ok { --k: var(--accent); } .mgk-soft { --k: var(--blue); }
.mgk-warn { --k: #b7791f; } .mgk-block { --k: var(--coral); } .mgk-na { --k: var(--line-strong); }
</style>
