<template>
  <div class="hd">
    <div class="hd-fig">
      <div class="hd-head">
        <span class="hd-eyebrow">Scheduling Agent · Runtime</span>
        <span class="hd-dot" :class="{ ready }"><i />{{ ready ? 'solver ready' : 'booting' }}</span>
      </div>

      <div class="hd-layers">
        <div v-for="(l, i) in layers" :key="l.code" class="hd-row">
          <span class="hd-code">{{ l.code }}</span>
          <div class="hd-body">
            <strong>{{ l.name }}</strong>
            <span>{{ l.sub }}</span>
          </div>
          <em>{{ l.tag }}</em>
        </div>
      </div>

      <div class="hd-gantt">
        <div v-for="b in bars" :key="b.name" class="hd-bar">
          <span class="hd-bar-name">{{ b.name }}</span>
          <div class="hd-bar-track">
            <div
              v-for="(seg, si) in b.segs"
              :key="si"
              class="hd-seg"
              :class="'t-' + seg.tone"
              :style="{ left: seg.x + '%', width: seg.w + '%' }"
            />
          </div>
        </div>
      </div>

      <div class="hd-foot">
        <span>LISAPRODUCT</span>
        <span>SHEET 01 / GANTT</span>
      </div>
    </div>
    <p class="hd-cap">有限产能 · 带归因 · 可回放 —— 这一版排产方案，人一眼能看懂为什么</p>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

const ready = ref(false)
onMounted(() => {
  setTimeout(() => (ready.value = true), 900)
})

const layers = [
  { code: 'A', name: '原子级排产智能体', sub: '锻造 / 机加 / 热表 / 钣焊 / 装配 / 试车 / 大修', tag: '只读建议' },
  { code: 'M', name: '分子级协调智能体', sub: '链式衔接 · 齐套 · 变更影响面', tag: '编排' },
  { code: 'C', name: '化合物级总控', sub: 'MPS 拉动 · 多目标 · 夜间全量重排', tag: '写基线' },
  { code: 'L', name: '求解与规则内核', sub: 'COPT / CP-SAT · 68 条规则 · 14 条硬约束', tag: '数值真相' }
]

const bars = [
  { name: '锻造', segs: [{ x: 2, w: 22, tone: 'teal' }, { x: 30, w: 14, tone: 'teal' }] },
  { name: '机加', segs: [{ x: 12, w: 30, tone: 'blue' }, { x: 48, w: 20, tone: 'coral' }] },
  { name: '热表', segs: [{ x: 40, w: 18, tone: 'lime' }, { x: 64, w: 12, tone: 'teal' }] },
  { name: '装配', segs: [{ x: 58, w: 26, tone: 'blue' }] },
  { name: '试车', segs: [{ x: 72, w: 20, tone: 'coral' }] }
]
</script>

<style scoped>
.hd { max-width: 520px; margin-left: auto; }
.hd-fig {
  position: relative;
  padding: 22px 20px 18px;
  border: 1px solid var(--line);
  border-radius: 28px;
  background: var(--panel);
  box-shadow: var(--shadow-lg);
  transform: rotate(-1.4deg);
  overflow: hidden;
}
.hd-fig::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 1px 1px, var(--grid-line) 1px, transparent 0) 0 0 / 26px 26px,
    radial-gradient(circle at 88% 6%, var(--coral-glow) 0, transparent 42%);
  pointer-events: none;
}
.hd-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.hd-eyebrow {
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--accent);
}
.hd-dot {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.1em;
  color: var(--faint);
}
.hd-dot i {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--line-strong);
}
.hd-dot.ready i { background: var(--accent); animation: hd-breath 2.4s var(--ease) infinite; }
@keyframes hd-breath { 0%, 100% { box-shadow: 0 0 0 0 var(--accent-soft); } 50% { box-shadow: 0 0 0 6px transparent; } }

.hd-layers { display: grid; gap: 8px; padding: 12px; border: 1px dashed var(--line-strong); border-radius: 14px; }
.hd-row { display: grid; grid-template-columns: 22px 1fr auto; align-items: center; gap: 10px; }
.hd-code {
  width: 22px; height: 22px; border-radius: 50%;
  border: 1px solid var(--line-strong);
  display: grid; place-items: center;
  font-family: var(--font-mono); font-size: 10px; color: var(--accent);
}
.hd-body strong { display: block; font-size: 12.5px; font-weight: 680; color: var(--ink); line-height: 1.4; }
.hd-body span { font-size: 11px; color: var(--muted); }
.hd-row em {
  font-style: normal;
  font-family: var(--font-mono); font-size: 9px; letter-spacing: 0.08em;
  color: var(--faint); white-space: nowrap;
}
.hd-gantt { margin-top: 16px; display: grid; gap: 7px; }
.hd-bar { display: grid; grid-template-columns: 44px 1fr; align-items: center; gap: 10px; }
.hd-bar-name { font-family: var(--font-mono); font-size: 10px; color: var(--faint); }
.hd-bar-track { position: relative; height: 14px; border-radius: 7px; background: var(--panel-3); }
.hd-seg { position: absolute; top: 2px; height: 10px; border-radius: 5px; background: var(--fill); opacity: .88; }
.t-teal { --fill: var(--accent); } .t-coral { --fill: var(--coral); }
.t-blue { --fill: var(--blue); } .t-lime { --fill: var(--lime); }
.hd-foot {
  display: flex; justify-content: space-between; margin-top: 14px;
  font-family: var(--font-mono); font-size: 9px; letter-spacing: 0.14em; color: var(--faint);
}
.hd-cap { margin: 16px 0 0; font-size: 12.5px; line-height: 1.7; color: var(--muted); text-align: right; }

@media (max-width: 960px) {
  .hd { max-width: 100%; margin: 0 auto; }
  .hd-fig { transform: none; }
  .hd-cap { text-align: center; }
}
@media (prefers-reduced-motion: reduce) { .hd-dot.ready i { animation: none; } }
</style>
