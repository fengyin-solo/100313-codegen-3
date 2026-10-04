"""安全生产费用台账业务规则。

台账只保存三类不可覆盖的事实：提取比例版本、月度计提、专项使用。
月度结余由这些事实统一推导；月末结转时再把同一口径固化为结转记录。
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any

from app.store import store

RATE_TABLE = "safetyfee_rates"
ACCRUAL_TABLE = "safetyfee_accruals"
USAGE_TABLE = "safetyfee_usages"
CLOSURE_TABLE = "safetyfee_closures"

MONEY_QUANTUM = Decimal("0.01")

LEDGER_COLUMNS = [
    "明细编号",
    "类型",
    "账期",
    "财务支出凭证号",
    "支出日期",
    "专项用途",
    "摘要",
    "原煤产量（吨）",
    "提取比例（%）",
    "计提金额（元）",
    "使用金额（元）",
    "结余（元）",
    "登记时间",
    "结转状态",
]


class SafetyFeeError(ValueError):
    """安全费用业务校验失败；事务应回滚，不能留下半截数据。"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _pick(values: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        value = values.get(name)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _text(values: dict[str, Any], names: tuple[str, ...]) -> str:
    value = _pick(values, names)
    return str(value).strip() if value is not None else ""


def _parse_month(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise SafetyFeeError("账期不能为空，格式为 YYYY-MM")
    try:
        parsed = datetime.strptime(text, "%Y-%m")
    except ValueError as exc:
        raise SafetyFeeError(f"账期「{text}」格式不正确，应为 YYYY-MM") from exc
    return parsed.strftime("%Y-%m")


def _previous_month(month: str) -> str:
    parsed = datetime.strptime(month, "%Y-%m")
    year = parsed.year
    previous = parsed.month - 1
    if previous == 0:
        year -= 1
        previous = 12
    return f"{year:04d}-{previous:02d}"


def _decimal(value: Any, field_name: str, *, allow_zero: bool = True) -> Decimal:
    if value is None or str(value).strip() == "":
        raise SafetyFeeError(f"{field_name}不能为空")
    text = str(value).strip().replace(",", "").replace("，", "")
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise SafetyFeeError(f"{field_name}「{value}」不是有效数字") from exc
    if not result.is_finite():
        raise SafetyFeeError(f"{field_name}必须是有限数字")
    if allow_zero:
        if result < 0:
            raise SafetyFeeError(f"{field_name}不能小于 0")
    elif result <= 0:
        raise SafetyFeeError(f"{field_name}必须大于 0")
    return result


def _money(value: Any, field_name: str, *, positive: bool = False) -> Decimal:
    result = _decimal(value, field_name, allow_zero=not positive)
    return result.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _number_float(value: Decimal) -> float:
    return float(value)


def _money_float(value: Decimal) -> float:
    return float(value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP))


def _next_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


