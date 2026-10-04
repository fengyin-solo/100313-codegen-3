"""安全生产费用台账端到端业务规则测试。

每条用例对应立账要求的一条硬规则：
- 计提按当时比例，比例调整只影响之后账期，历史数字保持原值；
- 同凭证号重复登记只认第一次、原样退回，不叠加结余；
- 台账明细、对账导出、结余三处口径一致；
- 月末使用登记与结余结转同事务，落库后对不上即失败（全回滚）。
"""
from __future__ import annotations

import csv
import io
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    db_file = tmp_path / "sf_test.db"
    monkeypatch.setenv("SF_DB_PATH", str(db_file))
    # 延迟导入，确保 SF_DB_PATH 已指向临时库
    from app.main import app
    from app.safety_fund.seed import seed_if_empty

    with TestClient(app) as test_client:
        assert seed_if_empty() is False  # startup 已播种
        yield test_client


def _accrual(client: TestClient, month: str, tonnes: str) -> None:
    resp = client.post("/api/safety-fund/accruals", json={"month": month, "outputTonnes": tonnes})
    assert resp.status_code == 200, resp.text


def _expense(client: TestClient, payload: dict) -> dict:
    resp = client.post("/api/safety-fund/expenditures", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["item"]


def _close(client: TestClient, month: str, expenses: list[dict] | None = None) -> dict:
    resp = client.post("/api/safety-fund/close", json={"month": month, "expenditures": expenses or []})
    assert resp.status_code == 200, resp.text
    return resp.json()["item"]


# ---------------------------------------------------------------- 计提与比例留档

def test_accrual_uses_rate_effective_in_that_month(client: TestClient) -> None:
    # 2026-09 起比例 35 元/吨：128000 吨 -> 4,480,000 元
    detail = client.get("/api/safety-fund/months/2026-09").json()
    assert detail["accruedYuan"] == "4480000.00"
    assert detail["accrual"]["rateYuan"] == "35.00"

    # 2026-07 按 30 元/吨留档
    july = client.get("/api/safety-fund/months/2026-07").json()
    assert july["accrual"]["rateYuan"] == "30.00"
    assert july["accruedYuan"] == "3600000.00"


def test_rate_change_does_not_recompute_prior_months(client: TestClient) -> None:
    # 再新增一条比例（40 元/吨，自 2026-12 起），历史账期数字保持不变
    resp = client.post("/api/safety-fund/rates", json={"effectiveMonth": "2026-12", "rateYuan": 40})
    assert resp.status_code == 200, resp.text

    july = client.get("/api/safety-fund/months/2026-07").json()
    august = client.get("/api/safety-fund/months/2026-08").json()
    september = client.get("/api/safety-fund/months/2026-09").json()
    assert july["accrual"]["rateYuan"] == "30.00"
    assert august["accrual"]["rateYuan"] == "30.00"
    assert september["accrual"]["rateYuan"] == "35.00"
    assert july["accruedYuan"] == "3600000.00"
    assert september["accruedYuan"] == "4480000.00"

    # 新账期计提用新比例：10 万吨 × 40 = 4,000,000
    _accrual(client, "2026-12", "100000")
    dec = client.get("/api/safety-fund/months/2026-12").json()
    assert dec["accrual"]["rateYuan"] == "40.00"
    assert dec["accruedYuan"] == "4000000.00"


def test_rate_for_same_month_cannot_overwrite(client: TestClient) -> None:
    resp = client.post("/api/safety-fund/rates", json={"effectiveMonth": "2026-09", "rateYuan": 50})
    assert resp.status_code == 409
    september = client.get("/api/safety-fund/months/2026-09").json()
    assert september["accrual"]["rateYuan"] == "35.00"


def test_accrual_amount_rounds_half_up_to_cent(client: TestClient) -> None:
    # 333.335 吨 × 35 元/吨 = 11666.725 -> 11666.73（四舍五入到分）
    client.post("/api/safety-fund/rates", json={"effectiveMonth": "2027-01", "rateYuan": 35})
    _accrual(client, "2027-01", "333.335")
    jan = client.get("/api/safety-fund/months/2027-01").json()
    assert jan["accruedYuan"] == "11666.73"


# ---------------------------------------------------------------- 重复凭证

def test_duplicate_voucher_is_rejected_and_not_added_to_balance(client: TestClient) -> None:
    before = client.get("/api/safety-fund/months/2026-09").json()
    assert before["usedYuan"] == "2420000.00"

    payload = {
        "month": "2026-09", "voucherNo": "PZ-202609-001",
        "category": "瓦斯综合治理", "summary": "重复提交的同一凭证",
        "amountYuan": "999999.00", "usedAt": "2026-09-20",
    }
    resp = client.post("/api/safety-fund/expenditures", json=payload)
    assert resp.status_code == 409
    assert "只认第一次" in resp.json()["detail"]

    after = client.get("/api/safety-fund/months/2026-09").json()
    assert after["usedYuan"] == before["usedYuan"]
    assert after["balanceYuan"] == before["balanceYuan"]
    # 明细仍然只有原来三笔，原笔金额未被覆盖
    vouchers = [it["voucherNo"] for it in after["items"]]
    assert vouchers.count("PZ-202609-001") == 1
    first = next(it for it in after["items"] if it["voucherNo"] == "PZ-202609-001")
    assert first["amountYuan"] == "1120000.00"


def test_duplicate_voucher_in_close_batch_rolls_back_entire_transaction(client: TestClient) -> None:
    # 结转 2026-09 的批量里混入一张历史已登记凭证：整批回滚
    before = client.get("/api/safety-fund/months/2026-09").json()
    batch = [
        {"voucherNo": "PZ-NEW-001", "category": "安全培训", "summary": "新凭证 A",
         "amountYuan": "100000.00", "usedAt": "2026-09-25"},
        {"voucherNo": "PZ-202609-001", "category": "瓦斯综合治理", "summary": "已登记过的凭证",
         "amountYuan": "200000.00", "usedAt": "2026-09-26"},
    ]
    resp = client.post("/api/safety-fund/close", json={"month": "2026-09", "expenditures": batch})
    assert resp.status_code == 409

    after = client.get("/api/safety-fund/months/2026-09").json()
    assert after["status"] == "open"  # 没有结转
    assert after["usedYuan"] == before["usedYuan"]  # 新凭证 A 也没有混进去
    assert all(it["voucherNo"] != "PZ-NEW-001" for it in after["items"])


# ---------------------------------------------------------------- 结转正流程与恒等式

def test_close_carries_balance_and_freezes_month(client: TestClient) -> None:
    _expense(client, {
        "month": "2026-09", "voucherNo": "PZ-202609-004", "category": "水害防治",
        "summary": "水仓清挖与排水管路维护", "amountYuan": "265000.00", "usedAt": "2026-09-28",
    })
    closed = _close(client, "2026-09")
    # 期初 205000 + 计提 4480000 - 使用 2685000 = 2000000
    assert closed["openingYuan"] == "205000.00"
    assert closed["usedYuan"] == "2685000.00"
    assert closed["balanceYuan"] == "2000000.00"

    # 封档后不能再补登使用，也不能重复结转
    resp = client.post("/api/safety-fund/expenditures", json={
        "month": "2026-09", "voucherNo": "PZ-LATE", "category": "防尘设施",
        "summary": "封档后补登", "amountYuan": "1.00", "usedAt": "2026-09-30"})
    assert resp.status_code == 409
    resp = client.post("/api/safety-fund/close", json={"month": "2026-09", "expenditures": []})
    assert resp.status_code == 409

    # 下月期初就是上月结转
    _accrual(client, "2026-10", "100000")
    october = client.get("/api/safety-fund/months/2026-10").json()
    assert october["openingYuan"] == "2000000.00"


def test_close_register_batch_and_carry_in_one_transaction(client: TestClient) -> None:
    # 先把 2026-09 空结掉，保证后续账期按月顺序
    _close(client, "2026-09")
    # 新账期：计提后直接通过 close 批量登记使用，在同事务落地
    client.post("/api/safety-fund/rates", json={"effectiveMonth": "2026-10", "rateYuan": 30})
    _accrual(client, "2026-10", "10000")
    closed = _close(client, "2026-10", [
        {"voucherNo": "PZ-202610-001", "category": "安全培训", "summary": "全员安全再培训",
         "amountYuan": "120000.00", "usedAt": "2026-10-10"},
    ])
    assert closed["accruedYuan"] == "300000.00"
    assert closed["usedYuan"] == "120000.00"
    # 期初承接 9 月期末 2,265,000，再加净额 180,000
    assert closed["openingYuan"] == "2265000.00"
    assert closed["balanceYuan"] == "2445000.00"
    assert closed["status"] == "closed"


def test_close_requires_month_order(client: TestClient) -> None:
    # 2026-09 未结转时直接结转 2026-10，应拒绝
    _accrual(client, "2026-10", "100000")
    resp = client.post("/api/safety-fund/close", json={"month": "2026-10", "expenditures": []})
    assert resp.status_code in (409, 400)
    assert "顺序" in resp.json()["detail"]


# ---------------------------------------------------------------- 口径一致：台账/导出/结余

def test_reconciliation_matches_ledger_detail_exactly(client: TestClient) -> None:
    month = "2026-09"
    ledger = client.get(f"/api/safety-fund/months/{month}").json()
    recon = client.get(f"/api/safety-fund/reconciliation/{month}").json()

    assert recon["items"] == ledger["items"]
    assert recon["usedYuan"] == ledger["usedYuan"]
    assert recon["balanceYuan"] == ledger["balanceYuan"]
    assert recon["accruedYuan"] == ledger["accruedYuan"]

    # CSV 明细行 == 台账明细行
    resp = client.get(f"/api/safety-fund/reconciliation/{month}?format=csv")
    assert resp.status_code == 200
    text = resp.content.decode("utf-8").lstrip("\ufeff")
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    data_rows = rows[1:1 + len(ledger["items"])]
    for csv_row, item in zip(data_rows, ledger["items"]):
        mapping = dict(zip(header, csv_row))
        assert mapping["凭证号"] == item["voucherNo"]
        assert mapping["金额(元)"] == item["amountYuan"]
        assert mapping["账期"] == item["month"]
    # 汇总区数字也来自同一 detail
    flat = text
    assert ledger["balanceYuan"] in flat
    assert ledger["usedYuan"] in flat


def test_reconciliation_closed_month_keeps_archived_detail(client: TestClient) -> None:
    # 结转后对账文件仍然等于结转时的明细
    _close(client, "2026-09", [
        {"voucherNo": "PZ-202609-009", "category": "应急演练", "summary": "三季度应急演练保障",
         "amountYuan": "30000.00", "usedAt": "2026-09-29"},
    ])
    ledger = client.get("/api/safety-fund/months/2026-09").json()
    recon = client.get("/api/safety-fund/reconciliation/2026-09").json()
    assert recon["items"] == ledger["items"]
    assert recon["detailHash"] == ledger["detailHash"]


def test_overview_balance_matches_ledger(client: TestClient) -> None:
    overview = client.get("/api/overview").json()
    balance = client.get("/api/safety-fund/balance").json()
    ledger_sep = client.get("/api/safety-fund/months/2026-09").json()
    assert overview["safetyFund"]["balanceYuan"] == balance["balanceYuan"]
    assert balance["balanceYuan"] == ledger_sep["balanceYuan"]
    # 卡片里同源
    card = next(c for c in overview["cards"] if c["label"] == "安全费用当前结余(元)")
    assert card["value"] == ledger_sep["balanceYuan"]


def test_seed_months_invariant(client: TestClient) -> None:
    # 播种数据自身满足各月恒等式：期末 = 期初 + 计提 - 使用
    months = {item["month"]: item for item in client.get("/api/safety-fund/months").json()["items"]}
    assert months["2026-07"]["balanceYuan"] == "85000.00"
    assert months["2026-08"]["openingYuan"] == "85000.00"
    assert months["2026-08"]["balanceYuan"] == "205000.00"
    assert months["2026-09"]["balanceYuan"] == "2265000.00"
    for m in months.values():
        assert int(float(m["balanceYuan"]) * 100) == (
            m["openingCents"] + m["accruedCents"] - m["usedCents"]
        )


# ---------------------------------------------------------------- 事务失败注入

def test_close_fails_and_rolls_back_when_sides_mismatch(client: TestClient, monkeypatch) -> None:
    """两边对不上就算失败：注入与落库明细不符的推导结果，提交前复核拦截，整笔回滚。"""
    from app.safety_fund import service as service_mod

    real = service_mod.SafetyFundService._month_detail_conn

    def tampered(self, conn, month):  # noqa: ANN001
        detail = real(self, conn, month)
        # 结转插入 sf_close 之前做提交前复核，此时该账期还没有结转记录
        exists = conn.execute("SELECT id FROM sf_close WHERE month = ?", (month,)).fetchone()
        if month == "2026-09" and exists is None:
            detail = dict(detail)
            detail["balanceCents"] += 999
            detail["balanceYuan"] = service_mod.cents_yuan(detail["balanceCents"])
        return detail

    monkeypatch.setattr(service_mod.SafetyFundService, "_month_detail_conn", tampered)
    resp = client.post("/api/safety-fund/close", json={
        "month": "2026-09",
        "expenditures": [
            {"voucherNo": "PZ-202609-100", "category": "防尘设施", "summary": "注入失败测试",
             "amountYuan": "10000.00", "usedAt": "2026-09-27"},
        ],
    })
    assert resp.status_code >= 400

    # 复核失败：同事务里的使用登记与结转一并回滚，不留半截账
    detail = client.get("/api/safety-fund/months/2026-09").json()
    assert detail["status"] == "open"
    assert all(it["voucherNo"] != "PZ-202609-100" for it in detail["items"])
