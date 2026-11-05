<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    eyebrow?: string
    title?: string
    lead?: string
    glow?: string
    jobs?: number[]
    note?: string
  }>(),
  { jobs: () => [4, 6, 8, 10, 12, 14, 16, 18, 20] }
)

/* 全部在 log₁₀ 空间算，否则 20!^10 直接变 Infinity */
const log10Fact = (n: number) => {
  let s = 0
  for (let i = 2; i <= n; i++) s += Math.log10(i)
  return s
}

const machines = ref(1)
const picked = ref(10)

const rows = computed(() =>
  props.jobs.map((n) => {
    const lg = machines.value === 1 ? log10Fact(n) : log10Fact(n) * machines.value
    return { n, lg }
  })
)

const maxLog = computed(() => Math.max(...rows.value.map((r) => r.lg), 1))
const current = computed(() => rows.value.find((r) => r.n === picked.value) ?? rows.value[rows.value.length - 1])

function sci(lg: number) {
  if (lg < 15) return Math.round(10 ** lg).toLocaleString('en-US')
  const e = Math.floor(lg)
  return `${(10 ** (lg - e)).toFixed(2)} × 10^${e}`
}

function humanSeconds(lg: number) {
  const ls = lg - 9 // 10 亿次/秒 → 秒数的 log10
  if (ls < 0) return '不到 1 秒'
  if (ls < 3) return `${(10 ** ls).toFixed(0)} 秒`
  if (ls < 6.4) return `${(10 ** (ls - 3)).toFixed(1)} 小时`
  if (ls < 8.5) return `${(10 ** (ls - 6.4)).toFixed(1)} 年`
  if (ls < 12) return `${(10 ** (ls - 8.5)).toFixed(1)} 万年`
  if (ls < 16) return `${(10 ** (ls - 12)).toFixed(1)} 亿年`
  return `10^${Math.round(ls - 8.5)} 年（宇宙年龄才 1.4 × 10^10 年）`
}

const atoms = 80.4 // 可观测宇宙原子数 ≈ 10^80
</script>

<template>
  <figure class="psa-fig" :class="glow ? 'glow-' + glow : ''">
    <p v-if="eyebrow" class="psa-eyebrow">{{ eyebrow }}</p>
    <p v-if="title" class="psa-h">{{ title }}</p>
    <p v-if="lead" class="psa-lead">{{ lead }}</p>

    <div class="ec-picks">
      <button
        v-for="r in rows"
        :key="r.n"
        class="psa-btn"
        :class="{ 'is-on': r.n === picked }"
        type="button"
        @click="picked = r.n"
      >
        {{ r.n }} 件
      </button>
      <label class="ec-mach">
        <span>设备台数 m</span>
        <input v-model.number="machines" type="range" min="1" max="10" step="1" />
        <b>{{ machines }}</b>
      </label>
    </div>

    <div class="ec-readout">
      <div class="ec-big">
        <span class="ec-num">≈ {{ sci(current.lg) }}</span>
        <span class="ec-unit">种「每台设备各自一个顺序」</span>
      </div>
      <div class="ec-sub">
        <p>{{ current.n }} 件工件 × {{ machines }} 台设备 · 候选数有 {{ Math.floor(current.lg) + 1 }} 位数字</p>
        <p>10 亿次/秒穷举到底要 <b>{{ humanSeconds(current.lg) }}</b></p>
      </div>
    </div>

    <div class="ec-bars">
      <div v-for="r in rows" :key="'b' + r.n" class="ec-row" :class="{ 'is-pick': r.n === picked }">
        <span class="ec-label">{{ r.n }} 件</span>
        <span class="ec-track">
          <span class="ec-fill" :style="{ width: (r.lg / maxLog) * 100 + '%' }" />
          <span v-if="atoms <= maxLog" class="ec-univ" :style="{ left: (atoms / maxLog) * 100 + '%' }" />
        </span>
        <span class="ec-val">10^{{ Math.floor(r.lg) }}</span>
      </div>
    </div>
    <p v-if="atoms <= maxLog" class="ec-univ-hint">
      ┃ 竖线 = 可观测宇宙里的原子总数 10<sup>80</sup>。条子超过它，穷举就不是「慢」，是「不成立」。
    </p>

    <div class="ec-calib">
      <p><b>ft10</b> 10 件 × 10 台 → (10!)<sup>10</sup> ≈ 4×10<sup>65</sup>。最优值 930 从 1963 年挂到现在。</p>
      <p><b>典型小厂</b> 100 件 × 20 台 → 约 10<sup>3159</sup>。所以没人穷举，全靠约束传播把候选砍掉九成再九成。</p>
    </div>

    <p v-if="note" class="psa-note">{{ note }}</p>
    <p v-else class="psa-note">
      条长按 log₁₀ 绘制 —— 用线性条画这张图，20 件的条子会粗到溢出屏幕、10 件的看不见。
      这个数字是「设备顺序的定向方案数」上界，不是解的总数；工序顺序固定 + 传播器推出的必然先后关系，会让真实搜索空间小得多。
      但它足够说明为什么「强 NP-hard」这四个字是排产项目的需求，不是学术论文的修辞。
    </p>
  </figure>