class SafetyFeeService:
    """安全费用提取、使用、对账和月末结转的唯一业务口径。"""

    def list_rates(self) -> list[dict[str, Any]]:
        return [dict(row) for row in sorted(store.rows(RATE_TABLE), key=lambda row: row["effective_month"])]

    def create_rate(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        try:
            with store.transaction():
                effective_month = _parse_month(_pick(values, ("生效账期", "生效月份", "effective_month")))
                rate_percent = _decimal(
                    _pick(values, ("提取比例（%）", "提取比例", "rate_percent", "rate")),
                    "提取比例",
                    allow_zero=False,
                )
                if rate_percent > Decimal("100"):
                    raise SafetyFeeError("提取比例不能大于 100%")

                rates = store.rows(RATE_TABLE)
                if any(row["effective_month"] == effective_month for row in rates):
                    raise SafetyFeeError(f"{effective_month} 的提取比例已留档，不能覆盖原版本")

                row = {
                    "id": _next_id(rates),
                    "effective_month": effective_month,
                    "生效账期": effective_month,
                    "rate_percent": _number_float(rate_percent),
                    "提取比例（%）": _number_float(rate_percent),
                    "remark": _text(values, ("备注", "remark")),
                    "created_at": _now(),
                }
                rates.append(row)
                return dict(row), "提取比例已登记，只对该账期及之后的新计提生效"
        except SafetyFeeError as exc:
            return None, str(exc)

    def _rate_for_month(self, month: str) -> dict[str, Any] | None:
        candidates = [row for row in store.rows(RATE_TABLE) if row["effective_month"] <= month]
        if not candidates:
            return None
        return dict(max(candidates, key=lambda row: row["effective_month"]))

    def list_accruals(self, month: str | None = None) -> list[dict[str, Any]]:
        rows = [dict(row) for row in store.rows(ACCRUAL_TABLE)]
        if month:
            month = _parse_month(month)
            rows = [row for row in rows if row["accrual_month"] == month]
        return rows

    def accrue(
        self,
        values: dict[str, Any],
        *,
        month: str | None = None,
        raw_coal_output: Any = None,
    ) -> tuple[dict[str, Any] | None, str]:
        try:
            with store.transaction():
                accrual_month = _parse_month(month or _pick(values, ("账期", "月份", "accrual_month", "month")))
                if self._is_closed(accrual_month):
                    raise SafetyFeeError(f"{accrual_month} 已月末结转，计提金额不能补改")

                rows = store.rows(ACCRUAL_TABLE)
                existing = next((row for row in rows if row["accrual_month"] == accrual_month), None)
                if existing is not None:
                    raise SafetyFeeError(
                        f"{accrual_month} 已按 {existing['提取比例（%）']}% 计提，原账期金额保持不变"
                    )

                output_value = raw_coal_output if raw_coal_output is not None else _pick(
                    values, ("原煤产量（吨）", "原煤产量", "raw_coal_output", "output")
                )
                output = _decimal(output_value, "原煤产量")
                rate_row = self._rate_for_month(accrual_month)
                if rate_row is None:
                    raise SafetyFeeError(f"缺少 {accrual_month} 适用的提取比例，请先登记比例版本")

                amount = (output * Decimal(str(rate_row["rate_percent"])) / Decimal("100")).quantize(
                    MONEY_QUANTUM, rounding=ROUND_HALF_UP
                )
                row = {
                    "id": _next_id(rows),
                    "accrual_month": accrual_month,
                    "账期": accrual_month,
                    "raw_coal_output": _number_float(output),
                    "原煤产量（吨）": _number_float(output),
                    "rate_percent": rate_row["rate_percent"],
                    "提取比例（%）": rate_row["提取比例（%）"],
                    "amount": _money_float(amount),
                    "计提金额（元）": _money_float(amount),
                    "created_at": _now(),
                }
                rows.append(row)
                return dict(row), f"{accrual_month} 应提安全费用 {_money_float(amount):.2f} 元"
        except SafetyFeeError as exc:
            return None, str(exc)

    def list_usages(
        self,
        *,
        month: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        if month:
            month = _parse_month(month)
        rows = [dict(row) for row in store.rows(USAGE_TABLE)]
        if month:
            rows = [row for row in rows if row["usage_month"] == month]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("voucher_no", ""))]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def _find_usage_by_voucher(self, voucher_no: str) -> dict[str, Any] | None:
        return next(
            (dict(row) for row in store.rows(USAGE_TABLE) if row["voucher_no"] == voucher_no),
            None,
        )

    def _is_closed(self, month: str) -> bool:
        return any(row["closure_month"] == month for row in store.rows(CLOSURE_TABLE))

    def _usage_values(
        self,
        values: dict[str, Any],
        *,
        batch_month: str | None = None,
        index: int | None = None,
    ) -> dict[str, Any]:
        prefix = f"第 {index + 1} 笔使用明细" if index is not None else "使用明细"
        month_value = _pick(values, ("账期", "月份", "usage_month", "month"))
        if batch_month and month_value and _parse_month(month_value) != batch_month:
            raise SafetyFeeError(f"{prefix}的账期与结转账期 {batch_month} 不一致")
        usage_month = _parse_month(batch_month or month_value)

        voucher_no = _text(values, ("财务支出凭证号", "凭证号", "voucher_no", "voucher"))
        purpose = _text(values, ("专项用途", "用途", "安全投入项目", "purpose", "usage_item"))
        if not voucher_no:
            raise SafetyFeeError(f"{prefix}缺少财务支出凭证号")
        if not purpose:
            raise SafetyFeeError(f"{prefix}缺少专项用途")

        amount = _money(
            _pick(values, ("使用金额（元）", "支出金额（元）", "使用金额", "支出金额", "amount")),
            f"{prefix}使用金额",
            positive=True,
        )
        return {
            "usage_month": usage_month,
            "voucher_no": voucher_no,
            "purpose": purpose,
            "amount": amount,
            "spent_at": _text(values, ("支出日期", "发生日期", "spent_at")),
            "remark": _text(values, ("备注", "remark")),
        }

    def _insert_usage(self, prepared: dict[str, Any]) -> dict[str, Any]:
        amount = prepared["amount"]
        row = {
            "id": _next_id(store.rows(USAGE_TABLE)),
            "usage_month": prepared["usage_month"],
            "账期": prepared["usage_month"],
            "voucher_no": prepared["voucher_no"],
            "财务支出凭证号": prepared["voucher_no"],
            "purpose": prepared["purpose"],
            "专项用途": prepared["purpose"],
            "amount": _money_float(amount),
            "使用金额（元）": _money_float(amount),
            "spent_at": prepared["spent_at"],
            "支出日期": prepared["spent_at"],
            "remark": prepared["remark"],
            "备注": prepared["remark"],
            "created_at": _now(),
        }
        store.rows(USAGE_TABLE).append(row)
        return dict(row)

    def register_usage(
        self,
        values: dict[str, Any],
        *,
        month: str | None = None,
    ) -> tuple[dict[str, Any] | None, str, dict[str, Any], dict[str, Any] | None]:
        received = dict(values)
        try:
            with store.transaction():
                prepared = self._usage_values(values, batch_month=month)
                existing = self._find_usage_by_voucher(prepared["voucher_no"])
                if existing is not None:
                    return (
                        None,
                        f"财务支出凭证 {prepared['voucher_no']} 已登记，重复凭证已原样退回，金额未计入结余",
                        received,
                        existing,
                    )
                if self._is_closed(prepared["usage_month"]):
                    raise SafetyFeeError(f"{prepared['usage_month']} 已月末结转，不能再登记新使用明细")
                row = self._insert_usage(prepared)
                return row, "专项使用已登记", {}, None
        except SafetyFeeError as exc:
            return None, str(exc), received, None

    def _closure(self, month: str) -> dict[str, Any] | None:
        return next(
            (dict(row) for row in store.rows(CLOSURE_TABLE) if row["closure_month"] == month),
            None,
        )

    def list_closures(self) -> list[dict[str, Any]]:
        return [dict(row) for row in sorted(store.rows(CLOSURE_TABLE), key=lambda row: row["closure_month"])]

    def close_month(self, payload: dict[str, Any]) -> dict[str, Any]:
        """使用登记与月末结余结转放在同一个内存事务里提交。"""
        month = _parse_month(_pick(payload, ("账期", "月份", "month", "closure_month")))
        raw_output = _pick(payload, ("原煤产量（吨）", "原煤产量", "raw_coal_output", "output"))
        usage_payloads = payload.get("usages") or payload.get("使用明细") or []
        if not isinstance(usage_payloads, list):
            raise SafetyFeeError("使用明细必须是数组")

        with store.transaction():
            if self._closure(month) is not None:
                raise SafetyFeeError(f"{month} 已完成月末结转，不能重复结转")

            activity_months = {
                row["accrual_month"] for row in store.rows(ACCRUAL_TABLE)
            } | {row["usage_month"] for row in store.rows(USAGE_TABLE)}
            if any(past_month < month for past_month in activity_months):
                prior = _previous_month(month)
                if self._closure(prior) is None:
                    raise SafetyFeeError(f"上一账期 {prior} 尚未结转，不能跳过历史账期")

            accrual_row = next(
                (row for row in store.rows(ACCRUAL_TABLE) if row["accrual_month"] == month),
                None,
            )
            if accrual_row is None:
                if raw_output is None:
                    raise SafetyFeeError(f"缺少 {month} 原煤产量，无法在结转时计提")
                accrual, message = self.accrue(
                    {},
                    month=month,
                    raw_coal_output=raw_output,
                )
                if accrual is None:
                    raise SafetyFeeError(message)
                accrual_row = accrual
            elif raw_output is not None:
                provided = _decimal(raw_output, "原煤产量")
                if provided != Decimal(str(accrual_row["raw_coal_output"])):
                    raise SafetyFeeError(f"{month} 已按原原煤产量计提，不能借月末结转改写历史金额")

            registered: list[dict[str, Any]] = []
            rejected: list[dict[str, Any]] = []
            for index, usage_values in enumerate(usage_payloads):
                if not isinstance(usage_values, dict):
                    raise SafetyFeeError(f"第 {index + 1} 笔使用明细必须是对象")
                prepared = self._usage_values(usage_values, batch_month=month, index=index)
                existing = self._find_usage_by_voucher(prepared["voucher_no"])
                if existing is not None:
                    rejected.append({
                        "index": index,
                        "message": f"凭证 {prepared['voucher_no']} 重复，已原样退回",
                        "received": dict(usage_values),
                        "existing": existing,
                    })
                    continue
                registered.append(self._insert_usage(prepared))

            summary = self.monthly_summary(month)
            if not self.list_accruals(month):
                raise SafetyFeeError(f"{month} 尚未计提，不能结转")
            previous_closure = self._closure(_previous_month(month))
            if previous_closure is not None:
                if Decimal(str(previous_closure["closing_balance"])) != Decimal(str(summary["opening_balance"])):
                    raise RuntimeError("期初结余与上月结转不一致，事务回滚")

            created_at = _now()
            closure = {
                "id": _next_id(store.rows(CLOSURE_TABLE)),
                "closure_month": month,
                "账期": month,
                "opening_balance": summary["opening_balance"],
                "期初结余": summary["期初结余"],
                "accrued_amount": summary["accrued_amount"],
                "本月计提": summary["本月计提"],
                "used_amount": summary["used_amount"],
                "本月使用": summary["本月使用"],
                "closing_balance": summary["closing_balance"],
                "期末结余": summary["期末结余"],
                "usage_count": summary["usage_count"],
                "使用明细笔数": summary["使用明细笔数"],
                "created_at": created_at,
                "结转时间": created_at,
            }
            store.rows(CLOSURE_TABLE).append(closure)

            persisted_summary = self.monthly_summary(month)
            persisted_closure = self._closure(month)
            if persisted_closure is None:
                raise RuntimeError("结转记录落库后缺失，事务回滚")
            for field_name in ("opening_balance", "accrued_amount", "used_amount", "closing_balance", "usage_count"):
                if persisted_closure[field_name] != summary[field_name]:
                    raise RuntimeError("结转记录与台账结余不一致，事务回滚")
            if persisted_summary["closing_balance"] != summary["closing_balance"]:
                raise RuntimeError("结余查询与结转结果不一致，事务回滚")

            return {
                "ok": True,
                "message": f"{month} 月末结转完成",
                "summary": persisted_summary,
                "closure": persisted_closure,
                "registered": registered,
                "rejected": rejected,
            }

    def monthly_summary(self, month: str | None = None) -> dict[str, Any]:
        if month is None:
            month = self._latest_month()
        month = _parse_month(month)

        accruals = store.rows(ACCRUAL_TABLE)
        usages = store.rows(USAGE_TABLE)

        opening_accrued = sum(
            (Decimal(str(row["amount"])) for row in accruals if row["accrual_month"] < month),
            Decimal("0"),
        )
        opening_used = sum(
            (Decimal(str(row["amount"])) for row in usages if row["usage_month"] < month),
            Decimal("0"),
        )
        month_accrued = sum(
            (Decimal(str(row["amount"])) for row in accruals if row["accrual_month"] == month),
            Decimal("0"),
        )
        month_used = sum(
            (Decimal(str(row["amount"])) for row in usages if row["usage_month"] == month),
            Decimal("0"),
        )
        opening = opening_accrued - opening_used
        closing = opening + month_accrued - month_used
        month_output = sum(
            (Decimal(str(row["raw_coal_output"])) for row in accruals if row["accrual_month"] == month),
            Decimal("0"),
        )
        month_usages = [row for row in usages if row["usage_month"] == month]
        closure = self._closure(month)

        result = {
            "month": month,
            "账期": month,
            "opening_balance": _money_float(opening),
            "期初结余": _money_float(opening),
            "accrued_amount": _money_float(month_accrued),
            "本月计提": _money_float(month_accrued),
            "used_amount": _money_float(month_used),
            "本月使用": _money_float(month_used),
            "closing_balance": _money_float(closing),
            "期末结余": _money_float(closing),
            "raw_coal_output": _number_float(month_output),
            "原煤产量（吨）": _number_float(month_output),
            "usage_count": len(month_usages),
            "使用明细笔数": len(month_usages),
            "closed": closure is not None,
            "已结转": closure is not None,
            "closed_at": closure["created_at"] if closure else None,
            "结转时间": closure["结转时间"] if closure else None,
        }
        return result

    def _latest_month(self) -> str:
        months = (
            [row["accrual_month"] for row in store.rows(ACCRUAL_TABLE)]
            + [row["usage_month"] for row in store.rows(USAGE_TABLE)]
            + [row["closure_month"] for row in store.rows(CLOSURE_TABLE)]
        )
        return max(months) if months else datetime.now().strftime("%Y-%m")

    def reconciliation(self, month: str | None = None) -> dict[str, Any]:
        """生成月度对账快照；台账列表和导出文件共用这一份结果。"""
        summary = self.monthly_summary(month)
        month_value = summary["month"]
        entries: list[dict[str, Any]] = []
        running = Decimal(str(summary["opening_balance"]))

        accruals = sorted(
            [row for row in store.rows(ACCRUAL_TABLE) if row["accrual_month"] == month_value],
            key=lambda row: int(row["id"]),
        )
        usages = sorted(
            [row for row in store.rows(USAGE_TABLE) if row["usage_month"] == month_value],
            key=lambda row: int(row["id"]),
        )

        for row in accruals:
            amount = Decimal(str(row["amount"]))
            running += amount
            entries.append(self._ledger_row(
                f"A{int(row['id']):04d}",
                "计提",
                month_value,
                "",
                "",
                "按月度原煤产量和当时提取比例计提",
                Decimal(str(row["raw_coal_output"])),
                Decimal(str(row["rate_percent"])),
                amount,
                Decimal("0"),
                running,
                row["created_at"],
                summary["已结转"],
            ))

        for row in usages:
            amount = Decimal(str(row["amount"]))
            running -= amount
            entries.append(self._ledger_row(
                f"U{int(row['id']):04d}",
                "使用",
                month_value,
                row["voucher_no"],
                row.get("spent_at", ""),
                row["purpose"],
                None,
                None,
                Decimal("0"),
                amount,
                running,
                row["created_at"],
                summary["已结转"],
            ))

        return {
            "module": "safetyfee",
            "month": month_value,
            "账期": month_value,
            "summary": summary,
            "total": len(entries),
            "items": entries,
        }

    def _ledger_row(
        self,
        entry_id: str,
        entry_type: str,
        month: str,
        voucher_no: str,
        spent_at: str,
        purpose: str,
        output: Decimal | None,
        rate_percent: Decimal | None,
        accrued: Decimal,
        used: Decimal,
        balance: Decimal,
        created_at: str,
        closed: bool,
    ) -> dict[str, Any]:
        closed_text = "已结转" if closed else "未结转"
        return {
            "id": entry_id,
            "明细编号": entry_id,
            "type": entry_type,
            "类型": entry_type,
            "month": month,
            "账期": month,
            "voucher_no": voucher_no,
            "财务支出凭证号": voucher_no,
            "spent_at": spent_at,
            "支出日期": spent_at,
            "purpose": purpose,
            "专项用途": purpose,
            "摘要": "按月度原煤产量和当时提取比例计提" if entry_type == "计提" else purpose,
            "raw_coal_output": _number_float(output) if output is not None else None,
            "原煤产量（吨）": _number_float(output) if output is not None else None,
            "rate_percent": _number_float(rate_percent) if rate_percent is not None else None,
            "提取比例（%）": _number_float(rate_percent) if rate_percent is not None else None,
            "accrued_amount": _money_float(accrued),
            "计提金额（元）": _money_float(accrued),
            "used_amount": _money_float(used),
            "使用金额（元）": _money_float(used),
            "closing_balance": _money_float(balance),
            "结余（元）": _money_float(balance),
            "created_at": created_at,
            "登记时间": created_at,
            "closed": closed,
            "结转状态": closed_text,
        }


service = SafetyFeeService()
