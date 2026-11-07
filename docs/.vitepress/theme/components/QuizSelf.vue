<script setup lang="ts">
import { computed, reactive } from 'vue'

type Q = { q: string; options: string[]; answer: number; why: string; tag: string }

const props = withDefaults(
  defineProps<{
    eyebrow?: string
    title?: string
    lead?: string
    glow?: string
    note?: string
    questions?: Q[]
  }>(),
  {
    questions: () => [
      {
        tag: '复杂度',
        q: 'n 个工件在 1 台机器上、目标是最小化总完工时间 ΣC，正确的做法是？',
        options: ['枚举 n! 种排列', '按加工时间从短到长排（SPT）', '按交期从早到晚排（EDD）', '交给遗传算法搜'],
        answer: 1,
        why: '单机 ΣC 有多项式最优解：SPT（最短加工时间优先），交换论证两行就证完。n! 是「工件在多台机器上的顺序也要定」时才出现的爆炸。'
      },
      {
        tag: '复杂度',
        q: '作业车间调度（JSP，m 台机器、工序顺序各异）为什么难？',
        options: ['因为目标函数非线性', '因为它是强 NP-hard，机器间顺序组合随规模爆炸', '因为没有求解器', '因为数据不准'],
        answer: 1,
        why: 'JSP 是强 NP-hard（Garey–Johnson–Sethi，1976）。强 NP-hard 意味着连「伪多项式动态规划」都别想，这就是排产项目必须接受近似解的根本原因。'
      },
      {
        tag: '拉格朗日',
        q: '拉格朗日松弛给出的 θ(λ) 对最小化原问题是？',
        options: ['上界，可能低估', '下界，且对任意 λ ≥ 0 都成立', '等于最优值', '只在 LP 松弛时成立'],
        answer: 1,
        why: '弱对偶定理：λ ≥ 0 时 θ(λ) ≤ z* 恒成立。所以它可以安全地拿去分支定界里剪枝 —— 下界不会假装「已经够好了」。'
      },
      {
        tag: '拉格朗日',
        q: '对偶间隙（z* − max θ）通常来自什么？',
        options: ['步长太大', '整数性间隙：松弛后允许了原问题不允许的分数解', '求解器 bug', '数据缺失'],
        answer: 1,
        why: '整数规划的对偶间隙是整数性造成的，不是数值误差。所以「间隙归零」是个不该写进验收指标的目标 —— 能收敛到一个稳定值就该收手。'
      },
      {
        tag: '约束规划',
        q: 'CP 求解器里 `no_overlap` / `cumulative` 约束靠什么把搜索空间砍掉一大半？',
        options: ['单纯枚举', '传播器（如 edge-finding）在搜索前就推出大量必然的先后关系', '梯度下降', '随机重启'],
        answer: 1,
        why: '这是 CP 在排产上打赢通用 MILP 的核心原因：时序传播器专门对付「不相交 + 释放期 + 工期」这类结构。'
      },
      {
        tag: '排产语义',
        q: '「有限产能排产」和「无限产能 + 事后负荷检查」的本质差别是？',
        options: ['前者算得更慢', '前者在搜索时就把产能当约束，方案天生可执行；后者先排再查，冲突靠人消化', '前者不需要工艺路线', '没差别，只是叫法'],
        answer: 1,
        why: '很多国产软件把「有限产能检查」做成甘特图上的红条来冒充优化排程 —— 看演示时问一句「你的产能是约束还是报表」就能拆穿。'
      },
      {
        tag: '排产语义',
        q: '齐套检查为什么必须做在排产前，而不是排产后？',
        options: ['排产后算力不够', '不齐套的工单排进去只会产出一张必然违约的计划，还会挤占真能开工的产能', '齐套数据太慢', '其实排后排前一样'],
        answer: 1,
        why: '关重件缺料要在开工前硬阻断（某某项目的口径是「不齐套工单禁止排入」）。排产后才发现缺料 = 整条链的方案作废 + 现场停线。'
      },
      {
        tag: '工程',
        q: '冻结窗口（时间围栏，比如「排 7 天、锁 3 天」）存在的意义是？',
        options: ['保护算法性能', '车间已经领料、排刀、派人，计划再改一次就是一笔真实成本', '数据库锁', '防止重复排产'],
        answer: 1,
        why: '排产 Agent 优化的不是「理论最优」而是「可执行且稳定」。改动冻结区必须走审批 —— 这也是采纳率最高的来源之一。'
      },
      {
        tag: '评测',
        q: '「影子模式」在排产项目里解决的是哪个问题？',
        options: ['降低服务器成本', '在不接管现场的前提下并行出方案、与计划员实际方案比对，攒出人机分歧数据', '给模型做数据增强', '绕过安全审计'],
        answer: 1,
        why: '采纳率从 60% 爬到 85% 的唯一燃料就是「分歧即采集」。不跑影子就上生产，出事一次就再也推不动了。'
      },
      {
        tag: 'MCP',
        q: '排产 Agent 通过 MCP 暴露给外部模型的工具，为什么应该标 `readOnlyHint`？',
        options: ['为了加速', '让宿主能在没有人类确认时安全调用；写能力混进来就等于把 MES 交给一个不确定会不会幻觉的模型', '协议要求必须有', '只是文档习惯'],
        answer: 1,
        why: '写动作（下发、改基线、锁工单）不该进只读面。某某项目更狠：名字形如 `apply_/approve_/write_/save_` 的注册即报错 —— 从注册层拦，而不是靠提示词祈祷。'
      },
      {
        tag: '安全',
        q: '内网模型编排里，把「客户、图号、人名」送进模型前先化名成 «客户#1»，这一步叫？',
        options: ['加密', '脱敏（可逆占位符）—— 模型只见代号，回述时再在本地还原', '压缩', '差分隐私'],
        answer: 1,
        why: '化名是「进模型前替换、回来后还原」，密钥和明文凭据则任何情况下都不进模型、不进日志。审计链路里也不该出现明文。'
      },
      {
        tag: '落地',
        q: '排产方案「算得对但没人用」，最常见的根因是？',
        options: ['算法不够先进', '数据口径不可信 + 规则没被显性化 + 计划员觉得失控', '界面太丑', '算力不足'],
        answer: 1,
        why: '调研里反复出现的三件事：BOM/工时/日历失真、隐性约束锁在老师傅脑子里、改完计划没人知道为什么。所以先做数据治理和可解释（白盒归因），再谈优化。'
      }
    ]
  }
)

