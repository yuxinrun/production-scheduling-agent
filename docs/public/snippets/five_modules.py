from dataclasses import dataclass
from datetime import datetime
import hashlib
import json


@dataclass
class Trace:
    agent: str
    stage: str
    payload: dict
    parent: str | None = None

    def to_log(self) -> dict:
        h = hashlib.sha256(json.dumps(self.payload, sort_keys=True, default=str).encode())
        return {"ts": datetime.now().isoformat(timespec="seconds"),
                "agent": self.agent, "stage": self.stage,
                "digest": h.hexdigest()[:12], "parent": self.parent,
                "payload": self.payload}


def in_window(plan):
    b = plan["ops"][0]
    return b["start"] + b["dur"] <= b["end"], "工序落在资源可用窗之外"


GUARDRAILS = [
    lambda plan: (len(plan["violations"]) == 0, "HC 硬约束必须为 0 违反"),
    lambda plan: (plan["horizon"] <= 7 * 24, "排产窗口不得超过一个冻结周期"),
    in_window,
]


def run(agent: str, order: dict, tools: dict, approvals: list) -> dict:
    """五大模块 + 执行控制的最小骨架。每一段都产出一条可重放的 trace。"""
    t, prev = [], None

    def emit(stage, payload):
        nonlocal prev
        e = Trace(agent, stage, payload, parent=prev).to_log()
        prev = e["digest"]
        t.append(e)

    # 1 感知：只经工具面取数，不拼 SQL、不读对话历史
    obs = {name: fn(order) for name, fn in tools.items()}
    emit("perceive", {"tools": list(obs), "obs": obs})

    # 2 记忆：结构化事实 + 来源，不是文本
    mem = [{"fact": "上月同型件换型 3 次/日", "source": "ZD-05/设备实绩", "confidence": 0.81}]
    emit("recall", {"used": mem})

    # 3 推理：ReAct 链，thought 只用于解释，不用于算数
    w0, w1 = obs["resource_calendar"]["free_window"]
    thought = f"{order['op']} 尝试排入 {obs['resource_calendar']['machine']} 的窗口 {w0}-{w1}"
    emit("reason", {"thought": thought})

    # 4 规划：产出「可校验对象」，不是自然语言
    plan = {"ops": [{"op": order["op"], "res": obs["resource_calendar"]["machine"],
                     "start": w0, "dur": order["p"], "end": w1}],
            "horizon": 72, "violations": []}
    for check in GUARDRAILS:
        ok, why = check(plan)
        if not ok:
            plan["violations"].append(why)
    emit("plan", {"plan": plan, "guardrails": len(GUARDRAILS)})

    # 5 决策：只出建议，A/B/C 三案 + 影响面；不选
    proposals = [{"id": "A", "value": plan}, {"id": "B", "value": None}, {"id": "C", "value": None}]
    emit("decide", {"proposals": [x["id"] for x in proposals], "auto_approved": False})

    # 6 执行控制：写之前查审批表；查不到就拦截
    approved = any(a["plan_id"] == "A" for a in approvals)
    action = "write" if approved else "blocked"
    emit("execute", {"action": action, "reason": None if approved else "无电子签名"})
    return {"plan": plan, "action": action, "trace": t}


tools = {"resource_calendar": lambda o: {"machine": "M-1103", "free_window": (8, 20)},
         "wip_status": lambda o: {"qty": 12}}
for p, label in [(6, "窗口内"), (20, "窗口外")]:
    r = run("A-02", {"op": "OP-30", "p": p}, tools, approvals=[])
    print(f"{label}: action={r['action']}  violations={r['plan']['violations']}")
    print("   stages:", [x["stage"] for x in r["trace"]])

ok = run("A-02", {"op": "OP-30", "p": 6}, tools,
         approvals=[{"plan_id": "A", "who": "张某某", "sign": "e0f3"}])
print("有签名时:", ok["action"])
print("最后一条 trace:", json.dumps(r["trace"][-1], ensure_ascii=False))
