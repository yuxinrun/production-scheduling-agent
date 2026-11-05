"""审计链挡不挡得住三种攻击：改一条、删一条、整条重算。再加一问：所谓「可回放」到底能不能回放。

用法:  python audit_chain.py
对照的验收基准（《黎阳智能排产智能体技术能力点检清单 V1.0》原文）:
  #49 审计    全链路审计留痕（操作/调用/审批/数据版本审计）。
              验收基准：审计覆盖率100%（含模型调用/工具调用/审批/写入），留存期限达标。
              Harness 要求：审计日志防篡改。OpenTrek 状态：部分满足（防篡改与密级留痕需按保密要求加固）
  #53 解释    白盒化解释。验收基准：方案调整100%附带归因说明
  #21 写保护  验收基准：未审批写入拦截率100%，熔断日志完整
  #41 降级    算法超时熔断 15 秒

链的构造照《投产配置清单》E5：库内 SHA-256 前序哈希链 + 库外 HMAC-SHA256 锚点链，两条链互为反证。
纯标准库。
"""
import hashlib
import hmac
import json
import random
import threading
import time

# ===================== 最小的一套审计原语 =====================
GENESIS = "0" * 64
REQUIRED_KINDS = ("model_call", "tool_call", "approval", "write")   # #49 括号里点名的四类


def canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def ev_hash(e):
    body = {k: v for k, v in e.items() if k != "hash"}
    return hashlib.sha256(canon(body).encode("utf-8")).hexdigest()


def cover(entries, renumber=True):
    """从头把 prev / hash 重算一遍。renumber=False 时保留原来的 seq。
       诚实系统用它做追加；攻击者用它抹平痕迹——差别只在攻击者会重算。"""
    chain, prev = [], GENESIS
    for i, e in enumerate(entries):
        e = dict(e)
        e["prev"] = prev
        if renumber:
            e["seq"] = i + 1
        e["hash"] = ev_hash(e)
        prev = e["hash"]
        chain.append(e)
    return chain


def build(events):
    """正常入链：seq 由入链顺序决定，谁也别想改已经落盘的条目。"""
    return cover(events, renumber=True)


rehash = cover


def verify(chain):
    """内部自洽校验。返回 (第一个失配的 seq, 失配条数)，全对则 (None, 0)。"""
    bad = []
    prev = GENESIS
    for e in chain:
        if e.get("prev") != prev or ev_hash(e) != e.get("hash"):
            bad.append(e["seq"])
        prev = e["hash"]
    return (bad[0] if bad else None), len(bad)


def seq_gap(chain):
    return sum(1 for i, e in enumerate(chain) if e["seq"] != i + 1)


def make_anchor(chain, secret):
    """把链尾指纹 + 条数签进一个 LISA 写不了的落点（WORM / 日志平台 / 另一台主机）。"""
    payload = canon({"head": chain[-1]["hash"], "n": len(chain), "first": chain[0]["hash"]})
    return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def check_anchor(chain, recorded, secret):
    return make_anchor(chain, secret) == recorded


