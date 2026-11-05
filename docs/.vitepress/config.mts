import { defineConfig } from 'vitepress'

const repo = 'https://github.com/yuxinrun/production-scheduling-agent'
const base = process.env.BASE ?? '/'

const nav = [
  { text: '认知', link: '/what-is', activeMatch: '/what-is|/start|/glossary' },
  { text: '数学', link: '/problem/np-hard', activeMatch: '/problem/' },
  { text: '架构', link: '/arch/seven-layers', activeMatch: '/arch/' },
  { text: '实战', link: '/case/background', activeMatch: '/case/' },
  { text: '落地', link: '/build/roadmap', activeMatch: '/build/|/tools/' },
  {
    text: '更多',
    items: [
      { text: '术语速查卡', link: '/glossary' },
      { text: '12 题自测', link: '/quiz' },
      { text: '参考资料', link: '/references' },
      { text: '关于本站', link: '/about' }
    ]
  }
]

const sidebar = [
  {
    text: '开始',
    collapsed: false,
    items: [
      { text: '这本手册怎么读', link: '/start' },
      { text: '排产 Agent 到底是什么', link: '/what-is' },
      { text: '它不是 APS，也不是聊天机器人', link: '/not-aps' },
      { text: '现场术语速查卡', link: '/glossary' }
    ]
  },
  {
    text: '数学与算法',
    collapsed: false,
    items: [
      { text: '为什么排产是 NP-hard', link: '/problem/np-hard' },
      { text: '把车间写成数学：变量、约束、目标', link: '/problem/model' },
      { text: '拉格朗日松弛与对偶定理', link: '/problem/lagrangian' },
      { text: '精确算法：分支定界、割平面、约束传播', link: '/problem/exact' },
      { text: '启发式与元启发式：现场真正在跑的', link: '/problem/heuristic' },
      { text: '多目标：Pareto、ε-约束、字典序', link: '/problem/multiobjective' },
      { text: '不确定性：排队、鲁棒与重排', link: '/problem/uncertainty' },
      { text: '学习与大模型：RL 与 LLM 能做到哪步', link: '/problem/learning' },
      { text: '你怎么知道方案好不好：下界与间隙', link: '/problem/bounds' }
    ]
  },
  {
    text: '系统架构',
    collapsed: false,
    items: [
      { text: '七层底座', link: '/arch/seven-layers' },
      { text: '三级智能体：C / M / A', link: '/arch/three-level' },
      { text: '智能体五大模块与执行控制', link: '/arch/five-modules' },
      { text: 'MCP 接入层：只读工具面', link: '/arch/mcp' },
      { text: '本体、图谱与 SHACL 护栏', link: '/arch/ontology' },
      { text: '求解服务怎么编排', link: '/arch/solver' },
      { text: '写保护、熔断与降级链', link: '/arch/guardrail' },
      { text: '审计链：让决策可回放', link: '/arch/audit' }
    ]
  },
  {
    text: '实战案例：LISA',
    collapsed: false,
    items: [
      { text: '客户与现场', link: '/case/background' },
      { text: '37 项问题：数据说话', link: '/case/pain' },
      { text: '客户明码标价的 KPI', link: '/case/kpi' },
      { text: '68 条规则与 137 条约束', link: '/case/rules' },
      { text: '数据四区间与五维门禁', link: '/case/data' },
      { text: '14 个智能体逐个拆', link: '/case/agents' },
      { text: '七大扰动的处置流程', link: '/case/disturbance' },
      { text: '难度、准确率与形态四档', link: '/case/verdict' },
      { text: '投产配置清单：还差什么', link: '/case/checklist' }
    ]
  },
  {
    text: '工程落地',
    collapsed: false,
    items: [
      { text: '从 0 到 1 的路线图', link: '/build/roadmap' },
      { text: '先修数据，再谈智能', link: '/build/data-first' },
      { text: '评测：影子模式与人机分歧', link: '/build/eval' },
      { text: '采纳率是个组织问题', link: '/build/adoption' },
      { text: '性能：万级变量与秒级重排', link: '/build/perf' },
      { text: '代码：从贪心到 CP-SAT 到 Agent', link: '/build/code' },
      { text: '调度员工作台', link: '/build/workbench' },
      { text: '20 个真实翻车现场', link: '/build/pitfalls' },
      { text: '求解器与技术栈选型表', link: '/tools/stack' }
    ]
  },
  {
    text: '关于',
    collapsed: false,
    items: [{ text: '关于本站', link: '/about' }]
  }
]

