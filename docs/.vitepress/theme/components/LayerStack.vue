<script setup lang="ts">
withDefaults(
  defineProps<{
    eyebrow?: string
    title?: string
    lead?: string
    glow?: string
    layers: { code: string; name: string; sub?: string; tone?: string; items?: string[]; tag?: string }[]
    note?: string
  }>(),
  { layers: () => [] }
)
</script>

<template>
  <figure class="psa-fig" :class="glow ? 'glow-' + glow : ''">
    <p v-if="eyebrow" class="psa-eyebrow">{{ eyebrow }}</p>
    <p v-if="title" class="psa-h">{{ title }}</p>
    <p v-if="lead" class="psa-lead">{{ lead }}</p>

    <div class="ls">
      <div v-for="l in layers" :key="l.code" class="ls-row" :class="'ls-' + (l.tone || 'teal')">
        <span class="ls-code">{{ l.code }}</span>
        <div class="ls-main">
          <strong>{{ l.name }}</strong>
          <span v-if="l.sub">{{ l.sub }}</span>
        </div>
        <div class="ls-items">
          <span v-for="it in l.items || []" :key="it" class="ls-chip">{{ it }}</span>
        </div>
        <em v-if="l.tag" class="ls-tag">{{ l.tag }}</em>
      </div>
    </div>

    <p v-if="note" class="psa-note">{{ note }}</p>
  </figure>
</template>

<style scoped>
.ls { display: grid; gap: 8px; }
.ls-row {
  display: grid; grid-template-columns: 46px minmax(150px, 0.9fr) 1.5fr auto;
  gap: 14px; align-items: center;
  padding: 13px 14px;
  border: 1px solid var(--line);
  border-left: 3px solid var(--fill);
  border-radius: 12px;
  background: var(--panel-2);
  transition: transform .18s var(--ease);
}
.ls-row:hover { transform: translateX(3px); }
.ls-code {
  font-family: var(--font-mono); font-size: 12px; font-weight: 700;
  color: var(--fill); letter-spacing: .04em;
}
.ls-main strong { display: block; font-size: 12.5px; font-weight: 680; color: var(--ink); }
.ls-main span { font-size: 11px; color: var(--muted); }
.ls-items { display: flex; flex-wrap: wrap; gap: 5px; }
.ls-chip {
  padding: 2px 7px; border: 1px solid var(--line); border-radius: 5px;
  background: var(--panel);
  font-family: var(--font-mono); font-size: 10px; color: var(--ink-2);
}
.ls-tag {
  font-style: normal; white-space: nowrap;
  font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .1em;
  color: var(--fill);
}
.ls-teal { --fill: var(--accent); } .ls-coral { --fill: var(--coral); }
.ls-blue { --fill: var(--blue); } .ls-lime { --fill: var(--lime); }
.ls-ink { --fill: var(--ink-2); }

@media (max-width: 760px) {
  .ls-row { grid-template-columns: 40px 1fr; gap: 8px 10px; }
  .ls-items { grid-column: 2; }
  .ls-tag { grid-column: 2; }
}
</style>