# ===================== 一段真实形状的排产决策 =====================
def session_events():
    return [
        {"kind": "solve", "actor": "solver", "tool": "mip", "note": "MIP 超 15s，带界降级",
         "degraded": "D1", "bound": 139, "makespan": 155, "ev": 20000},
        {"kind": "tool_call", "actor": "agent-A", "tool": "get_production_orders", "ms": 41},
        {"kind": "model_call", "actor": "llm", "tool": "qwen-intranet", "ms": 2310, "focusNode": "W-3"},
        {"kind": "tool_call", "actor": "agent-A", "tool": "get_routing", "ms": 27},
        {"kind": "model_call", "actor": "llm", "tool": "qwen-intranet", "ms": 1874, "focusNode": "W-3"},
        {"kind": "plan_adjust", "actor": "agent-A", "planBatchId": "PB-01",
         "change": "工序 12.0 从 M2 挪到 M4", "attribution": "M2 负载 136 是瓶颈"},
        {"kind": "approval", "actor": "planner", "planBatchId": "PB-01",
         "ticket": "tk-1-a3f1c9", "decision": "agree"},
        {"kind": "write", "actor": "shield", "tool": "write_aps_plan", "planBatchId": "PB-01",
         "writtenDetailRows": 105},
        {"kind": "tool_call", "actor": "agent-A", "tool": "get_dispatch_status", "ms": 33},
        {"kind": "plan_adjust", "actor": "agent-A", "planBatchId": "PB-02",
         "change": "急单插 3 道工序", "attribution": "急单走空闲 M3，不动冻结窗口"},
        {"kind": "approval", "actor": "planner", "planBatchId": "PB-02",
         "ticket": "tk-2-77bd10", "decision": "agree"},
        {"kind": "write", "actor": "shield", "tool": "write_aps_plan", "planBatchId": "PB-02",
         "writtenDetailRows": 8},
    ]


t0 = time.perf_counter()
chain = build(session_events())
tail = chain[-1]["hash"]
first, nbad = verify(chain)
kinds = {k: sum(1 for e in chain if e["kind"] == k) for k in REQUIRED_KINDS}
print("=" * 74)
print("[1] 一条 12 事件的决策链（#49 点名的四类事件都在）")
print(f"    建链耗时 {(time.perf_counter() - t0) * 1000:.3f} ms，链尾哈希 {tail[:16]}…，verify → 失配 {nbad} 条")
print(f"    四类事件条数 = {kinds}")
print("    第 1 条 solve 带 degraded=D1、bound=139、ev=20000。降级标记进链不是为了好看：")
print("    #41 说「降级演练通过」，演练的证据只能是这样一条带界带计数器的记录。")

SECRET = b"DUMMY-not-from-env"          # 真系统只从 LISA_ANCHOR_SECRET 读，值永不落库、永不进日志
anchored = make_anchor(chain, SECRET)
print(f"    外部锚点（HMAC-SHA256 over 链尾+条数+链头）= {anchored[:16]}…")

# ===================== [2] 五种攻击 =====================
print("\n" + "=" * 74)
print("[2] 五种攻击 × 三种防线。√ = 检出，× = 蒙混过关")
rows = []


def attack(name, mutated, seq_defense=True, secret=SECRET, anchor=anchored):
    f1, n1 = verify(mutated)
    g = seq_gap(mutated)
    a_bad = not check_anchor(mutated, anchor, secret)
    d_chain = "√" if f1 else "×"
    d_seq = ("√" if g else "×") if seq_defense else "不适用"
    d_anchor = "√" if a_bad else "×"
    print(f"  {name}")
    print(f"      内部自洽校验 → {'失配从第 ' + str(f1) + ' 条起，共 ' + str(n1) + ' 条' if f1 else '全部通过（链看起来是好的）'}：{d_chain}")
    print(f"      序号连续性检查 → {'缺口 ' + str(g) + ' 处' if g else '无缺口'}：{d_seq}")
    print(f"      外部锚点比对   → {'链尾/条数与锚点不符' if a_bad else '锚点仍然吻合'}：{d_anchor}")
    print(f"      结论：{'这条攻击会被发现' if '√' in (d_chain, d_seq, d_anchor) else '这条攻击在当前配置下无人可见'}")
    rows.append((name.split()[0], d_chain, d_seq, d_anchor))


c = [dict(e) for e in chain]
for e in c:
    if e["seq"] == 8:
        e["writtenDetailRows"] = 10500
attack("A1 改一条：第 8 条 write 的 writtenDetailRows 105 → 10500（哈希没动）", c)

c2 = [dict(e) for e in c]
attack("A2 改一条 + 从第 8 条起重算后面所有哈希（等价于整条重算，前 7 条结果不变）", rehash(c2))

