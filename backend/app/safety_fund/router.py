"""安全生产费用台账接口。

对账导出的 CSV 明细行与台账明细来自同一个 service.reconciliation()，
不允许在路由里再拼一套数字。
"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.safety_fund.schemas import AccrualPayload, ClosePayload, ExpenditurePayload, RatePayload
from app.safety_fund.service import EXPENDITURE_EXPORT_COLUMNS, LedgerError, service

router = APIRouter(prefix="/api/safety-fund", tags=["安全生产费用台账"])


def _raise(exc: LedgerError) -> None:
    raise HTTPException(status_code=exc.status, detail=str(exc))


@router.get("/rates")
def list_rates() -> dict[str, Any]:
    """提取比例历史留档清单。"""
    return {"items": service.list_rates()}


@router.post("/rates")
def register_rate(payload: RatePayload) -> dict[str, Any]:
    try:
        item = service.register_rate(payload.effectiveMonth, payload.rateYuan, payload.note)
    except LedgerError as exc:
        _raise(exc)
    return {"ok": True, "message": "提取比例已登记，仅对之后的账期生效", "item": item}


@router.get("/months")
def list_months() -> dict[str, Any]:
    """月度台账清单：期初/计提/使用/结余全部来自唯一口径。"""
    return {"items": service.list_months()}


@router.get("/months/{month}")
def month_detail(month: str) -> dict[str, Any]:
    try:
        return service.month_detail(month)
    except LedgerError as exc:
        _raise(exc)


@router.post("/accruals")
def register_accrual(payload: AccrualPayload) -> dict[str, Any]:
    try:
        item = service.register_accrual(payload.month, payload.outputTonnes)
    except LedgerError as exc:
        _raise(exc)
    return {"ok": True, "message": f"账期 {payload.month} 应提金额已按当时比例登记并快照", "item": item}


@router.get("/expenditures")
def list_expenditures(month: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        return {"items": service.list_expenditures(month)}
    except LedgerError as exc:
        _raise(exc)


@router.post("/expenditures")
def register_expenditure(payload: ExpenditurePayload) -> dict[str, Any]:
    try:
        item = service.register_expenditure(
            payload.month,
            payload.voucherNo,
            payload.category,
            payload.summary,
            payload.amountYuan,
            payload.usedAt,
        )
    except LedgerError as exc:
        _raise(exc)
    return {"ok": True, "message": "专项使用已逐笔登记", "item": item}


@router.post("/close")
def close_month(payload: ClosePayload) -> dict[str, Any]:
    """月末结转：使用登记与结余结转在同一事务落地，落库后两边对不上即失败。"""
    try:
        detail = service.close_month(payload.month, payload.expenditures)
    except LedgerError as exc:
        _raise(exc)
    return {"ok": True, "message": f"账期 {payload.month} 已结转封档，结余 {detail['balanceYuan']} 元", "item": detail}


@router.get("/balance")
def current_balance() -> dict[str, Any]:
    """当前结余；与台账、对账走同一套推导，Dashboard 直接取这里。"""
    return service.current_balance()


@router.get("/reconciliation/{month}")
def reconciliation(month: str, format: str = Query(default="json", pattern="^(json|csv)$")) -> Any:
    """按月导出对账文件。明细即台账明细本身，导出前做口径自检。"""
    try:
        detail = service.reconciliation(month)
    except LedgerError as exc:
        _raise(exc)

    if format == "json":
        return {
            "month": month,
            "status": detail["status"],
            "openingYuan": detail["openingYuan"],
            "accruedYuan": detail["accruedYuan"],
            "usedYuan": detail["usedYuan"],
            "balanceYuan": detail["balanceYuan"],
            "detailHash": detail["detailHash"],
            "items": detail["items"],
        }

    # CSV：明细行字段与台账 items 一一对应，不另算
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([header for _, header in EXPENDITURE_EXPORT_COLUMNS])
    for item in detail["items"]:
        writer.writerow([item[key] for key, _ in EXPENDITURE_EXPORT_COLUMNS])
    # 汇总区只引用同一 detail 里的数字，保持「导出即台账」
    writer.writerow([])
    writer.writerow(["期初结余(元)", detail["openingYuan"]])
    writer.writerow(["本月计提(元)", detail["accruedYuan"]])
    writer.writerow(["本月使用(元)", detail["usedYuan"]])
    writer.writerow(["期末结余(元)", detail["balanceYuan"]])
    data = "\ufeff" + buffer.getvalue()
    return Response(
        content=data.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''safety-fund-{month}.csv"},
    )
