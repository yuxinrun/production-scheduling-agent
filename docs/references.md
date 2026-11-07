---
title: 参考资料
description: 本手册引用的教科书、经典论文、公开算例库、求解器文档与行业报告的完整清单，附「哪些数字经过核实、哪些口径存在冲突」的诚实标注。
---

# 参考资料

这一页列本手册所有结论的出处，按「你该从哪里读起」排序。
两条诚实声明先放在最前面：

1. **案例数字的口径冲突没有被抹平。** 规则条数一处写 68 条、另一处数出来 56 条；
   约束总数一处写 137 条、按可数条目累加是 132 条。两份口径在对应页面都保留并标注，
   因为「同一个指标三套数」本身就是排产项目的头号坑（见[首页第九节](/)）。
2. **行业数字凡未能核实的照写不误并注明。** 转载数据（如 IDC、智研咨询的口径差异）会同时给出两个数。

---

## 一、教科书与综述（从这里读起）

- **Pinedo, M. L.**, *Scheduling: Theory, Algorithms, and Systems*（Springer）。
  排产领域的标准教材：三字段记号 `α|β|γ`、单机最优规则、车间调度复杂度总表都从这里查。
- **Garey, M. R. & Johnson, D. S.**, *Computers and Intractability*（Freeman, 1979）。
  NP-completeness 的「圣经」；作业车间强 NP-hard 的出处链从这走。
- **Baptiste, P., Le Pape, C., Nuijten, W.**, *Constraint-Based Scheduling*（Kluwer, 2001）。
  约束排产的奠基书：edge-finding、timetable 传播器、`no_overlap` 的全部理论依据。
- **Fisher, M. L.**, "The Lagrangian Relaxation Method for Solving Integer Programming Problems",
  *Management Science*, 27(1), 1981。拉格朗日松弛的工程化经典综述。
- **Graham, R. L.** 等， "Optimization and Approximation in Deterministic Sequencing and Scheduling:
  A Survey", *Annals of Discrete Mathematics*, 1979。近似比分析的起点（也是 Graham 记号的出处）。

## 二、公开算例库

- **Taillard 算例集**：`ta01`–`ta100`，作业车间与流水车间的标准基准，含已知最好解与下界。
- **Lawrence 算例集**：`la01`–`la40`；**Adams 算例集**：`abz5`–`abz9`（`abz8` 的最好上界 665、
  最好下界 645 的 3% 雾就是本页提到的那个，从 1988 年飘到今天）。
- **OR-Library**（J. E. Beasley 维护）：上面所有算例的历史总入口。
- **PSPLIB**：RCPSP（资源受限项目调度）的标准算例库，多项目/广义约束场景用。

## 三、求解器与工具文档

- **Google OR-Tools**：CP-SAT 的官方文档与参考手册（Apache-2.0）。`no_overlap`、`cumulative`、
  求解参数（`max_time_in_seconds`、`num_search_workers`）的正确用法以官方文档为准。
- **HiGHS**（MIT）：纯 LP/MIP 的开源底座。
- **SCIP**（8.0.3 起 Apache-2.0）：混合整数与约束整数规划。
- **Gurobi**：商业 MILP 标杆，许可按核数计费。
- **杉数 COPT**：国产商业求解器，信创/军工合规场景的候选（见[选型表](/tools/stack)）。
- **Timefold Solver**（Apache-2.0）：OptaPlanner 的后继，Java 生态的领域模型参考。
- **Model Context Protocol（MCP）**：工具面协议规范；`readOnlyHint` 等注解的语义以协议文档为准。

## 四、行业报告与公开报道（转载数据，口径未逐一核实）

- **IDC**：中国 APS 软件市场跟踪报告——2025 年收入约 27.3 亿元、同比 +21.8%（经第三方转载；
  另一口径为 2024 年 25.11 亿元、+23.45%，出自智研咨询。两个口径并存，本站不裁决）。
- **中国信通院**《制造业数字化转型发展报告(2025)》：规上工业企业数字化改造比例 89.6%。
- **八部门**《「人工智能+制造」专项行动实施意见》：2027 年打造 1000 个高水平工业智能体。
- **工信部**《智能制造典型场景参考指引（2025 年版）》：40 个场景，含「车间智能排产」「生产动态调度」。
- **华为天筹（OptVerse）公开案例**：中铝瑞闽冷轧排产，1500 订单 × 10 余工序 × 40+ 组辊组炉组刀规则，
  按时交货率 94.1% → 98%+（厂商口径）。
- **联友科技公开观点**：「单靠大模型排产是幻觉——必须 LLM 交互 + 求解器寻优 + 规则引擎校验分层」。

## 五、案例材料（已脱敏）

实战案例各页（[客户与现场](/case/background) 起的九页）引用的项目材料——调研现状报告、
业务管理模式设计方案、问题提炼与目标对齐清单、排产规则提取清单、技术能力点检清单、
需求分析与技术栈方案——**来自一个已脱敏的航空发动机厂排产项目**（客户与咨询方名称均已匿名化）。
原始文档不随本仓库分发，页面上用到的数字已全部内联，
并由仓库里 [`/snippets/`](/snippets/) 的脚本离线复算（每个案例页开头都标了对应脚本）。

## 六、本站的实测脚本

所有「实测数字」的完整脚本在 [`/snippets/`](/snippets/)，纯标准库为主（个别页需要 `ortools`）：

| 脚本 | 支撑的页面 |
| --- | --- |
| `code_probe.py` | [代码：从贪心到 CP-SAT 到 Agent](/build/code) |
| `perf_probe.py` | [性能：万级变量与秒级重排](/build/perf) |
| `bounds_demo.py` | [下界与间隙](/problem/bounds) |
| `lisa_totals.py` / `pain_matrix.py` / `rules_check.py` | [案例](/case/background)各页的总数复算 |
| `data_gate.py` / `checklist_probe.py` | [数据四区间与五维门禁](/case/data)、[投产配置清单](/case/checklist) |
| `mcp_catalog.py` / `guardrail_probe.py` / `audit_chain.py` | [MCP](/arch/mcp)、[护栏](/arch/guardrail)、[审计链](/arch/audit) |

换机器会变的只有 `us/ms` 级耗时与 CP-SAT 的墙钟；变量数、组合数、可行性结论与 stdout 的结构不会变。