c3 = [dict(e) for e in chain if e["seq"] != 7]
attack("A3 删一条：把第 7 条 approval 整条删掉，只重算第 8 条往后的 prev/hash（seq 不动）",
       cover(c3, renumber=False))

c4 = [dict(e) for e in c3]
attack("A4 = A3，但攻击者连 seq 一起重排成 1..11（上面那次重算多加一个参数而已）",
       cover(c4, renumber=True))

print("  A5 = A4，而且锚点文件也在他能写的盘上、密钥也在同一份 .env 里")
fake = cover(c4, renumber=True)
new_anchor = make_anchor(fake, SECRET)
print(f"      外部锚点比对 → 原锚点失配 √，但他自己签了一个新锚点 {new_anchor[:16]}…，之后校验通过：×")
print("      ⇒ 这就是 E5 要「一个只追加、LISA 写不了的落点 + 密钥单独交付」的全部理由。")
print("        锚点跟链放同一块可写盘 = 没有锚点；没有密钥时锚定一律被拒（ANCHOR_SECRET_MISSING），")
print("        宁可没锚点，也不写一个谁都能重算的假锚点。拷贝周期就是攻击窗口（清单建议 ≤ 一个工作日）。")

det = lambda i: sum(1 for r in rows if r[i] == "√")
union = sum(1 for r in rows if "√" in r[1:])
print(f"\n  A1~A4 四种攻击的检出数：内部自洽校验 {det(1)}/4、序号连续性 {det(2)}/4、外部锚点 {det(3)}/4，"
      f"三条防线合起来 {union}/4")
print("  没有任何一条单独防线能到 4/4——A1（改一条不动哈希）只有内部校验看得见，")
print("  因为锚点签的是链尾指纹，中间某条被改而链尾没变时，锚点完全无感。")
print("  这就是《投产配置清单》E5 那句「两条链互为反证」的字面意思：不是冗余，是覆盖面。")
print("  A5（拿到密钥 + 能写锚点）任何内部机制都看不见，只能靠「LISA 写不了的落点」这个物理前提。")

# ===================== [3] #49 的「审计覆盖率 100%」 =====================
print("\n" + "=" * 74)
print("[3] #49：审计覆盖率 100%（含模型调用/工具调用/审批/写入）")
loose_events = [e for e in session_events() if e["kind"] not in ("model_call", "approval")]
loose = build(loose_events)
f_l, n_l = verify(loose)
kinds_loose = {k for k in REQUIRED_KINDS if any(e["kind"] == k for e in loose)}
print(f"    只在「调了工具」和「写了 MES」时打日志，模型调用与审批不打：")
print(f"    链长 {len(loose)} 条，内部自洽校验 → 失配 {n_l} 条；覆盖率 = {len(kinds_loose)}/{len(REQUIRED_KINDS)}")
print(f"    序号连续性 → 缺口 {seq_gap(loose)} 处（1..{len(loose)} 连续，也查不出来）")
print(f"    ⇒ 哈希链对「少记了两类事件」完全无感。防篡改和防漏记是两个东西，")
print(f"       #49 的验收基准里那半句「覆盖率 100%」不是哈希链能给的。")
print(f"    可实现的版本只有两条，都得自己写：")
print(f"      ① 覆盖率当闸门：四类不齐就不许关闭这段会话（拒绝收尾，不是事后统计）；")
print(f"      ② 跟外部事实对账：链里 write 事件 {sum(1 for e in chain if e['kind'] == 'write')} 条，")
print(f"         MES 侧 dispatchNo 去重后必须同数。对不上就是漏记，跟哈希一点关系都没有。")

# ===================== [4] #53：方案调整 100% 附带归因说明 =====================
print("\n" + "=" * 74)
print("[4] #53：方案调整 100% 附带归因说明 —— 同一批调整记录，两种实现")
rng = random.Random(5)
reasons = ["M2 负载 136 是瓶颈", "急单走空闲 M3", "换型成本省 2 小时", "冻结窗口外唯一可行槽位",
           "工装可用时刻 118", "热处理拼炉省 1 炉"]
