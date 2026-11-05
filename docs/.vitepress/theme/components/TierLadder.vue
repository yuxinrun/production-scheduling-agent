<script setup lang="ts">
withDefaults(
  defineProps<{
    eyebrow?: string
    title?: string
    lead?: string
    glow?: string
    tiers: {
      band: string
      name: string
      en?: string
      tone?: string
      can: string
      cannot: string
      human: string
      who?: string
    }[]
    note?: string
  }>(),
  { tiers: () => [] }
)
</script>

<template>
  <figure class="psa-fig" :class="glow ? 'glow-' + glow : ''">
    <p v-if="eyebrow" class="psa-eyebrow">{{ eyebrow }}</p>
    <p v-if="title" class="psa-h">{{ title }}</p>
    <p v-if="lead" class="psa-lead">{{ lead }}</p>

    <div class="tl">
      <div
        v-for="(t, i) in tiers"
        :key="t.band"
        class="tl-card"
        :class="'tl-' + (t.tone || 'teal')"
        :style="{ marginTop: (tiers.length - 1 - i) * 16 + 'px' }"
      >
        <span class="tl-band">{{ t.band }}</span>
        <strong>{{ t.name }}</strong>
        <em v-if="t.en">{{ t.en }}</em>
        <p class="tl-can"><b>能做</b>{{ t.can }}</p>
        <p class="tl-cannot"><b>不能做</b>{{ t.cannot }}</p>
        <p class="tl-human"><b>人</b>{{ t.human }}</p>
        <span v-if="t.who" class="tl-who">{{ t.who }}</span>
      </div>
    </div>

    <p v-if="note" class="psa-note">{{ note }}</p>
  </figure>
</template>

<style scoped>
.tl { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; align-items: end; }
.tl-card {
  position: relative;
  display: flex; flex-direction: column; gap: 6px;
  padding: 16px 14px 14px;
  border: 1px solid var(--line); border-radius: 16px;
  background: var(--panel-2);
  transition: transform .2s var(--ease), border-color .2s var(--ease);
}
.tl-card:hover { transform: translateY(-4px); border-color: var(--fill); }
.tl-band {
  align-self: flex-start;
  padding: 2px 9px; border-radius: 999px;
  background: var(--soft); color: var(--fill);
  font-family: var(--font-mono); font-size: 10px; letter-spacing: .08em;
}
.tl-card strong { font-size: 13.5px; font-weight: 720; color: var(--ink); letter-spacing: -.01em; }
.tl-card em {
  font-style: normal; margin-top: -4px;
  font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .1em; text-transform: uppercase; color: var(--faint);
}
.tl-card p { margin: 0; font-size: 11.5px; line-height: 1.6; color: var(--ink-2); }
.tl-card p b {
  display: block; font-family: var(--font-mono); font-size: 9px; font-weight: 600;
  letter-spacing: .12em; text-transform: uppercase; color: var(--faint);
}
.tl-cannot b { color: var(--coral); }
.tl-can b { color: var(--accent); }
.tl-who {
  margin-top: 4px; padding-top: 8px; border-top: 1px dashed var(--line-strong);
  font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .04em; color: var(--fill);
}
.tl-teal { --fill: var(--accent); --soft: var(--accent-soft); }
.tl-coral { --fill: var(--coral); --soft: var(--coral-soft); }
.tl-blue { --fill: var(--blue); --soft: var(--blue-soft); }
.tl-lime { --fill: var(--lime); --soft: rgba(169, 204, 63, .18); }

@media (max-width: 960px) { .tl { grid-template-columns: repeat(2, minmax(0, 1fr)); } .tl-card { margin-top: 0 !important; } }
@media (max-width: 620px) { .tl { grid-template-columns: 1fr; } }
</style>