const picked = reactive<Record<number, number>>({})

const answered = computed(() => Object.keys(picked).length)
const correct = computed(() => props.questions.filter((q, i) => picked[i] === q.answer).length)
const done = computed(() => answered.value === props.questions.length)

const verdict = computed(() => {
  const p = (correct.value / props.questions.length) * 100
  if (p >= 90) return { band: '可以上线', text: '数学、排产语义、工程护栏你都对得上。缺的只有真实数据 —— 去把五维点检跑起来。' }
  if (p >= 70) return { band: '能干，但会被现场打脸', text: '概念没问题，坑在「口径」：齐套要素归口、冻结窗口、关重件阻断这些没一条是算法问题。' }
  if (p >= 45) return { band: '别急着自己写求解器', text: '先把 NP-hard 为什么、CP 的传播器、以及「有限产能是约束不是报表」这三件事吃透。' }
  return { band: '建议从头读起', text: '这不是你的错 —— 排产领域的坑一大半不在算法里。先读「排产不是排程」和「术语表」两页。' }
})

function reset() {
  for (const k of Object.keys(picked)) delete picked[Number(k)]
}
</script>

<template>
  <figure class="psa-fig" :class="glow ? 'glow-' + glow : ''">
    <p v-if="eyebrow" class="psa-eyebrow">{{ eyebrow }}</p>
    <p v-if="title" class="psa-h">{{ title }}</p>
    <p v-if="lead" class="psa-lead">{{ lead }}</p>

    <div class="qs-score">
      <span class="qs-bar">
        <i :style="{ width: (answered / questions.length) * 100 + '%' }" />
      </span>
      <span class="qs-num">{{ answered }}/{{ questions.length }} 已答 · <b>{{ correct }}</b> 对</span>
      <button type="button" class="psa-btn" @click="reset">↺ 重做</button>
    </div>

    <ol class="qs-list">
      <li v-for="(q, qi) in questions" :key="qi" class="qs-item" :class="{ 'is-answered': picked[qi] != null, 'is-wrong': picked[qi] != null && picked[qi] !== q.answer }">
        <p class="qs-q">
          <span class="qs-idx">{{ String(qi + 1).padStart(2, '0') }}</span>
          <span class="qs-tag">{{ q.tag }}</span>
          {{ q.q }}
        </p>
        <div class="qs-opts">
          <button
            v-for="(o, oi) in q.options"
            :key="oi"
            type="button"
            class="qs-opt"
            :class="{ right: picked[qi] != null && oi === q.answer, yours: picked[qi] === oi && oi !== q.answer, dim: picked[qi] != null && oi !== q.answer && picked[qi] !== oi }"
            :disabled="picked[qi] != null"
            @click="picked[qi] = oi"
          >
            <span class="qs-letter">{{ 'ABCD'[oi] }}</span>
            {{ o }}
          </button>
        </div>
        <p v-if="picked[qi] != null" class="qs-why">
          <b>{{ picked[qi] === q.answer ? '对了' : '错了 —— 正确项是 ' + 'ABCD'[q.answer] }}</b>
          {{ q.why }}
        </p>
      </li>
    </ol>

    <div v-if="done" class="qs-verdict" :class="{ good: correct >= 9, mid: correct >= 5 && correct < 9, bad: correct < 5 }">
      <p class="qs-vhead">{{ correct }} / {{ questions.length }} —— {{ verdict.band }}</p>
      <p class="qs-vtext">{{ verdict.text }}</p>
    </div>

    <p v-if="note" class="psa-note">{{ note }}</p>
    <p v-else class="psa-note">答错不扣分，但答错的题请回去把对应章节读完 —— 这套题的每一题都对应一个真实项目里翻过的车。</p>
  </figure>
