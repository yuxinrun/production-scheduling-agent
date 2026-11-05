"""把本体方案里的 HC-01 / 03 / 08 / 12 / 14 五条护栏写成可执行形状，
在四个排产方案上跑一遍（纯标准库，无 RDF/SHACL 依赖）。

用法:  python ontology_guardrails.py
数据:  类与必备属性取自《本体结构构建方案细化》表 1；HC 条目取自同文表 4。
       四个方案实例是本页编的最小例，每个埋一种违例。
"""
from collections import defaultdict

# ---- 表 1：核心类的必备属性（HC-01「概念完备性」的 mandatory 清单）----
MANDATORY = {
    "Order": ["订单号", "产品", "数量", "交期", "优先级", "军品属性"],
    "Part": ["图号", "材质", "批次", "关重件标识"],
    "Operation": ["工序号", "工时", "前后约束", "外委标识"],
    "Resource": ["能力矩阵", "日历", "状态", "技能等级"],
    "Constraint": ["约束类型", "强度", "作用域", "违约代价"],
    "Disturbance": ["类型", "级别", "发生时刻", "影响范围"],
    "Plan": ["版本", "指标", "冻结窗口", "状态"],
}
# ---- HC-03：枚举字段的值域（方案里声明的三组枚举）----
ENUM = {"军品属性": {"是", "否"}, "交期刚性": {"硬", "软", "弹性"}}

CALENDAR = [("M1", 0, 12), ("M1", 16, 24)]      # 资源日历可用区间；12—16 是维护窗


def available(res, s, e):
    return any(r == res and s >= lo and e <= hi for r, lo, hi in CALENDAR)


def closure(prec):
    """precedes 声明为传递属性：把传递闭包算出来。有环时闭包里会出现 a→a。"""
    adj = defaultdict(set)
    for a, b in prec:
        adj[a].add(b)
    nodes = set(adj) | {b for bs in adj.values() for b in bs}
    reach = {n: set(adj[n]) for n in nodes}
    changed = True
    while changed:                       # Warshall 风格不动点迭代
        changed = False
        for n in nodes:
            for m in list(reach[n]):
                add = reach[m] - reach[n]
                if add:
                    reach[n] |= add
                    changed = True
    return reach


ORDER = {"订单号": "MO-2026-0417", "产品": "某型涡轮盘", "数量": 30,
         "交期": "2026-11-20", "优先级": 8.5, "军品属性": "是", "交期刚性": "硬"}

PLANS = {
    "方案 A": {
        "Order": dict(ORDER),
        "ops": [("OP1", "M1", 0, 5), ("OP2", "M1", 5, 9)],
        "precedes": [("OP1", "OP2"), ("OP2", "OP3")],
        "数量": {"订单": 30, "报工": 30, "交付": 28, "报废": 2},
        "Plan": {"版本": "v12", "指标": {"makespan": 9}, "冻结窗口": "T-24h", "状态": "待审批"}},
    "方案 B": {                                   # 指派落在维护窗内 → HC-08
        "Order": dict(ORDER),
        "ops": [("OP1", "M1", 13, 18)],
        "precedes": [("OP1", "OP2"), ("OP2", "OP3")],
        "数量": {"订单": 30, "报工": 30, "交付": 28, "报废": 2},
        "Plan": {"版本": "v12", "指标": {"makespan": 18}, "冻结窗口": "T-24h", "状态": "待审批"}},
    "方案 C": {                                   # 先序关系成环 → HC-12
        "Order": dict(ORDER),
        "ops": [("OP1", "M1", 0, 5), ("OP2", "M1", 5, 9)],
        "precedes": [("OP1", "OP2"), ("OP2", "OP3"), ("OP3", "OP1")],
        "数量": {"订单": 30, "报工": 30, "交付": 28, "报废": 2},
        "Plan": {"版本": "v13", "指标": {"makespan": 9}, "冻结窗口": "T-24h", "状态": "待审批"}},
    "方案 D": {                                   # 枚举越界 + 缺字段 + 数量不守恒
        "Order": {**ORDER, "军品属性": "待定", "交期刚性": "很硬"},
        "ops": [("OP1", "M1", 0, 5)],
        "precedes": [("OP1", "OP2")],
        "数量": {"订单": 30, "报工": 26, "交付": 24, "报废": 3},
        "Plan": {"版本": "v13", "指标": {"makespan": 5}, "状态": "待审批"}},
}


