<script setup lang="ts">
withDefaults(
  defineProps<{
    eyebrow?: string
    title?: string
    lead?: string
    glow?: string
    steps: { code?: string; name: string; desc?: string; meta?: string; tone?: string }[]
    note?: string
    compact?: boolean
  }>(),
  { steps: () => [] }
)
</script>

<template>
  <figure class="psa-fig" :class="glow ? 'glow-' + glow : ''">
    <p v-if="eyebrow" class="psa-eyebrow">{{ eyebrow }}</p>
    <p v-if="title" class="psa-h">{{ title }}</p>
    <p v-if="lead" class="psa-lead">{{ lead }}</p>

    <div class="fr" :style="{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }">
      <template v-for="(s, i) in steps" :key="s.name">
        <div class="fr-step" :class="'fr-' + (s.tone || 'teal')">
          <span class="fr-code">{{ s.code ?? String(i + 1).padStart(2, '0') }}</span>
          <strong>{{ s.name }}</strong>
          <p v-if="s.desc">{{ s.desc }}</p>
          <em v-if="s.meta">{{ s.meta }}</em>
        </div>
        <span v-if="i < steps.length - 1" class="fr-arrow" aria-hidden="true">→</span>
      </template>
    </div>

    <p v-if="note" class="psa-note">{{ note }}</p>
  </figure>
</template>

<style scoped>
.fr {
  display: grid;
  gap: 0;
  align-items: stretch;
}
.fr-step {
  position: relative;
  padding: 14px 12px 12px;
  border: 1px solid var(--line);
  border-top: 3px solid var(--fill);
  border-radius: 14px;
  background: var(--panel-2);
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: transform .18s var(--ease), border-color .18s var(--ease);
}
.fr-step:hover { transform: translateY(-3px); border-color: var(--fill); }
.fr-code {
  font-family: var(--font-mono); font-size: 9px; letter-spacing: .14em;
  color: var(--fill); text-transform: uppercase;
}
.fr-step strong { font-size: 12.5px; font-weight: 680; color: var(--ink); line-height: 1.35; }
.fr-step p { margin: 0; font-size: 11.5px; line-height: 1.6; color: var(--muted); }
.fr-step em {
  font-style: normal; margin-top: auto; padding-top: 6px;
  font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .04em; color: var(--faint);
}
.fr-arrow {
  display: grid; place-items: center; width: 22px;
  font-size: 15px; color: var(--line-strong);
}
.fr-teal { --fill: var(--accent); } .fr-coral { --fill: var(--coral); }
.fr-blue { --fill: var(--blue); } .fr-lime { --fill: var(--lime); }
.fr-ink { --fill: var(--ink-2); }
</style>

<style>
/* FlowRail 的栅格列数需要随步骤数变化，同时给窄屏留一条纵向出路 */
@media (max-width: 960px) {
  .fr { grid-template-columns: repeat(auto-fit, minmax(168px, 1fr)) !important; gap: 10px; }
  .fr-arrow { display: none; }
}
</style>
