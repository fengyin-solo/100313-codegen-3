"""安全生产费用台账接口：比例留档、月度计提、专项使用与月末对账。"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.safetyfee import LEDGER_COLUMNS, SafetyFeeError, service

router = APIRouter(prefix="/api/safetyfee", tags=["安全生产费用台账"])


def bad_request(exc: SafetyFeeError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/rates")
def list_rates() -> dict[str, Any]:
    """列出按账期留档的提取比例。"""
    return {"items": service.list_rates(), "total": len(service.list_rates())}


@router.post("/rates", response_model=ActionResult)
def create_rate(payload: EntryPayload) -> ActionResult:
    """登记新生效比例；已有计提的历史账期不允许补改。"""
    entry, message = service.create_rate(payload.values)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


@router.get("/accruals")
def list_accruals(month: str | None = None) -> dict[str, Any]:
    """查询月度计提留档。"""
    try:
        items = service.list_accruals(month)
    except SafetyFeeError as exc:
        raise bad_request(exc) from exc
    return {"items": items, "total": len(items)}


@router.post("/accruals", response_model=ActionResult)
def create_accrual(payload: EntryPayload) -> ActionResult:
    """按账期原煤产量 × 当时适用比例计算并登记当月应提金额。"""
    entry, message = service.accrue(payload.values)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


@router.get("/usages", response_model=PageResult[dict])
def list_usages(
    month: str | None = Query(default=None, description="账期，格式 YYYY-MM"),
    keyword: str | None = Query(default=None, description="按财务支出凭证号检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """分页登记台账的专项使用明细。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    try:
        items, total = service.list_usages(month=month, keyword=keyword, page=page, size=size)
    except SafetyFeeError as exc:
        raise bad_request(exc) from exc
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/usages", response_model=ActionResult)
def register_usage(payload: EntryPayload) -> ActionResult:
    """登记一笔专项使用；同一财务支出凭证重复提交时原样退回。"""
    entry, message, received, existing = service.register_usage(payload.values)
    return ActionResult(
        ok=entry is not None,
        message=message,
        entry=entry,
    ).model_copy(update={"received": received, "existing": existing})


@router.get("/summary")
def monthly_summary(month: str | None = None) -> dict[str, Any]:
    """查询月度期初、计提、使用、期末结余。"""
    try:
        return service.monthly_summary(month)
    except SafetyFeeError as exc:
        raise bad_request(exc) from exc


@router.get("/balance")
def balance(month: str | None = None) -> dict[str, Any]:
    """其他页面读取结余时复用月度台账同一套汇总口径。"""
    try:
        return service.monthly_summary(month)
    except SafetyFeeError as exc:
        raise bad_request(exc) from exc


@router.get("/ledger")
def ledger(month: str | None = None) -> dict[str, Any]:
    """读取月度台账流水，是对账文件和页面明细的共同来源。"""
    try:
        return service.reconciliation(month)
    except SafetyFeeError as exc:
        raise bad_request(exc) from exc


@router.get("/export")
def export_ledger(
    month: str | None = Query(default=None, description="账期，格式 YYYY-MM"),
    format: str = Query(default="json", description="json 或 csv"),
) -> Any:
    """导出月度对账文件；内容直接取自 /ledger 快照，不另算口径。"""
    try:
        snapshot = service.reconciliation(month)
    except SafetyFeeError as exc:
        raise bad_request(exc) from exc
    if format.lower() != "csv":
        return snapshot

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=LEDGER_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in snapshot["items"]:
        writer.writerow(row)
    encoded = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    filename = f"safetyfee_reconciliation_{snapshot['month']}.csv"
    return StreamingResponse(
        encoded,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/closures")
def list_closures() -> dict[str, Any]:
    """查询历史月末结转留档。"""
    items = service.list_closures()
    return {"items": items, "total": len(items)}


@router.post("/closures")
def close_month(payload: dict[str, Any]) -> dict[str, Any]:
    """使用明细登记和月末结余结转账务一致地提交；不一致即回滚。"""
    try:
        return service.close_month(payload)
    except SafetyFeeError as exc:
        return {"ok": False, "message": str(exc)}