drafts = []
for i in range(10):
    e = {"kind": "plan_adjust", "actor": "agent-A", "planBatchId": f"PB-{i + 1:02d}",
         "change": f"调整第 {i + 1} 版方案"}
    if rng.random() < 0.6:                       # 每条独立有六成概率把归因写全
        e["attribution"] = reasons[i % len(reasons)]
    drafts.append(e)
missing = sum(1 for e in drafts if "attribution" not in e)

t0 = time.perf_counter()
sloppy = build(drafts)
cov_sloppy = sum(1 for e in sloppy if e.get("attribution")) / len(sloppy)
t_slip = time.perf_counter() - t0

t0 = time.perf_counter()
strict_in, rejected = [], 0
for e in drafts:
    if "attribution" not in e:
        rejected += 1                             # 闸门拒收，补齐再提交
        e = dict(e, attribution="(补齐：由 focusNode 与机器负载差分回填)")
    strict_in.append(e)
strict = build(strict_in)
cov_strict = sum(1 for e in strict if e.get("attribution")) / len(strict)
t_strict = time.perf_counter() - t0

print(f"    10 条调整里 {missing} 条没带归因（模型输出不完整，这是常态）")
print(f"    实现①「先入链，报表里再统计覆盖率」：入链 {len(sloppy)} 条，"
      f"归因覆盖率 {cov_sloppy * 100:.0f}%，耗时 {t_slip * 1000:.2f} ms")
print(f"       → 差口 {(cov_strict - cov_sloppy) * 100:.0f} 个百分点，而且事后补救不了：链不许改，改了 verify 就红。")
print(f"    实现②「缺归因就拒收，补齐才入链」：入链 {len(strict)} 条，拒收 {rejected} 次，"
      f"归因覆盖率 {cov_strict * 100:.0f}%，耗时 {t_strict * 1000:.2f} ms")
print(f"    代价不在时间上（两次都是 0.1x ms），在 {rejected} 次拒收重提，和一条「归因必填」的 schema 约束。")
print(f"    「100%」不是统计目标，是入链前的一个必填校验。#21 那句「熔断日志完整」同理。")

# ===================== [5] 回放：审计链的最后一公里 =====================
print("\n" + "=" * 74)
print("[5] 可回放：同一份输入 + 同一个种子，能不能重算出同一版方案？")


def make_eval(jobs):
    m = max(k for j in jobs for k, _ in j) + 1
    ops_of = {k: [] for k in range(m)}
    dur = {}
    for i, j in enumerate(jobs):
        for o, (k, p) in enumerate(j):
            ops_of[k].append((i, o))
            dur[(i, o)] = p
    return m, ops_of, dur


def starts(dur, order, jobs):
    nxt, indeg = {}, {n: 0 for n in dur}
    for seq in order.values():
        for a, b in zip(seq, seq[1:]):
            nxt.setdefault(a, []).append(b)
            indeg[b] += 1
    for i, j in enumerate(jobs):
        for o in range(len(j) - 1):
            nxt.setdefault((i, o), []).append((i, o + 1))
            indeg[(i, o + 1)] += 1
    st = {n: 0 for n in dur}
    ready = [n for n in dur if indeg[n] == 0]
    done = 0
    while ready:
        n = ready.pop()
        done += 1
        for c in nxt.get(n, []):
            if st[c] < st[n] + dur[n]:
                st[c] = st[n] + dur[n]
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
    return None if done < len(dur) else st


class Eval:
    def __init__(self, jobs, dur):
        self.jobs, self.dur, self.n = jobs, dur, 0

    def __call__(self, order):
        self.n += 1
        st = starts(self.dur, order, self.jobs)
        return None if st is None else max(s + self.dur[x] for x, s in st.items())


