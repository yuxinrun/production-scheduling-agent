<script setup lang="ts">
import { withBase } from 'vitepress'

withDefaults(defineProps<{ variant?: 'pill' | 'card' }>(), { variant: 'pill' })
</script>

<template>
  <div :class="['mp-brand', `mp-brand--${variant}`]">
    <img
      :src="withBase('/sched-fish.svg')"
      alt="戴着安全帽和调度耳麦的青色小鱼，正把一块甘特条挪回正确的时窗"
      width="546"
      height="363"
    />
    <div class="mp-brand-copy">
      <strong>鱼心快跑</strong>
      <span>鱼心快跑，Bug 追不上</span>
    </div>
  </div>
</template>
