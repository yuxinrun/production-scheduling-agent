"""MCP 工具目录与分页的上下文成本估算（纯标准库，几秒跑完）。

用法:  python mcp_catalog.py
说明:  工具名、描述、输入参数取自《黎阳智能排产软件 MCP 开发技术方案 V1.0》第 5 章，
       即 4 个 Server / 24 个 Tool 的真实清单；这里只计算它们进入模型上下文后的体积。
       字符数(char count)不等于 token 数——token 取决于分词器，本脚本不做换算。
"""
import json
import math

# (工具名, 所属 Server, 描述, 业务输入参数)
TOOLS = [
    ("get_production_orders", "mes", "按订单号、机型、计划员、计划日期查询 MES 生产订单，为订单齐套判断、优先级排序与排产池筛选提供订单主数据。",
     ["orderNo", "productFamilyName", "planner", "plannedStartFrom", "plannedStartTo"]),
    ("get_order_shortage", "mes", "查询订单组件需求、已领、未清领与缺料数量，支撑齐套检查和缺料原因定位。",
     ["orderNo", "materialNo", "storageLocation"]),
    ("get_container_status", "mes", "查询批次基本状态与当前工序位置，识别在制、暂停、可派工和排产池状态。",
     ["containerName", "orderNo", "workCenterId"]),
    ("get_workflow_steps", "mes", "按工艺路线读取工序顺序、工区、工时与转工/外委周期，为排产计算提供工艺约束。",
     ["workflowId", "processNo", "workflowRevision"]),
    ("get_step_quota", "mes", "读取工序定额工时，支撑产能核算、排产时长计算与瓶颈识别。",
     ["workflowStepId"]),
    ("get_resource_calendar", "mes", "查询设备能力属性、瓶颈/无限能力标识和制造日历，为有限产能排产提供资源约束。",
     ["resourceId", "workCenterId", "year"]),
    ("get_wip_info", "mes", "按订单、零件、批次和工序查询正常/异常在制数量与工时，支撑数据点检和产能核算。",
     ["orderNo", "itemCode", "batch", "operationNo"]),
    ("get_dispatch_status", "mes", "查询批次工序派工计划、开工、完成及报工数量，为执行偏差分析提供状态。",
     ["containerId", "workflowStepId", "dateFrom", "dateTo"]),
    ("write_aps_plan", "mes", "将审核后的排产结果写入 MES 排产计划主表与明细表；该工具为写操作，必须经过人工确认、幂等校验与事务控制。",
     ["planBatchId", "containerId", "workflowId", "apsType", "apsType2", "details", "confirmTicket"]),
    ("get_erp_production_orders", "erp", "读取 SAP 生产订单主数据与订单项目，校验 MES 订单、数量、日期、优先级和批次信息。",
     ["orderNo", "materialNo", "mrpController", "dateFrom", "dateTo"]),
    ("get_material_master", "erp", "查询物料基本视图与工厂视图，统一零件号、物料类型、物料组、单位、计划员等主数据口径。",
     ["materialNo", "plant"]),
    ("get_stock_overview", "erp", "按物料、工厂和库存地点读取非限制、质检、冻结及限制使用库存，支撑齐套与可承诺量判断。",
     ["materialNo", "plant", "storageLocation"]),
    ("get_bom_components", "erp", "读取 BOM 头与组件行，校验订单物料组成、组件数量和单位。",
     ["bomNumber", "alternativeBom"]),
    ("get_order_reservations", "erp", "读取生产订单组件预留、需求数量、已领数量与需求日期，支撑缺料追溯。",
     ["orderNo", "componentMaterialNo", "storageLocation"]),
    ("get_planned_orders", "erp", "读取计划订单号、物料、数量、开始/完成日期、生产版本和机型，支撑计划订单转生产订单前的排产预判。",
     ["plannedOrderNo", "materialNo", "model"]),
    ("get_routing", "erp", "读取 SAP 工艺路线头、工序行与工作中心，校验 MES 工艺工序和工时口径。",
     ["routingGroup", "groupCounter", "plant"]),
    ("get_inspection_records", "qms", "查询检验数量、合格/不合格/报废数量、让步使用数、合格证号与检验完工状态，支撑质量约束校验。",
     ["containerId", "certificateNumber", "checkDateFrom", "checkDateTo"]),
    ("get_check_results", "qms", "按流水卡、子序号和工序查询操作工/检验员实测值，供质量追溯与完工条件判断。",
     ["containerId", "childContainerId", "stepId"]),
    ("get_stove_temperature", "qms", "读取加热炉类别、实际作用温度、准确度等级、检测结果与下次检测日期，支撑热处理资源能力判定。",
     ["resourceName", "heatingFurnaceType", "checkDateFrom", "checkDateTo"]),
    ("get_qualification", "qms", "查询质控卡合格证的结论、审批状态、贮存期和订货代表审批信息，支撑交付条件判断。",
     ["containerId", "qualificationStatus"]),
    ("get_wms_inventory", "wms", "读取 WMS 库存数量、分配数量、可用数量、冻结数量及批次质量状态，与 ERP 库存进行交叉核验。",
     ["warehouseCode", "itemCode", "locationCode", "batchNum"]),
    ("get_lack_warnings", "wms", "读取出库缺件预警单，按 SAP 单号、生产订单号和物料编码返回计划出库数量与缺件数量。",
     ["erpNo", "productionOrderNo", "itemCode"]),
    ("get_asn_arrivals", "wms", "查询 ASN 单、ERP 单、生产订单/采购单、预期到货时间与到货状态，支撑齐套时间预测。",
     ["asnNo", "erpNo", "poNo"]),
    ("get_shipping_status", "wms", "查询发运订单、波次、最晚出库时间、物流任务状态及库存冻结状态，支撑转工与交付跟踪。",
     ["orderNo", "erpOrderNo", "logisticsNo"]),
]