def dispatch(jobs, dur, key):
    m = make_eval(jobs)[0]
    n = len(jobs)
    ptr, mfree, jfree = [0] * n, [0.0] * m, [0.0] * n
    order = {k: [] for k in range(m)}
    while sum(ptr) < sum(len(j) for j in jobs):
        cand = []
        for i in range(n):
            if ptr[i] < len(jobs[i]):
                k, p = jobs[i][ptr[i]]
                cand.append((max(jfree[i], mfree[k]), p, i, k))
        ranked = [(key(*c), c) for c in cand]
        best = min(r for r, _ in ranked)
        _, _, i, k = random.choice([c for r, c in ranked if r == best])
        p = jobs[i][ptr[i]][1]
        s = max(jfree[i], mfree[k])
        jfree[i] = mfree[k] = s + p
        order[k].append((i, ptr[i]))
        ptr[i] += 1
    return order


def local_search(jobs, budget=10 ** 9, seed=0, deadline=None):
    m, ops_of, dur = make_eval(jobs)
    t_end = None if deadline is None else time.perf_counter() + deadline
    random.seed(seed)
    ev = Eval(jobs, dur)

    def spent():
        return ev.n >= budget or (t_end is not None and time.perf_counter() >= t_end)

    def climb(order, cur):
        improved = True
        while improved and not spent():
            improved = False
            for k in range(m):
                seq = order[k]
                for a in range(len(seq) - 1):
                    if spent():
                        return cur
                    seq[a], seq[a + 1] = seq[a + 1], seq[a]
                    v = ev(order)
                    if v is not None and (cur is None or v < cur):
                        cur, improved = v, True
                    else:
                        seq[a], seq[a + 1] = seq[a + 1], seq[a]
        return cur

    order = dispatch(jobs, dur, lambda s, p, i, k: (random.random(), i, k))
    best = climb(order, ev(order))
    return best, {k: list(v) for k, v in order.items()}, ev.n


def fingerprint(order, makespan):
    return hashlib.sha256(canon([order, makespan]).encode("utf-8")).hexdigest()[:16]


rng2 = random.Random(9)
BIG = [[(k, rng2.randint(1, 9)) for k in range(5)] for _ in range(20)]
_, ops_of_b, dur_b = make_eval(BIG)
load_b = {k: sum(dur_b[n] for n in ops) for k, ops in ops_of_b.items()}
LB = max(max(load_b.values()), max(sum(p for _, p in j) for j in BIG))

N = 60
h1, o1, e1 = local_search(BIG, budget=300, seed=7)
fps, hs, secs = {fingerprint(o1, h1)}, {h1}, []
for _ in range(N - 1):
    t = time.perf_counter()
    h, o, e = local_search(BIG, budget=300, seed=7)
    secs.append(time.perf_counter() - t)
    fps.add(fingerprint(o, h))
    hs.add(h)
print(f"    算例 = 20 工件 × 5 机器（本机现造，各机器负载 {sorted(load_b.values())} → 平凡下界 LB = {LB}）")
print(f"    起点 = 同一颗种子(7)的随机派工，邻域 = 机器序列相邻交换。回放 {N} 次")
print(f"    按「评估次数 ≤ 300」停：{N} 次 → makespan {len(hs)} 种取值 {sorted(hs)}，"
      f"方案指纹 {len(fps)} 种，单次 {sum(secs) / len(secs) * 1000:.1f} ms")
print(f"    收敛于 makespan {h1}（vs 下界 +{(h1 - LB) / LB * 100:.0f}%），实际用掉 {e1} 次评估，指纹 {fingerprint(o1, h1)}")
print(f"    ⇒ 停止规则只依赖计数器的话，「可回放」是免费的：输入 + 代码版本 + 种子 + 预算 = 同一版方案。")


def burn(sec):
    x = 1.000001
    t_end = time.perf_counter() + sec
    while time.perf_counter() < t_end:
        x *= 1.0000001


