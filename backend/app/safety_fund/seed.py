"""安全费用台账初始数据。

只在库为空时播种；全部通过 service 的正式接口造数（计提、使用、月末结转），
所以示例数据本身就满足「期初+计提-使用=结余」和「登记与结转同事务」。
历史账期 2026-07 按 30 元/吨 留档，2026-09 起比例调整为 35 元/吨，
用来直观体现「调整只影响之后账期」。
"""
from __future__ import annotations

from app.safety_fund.db import connect, init_db
from app.safety_fund.service import service


def seed_if_empty() -> bool:
    init_db()
    conn = connect()
    try:
        has_rates = conn.execute("SELECT COUNT(*) AS c FROM sf_rate").fetchone()["c"]
    finally:
        conn.close()
    if has_rates:
        return False

    # 1) 提取比例：年初 30 元/吨，自 2026-09 起调整为 35 元/吨
    service.register_rate("2026-01", 30, "年初设立：30 元/吨")
    service.register_rate("2026-09", 35, "三季度评估后调整，自 9 月账期起生效")

    # 2) 2026-07：产量 12 万吨，使用明细随月末结转在同一事务落地
    service.register_accrual("2026-07", 120000)
    service.close_month("2026-07", [
        {"voucherNo": "PZ-202607-001", "category": "瓦斯综合治理", "summary": "瓦斯抽采泵站管路维护与钻孔施工",
         "amountYuan": "1500000.00", "usedAt": "2026-07-08"},
        {"voucherNo": "PZ-202607-002", "category": "个体防护装备", "summary": "自救器统一更新及气瓶检验",
         "amountYuan": "820000.00", "usedAt": "2026-07-15"},
        {"voucherNo": "PZ-202607-003", "category": "通风系统改造", "summary": "回风巷风门与调节风窗改造",
         "amountYuan": "1195000.00", "usedAt": "2026-07-22"},
    ])

    # 3) 2026-08：产量 13.5 万吨，仍按 30 元/吨计提
    service.register_accrual("2026-08", 135000)
    service.close_month("2026-08", [
        {"voucherNo": "PZ-202608-001", "category": "防尘设施", "summary": "防尘供水管路延伸及喷雾装置增设",
         "amountYuan": "960000.00", "usedAt": "2026-08-06"},
        {"voucherNo": "PZ-202608-002", "category": "安全监控系统", "summary": "安全监控系统分站与传感器升级",
         "amountYuan": "1480000.00", "usedAt": "2026-08-14"},
        {"voucherNo": "PZ-202608-003", "category": "应急救援装备", "summary": "应急救援器材补充与救护车检修",
         "amountYuan": "1490000.00", "usedAt": "2026-08-25"},
    ])

    # 4) 2026-09（未结转）：新比例 35 元/吨，使用逐笔登记中
    service.register_accrual("2026-09", 128000)
    service.register_expenditure("2026-09", "PZ-202609-001", "顶板与支护", "回采工作面顶板支护材料采购",
                                 "1120000.00", "2026-09-05")
    service.register_expenditure("2026-09", "PZ-202609-002", "人员定位系统", "井下人员定位基站维护与识别卡补充",
                                 "760000.00", "2026-09-12")
    service.register_expenditure("2026-09", "PZ-202609-003", "防灭火", "注氮防灭火材料与束管监测耗材",
                                 "540000.00", "2026-09-18")
    return True