</template>

<style scoped>
.qs-score { display: flex; align-items: center; gap: 14px; margin-bottom: 20px; }
.qs-bar { position: relative; flex: 1; height: 6px; border-radius: 3px; background: var(--panel-2); border: 1px solid var(--line); overflow: hidden; }
.qs-bar i { position: absolute; inset: 0 auto 0 0; background: var(--accent); transition: width .3s var(--ease); }
.qs-num { font-family: var(--font-mono); font-size: 10.5px; color: var(--muted); white-space: nowrap; }
.qs-num b { color: var(--coral); }
.qs-score .psa-btn { height: 28px; font-size: 10px; }

.qs-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.qs-item { padding: 16px 0; border-bottom: 1px dashed var(--line); }
.qs-item:last-child { border-bottom: 0; }
.qs-q { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; margin: 0 0 10px; font-size: 13.5px; font-weight: 660; line-height: 1.62; color: var(--ink); }
.qs-idx { font-family: var(--font-mono); font-size: 10px; color: var(--faint); }
.qs-tag {
  font-family: var(--font-mono); font-size: 8.8px; letter-spacing: .1em; text-transform: uppercase;
  padding: 2px 7px; border-radius: 999px; border: 1px solid var(--line-strong); color: var(--muted);
}
.qs-opts { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 7px; }
.qs-opt {
  display: flex; align-items: flex-start; gap: 9px; text-align: left; padding: 9px 12px;
  border: 1px solid var(--line-strong); border-radius: 9px; background: transparent;
  font-size: 12.5px; line-height: 1.6; color: var(--ink-2); cursor: pointer; transition: all .16s var(--ease);
}
.qs-opt:hover:not(:disabled) { border-color: var(--accent); background: var(--panel-2); }
.qs-opt:disabled { cursor: default; }
.qs-letter { font-family: var(--font-mono); font-size: 10px; color: var(--faint); flex: none; padding-top: 1px; }
.qs-opt.right { border-color: var(--accent); background: var(--panel-2); color: var(--ink); }
.qs-opt.right .qs-letter { color: var(--accent); font-weight: 700; }
.qs-opt.yours { border-color: var(--coral); color: var(--ink); }
.qs-opt.yours .qs-letter { color: var(--coral); font-weight: 700; }
.qs-opt.dim { opacity: .48; }
.qs-why {
  margin: 11px 0 0; padding: 10px 13px; border-left: 2px solid var(--accent); border-radius: 0 8px 8px 0;
  background: var(--panel-2); font-size: 12.3px; line-height: 1.78; color: var(--muted);
}
.qs-item.is-wrong .qs-why { border-left-color: var(--coral); }
.qs-why b {
  display: block; font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .1em; text-transform: uppercase;
  color: var(--accent); margin-bottom: 4px;
}
.qs-item.is-wrong .qs-why b { color: var(--coral); }

.qs-verdict { margin-top: 20px; padding: 16px 18px; border-radius: 13px; border: 1px solid var(--line-strong); background: var(--panel-2); }
.qs-verdict.good { border-color: var(--accent); }
.qs-verdict.bad { border-color: var(--coral); }
.qs-vhead { margin: 0 0 5px; font-size: 14px; font-weight: 740; letter-spacing: -.015em; color: var(--ink); }
.qs-vtext { margin: 0; font-size: 12.6px; line-height: 1.75; color: var(--muted); }

@media (max-width: 620px) {
  .qs-opts { grid-template-columns: minmax(0, 1fr); }
}
</style>