DL = 0.012
hs2, fps2, evs2 = set(), set(), []
for _ in range(N):
    h, o, e = local_search(BIG, budget=10 ** 9, seed=7, deadline=DL)
    hs2.add(h)
    fps2.add(fingerprint(o, h))
    evs2.append(e)
print(f"    按「墙钟 ≤ {DL * 1000:.0f} 毫秒」停（#41 那个 15 秒熔断的缩影），空载 {N} 次 → "
      f"makespan {len(hs2)} 种取值 {sorted(hs2)}，方案指纹 {len(fps2)} 种，评估次数落在 {min(evs2)}~{max(evs2)}")

for _ in range(2):
    threading.Thread(target=burn, args=(3.0,), daemon=True).start()
time.sleep(0.2)
hs3, fps3, evs3 = set(), set(), []
for _ in range(40):
    h, o, e = local_search(BIG, budget=10 ** 9, seed=7, deadline=DL)
    hs3.add(h)
    fps3.add(fingerprint(o, h))
    evs3.append(e)
print(f"    同样 {DL * 1000:.0f} 毫秒，但本机另开 2 个满载线程（等价于隔壁那个请求在吃核）：40 次 → "
      f"makespan {len(hs3)} 种取值 {sorted(hs3)}，评估次数落在 {min(evs3)}~{max(evs3)}")
burn(3.0)
print(f"    ⇒ 墙钟截断把「本机此刻的负载」变成了决策的输入。空载和带负载跑出来的方案不是同一版，")
print(f"       而日志里那句「耗时 12ms」完全无法告诉你少了哪几十次评估。")
print(f"       熔断预算一旦进了决策路径，「回放」在数学上就没了：你只能重现当年那次决策的分布，")
print(f"       重现不了它本身。所以审计要记的是 ev / bound / elapsed 三个数，回放时按 ev 截断，")
print(f"       而不是按时间截断——否则 #49 那句「可追溯」只是个形容词。")

h3r, o3r, e3r = local_search(BIG, budget=e1, seed=7)
print(f"    用链里记下的 ev={e1} 回放 → makespan {h3r}，与那条 solve 记录的指纹一致 = "
      f"{fingerprint(o3r, h3r) == fingerprint(o1, h1)}")

# ===================== [6] 时间戳能不能定序 =====================
print("\n" + "=" * 74)
print("[6] 时间：#49 要求留存期限达标，H7 要求客户给 NTP 源。先问时间戳能不能定序")
base = 1_700_000_000_000_000_000
ts_ok = [base + i * 500_000 for i in range(12)]          # 每条间隔 0.5ms
skew = [t if i < 6 else t - 2_000_000 for i, t in enumerate(ts_ok)]   # NTP 回拨 2ms
order_by_time = sorted(range(12), key=lambda i: skew[i])
displaced = sum(1 for i, p in enumerate(order_by_time) if p != i)
print(f"    12 条事件按 0.5ms 间隔打戳，第 7 条起被 NTP 校时回拨 2ms：")
print(f"    按时间戳排序后 {displaced}/12 条落在错误位置上（其中 approval 排到了它批的方案之后）")
print(f"    ⇒ 能定序的只有 seq + prev。时间戳的作用是「对齐业务时刻」（几点几分下发的），")
print(f"       不是「判定因果」。时钟源不可信时，先坏的是归因链而不是报表。")
print(f"    顺带一句 #49 的「留存期限达标」：军工审计通常按年计，链不许改，")
print(f"       但密钥要轮换 —— 轮换后老锚点必须留档，否则三年后的审计页会一片红。")

print("\n" + "=" * 74)
print("一句话：SHA-256 链管「改」，序号管「删」，外部锚点管「整条重算」，")
print("      对账 + 闸门管「漏记」，ev 计数管「回放」。五种机制，缺一个就有一类攻击免费。")