PAGING = ["cursor", "pageSize"]      # 所有多记录工具共用的分页参数（默认 50，最大 200）
ENVELOPE = {"items": [], "nextCursor": "cur_000000000000", "totalReturned": 50, "traceId": "tr_0000000000000000"}


def tool_def(name, desc, params):
    props = {p: {"type": "string", "description": f"{name} 输入参数 {p}"} for p in params + PAGING}
    return {
        "name": name,
        "description": desc,
        "inputSchema": {"type": "object", "properties": props, "required": []},
        "annotations": {
            "readOnlyHint": not name.startswith("write_"),
            "destructiveHint": name.startswith("write_"),
            "idempotentHint": not name.startswith("write_"),
        },
    }


def chars(obj, ascii_wire):
    """ensure_ascii=True 模拟中文被转成 \\uXXXX 的线路格式；False 是可读 JSON。"""
    return len(json.dumps(obj, ensure_ascii=ascii_wire, separators=(",", ":")))


print(f"工具数 = {len(TOOLS)}   业务输入参数合计 = {sum(len(t[3]) for t in TOOLS)}")
print()
print("按 Server 分组的 tools/list 体积（字符数，紧凑 JSON）")
print(f"{'Server':<6}{'工具':>5}{'参数':>6}{'中文原样':>11}{'转义上线':>12}{'UTF-8 字节':>12}{'单工具均':>10}")
tot = tot_4srv = 0
for srv in ("mes", "erp", "qms", "wms"):
    grp = [t for t in TOOLS if t[1] == srv]
    cat = {"tools": [tool_def(n, d, p) for n, _s, d, p in grp]}
    c, ca = chars(cat, False), chars(cat, True)
    b = len(json.dumps(cat, ensure_ascii=False).encode("utf-8"))
    tot_4srv += c
    print(f"{srv:<6}{len(grp):>5}{sum(len(t[3]) for t in grp):>6}{c:>11,}{ca:>12,}{b:>12,}{c // len(grp):>10,}")
cat_all = {"tools": [tool_def(n, d, p) for n, _s, d, p in TOOLS]}
tot, tot_ascii = chars(cat_all, False), chars(cat_all, True)
tot_bytes = len(json.dumps(cat_all, ensure_ascii=False).encode("utf-8"))
print(f"{'ALL':<6}{len(TOOLS):>5}{sum(len(t[3]) for t in TOOLS):>6}{tot:>11,}{tot_ascii:>12,}"
      f"{tot_bytes:>12,}{tot // len(TOOLS):>10,}")
print(f"（四组分别拉取合计 {tot_4srv:,}，比一次拉全量多 {tot_4srv - tot:,} 个字符——四次 {chr(34)}tools 外层壳{chr(34)}）")
print(f"\n线路格式（ensure_ascii）/ 中文原样 = {tot_ascii / tot:.2f}x —— 同一个目录，转义后写进日志胖 {round((tot_ascii / tot - 1) * 100)}%")

print("\n目录条目里各部分占多少字符（全 24 工具，含各自的键名）")
parts = {"name": 0, "description": 0, "inputSchema": 0, "annotations": 0}
for n, d, p in [(a, c, e) for a, _s, c, e in TOOLS]:
    td = tool_def(n, d, p)
    for k in parts:
        parts[k] += len(json.dumps({k: td[k]}, ensure_ascii=False, separators=(",", ":"))) - 2
part_sum = sum(parts.values())
for k, v in parts.items():
    print(f"  {k:<12}{v:>9,}  {v / tot * 100:>5.1f}%")
shell, entry_commas, entry_braces, key_commas = 12, len(TOOLS) - 1, len(TOOLS) * 2, len(TOOLS) * 3
print(f"  {'合计':<11}{part_sum:>9,}  对账：+ 外层壳 {shell} + 条目间逗号 {entry_commas}"
      f" + 条目括号 {entry_braces} + 键间逗号 {key_commas} = {part_sum + shell + entry_commas + entry_braces + key_commas:,}"
      f"（全目录 {tot:,}）")

print("\n翻页：数据量由行数决定，往返次数由 pageSize 决定")
rows = [120, 240, 480]          # 一行裁剪后的字符数
n_rows = 3000                   # 一张典型的订单/批次表
env = len(json.dumps(ENVELOPE, ensure_ascii=False))
print(f"表行数 = {n_rows}   单次响应信封开销 = {env} 字符（items/nextCursor/totalReturned/traceId）")
print(f"{'每行字符':>9}{'pageSize':>9}{'往返次数':>10}{'数据字符':>12}{'信封字符':>11}{'信封占比':>10}")
for c in rows:
    for ps in (50, 200):
        trips = math.ceil(n_rows / ps)
        data = n_rows * c
        over = trips * env
        print(f"{c:>9}{ps:>9}{trips:>10}{data:>12,}{over:>11,}{over / (data + over) * 100:>9.2f}%")
print(f"\n对比：24 工具目录一次性成本 = {tot:,} 字符；一页 50 行（每行 240）= {50 * 240:,} 字符"
      f" → 目录 ≈ {tot / (50 * 240):.2f} 页数据")
print(f"全表 {n_rows} 行（每行 240）= {n_rows * 240:,} 字符 → 目录只占 {tot / (n_rows * 240) * 100:.1f}%")
print("所以省上下文的杠杆是「裁剪字段 + 收窄过滤条件」，不是「调小 pageSize」。")

print("\n口径核对：本脚本只算字符，不冒充 token。")