def validate(plan):
    v = []
    # HC-01 概念完备性：实例挂载到有效类，且该类必备属性非空
    for cls in ("Order", "Plan"):
        for f in MANDATORY[cls]:
            if f not in plan[cls]:
                v.append(("HC-01", f"{cls}/{plan['Plan']['版本']}", f, "缺失"))
    # HC-03 值域约束：枚举字段取值落在定义值域内
    for f, allowed in ENUM.items():
        val = plan["Order"].get(f)
        if val is not None and val not in allowed:
            v.append(("HC-03", "Order/" + str(plan["Order"]["订单号"]), f, f"{val} ∉ {sorted(allowed)}"))
    # HC-08 日历边界：排产指派时刻落在资源日历可用区间内
    for op, res, s, e in plan["ops"]:
        if not available(res, s, e):
            v.append(("HC-08", op, f"{res}[{s},{e}]", "不在日历可用区间"))
    # HC-12 工序依赖闭环：先序关系无环
    for n, rs in sorted(closure(plan["precedes"]).items()):
        if n in rs:
            v.append(("HC-12", n, "precedes+", f"{n} 可达自身（成环）"))
    # HC-14 数量平衡：订单 = 交付 + 报废 + 报工未结 + 未报工在制，四项都不得为负
    q = plan["数量"]
    unsettled = q["报工"] - q["交付"] - q["报废"]        # 已报工但既没交付也没判废
    wip = q["订单"] - q["报工"]                          # 还没报工的部分
    detail = f"交付{q['交付']} + 报废{q['报废']} + 报工未结{unsettled} + 在制{wip}"
    if unsettled < 0:
        v.append(("HC-14", "Order/数量", "报工 ≥ 交付+报废",
                  f"报工{q['报工']} < 交付{q['交付']}+报废{q['报废']}={q['交付'] + q['报废']}，差 {-unsettled} 件"))
    if wip < 0:
        v.append(("HC-14", "Order/数量", "订单 ≥ 报工", f"报工{q['报工']} 超过订单{q['订单']}"))
    if q["订单"] != q["交付"] + q["报废"] + unsettled + wip:
        v.append(("HC-14", "Order/数量", "守恒", f"订单{q['订单']} ≠ {detail}"))
    return v


print(f"7 个核心类的必备属性合计 = {sum(len(v) for v in MANDATORY.values())} 条 mandatory 断言")
print(f"资源日历 = {CALENDAR}（12—16 为维护窗）")
print()
print("四个方案过护栏：SHACL 风格报告")
for name, plan in PLANS.items():
    v = validate(plan)
    print(f"\n{name}  conforms = {not v}")
    for c, focus, path, msg in v:
        assert c.startswith("HC-") and msg, (c, msg)
        print(f"    {c:<7} focusNode={focus:<22} path={path:<12} {msg}")
    if not v:
        print("    （无违例，可以进入排产链路）")

print("\nHC-12 单独看：传递属性的闭包展开")
for name in ("方案 A", "方案 C"):
    reach = closure(PLANS[name]["precedes"])
    print(f"  {name}: " + "   ".join(f"{n}→+{sorted(reach[n])}" for n in sorted(reach)))

print("\n开放世界陷阱：如果 Operation 实例只写了 {工序号, 工时}，没写「外委标识」呢？")
partial = {"工序号": "OP7", "工时": 3}
miss = [f for f in MANDATORY["Operation"] if f not in partial]
print(f"  缺失的必备属性 = {miss}")
print("  OWL 推理机：不报。OWA 下「没人说」不等于「假」，可能只是数据没录。")
print("  SHACL 形状：报。mandatory 缺失 = validation result，按 HC-01 禁止入库。")
print("\n同一条缺失，两套语义给出相反结论——这就是 HC-01~14 要 SHACL 化、不能只靠 OWL 的原因。")