export default defineConfig({
  title: '排产 Agent 手册',
  titleTemplate: ':title | 排产 Agent 手册',
  description:
    'Production Scheduling Agent 完全手册：问题建模、拉格朗日松弛、分支定界、约束规划、元启发式、强化学习、三级智能体架构、MCP 接入、护栏与审计，外加一个航空发动机厂的真实案例。',
  base,
  lang: 'zh-CN',
  ignoreDeadLinks: true,
  appearance: true,
  lastUpdated: true,
  metaChunk: true,
  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: `${base}favicon.svg` }],
    ['meta', { name: 'theme-color', content: '#f6f4ee', media: '(prefers-color-scheme: light)' }],
    ['meta', { name: 'theme-color', content: '#06100e', media: '(prefers-color-scheme: dark)' }],
    ['meta', { name: 'author', content: '鱼心快跑' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:title', content: '排产 Agent 手册｜从 NP-hard 到车间现场' }],
    [
      'meta',
      {
        property: 'og:description',
        content: '写给要做 production-scheduling-agent 的程序员：数学怎么建模、算法怎么选、架构怎么搭、坑在哪。'
      }
    ],
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }]
  ],
  markdown: {
    theme: { light: 'github-dark', dark: 'github-dark' },
    lineNumbers: false,
    image: { lazyLoading: true }
  },
  themeConfig: {
    logo: { light: '/logo.svg', dark: '/logo-dark.svg' },
    siteTitle: '排产 Agent 手册',
    nav,
    sidebar,
    outline: { level: [2, 3], label: '本页目录' },
    docFooter: { prev: '上一页', next: '下一页' },
    lastUpdated: { text: '最后更新于', formatOptions: { dateStyle: 'short', timeStyle: 'short' } },
    editLink: { pattern: `${repo}/edit/main/docs/:path`, text: '在 GitHub 上编辑此页' },
    socialLinks: [{ icon: 'github', link: repo }],
    footer: {
      message: `<span class="mp-footer-brand"><img src="${base}sched-fish.svg" alt="戴着安全帽和调度耳麦、正在把甘特条挪回时窗的青色小鱼" width="546" height="363" /><span>鱼心快跑，Bug 追不上</span></span>`,
      copyright: '© 2026 鱼心快跑 · 排产 Agent 手册'
    },
    search: {
      provider: 'local',
      options: {
        detailedView: true,
        translations: {
          button: { buttonText: '搜索手册', buttonAriaLabel: '搜索手册' },
          modal: {
            displayDetails: '显示详情',
            resetButtonTitle: '清除查询',
            backButtonTitle: '返回',
            noResultsText: '没有找到结果。换个说法，比如「齐套」「拉格朗日」「采纳率」。',
            footer: {
              selectText: '选择',
              selectKeyAriaLabel: '回车',
              navigateText: '切换',
              navigateUpKeyAriaLabel: '上箭头',
              navigateDownKeyAriaLabel: '下箭头',
              closeText: '关闭',
              closeKeyAriaLabel: 'Esc'
            }
          }
        }
      }
    },
    returnToTopLabel: '回到顶部',
    sidebarMenuLabel: '菜单',
    darkModeSwitchLabel: '主题',
    lightModeSwitchTitle: '切换到浅色模式',
    darkModeSwitchTitle: '切换到深色模式',
    langMenuLabel: '切换语言',
    notFound: {
      title: '这一页不存在',
      quote: '这条工序在工艺路线里找不到。回首页重新排一遍。',
      linkText: '返回首页'
    }
  },
  transformHead({ pageData }) {
    const title = pageData.frontmatter.title
      ? `${pageData.frontmatter.title} | 排产 Agent 手册`
      : '排产 Agent 手册｜从 NP-hard 到车间现场'
    return [['meta', { property: 'og:title', content: title }]]
  }
})