</template>

<style scoped>
.ec-picks { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 18px; }
.ec-mach {
  display: inline-flex; align-items: center; gap: 9px; margin-left: auto;
  font-family: var(--font-mono); font-size: 10px; letter-spacing: .06em; color: var(--muted);
}
.ec-mach b { color: var(--coral); font-size: 12px; }
.ec-mach input { width: 92px; accent-color: var(--coral); }

.ec-readout {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 26px;
  padding: 14px 16px; border: 1px dashed var(--line-strong); border-radius: 12px;
  background: var(--panel-2); margin-bottom: 18px;
}
.ec-big { display: flex; align-items: baseline; gap: 9px; flex-wrap: wrap; }
.ec-num {
  font-family: var(--font-mono); font-size: 1.5rem; font-weight: 600; letter-spacing: -.02em; color: var(--coral);
}
.ec-unit { font-size: 12px; color: var(--muted); }
.ec-sub { display: flex; flex-direction: column; gap: 3px; }
.ec-sub p { margin: 0; font-family: var(--font-mono); font-size: 10.5px; color: var(--faint); }
.ec-sub b { color: var(--ink-2); font-weight: 600; }

.ec-bars { display: flex; flex-direction: column; gap: 5px; }
.ec-row { display: grid; grid-template-columns: 46px minmax(0, 1fr) 68px; align-items: center; gap: 10px; }
.ec-label, .ec-val { font-family: var(--font-mono); font-size: 10px; color: var(--faint); }
.ec-val { text-align: right; }
.ec-track {
  position: relative; height: 13px; border-radius: 3px; background: var(--panel-2);
  border: 1px solid var(--line); overflow: hidden;
}
.ec-fill {
  position: absolute; left: 0; top: 0; bottom: 0;
  background: repeating-linear-gradient(90deg, var(--accent) 0 5px, rgba(10, 149, 138, .5) 5px 7px);
  transition: width .3s var(--ease);
}
.ec-univ { position: absolute; top: -2px; bottom: -2px; width: 1px; background: var(--ink); opacity: .75; }
.ec-row.is-pick .ec-label, .ec-row.is-pick .ec-val { color: var(--coral); }
.ec-row.is-pick .ec-fill {
  background: repeating-linear-gradient(90deg, var(--coral) 0 5px, rgba(232, 87, 52, .5) 5px 7px);
}
.ec-univ-hint {
  margin: 9px 0 0; font-family: var(--font-mono); font-size: 9.8px; color: var(--faint); letter-spacing: .02em;
}

.ec-calib {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; margin-top: 18px;
}
.ec-calib p {
  margin: 0; padding: 10px 13px; border: 1px solid var(--line); border-radius: 9px; background: var(--panel-2);
  font-size: 12px; line-height: 1.7; color: var(--muted);
}
.ec-calib b { font-family: var(--font-mono); font-size: 10px; letter-spacing: .1em; color: var(--accent); }

@media (max-width: 760px) {
  .ec-mach { margin-left: 0; width: 100%; }
  .ec-row { grid-template-columns: 40px minmax(0, 1fr) 54px; gap: 7px; }
  .ec-num { font-size: 1.24rem; }
}
html.dark .ec-univ { background: var(--bg); }
</style>
