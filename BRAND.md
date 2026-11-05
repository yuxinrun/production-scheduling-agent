# 鱼心快跑 · 品牌与设计系统

> 从 `mcp-patterns` 仓库反向提炼出来的完整设计资产。这份文档不是「理想规范」，而是当前代码里**真实生效**的那一套——每一条都能在 [docs/.vitepress/theme/style.css](file:///D:/yuxinrun/mcp-patterns/docs/.vitepress/theme/style.css) 或某个 `.vue` 组件里找到出处。

适用范围：`鱼心快跑 / Yuxin Runs` 品牌下的所有站点。目前已落地四类：技术手册（本站 MCP Patterns、姊妹站《如何构建更好的 Agent》）、工程讲解站（Super-agent）、大众科普手册（《养大一个人》养育站、本站姊妹的睡眠站 good-sleep）。**技术站与科普站共用同一套视觉系统，只在内容纪律上分岔——分岔规则见第九节。**

---

## 一、品牌内核

### 1.1 命名与标识

| 项目 | 中文 | 英文 |
| --- | --- | --- |
| 品牌名 | 鱼心快跑 | Yuxin Runs |
| Slogan | 鱼心快跑，Bug 追不上 | Run, Yuxin, run. Bugs cannot catch you. |
| 吉祥物 | 奔跑的青色小鱼（**姿态按站点主题重画**，见第九节） | a running teal fish with headphones |
| 作者署名 | `meta[name=author]` = 鱼心快跑 | — |
| 主域名 | `yuxin.run` | 站点用二级域名承载手册 |

品牌名是「余心快跑」的谐音梗 + 一条会跑的鱼，**兼作 GitHub 用户名 `yuxinrun`**。整套命名走的是「有画面感的自嘲」而不是「正经技术品牌」，所以文案里可以出现「Bug 追不上」这种话，而不会显得违和。

### 1.2 内容人格

品牌语气由 slogan 决定：**跑得快、不废话、给真东西**。本站把它具体化成五条内容原则（出自 [docs/about.md](file:///D:/yuxinrun/mcp-patterns/docs/about.md)）：

1. **代码优先**——能跑的代码比架构图更有说服力。
2. **工程视角**——关注权限、隔离、超时、观测，而不是只讲协议字段。
3. **可复制**——示例尽量单文件、少依赖，复制后能直接跑。
4. **标注时效**——协议与 SDK 迭代快，过时处明确说明。
5. **不堆术语**——能用一句话说清，就不写三段。

首页主标题直接把它写成宣言：**「把 MCP 当"服务端工程"来做，而不是当"提示词技巧"」**。

这个人格不只体现在正文里，连错误页都在讲话：

> 404 quote：「这个路由没有对应的 MCP 工具。回到首页重新发现。」
> EN：「No MCP tool is registered for this route. Head back home.」

用领域黑话（tool / route / discover）写 404，是这个品牌很小但很稳的一致性动作。

### 1.3 视觉母题：「工程蓝图」

整套界面围绕一个隐喻：**这是一张工程师的图纸，不是一份营销落地页。** 落地成五个可复用的视觉母题：

| 母题 | 实现 | 出现位置 |
| --- | --- | --- |
| **点阵网格** | `radial-gradient(circle at 1px 1px, var(--grid-line) 1px, transparent 0)` + `background-size: 26px 26px` | Hero 背景、深色横幅 `.mp-band` |
| **虚线** | `1px dashed var(--line)` / `--line-strong` | 分割线 `hr`、步骤列表、图表容器内框、架构连线、时间轴主干 |
| **等宽小标签** | mono 9–11px + `letter-spacing: 0.06em~0.16em` + `uppercase` | 板块 eyebrow、侧栏分组、目录标题、统计单位、卡片编号、协议标签 |
| **发光晕染** | 两枚错位的 `radial-gradient` ellipse（teal 左上、coral 右下） | Hero `.VPHero::before`、`.mp-band::before` |
| **微倾斜 + 悬浮** | `transform: rotate(-1.4deg)`；hover `translateY(-3px / -4px)` | Hero 架构图、所有卡片 |

`--ease: cubic-bezier(0.2, 0.7, 0.2, 1)` 全站唯一缓动曲线，所有过渡都用它，不会出现「这个动效和那个不一样」。

---

## 二、配色系统

### 2.1 色彩哲学

**暖白纸面 + 深海墨绿 + 青色主强调 + 珊瑚红补强。**

- 浅色不是纯白，是带黄调的米纸色（`#f6f4ee`），深色不是纯黑，是偏绿的深海（`#06100e`）。两套主题共享同一条 hue 轴（青绿），所以切换主题时「气质」不变，只是照度变了。
- 文字色不是灰，是**墨绿稀释**：`#0e201c → #334a45 → #687a75 → #93a19d` 四级，全部带同一份绿底，避免了灰色文字在暖背景上显脏。
- 语义色只保留三枚高饱和：**teal（主）、coral（警示/否定）、blue（信息/第三系列）**，外加一枚 lime 做第四分类。所有语义色都成对提供 `-soft`（10%~12% alpha）版本，专门用于底色而非描边。

### 2.2 完整 Token 对照表

浅色值来自 `:root`，深色值来自 `html.dark`（[style.css:4-162](file:///D:/yuxinrun/mcp-patterns/docs/.vitepress/theme/style.css#L4-L162)）。

#### 背景层（三级递进）

| Token | 浅色 | 深色 | 用途 |
| --- | --- | --- | --- |
| `--bg` | `#f6f4ee` | `#06100e` | 页面底色 |
| `--bg-soft` | `#eeeae0` | `#0a1815` | 侧栏、页脚、品牌卡底色 |
| `--bg-deep` | `#e7e2d6` | `#0d1e1a` | 更深一层背景（预留） |
| `--panel` | `#fffdf8` | `#0c1b18` | 卡片/图表「纸片」 |
| `--panel-2` | `#f4f0e7` | `#10231e` | 面板内的次级填充、表头、行内代码底 |
| `--panel-3` | `#ebe5d9` | `#152c26` | 进度条轨道等凹槽 |

> 卡片（`--panel`）**永远比页面背景（`--bg`）亮一档**，浅色下 `#fffdf8 > #f6f4ee`，深色下 `#0c1b18 > #06100e`——层级关系靠「照度」而不是靠边框，边框只负责收边。

#### 文字层（四级）

| Token | 浅色 | 深色 | 用途 |
| --- | --- | --- | --- |
| `--ink` | `#0e201c` | `#eaf4ef` | 标题、按钮文字、行内 code |
| `--ink-2` | `#334a45` | `#b4c9c1` | 正文段落 |
| `--muted` | `#687a75` | `#80968f` | 导语、说明、卡片描述 |
| `--faint` | `#93a19d` | `#5f746e` | mono 小标签、时间戳、图注 |

#### 描边层

| Token | 浅色 | 深色 |
| --- | --- | --- |
| `--line` | `rgba(14,32,28,0.13)` | `rgba(234,243,238,0.12)` |
| `--line-strong` | `rgba(14,32,28,0.28)` | `rgba(234,243,238,0.26)` |

注意描边**不是纯色而是前景色的 alpha**——浅色用墨绿透明，深色用米白透明，所以边框自动适配任何背景，且永不出现「白线压在深色上」的突兀。

#### 强调色

| Token | 浅色 | 深色 | 语义 |
| --- | --- | --- | --- |
| `--accent` | `#0a958a` | `#35d8c4` | 品牌主色 teal：链接、active、eyebrow、图表第一系列 |
| `--accent-bright` | `#0bb3a6` | `#5ce8d7` | hover / active / 代码 tab 选中 |
| `--accent-ink` | `#042e2a` | `#032622` | teal 实心底上的文字色 |
| `--accent-soft` | `rgba(10,149,138,0.1)` | `rgba(53,216,196,0.12)` | teal 大面积底色 |
| `--coral` | `#e85734` | `#ff7c5e` | 警示、危险块、图表第二系列、「坑」 |
| `--coral-soft` | `rgba(232,87,52,0.1)` | `rgba(255,124,94,0.12)` | |
| `--blue` | `#3568d4` | `#7ba1ff` | 信息、图表第三系列 |
| `--blue-soft` | `rgba(53,104,212,0.1)` | `rgba(123,161,255,0.12)` | |
| `--lime` | `#a9cc3f` | `#c4e35d` | 第四分类（实战案例卡） |
| — | `#b7791f` | 同左 | VitePress warning 琥珀，仅用于 warning 块 |

> 深色主题下所有强调色**提亮并降饱和**（`#0a958a → #35d8c4`、`#e85734 → #ff7c5e`），这是保证深底可读性的关键，不是简单反相。

#### 氛围与阴影

| Token | 浅色 | 深色 |
| --- | --- | --- |
| `--hero-glow` | `rgba(10,149,138,0.14)` | `rgba(53,216,196,0.12)` |
| `--coral-glow` | `rgba(232,87,52,0.12)` | `rgba(255,124,94,0.1)` |
| `--grid-line` | `rgba(14,32,28,0.05)` | `rgba(234,243,238,0.045)` |
| `--nav-bg` | `rgba(246,244,238,0.82)` | `rgba(6,16,14,0.8)` |
| `--shadow` | `0 22px 60px -32px rgba(14,32,28,0.4)` | `0 24px 70px -34px rgba(0,0,0,0.9)` |
| `--shadow-lg` | `0 40px 100px -50px rgba(14,32,28,0.5)` | `0 40px 110px -50px rgba(0,0,0,0.95)` |

阴影全部是**大扩散 + 强负 spread**（如 `60px -32px`），效果是「柔和的悬浮」而不是「明显的投影」，符合纸片/蓝图的调性。导航栏用 `rgba` 半透明 + `backdrop-filter: blur(14px)` 做毛玻璃。

#### 代码块色板（不随主题切换）

| Token | 浅色 | 深色 |
| --- | --- | --- |
| `--code-bg` | `#0c1a17` | `#081411` |
| `--code-head` | `#11241f` | `#0d201b` |
| `--code-line` | `rgba(234,243,238,0.1)` | `rgba(234,243,238,0.09)` |

配合 [config.mts:201](file:///D:/yuxinrun/mcp-patterns/docs/.vitepress/config.mts#L201) 的 `markdown.theme: { light: 'github-dark', dark: 'github-dark' }`——**浅色主题下代码块依然是深墨绿**。这是刻意为之：正文是纸，代码是终端，两者必须形成强对比，也让「代码优先」的品牌主张在视觉上被突出。

### 2.3 VitePress 官方 Token 接管

品牌不直接改组件，而是把自有变量注入 VitePress 的语义槽位（[style.css:46-120](file:///D:/yuxinrun/mcp-patterns/docs/.vitepress/theme/style.css#L46-L120)），因此升级主题不丢设计：

```css
--vp-c-bg / --vp-c-bg-alt / --vp-c-bg-soft / --vp-c-bg-elv / --vp-c-bg-mute  ← 五级背景
--vp-c-text-1/2/3                                                            ← 三级文字
--vp-c-divider / --vp-c-gutter / --vp-c-border                               ← --line
--vp-c-brand-1/2/3/soft                                                       ← teal 三档 #0a958a / #0b837a / #086f68
--vp-c-tip-*  = teal      --vp-c-warning-* = #b7791f      --vp-c-danger-* = coral
--vp-nav-height: 68px      --vp-home-hero-name-color: var(--ink)   /* 禁用官方渐变字 */
```

**主按钮的反常规设定**（最值得记住的一处）：

| 状态 | 浅色主题 | 深色主题 |
| --- | --- | --- |
| 默认 | 底 `--ink`（墨绿实色）+ 字 `#f6f4ee` | 底 `#35d8c4` + 字 `#042e2a` |
| hover | 底 `--accent`（teal）+ 字 `--accent-ink` | 底 `#5ce8d7` |
| active | 底 `--accent-bright` | — |

浅色模式的品牌按钮是**深色实心**而非「品牌色实心」，把 teal 留给 hover 那一刻——克制、不喧哗，同时让青色的「鱼」只在互动时出现。
次按钮 `alt` 是**完全透明 + 描边**，hover 时才填 10% teal。

另外两条硬性覆盖：`--vp-home-hero-name-color` 与 `.VPHero .name .clip { background: none !important }`（[style.css:792-799](file:///D:/yuxinrun/mcp-patterns/docs/.vitepress/theme/style.css#L792-L799)）**主动关闭 VitePress 默认的彩虹渐变标题字**，改用纯 `--ink`。这是判断「一个站是不是认真做过品牌」的快速试纸——默认渐变字被系统性移除。

### 2.4 图表配色约定（三系列固定语义）

所有数据可视化沿用同一套「颜色 = 类别」映射（[RatingBars.vue:116-129](file:///D:/yuxinrun/mcp-patterns/docs/.vitepress/theme/components/RatingBars.vue#L116-L129)）：

| 语义 | 颜色 | 用于 |
| --- | --- | --- |
| stdio / Client / 正常态 | `--accent` teal | 传输第一系列、架构 Client 节点、AuthFlow `tone-teal` |
| Streamable HTTP / Server / 风险态 | `--coral` | 传输第二系列、架构 Server 节点、AuthFlow 401/token 步骤 |
| Legacy SSE / Capability | `--blue` | 传输第三系列、Tools 节点、AuthFlow 元数据发现 |
| 第四分类 | `--lime` | `tone-lime`（实战案例卡） |

`.mp-card` 用 `--card-color` 局部变量 + `.tone-*` 类实现同一套：顶部 3px 色条、hover 描边、`mp-go` 文字色三处同时联动（[style.css:981-1044](file:///D:/yuxinrun/mcp-patterns/docs/.vitepress/theme/style.css#L981-L1044)）。

板块色序（首页七大板块）：`accent → coral → blue → lime → accent → coral`，不重复相邻同色。

### 2.5 深色横幅（唯一的固定深色块）

`.mp-band` 是首页里**唯一不跟随主题**的容器，永远深墨绿（[style.css:1105-1178](file:///D:/yuxinrun/mcp-patterns/docs/.vitepress/theme/style.css#L1105-L1178)）：

```
底 #0a1714 / 圆角 28px / padding 54px
自带点阵 + teal(0.16) 左上光 + coral(0.10) 右下光
文字：eyebrow #35d8c4 / 标题 #f2fbf6 / 导语 #9fb6ae
内部卡：边框 rgba(234,243,238,.14) + 底 rgba(255,255,255,.035) + backdrop-filter blur(6px)
```

用途：**观点级内容**（「工具是手，Skill 是操作手册」）。在浅色主题里它像关灯聚焦，在深色主题里它是加深一档。这是版面上最强的层级信号，一页最多用一次。

---

## 三、字体排印

### 3.1 字体栈

```css
--font-sans: 'Manrope Variable', 'PingFang SC', 'Hiragino Sans GB',
            'Microsoft YaHei', 'Noto Sans SC', sans-serif;
--font-mono: 'JetBrains Mono Variable', 'SFMono-Regular', Consolas,
             'Liberation Mono', monospace;
```

- 两者通过 `@fontsource-variable/*` **自托管可变字体**（无 CDN 依赖、无 FOUT 抖动、离线可构建），见 [package.json:12-14](file:///D:/yuxinrun/mcp-patterns/package.json#L12-L14)。
- 中文回退顺序按 macOS → macOS 日文环境 → Windows → Linux 排列，覆盖三大平台原生中文字体。
- `font-synthesis: none`：**禁止浏览器伪粗/伪斜**——可变字体自己有权重轴，合成粗体会破坏字形。这条设置是「字体认真挑过」的标志。

### 3.2 字号与字重刻度

| 层级 | 字号 | 字重 | 行高 | 字距 |
| --- | --- | --- | --- | --- |
| 正文 body | 16px | 400 | 1.72 | 0 |
| 文档正文 `.vp-doc` | 15.5px（移动 15px） | 400 | 1.78 | 0 |
| 文档 H1 | `clamp(2rem, 4vw, 2.85rem)` | **760** | 1.1 | `-0.035em` |
| 文档 H2 | `clamp(1.42rem, 2.4vw, 1.78rem)` | **730** | 1.25 | `-0.028em` |
| 文档 H3 | 1.16rem | 700 | — | `-0.018em` |
| 正文 strong | — | **680** | — | — |
| 正文链接 | — | **560** | — | — |
| Hero `name` | `clamp(3.1rem, 7vw, 5.2rem)` | **780** | 1.02 | `-0.055em` |
| Hero `text` | `clamp(1.45rem, 3.2vw, 2.35rem)` | **720** | 1.18 | `-0.035em` |
| Hero `tagline` | `clamp(0.98rem, 1.4vw, 1.08rem)` | 400 | 1.75 | 0 |
| 板块标题 `.mp-h2` | `clamp(1.8rem, 3.4vw, 2.75rem)` | **750** | 1.12 | `-0.035em` |
| 导语 `.mp-lead` | 15px | 400 | 1.75 | 0 |
| 卡片 H3 | 16px | **720** | — | `-0.02em` |
| 卡片正文 | 12.5px | 400 | 1.65 | 0 |
| 统计数字 `.mp-stat strong` | 2rem | **760** | 1 | `-0.04em` |
| 站点标题（导航） | 16px | **760** | — | `-0.03em` |
| 代码块 | 12.8px | — | 1.7 | 0 |
| 行内 code | 0.85em | 500 | — | — |
| 表格 | 13.5px（表头 11.5px） | 650 | — | — |

### 3.3 三条排印签名

1. **可变字体的非整数权重**。全站使用 `780 / 760 / 750 / 730 / 720 / 680 / 650 / 560` 这类字重，而不是 `700/800` 阶梯。效果是层级密、过渡顺，视觉上「贵」而不「重」。依赖可变字体，用静态字重家族无法照搬。
2. **越大的字越紧**。字距随字号递减：H1 `-0.035em` → Hero name `-0.055em` → 统计数字 `-0.04em`；而 mono 小标签反向操作，字号越小字距越宽（`9px / 0.16em`）。一收一放，形成「大标题紧凑 + 小标签松散」的强对比。
3. **sans 讲人话，mono 讲机器话**。任何「非人类阅读主体」的信息一律 mono + uppercase + 宽字距：板块 eyebrow、侧栏分组名、目录标题、卡片编号、统计单位、分页 `desc`、协议标签、图注。正文与标题永不使用 mono。

Hero 明确禁用 VitePress 渐变字（`.clip { background: none !important }`），标题用纯 `--ink`；`text-wrap: balance` 用于 `.mp-h2` 防止标题断行难看。

---

## 四、尺寸与节奏 Token

```css
--radius-sm: 10px;      --radius: 18px;      --radius-lg: 28px;
--container: 1180px;    --ease: cubic-bezier(0.2, 0.7, 0.2, 1);
```

| 尺寸 | 值 | 用在哪 |
| --- | --- | --- |
| 内容容器 | `min(1180px, 100% - 48px)`（移动 `100% - 36px`） | `.mp-wrap` |
| 正文栏宽 | `760px` | `.VPDoc .content-container`（单栏窄正文） |
| 导航高度 | `68px` | `--vp-nav-height` |
| 锚点偏移 | `scroll-padding-top: 92px` | 防止标题被导航遮住 |
| 板块纵向 | `72px 0`（移动 `52px 0`） | `.mp-section` |
| Hero 纵向 | `96px 24px 76px`（≤960px：`66px 24px 54px`） | `.VPHero` |
| 深色横幅内边距 | `54px`（≤960：`38/30`；≤760：`30/22`） | `.mp-band` |
| 卡片内边距 | `24px 22px 22px` | `.mp-card` |
| 图表内边距 | `22~26px 24px` | 各组件容器 |
| 块级元素外边距 | `22px 0` | 表格、代码块、code-group、custom-block、blockquote |
| 文档 H2 上边距 | `52px` + `padding-top: 26px` + 上边框 | 段落级分隔 |
| `hr` | `40px 0`，`1px dashed --line-strong` | 手写分隔 |

### 圆角分档（从「纸片」到「胶囊」）

| 半径 | 归属 |
| --- | --- |
| `999px` | 主/次按钮、品牌 pill、标签 chips、状态点、进度条轨道 |
| `28px` | Hero 架构图、深色横幅 |
| `18~20px` | `.mp-card`、图表容器、品牌卡 |
| `16px` | 统计块、搜索弹窗外壳 |
| `12~14px` | 表格、custom-block、代码块、分页卡、正文图片 |
| `9~10px` | 网格内小格、侧栏链接 |
| `5px` | 行内 code、协议小标签 |

规律：**外容器大圆角、内元素小圆角**，层级靠半径递减排列，不出现内层比外层更圆。

---

## 五、网页布局

### 5.1 全局骨架

```
┌─ VPNavBar (68px, 毛玻璃 blur14, 底部 1px 实线) ─────────────────┐
│  [Logo 26px] MCP Patterns │ 基础 Server 工程模式 实战 生态 ⌄更多  │
│                                    🌙 主题  🌐 语言  GitHub  搜索 │
└──────────────────────────────────────────────────────────────────┘
┌─ VPSidebar ─┬─ 主内容 ───────────────────────────┬─ Outline ───┐
│ bg --bg-soft│                                    │ 「本页目录」│
│ 右 1px 描边 │  首页：.mp-wrap (1180)             │  h2–h3 二级 │
│ 顶 pad 26px │  文档：760 单栏居中                 │  吸顶       │
│  分组=mono  │                                    │             │
│  项=圆角链接│                                    │             │
├─────────────┴────────────────────────────────────┴─────────────┤
│ VPFooter：bg --bg-soft / 上边框 / [鱼 icon 40px] 鱼心快跑，Bug 追不上 │
│                          © 2026 鱼心快跑 · MCP Patterns        │
└──────────────────────────────────────────────────────────────────┘
```

- **导航（信息架构 6 项）**：`基础 / Server / 工程模式 / 实战 / 生态` 五项直出 + `更多` 下拉收纳低频入口（调试排坑、Skill Hub、框架对接、关于本站、姊妹站 ↗）。低频内容**折叠而不是堆满**，是这套 IA 的核心取舍。
- **侧栏**：分组标题用 mono 10px `uppercase` `0.12em` 灰 `--faint`；二级项圆角 8px 内缩 `margin-inline: -10px`；**当前项 = teal 10% 底色 + teal 文字 + 字重 650**（三重信号，不只变色）。所有分组 `collapsed: false`——手册类站点不做折叠，避免隐藏结构。
- **目录（Outline）**：`level: [2, 3]`，标题同样 mono 9.5px 大写。
- **文档页正文只有 760px 单栏**，而首页用 1180px 宽栅格——**阅读宽度与营销宽度分离**，正文行长控制在约 75 字符（15.5px）。

### 5.2 首页版面（8 段式叙事）

Hero 由 VitePress frontmatter 提供，正文之后的 8 个 `<section class="mp-section">` 全部手写排版（[docs/index.md](file:///D:/yuxinrun/mcp-patterns/docs/index.md)）。每段结构固定为 **eyebrow → h2 → lead → 版面组件**：

| # | eyebrow | 主张 | 版面组件 |
| --- | --- | --- | --- |
| Hero | — | name + text + tagline + 3 actions | `BrandMark pill`（注入 slot）+ `HeroDiagram` |
| 01 | `MCP Patterns · 工程实战手册` | 一句话：把 MCP 当服务端工程 | `.mp-stats`(4) + `.mp-tags`(8) |
| 02 | `Quickstart · 15 分钟` | 先跑通，再理解 | `.mp-split`：左 `.mp-steps`(3) + quote，右 code-group |
| 03 | `Map · 七个板块` | 按工程问题组织，不按协议章节 | `.mp-grid` 6 张 `.mp-card` |
| 04 | `Transport · 怎么选`（coral） | 三种传输不是偏好而是边界 | `<RatingBars />` + 结论 lead |
| 05 | `Ecosystem · 2026` | 谁在支持，支持到什么程度 | 8 行对照表 + quote |
| 06 | `Skill vs MCP`（coral） | 工具是手，Skill 是操作手册 | `.mp-band` 深色横幅 + `.mp-band-grid` 2×2 |
| 07 | `Field notes · 避坑` | 上线前最常翻车的 6 件事 | `.mp-grid` 6 张**全 coral** 卡 |
| 08 | `Sister site · 姊妹站` | 一个讲 Agent，一个讲工具 | `.mp-friend` 2 卡 + quote |

叙事顺序本身就是品牌主张：**宣言 → 立即动手 → 全景地图 → 选型 → 生态 → 观点 → 风险 → 关联**。先给「跑通」再给「理解」，第 02 段就跑在地图前面。

首段用 `style="border-top:0;padding-top:20px"` 抹掉与 Hero 相接的横线——细节上不允许两段紧贴出现双线。

### 5.3 Hero 版式

```
.VPHero  padding 96/24/76, overflow hidden
  ::before  两层 radial 光晕 + 26px 点阵（pointer-events none）
  .container  ≥960px → grid 1.05fr | 0.95fr, gap 48px, align center
              默认 max-width 1180px
  .main     max-width 640px
    ├─ BrandMark pill（slot: home-hero-info-before，居中，上边距 0，下 20px）
    ├─ name   clamp(3.1~5.2rem) / 780 / -0.055em   ← 纯色，禁渐变
    ├─ text   clamp(1.45~2.35rem) / 720 / 620px
    ├─ tagline clamp(0.98~1.08rem) / 590px / --muted
    └─ actions gap 10px, padding-top 30px
  .image    HeroDiagram，max-width 520px，靠右
```

- **CTA 结构固定 3 枚**：1 个 `brand`（开始阅读）+ 2 个 `alt`（跑通第一个 Server / GitHub）。按钮高 46px、胶囊圆角、hover 上浮 2px。
- ≤960px：`.main` 与 `.image` 用 flex `order` 交换为**文案居中在前、图形在后**，动作按钮居中。
- VitePress 自带的 `.image-bg` 光斑与 `<img>` 全部隐藏，图形位改由 Vue 组件接管——**Hero 右侧不是图片，是一个可交互的架构示意图**。

### 5.4 组件级版式模式

**卡片 `.mp-card`**
```
display flex column / border 1px --line / radius 18 / bg --panel / overflow hidden
::before 顶部 3px 色条（--card-color, opacity .85）
结构：.mp-num（mono 1.8rem，颜色 --line-strong，作水印级编号）
      → h3 16px/720 → p 12.5px/--muted → .mp-go 11.5px 卡片色
hover：translateY(-4px) + 描边混入 55% 卡片色 + --shadow
.mp-go::after 内容 ' →'，hover 时 margin-left 0→4px（箭头自己往前挪）
```
编号是**装饰性 mono 大字**而非信息，用极低对比度（`--line-strong`）压成背景纹理——数字承担「秩序感」，不承担「读数」。

**统计 `.mp-stats`**：4 栏 → 移动 2 栏；数字 2rem/760 `-0.04em` + 单位 mono 9px 大写。数字与单位字号比约 4.5:1，夸张反差制造读数冲击。

**分栏 `.mp-split`**：`1.05fr 0.95fr` / gap 34px，**左叙事右实证**（左步骤 + 引文，右代码 code-group）。≤960px 塌成单列。

**步骤 `.mp-steps`**：`grid 34px 1fr` / 行间 `1px dashed`；序号是 30px 空心圆（边框 `--line-strong`）内 mono 10px teal。用**虚线 + 空心圆**而非实心编号块——图纸感来自这里。

**横幅内卡 `.mp-band-card`**：半透明白 3.5% + 毛玻璃 blur(6px) + 14% 米白描边，在固定深底上营造「玻璃压在深色液体上」。

**引文 `.mp-quote`**：`border-left: 2px solid var(--coral)` + 右圆角 12px + `--panel-2` 底。注意**引文强调条是 coral 不是 teal**——金句/警告用暖色，与链接的 teal 区分开，读者一眼知道「这句是提醒」。

**标签 `.mp-tags span`**：mono 9px 胶囊 + `--panel-2` 底 + 1px 描边。用于把技术栈压成一行可扫的清单。

### 5.5 品牌资产落位

| 资产 | 文件 | 形态 |
| --- | --- | --- |
| 站点 Logo（浅色） | [docs/public/logo.svg](file:///D:/yuxinrun/mcp-patterns/docs/public/logo.svg) | 单色 `#0E201C`，viewBox 1024 |
| 站点 Logo（深色） | [docs/public/logo-dark.svg](file:///D:/yuxinrun/mcp-patterns/docs/public/logo-dark.svg) | 同路径，`#EAFAF5` |
| Favicon | [docs/public/favicon.svg](file:///D:/yuxinrun/mcp-patterns/docs/public/favicon.svg) | `#0E201C` 圆角方块（rx 220）内嵌 0.7 倍 teal `#35D8C4` 图形 |
| 吉祥物 | [docs/public/yuxin-run.png](file:///D:/yuxinrun/mcp-patterns/docs/public/yuxin-run.png) | 546×363，戴耳机奔跑的青色小鱼 |

图形是**一个 path 三种底色**，明暗 logo 仅换 `fill`，favicon 才加底板——资产极省，且明暗切换时形状 100% 一致。

`BrandMark.vue` 提供两种落位（[style.css:624-725](file:///D:/yuxinrun/mcp-patterns/docs/.vitepress/theme/style.css#L624-L725)）：

- `variant="pill"`（默认）：胶囊容器，鱼图 42px 高 + 右侧两行文字（名 12.5px/700、slogan 11.5px/--muted，`white-space: nowrap`）。**自动注入首页 Hero 文案之前**。
- `variant="card"`：通栏卡，radius 20 + `--bg-soft` 底，鱼图 152px，名字 21px、slogan 14px 换行。用于「关于本站」正文。
- 页脚：`footer.message` 内联 HTML `.mp-footer-brand`，鱼图 40px + slogan 13px/650，居中可换行。
- README 顶部：吉祥物居中 180px，H1 与 slogan 均居中——**README 也遵守同一版式**。

`<BrandMark>` 通过 `useData().lang` 自动切换中英文文案与 alt，吉祥物 alt 写全「戴着耳机奔跑的青色小鱼」，无障碍描述与品牌叙述一体。

### 5.6 图表组件（文档可视化语言）

`theme/index.ts` 全局注册 5 个图表 + 2 个 slot 注入（[docs/.vitepress/theme/index.ts](file:///D:/yuxinrun/mcp-patterns/docs/.vitepress/theme/index.ts)）。共性：**外框 1px 实线 + radius 20 + `--panel` 底 + 可选一角 radial 光晕；内部分区用 dashed 分隔；图注 mono 极小；底部固定一句「免责/口径说明」**。

| 组件 | 位置 | 版式 |
| --- | --- | --- |
| `HeroDiagram` | Hero 图形 slot | 纵向四层节点 + 虚线连接 + `rotate(-1.4deg)` + 内嵌 10px 虚线框 + 右上珊瑚光斑 150px；`ready` 状态点 2.4s 呼吸闪烁 |
| `McpArch` | 「什么是 MCP」 | 4 列栅格 `1fr 30px 1fr 30px 1fr 30px 1fr`；列间虚线 + 三角箭头 + 居中 mono 标签；Client/Server/Tools 三列分别描 teal/coral/blue；≤900px 转纵向，箭头自动旋转 135° |
| `RatingBars` | 传输选型 | 图例（18×4 色条）+ 5 行 × 3 系列横向条（轨道 `--panel-3`，胶囊填充，宽 = 分/5）；`180px 1fr` 标签栅格；≤760px 单列 |
| `SpecTimeline` | 协议演进 | 桌面 5 列横轴 + 贯穿 dashed 主线 + 空心节点（最新节点 teal 描边 + 4px teal 光环 + 标题变 teal）；≤760px 重排为 `64px 16px 1fr` 三列纵向轴 |
| `AuthFlow` | 鉴权流程 | 5 步等分栅格 + 步间 18px 圆形箭头（绝对定位压在缝隙）+ 底部协议标签行（OAuth 2.1 / RFC 8707 / RFC 9728 / PKCE）；每步按风险态描 teal/coral/blue 边 |

**每个组件都自带中英双份文案数组**（`zhRows/enRows`、`zhSteps/enSteps`、`zhMilestones/enMilestones`），由 `useData().lang` 选择——图形内的文字也是双语资产，不靠机器翻译。

### 5.7 响应式策略

断点序列（全站只此五个）：

| 断点 | 触发变化 |
| --- | --- |
| `≥960px` | Hero 与 `.mp-split` 启用双栏；`HeroDiagram` 微倾斜 |
| `≤1080px` | `.mp-grid` 3 → 2 栏 |
| `≤960px` | Hero 文案/图形换序并居中；`.mp-split`/`.mp-band-grid`/`.mp-friend` → 单栏；横幅内边距 38/30；图形取消倾斜 |
| `≤760px` | 正文 15px；**表格转 `display:block` + 横向滚动 + `white-space:nowrap`**；`.mp-stats` 4→2；`.mp-grid`→1；横幅 30/22 且半径 20；板块纵向 52px；图表组件转纵向布局 |
| `≤640px` | 品牌卡纵向堆叠、图 118px |
| `≤480px` | Hero 图内边距 20/18，半径 20 |

移动端优先处理的不是缩放，而是**结构性变形**：横轴表格变可滑、横轴时间轴变纵轴、横向箭头变纵向箭头、倾斜变回正。窄屏不是缩小版，是另一套读法。

无障碍与偏好：`:focus-visible` 全局 2px teal 描边 + 3px offset；`::selection` 反色用 teal 底 + `--accent-ink` 字；`prefers-reduced-motion: reduce` 把全站动画/过渡压到 0.01ms（并单独关掉 `ready` 闪烁）；图表装饰层 `aria-hidden`；语言与主题切换文案完整双语覆盖。

---

## 六、内容层布局约定

### 6.1 每篇文档的固定骨架

```markdown
---
title: 页面标题（进 <title> 与 og:title，格式「标题 | MCP Patterns」）
description: 一句话摘要（进 SEO description）
---

# 标题（正文 H1，不复用 frontmatter title）

一段「先给判断」的开篇，关键名词用 **加粗** 锚定。

> **一句加粗的引用**，把核心比喻说死。
> 例：「MCP 是 AI 世界的 USB-C 接口。」

<ChartComponent />   ← 结构图紧跟概念之后

| 表头 | 表头 |        ← 对照信息一律用表格，不写成并列段落
```

- frontmatter 只写 `title` + `description` 两项，页面标题层级由正文 H1 承担。
- 中英双语是**镜像目录**：`docs/**` 与 `docs/en/**` 结构一一对应，链接路径与侧栏顺序保持一致；翻译是结构维护义务，不是附属产物。
- 安全类内容强制「错误写法 / 正确写法」对照；代码块必须标注语言；不引入无法验证的数据（[README.md:102](file:///D:/yuxinrun/mcp-patterns/README.md#L102)）。

### 6.2 VitePress 控件的品牌化

| 控件 | 品牌处理 |
| --- | --- |
| `::: tip` | teal 10% 底 + 30% teal 描边 + 标题 teal、大写 mono 11px |
| `::: warning` | 琥珀 8% 底 + 28% 琥珀描边 |
| `::: danger` | coral 10% 底 + 30% coral 描边 + 标题 coral |
| `::: info` | `--panel-2` 灰底 |
| 所有 custom block | 去粗边框，改 **1px 实线描边 + 圆角 12px + 浅色底**——不用默认那套左侧彩条 |
| 代码块 | 深墨绿底 + 14px 圆角 + `--shadow` + 右上 `lang` 标记（mono 9.5px）+ 实心按钮式复制键 |
| code-group | tab 栏 `--code-head` 底，标签 mono 10px，选中项 `--accent-bright` 文字 + 底部指示条 |
| 行内 code | `--panel-2` 底 + 1px 描边 + 5px 圆角 + `--ink`（**不上色**，避免正文里满屏彩色代码） |
| 表格 | `border-collapse: separate` + 12px 圆角 + `overflow: hidden`；表头 `--panel-2`；行 hover 55% 面板色；末行去底线 |
| 链接 | teal + 下划线（38% 淡色 underline）→ hover 描实，`text-underline-offset: 3px` |
| 分页 | 圆角 12 卡片，`desc` 用 mono 9px 大写，hover 描边变 teal |
| 搜索 | 本地搜索 `detailedView`，弹窗 16px 圆角 + `--shadow-lg`；全部按钮/快捷键文案中文化 |

所有自定义块**标题都变成 mono 大写**，与侧栏分组、目录标题、eyebrow 共用同一标签语言——整个站点的「元信息」在视觉上属于同一个家族。

---

## 七、可复制的最小品牌骨架

新项目要复刻这套品牌，直接抄下面这一段（**这是全部必要信息**），再遵守第八节纪律即可。

```css
:root {
  /* 字体（自托管可变字体） */
  --font-sans: 'Manrope Variable', 'PingFang SC', 'Hiragino Sans GB',
               'Microsoft YaHei', 'Noto Sans SC', sans-serif;
  --font-mono: 'JetBrains Mono Variable', 'SFMono-Regular', Consolas, monospace;
  font-synthesis: none;

  /* 骨架 */
  --container: 1180px;   /* 阅读栏另设 760px */
  --radius-sm: 10px; --radius: 18px; --radius-lg: 28px;
  --ease: cubic-bezier(0.2, 0.7, 0.2, 1);

  /* 纸与墨 */
  --bg: #f6f4ee; --bg-soft: #eeeae0; --panel: #fffdf8;
  --panel-2: #f4f0e7; --panel-3: #ebe5d9;
  --ink: #0e201c; --ink-2: #334a45; --muted: #687a75; --faint: #93a19d;
  --line: rgba(14,32,28,.13); --line-strong: rgba(14,32,28,.28);

  /* 三色语义 */
  --accent: #0a958a; --accent-bright: #0bb3a6;
  --accent-ink: #042e2a; --accent-soft: rgba(10,149,138,.1);
  --coral: #e85734;  --coral-soft: rgba(232,87,52,.1);
  --blue:  #3568d4;  --blue-soft:  rgba(53,104,212,.1);
  --lime:  #a9cc3f;

  /* 氛围 */
  --shadow: 0 22px 60px -32px rgba(14,32,28,.4);
  --hero-glow: rgba(10,149,138,.14); --coral-glow: rgba(232,87,52,.12);
  --grid-line: rgba(14,32,28,.05);   --nav-bg: rgba(246,244,238,.82);
  --code-bg: #0c1a17;                 /* 代码永远深色 */
}
html.dark {
  --bg:#06100e; --bg-soft:#0a1815; --panel:#0c1b18; --panel-2:#10231e; --panel-3:#152c26;
  --ink:#eaf4ef; --ink-2:#b4c9c1; --muted:#80968f; --faint:#5f746e;
  --line:rgba(234,243,238,.12); --line-strong:rgba(234,243,238,.26);
  --accent:#35d8c4; --accent-bright:#5ce8d7; --accent-ink:#032622;
  --accent-soft:rgba(53,216,196,.12);
  --coral:#ff7c5e;  --coral-soft:rgba(255,124,94,.12);
  --blue:#7ba1ff;   --blue-soft:rgba(123,161,255,.12);  --lime:#c4e35d;
  --shadow:0 24px 70px -34px rgba(0,0,0,.9);
  --hero-glow:rgba(53,216,196,.12); --coral-glow:rgba(255,124,94,.1);
  --grid-line:rgba(234,243,238,.045); --nav-bg:rgba(6,16,14,.8);
  --code-bg:#081411;
}
```

`<meta name="theme-color">` 同步为浅色 `#f6f4ee` / 深色 `#06100e`（与页面底色严格一致，不是品牌色）。

---

## 八、七条不可让步的纪律

这些是把「同一套变量」变成「同一个品牌」的真正差异，迁移新项目时必须逐条守住：

1. **纸不是白的，黑不是黑的。** 底色永远带hue（米白 / 深墨绿），文字与描边用前景色的 alpha 派生，禁止出现纯 `#fff` / `#000` / 中性灰。
2. **强调色不做大面积实心。** 浅色模式主按钮用 `--ink` 实心，teal 只在 hover、链接、active、色条上出现。
3. **代码块恒深色**，且浅色主题下也是（`github-dark` 双向）。
4. **禁用默认渐变标题字**，Hero 大标题用纯 `--ink` + 可变字重 780 + `-0.055em`。
5. **元信息一律 mono 大写宽字距**（9–11px / `0.06–0.16em`），与正文sans严格分工。
6. **虚线 + 点阵 + 大扩散阴影**三件套承担「工程蓝图」质感；一处观点级内容才允许一块固定深色横幅。
7. **窄屏做结构变形，不做等比缩放**；同时必须提供 `prefers-reduced-motion` 与完整双语/明暗文案。

吉祥物只在品牌位出现（Hero pill、关于页卡、页脚、README 顶），**不参与功能图标**；功能图形语义只留给那个单 path 的 logo 形。鱼负责情感识别，几何标记负责系统识别，两者不混用。

---

## 九、跨站点延展：图形按内容生成，科普站另加纪律

### 9.1 站点图形按站点内容生成

母品牌只有两样东西是固定的：**一条青色小鱼**（情感识别）和**一套 token**（色值 / 圆角 / 字号 / 落位）。至于 logo 长什么样、小鱼在干什么——**每个站点按自己的主题重画**。

| 站点 | 主题 | 几何标记形状 | 吉祥物姿态 |
| --- | --- | --- | --- |
| mcp-patterns / super-agent | 协议与 Agent 工程 | 接口节点 + 连线 | 戴耳机奔跑 |
| child-rearing | 0–22 岁养育 | 沿用节点标记（历史遗留） | 沿用奔跑款 |
| good-sleep | 睡眠 | 月牙 + 三个 Z | 戴睡帽抱枕头打呼 |
| start-a-business | 从 0 创业 | 火箭（弹体 + 舷窗孔 + 双尾翼 + 尾焰） | 戴安全帽推一枚比自己大的飞轮 |
| common-algorithms | 生产生活里常用的算法 | 两级台阶的阶梯路径（带起点孔与终点孔，`fill-rule: evenodd`） | 戴圆眼镜、拿直尺在方格纸上画最短路径 |

前三个站点其实复用了同一个节点状标记，只换 `aria-label`——**从 good-sleep 起改成按主题重画**，因为一个讲睡眠的站挂着一个"服务器接口"形状，读者第一眼就该觉得不对劲。

重画时的硬约束（这几条保证它还是同一个品牌，而不是换个 logo）：

1. **单 path、`viewBox 0 0 1024 1024`、纯几何**，不用渐变、不依赖描边，形状在 26px（导航尺寸）下仍可辨认。
2. **明暗两版只换 `fill`**：浅色 `#0E201C`、深色 `#EAFAF5`；favicon 才是"圆角方块 `rx 220` 底板 + 0.7 倍 teal `#35D8C4` 图形"。
3. 形状必须能被站点主题解释：月牙就是睡眠，节点就是接口。抽象到看不出主题的一律重做。
4. 吉祥物位图（PNG）保持**同一只鱼、同一配色、同一画风**，只换姿态与道具；`alt` 写全（"戴着睡帽抱着枕头打呼的青色小鱼"），无障碍描述与品牌叙述一体。
5. 生成式位图**只做品牌位**（Hero pill、关于页卡、页脚、README 顶），不参与功能图标；功能图形语义只留给那个单 path 标记。

start-a-business 的吉祥物 `founder-fish.svg` 是**手绘矢量**而非生成位图（当次图像生成额度不可用）。这反而暴露出一个可复用的做法：**标记讲读者以为的故事，吉祥物讲站点真正教的故事**——导航栏是火箭（人人脑里的"创业"），页脚是戴安全帽推飞轮的鱼（这门生意实际怎么转）。两个图形不重复表达同一件事。

### 9.2 大众科普站的六条附加纪律

技术站（代码优先、可复制）之外的另一套内容要求，适用于养育站、睡眠站、创业站这类给普通大众看的手册：

1. **先建事实库，再写正文。** 调研产物落在 `.qoder/research-*.md`，汇总成分级事实库（A 可核 / B 需限定 / C 流行但证据弱）＋红线清单（明确不许写的说法）。正文里出现的每个数字都要能在事实库里找到出处；查不到就写"不知道"。
2. **图表密度有硬指标。** 每 400–600 字至少一个可视化（图 / 表 / 卡 / 时间轴），连续纯文字不超过 12 行，一页 2–4 张为宜。图不是装饰，是"读数"的那一层。
3. **图读数，正文讲人话。** 每张图自带一句结论（听书时读不到图，只能读到这句话）；需要读者记住的数字，必须在正文里以口语句子再出现一次。
4. **幽默来自具体场景，不来自网络梗。** 允许"凌晨三点你第三次把宝宝放回婴儿床""和你的闹钟谈判"这类画面感和自嘲；不允许流行语堆砌。涉及医疗、法律、儿童保护的段落**不搞笑**，只把语气放软。
5. **全站可听。** 底部播放条把正文切成短句连读，读完自动跳下一页，锁屏继续，每页标"本页约 X 分钟"——科普站的真实使用场景是通勤，不是书桌。
6. **不诊断、不荐药、给出口。** 剂量一律写"遵医嘱或说明书"，每页结尾保留免责声明与"什么时候该去医院"；VitePress 默认在带侧边栏的页面隐藏页脚，科普站必须覆盖成显示（`style.css` 里 `.VPFooter.has-sidebar { display: block !important }`）。

   这条的领域替身：**讲钱的站换成"不承诺收益、不荐项目不带货、给出口"**（免责声明 + "这事要找执业律师/会计师/当地人社局"），讲法律的站换成"不给操作指引、不预测个案结果、给出口"。结构不变，只是把"医院"换成那个领域里真正能接住读者的地方。

另外两条踩过的坑，写在这里省得下一代站点重犯：

- `themeConfig.footer.message` 会被渲染进 `<p class="message">`，**里面不能放块级元素**（`<div>` 会让浏览器自动断段，SSR 与客户端首帧必然不一致，全站每页报 hydration mismatch）。品牌块用 `span` + `display:flex`。
- 依赖 `document` / `localStorage` / 正文 DOM 的组件（播放条就是典型）**要等挂载后再渲染**：SSR 阶段扫不到正文，输出必然和客户端不一致。用 `mounted` ref + `nextTick` 让它只在客户端出现。

---

## 十、资产清单与出处

| 类别 | 文件 |
| --- | --- |
| 设计 Token 与全站样式 | [docs/.vitepress/theme/style.css](file:///D:/yuxinrun/mcp-patterns/docs/.vitepress/theme/style.css)（1378 行，单一真相源） |
| 主题入口与 slot/组件注册 | [docs/.vitepress/theme/index.ts](file:///D:/yuxinrun/mcp-patterns/docs/.vitepress/theme/index.ts) |
| IA：导航 / 侧栏 / i18n / 搜索 / 页脚 / 404 | [docs/.vitepress/config.mts](file:///D:/yuxinrun/mcp-patterns/docs/.vitepress/config.mts) |
| 首页版式（8 段式样板） | [docs/index.md](file:///D:/yuxinrun/mcp-patterns/docs/index.md) |
| 品牌资产 | [docs/public/](file:///D:/yuxinrun/mcp-patterns/docs/public)：`logo.svg`、`logo-dark.svg`、`favicon.svg`、`yuxin-run.png` |
| 组件 | `docs/.vitepress/theme/components/`：`BrandMark` `HeroDiagram` `McpArch` `RatingBars` `SpecTimeline` `AuthFlow` |
| 品牌自述（含设计语言声明） | [docs/about.md](file:///D:/yuxinrun/mcp-patterns/docs/about.md) |
| 部署 | [.github/workflows/deploy.yml](file:///D:/yuxinrun/mcp-patterns/.github/workflows/deploy.yml) → GitHub Pages，仓库名前缀用 `BASE=/mcp-patterns/` |

一句话概括这套设计：**用暖白纸面与深海墨绿做底，用青色做唯一的声音、珊瑚红做风险的提醒；大标题靠可变字重与负字距撑住气势，所有元信息交给等宽大写小字；层级靠照度与虚线而不是靠粗边框；代码块永远是深色的，因为代码比装饰重要。**
