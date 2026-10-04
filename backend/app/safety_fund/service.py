"""安全生产费用台账的业务规则与唯一口径来源。

设计要点（对应台账立账要求）：

1. 计提：应提金额 = 月度原煤产量 × 当时生效的提取比例，比例以快照形式落在
   sf_accrual.rate_cents 上。比例调整只是新增一条生效比例，历史账期已登记的
   应提金额永远不重算（历史账期按当时比例留档）。
2. 使用：逐笔登记专项支出；凭证号由数据库 UNIQUE 兜底，重复登记原样退回，
   金额绝不叠加进结余。
3. 口径单一来源：_month_detail() 是唯一一处从落库数据推导
   期初/计提/使用/结余 的函数。台账明细、对账导出、Dashboard 结余全部调它，
   不允许另一处另算一套。
4. 月末结转：本账期的使用登记与结余结转在同一个 BEGIN IMMEDIATE 事务里完成；
   提交前用独立推导复核，提交后换连接再复核一次，两边对不上就判失败。
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.safety_fund.db import connect, transaction

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
DATE_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


class LedgerError(Exception):
    """台账业务规则被违反；status 给出建议的 HTTP 状态码。"""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------- 金额口径

def yuan_to_cents(value: Any) -> int:
    """把入参金额转成整数分。禁止用浮点直接乘 100（0.1 类误差），统一走 Decimal。"""
    if value is None or str(value).strip() == "":
        raise LedgerError("金额不能为空")
    try:
        dec = Decimal(str(value).strip())
    except Exception:  # noqa: BLE001 - 非法金额统一给出可读错误
        raise LedgerError(f"金额格式不正确：{value}") from None
    if dec <= 0:
        raise LedgerError("金额必须大于 0")
    cents = (dec * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def rate_yuan_to_cents(value: Any) -> int:
    """提取比例（元/吨）转整数分/吨，必须为正数。"""
    if value is None or str(value).strip() == "":
        raise LedgerError("提取比例不能为空")
    try:
        dec = Decimal(str(value).strip())
    except Exception:  # noqa: BLE001
        raise LedgerError(f"提取比例格式不正确：{value}") from None
    if dec <= 0:
        raise LedgerError("提取比例必须大于 0")
    return int((dec * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_output_tonnes(value: Any) -> float:
    if value is None or str(value).strip() == "":
        raise LedgerError("月度原煤产量不能为空")
    try:
        tonnes = float(Decimal(str(value).strip()))
    except Exception:  # noqa: BLE001
        raise LedgerError(f"原煤产量格式不正确：{value}") from None
    if tonnes < 0:
        raise LedgerError("原煤产量不能为负")
    return tonnes


def cents_yuan(cents: int) -> str:
    """整数分转两位小数字符串——所有接口金额的统一出口。"""
    sign = "-" if cents < 0 else ""
    cents = abs(int(cents))
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def _calc_accrued(output_tonnes: float, rate_cents: int) -> int:
    """应提金额（分）= 产量(吨) × 比例(分/吨)，四舍五入到分。"""
    amount = (Decimal(str(output_tonnes)) * Decimal(rate_cents)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(amount)


def _valid_month(month: Any) -> str:
    month = str(month or "").strip()
    if not MONTH_RE.match(month):
        raise LedgerError("账期格式必须为 YYYY-MM")
    return month


# --------------------------------------------------------------------------- 序列化（明细的统一出口）

def _expenditure_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "month": row["month"],
        "voucherNo": row["voucher_no"],
        "category": row["category"],
        "summary": row["summary"],
        "amountYuan": cents_yuan(row["amount_cents"]),
        "amountCents": row["amount_cents"],
        "usedAt": row["used_at"],
        "createdAt": row["created_at"],
    }


EXPENDITURE_EXPORT_COLUMNS = [
    ("month", "账期"),
    ("voucherNo", "凭证号"),
    ("usedAt", "支出日期"),
    ("category", "专项类别"),
    ("summary", "支出摘要"),
    ("amountYuan", "金额(元)"),
]


def expenditure_detail_hash(items: list[dict[str, Any]]) -> str:
    """使用明细的口径指纹：逐笔登记的 id 与金额定序后取 SHA-256。

    结转时算一次存档；导出对账时重算一次，不一致就说明导出口径与台账明细
    发生了偏离，直接判失败而不是出一份对不上的对账文件。
    """
    basis = [{"id": it["id"], "voucherNo": it["voucherNo"], "amountCents": it["amountCents"]} for it in items]
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SafetyFundService:
    # ---------------------------------------------------------------- 比例管理
    def list_rates(self) -> list[dict[str, Any]]:
        conn = connect()
        try:
            rows = conn.execute(
                "SELECT * FROM sf_rate ORDER BY effective_month, id"
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "effectiveMonth": r["effective_month"],
                    "rateYuan": cents_yuan(r["rate_cents"]),
                    "rateCents": r["rate_cents"],
                    "note": r["note"],
                    "createdAt": r["created_at"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def current_rate(self, month: str) -> dict[str, Any]:
        """取某账期生效的比例：effective_month <= month 的最新一条。

        比例调整只新增生效记录，因此查询天然是「调整只影响之后的账期」。
        """
        month = _valid_month(month)
        conn = connect()
        try:
            row = conn.execute(
                "SELECT * FROM sf_rate WHERE effective_month <= ? ORDER BY effective_month DESC, id DESC LIMIT 1",
                (month,),
            ).fetchone()
            if row is None:
                raise LedgerError(f"账期 {month} 尚无生效的提取比例，请先设立提取比例", status=409)
            return {
                "id": row["id"],
                "effectiveMonth": row["effective_month"],
                "rateCents": row["rate_cents"],
                "rateYuan": cents_yuan(row["rate_cents"]),
            }
        finally:
            conn.close()

    def register_rate(self, effective_month: Any, rate_yuan: Any, note: str | None = None) -> dict[str, Any]:
        """登记一条新的提取比例。同一账期重复登记被拒绝——比例留档不覆盖。"""
        month = _valid_month(effective_month)
        rate_cents = rate_yuan_to_cents(rate_yuan)
        conn = connect()
        try:
            with transaction(conn):
                exists = conn.execute(
                    "SELECT id FROM sf_rate WHERE effective_month = ?", (month,)
                ).fetchone()
                if exists is not None:
                    raise LedgerError(
                        f"账期 {month} 已登记过提取比例；比例调整请选择新的生效账期，"
                        "历史比例与历史账期数字保持不变",
                        status=409,
                    )
                try:
                    cur = conn.execute(
                        "INSERT INTO sf_rate (effective_month, rate_cents, note) VALUES (?, ?, ?)",
                        (month, rate_cents, note),
                    )
                except sqlite3.IntegrityError:
                    # 并发下唯一约束兜底
                    raise LedgerError(f"账期 {month} 的提取比例已存在，历史比例不覆盖", status=409) from None
                row = conn.execute("SELECT * FROM sf_rate WHERE id = ?", (cur.lastrowid,)).fetchone()
            return {
                "id": row["id"],
                "effectiveMonth": row["effective_month"],
                "rateYuan": cents_yuan(row["rate_cents"]),
                "note": row["note"],
                "createdAt": row["created_at"],
            }
        finally:
            conn.close()

    # ---------------------------------------------------------------- 月度计提
    def register_accrual(self, month: Any, output_tonnes: Any) -> dict[str, Any]:
        """按当月原煤产量 × 当时比例登记当月应提金额。

        比例与应提金额都做快照：登记后即便比例调整，这一账期的数字保持原值。
        """
        month = _valid_month(month)
        tonnes = parse_output_tonnes(output_tonnes)
        conn = connect()
        try:
            with transaction(conn):
                closed = conn.execute(
                    "SELECT id FROM sf_close WHERE month = ?", (month,)
                ).fetchone()
                if closed is not None:
                    raise LedgerError(f"账期 {month} 已月末结转，计提数字已封档，不能再登记", status=409)
                exists = conn.execute(
                    "SELECT id FROM sf_accrual WHERE month = ?", (month,)
                ).fetchone()
                if exists is not None:
                    raise LedgerError(f"账期 {month} 已计提，一个账期只能计提一次", status=409)
                rate_row = conn.execute(
                    "SELECT * FROM sf_rate WHERE effective_month <= ? "
                    "ORDER BY effective_month DESC, id DESC LIMIT 1",
                    (month,),
                ).fetchone()
                if rate_row is None:
                    raise LedgerError(f"账期 {month} 尚无生效的提取比例，请先设立提取比例", status=409)
                accrued = _calc_accrued(tonnes, rate_row["rate_cents"])
                try:
                    cur = conn.execute(
                        "INSERT INTO sf_accrual (month, output_tonnes, rate_cents, accrued_cents) "
                        "VALUES (?, ?, ?, ?)",
                        (month, tonnes, rate_row["rate_cents"], accrued),
                    )
                except sqlite3.IntegrityError:
                    raise LedgerError(f"账期 {month} 已计提，一个账期只能计提一次", status=409) from None
                row = conn.execute("SELECT * FROM sf_accrual WHERE id = ?", (cur.lastrowid,)).fetchone()
            return self._accrual_dict(row)
        finally:
            conn.close()

    @staticmethod
    def _accrual_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "month": row["month"],
            "outputTonnes": round(float(row["output_tonnes"]), 3),
            "rateYuan": cents_yuan(row["rate_cents"]),
            "rateCents": row["rate_cents"],
            "accruedYuan": cents_yuan(row["accrued_cents"]),
            "accruedCents": row["accrued_cents"],
            "createdAt": row["created_at"],
        }

    # ---------------------------------------------------------------- 使用登记
    def register_expenditure(
        self,
        month: Any,
        voucher_no: Any,
        category: Any,
        summary: Any,
        amount_yuan: Any,
        used_at: Any,
    ) -> dict[str, Any]:
        """逐笔登记一笔专项使用。重复凭证号原样退回（409），不写明细、不碰结余。"""
        month = _valid_month(month)
        voucher_no = str(voucher_no or "").strip()
        category = str(category or "").strip()
        summary = str(summary or "").strip()
        used_at = str(used_at or "").strip()
        if not voucher_no:
            raise LedgerError("财务支出凭证号不能为空")
        if not category:
            raise LedgerError("专项类别不能为空")
        if not summary:
            raise LedgerError("支出摘要不能为空")
        if not DATE_RE.match(used_at):
            raise LedgerError("支出日期格式必须为 YYYY-MM-DD")
        if not used_at.startswith(month):
            raise LedgerError(f"支出日期 {used_at} 不属于入账账期 {month}")
        amount_cents = yuan_to_cents(amount_yuan)

        conn = connect()
        try:
            with transaction(conn):
                self._assert_month_open_for_use(conn, month)
                payload = {
                    "month": month,
                    "voucherNo": voucher_no,
                    "category": category,
                    "summary": summary,
                    "amountYuan": cents_yuan(amount_cents),
                    "usedAt": used_at,
                }
                try:
                    cur = conn.execute(
                        "INSERT INTO sf_expenditure (month, voucher_no, category, summary, amount_cents, used_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (month, voucher_no, category, summary, amount_cents, used_at),
                    )
                except sqlite3.IntegrityError:
                    # 唯一约束兜底：同凭证号第二次到，原样退回，绝不叠加进结余
                    prior = conn.execute(
                        "SELECT * FROM sf_expenditure WHERE voucher_no = ?", (voucher_no,)
                    ).fetchone()
                    conn.execute(
                        "INSERT INTO sf_expenditure_rejections (month, voucher_no, payload_json, reason) "
                        "VALUES (?, ?, ?, ?)",
                        (
                            month,
                            voucher_no,
                            json.dumps(payload, ensure_ascii=False),
                            "凭证号已登记，重复提交原样退回",
                        ),
                    )
                    raise LedgerError(
                        f"凭证号 {voucher_no} 已在 {prior['month']} 登记（金额 {cents_yuan(prior['amount_cents'])} 元），"
                        "同一笔财务支出凭证只认第一次，本次原样退回，未计入结余",
                        status=409,
                    )
                row = conn.execute("SELECT * FROM sf_expenditure WHERE id = ?", (cur.lastrowid,)).fetchone()
            return _expenditure_to_dict(row)
        finally:
            conn.close()

    @staticmethod
    def _assert_month_open_for_use(conn: sqlite3.Connection, month: str) -> None:
        closed = conn.execute("SELECT id FROM sf_close WHERE month = ?", (month,)).fetchone()
        if closed is not None:
            raise LedgerError(f"账期 {month} 已月末结转封档，不能再补登使用明细", status=409)
        accrual = conn.execute("SELECT id FROM sf_accrual WHERE month = ?", (month,)).fetchone()
        if accrual is None:
            raise LedgerError(f"账期 {month} 尚未计提，请先按产量登记当月计提，再登记使用", status=409)

    def list_expenditures(self, month: str | None = None) -> list[dict[str, Any]]:
        month = _valid_month(month) if month else None
        conn = connect()
        try:
            if month:
                rows = conn.execute(
                    "SELECT * FROM sf_expenditure WHERE month = ? ORDER BY id", (month,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM sf_expenditure ORDER BY month, id").fetchall()
            return [_expenditure_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ---------------------------------------------------------------- 唯一口径：月台账
    def month_detail(self, month: Any) -> dict[str, Any]:
        """某账期台账明细与结余的唯一计算口径，台账页/导出/结余共用。"""
        month = _valid_month(month)
        conn = connect()
        try:
            return self._month_detail_conn(conn, month)
        finally:
            conn.close()

    def _month_detail_conn(self, conn: sqlite3.Connection, month: str) -> dict[str, Any]:
        accrual_row = conn.execute(
            "SELECT * FROM sf_accrual WHERE month = ?", (month,)
        ).fetchone()
        exp_rows = conn.execute(
            "SELECT * FROM sf_expenditure WHERE month = ? ORDER BY id", (month,)
        ).fetchall()
        close_row = conn.execute(
            "SELECT * FROM sf_close WHERE month = ?", (month,)
        ).fetchone()

        prior_close = conn.execute(
            "SELECT * FROM sf_close WHERE month < ? ORDER BY month DESC LIMIT 1", (month,)
        ).fetchone()
        opening_cents = prior_close["balance_cents"] if prior_close else 0

        accrued_cents = accrual_row["accrued_cents"] if accrual_row else 0
        items = [_expenditure_to_dict(r) for r in exp_rows]
        used_cents = sum(it["amountCents"] for it in items)
        balance_cents = opening_cents + accrued_cents - used_cents

        return {
            "month": month,
            "status": "closed" if close_row else "open",
            "openingYuan": cents_yuan(opening_cents),
            "openingCents": opening_cents,
            "accrual": self._accrual_dict(accrual_row) if accrual_row else None,
            "accruedYuan": cents_yuan(accrued_cents),
            "accruedCents": accrued_cents,
            "usedYuan": cents_yuan(used_cents),
            "usedCents": used_cents,
            "balanceYuan": cents_yuan(balance_cents),
            "balanceCents": balance_cents,
            "items": items,
            "closedAt": close_row["created_at"] if close_row else None,
            "detailHash": close_row["detail_hash"] if close_row else expenditure_detail_hash(items),
        }

    def list_months(self) -> list[dict[str, Any]]:
        """账期清单：所有计提过或已结转的账期，数字全部取自同一套口径。"""
        conn = connect()
        try:
            months = {
                r["month"]
                for r in conn.execute("SELECT month FROM sf_accrual").fetchall()
            }
            months.update(r["month"] for r in conn.execute("SELECT month FROM sf_close").fetchall())
            return [self._month_detail_conn(conn, m) for m in sorted(months)]
        finally:
            conn.close()

    # ---------------------------------------------------------------- 当前结余（Dashboard 同源）
    def current_balance(self) -> dict[str, Any]:
        """当前结余：最新已结转账期的期末结余，加上其后未结转账期的净发生额。

        只做「把各月 _month_detail_conn 串起来」一件事，不另算口径。
        """
        conn = connect()
        try:
            months = {
                r["month"]
                for r in conn.execute("SELECT month FROM sf_accrual").fetchall()
            }
            months.update(r["month"] for r in conn.execute("SELECT month FROM sf_expenditure").fetchall())
            months.update(r["month"] for r in conn.execute("SELECT month FROM sf_close").fetchall())
            if not months:
                latest_closed = None
                balance = 0
            else:
                latest_closed_row = conn.execute(
                    "SELECT month FROM sf_close ORDER BY month DESC LIMIT 1"
                ).fetchone()
                latest_closed = latest_closed_row["month"] if latest_closed_row else None
                balance = 0
                for month in sorted(months):
                    detail = self._month_detail_conn(conn, month)
                    balance = detail["balanceCents"]
            as_of = max(months) if months else None
            return {
                "balanceYuan": cents_yuan(balance),
                "balanceCents": balance,
                "latestClosedMonth": latest_closed,
                "asOfMonth": as_of,
            }
        finally:
            conn.close()

    # ---------------------------------------------------------------- 月末结转（同事务）
    def close_month(
        self,
        month: Any,
        expenditures: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """月末结转：把本账期待登记的使用与结余结转放在同一事务落地。

        - expenditures 内若混入已登记凭证号，整笔事务回滚（要么一起进，要么都不进）；
        - 提交前用独立推导复核 期初+计提-使用=结余、明细合计=使用；
        - 提交后换一个连接再复核一遍落库结果，并校验明细指纹，两边对不上判失败。
        """
        month = _valid_month(month)
        expenditures = expenditures or []
        prepared: list[tuple[str, str, str, int, str]] = []
        seen_in_batch: set[str] = set()
        raw_payloads: list[dict[str, Any]] = []
        for raw in expenditures:
            voucher_no = str(raw.get("voucherNo") or raw.get("voucher_no") or "").strip()
            category = str(raw.get("category") or "").strip()
            summary = str(raw.get("summary") or "").strip()
            used_at = str(raw.get("usedAt") or raw.get("used_at") or "").strip()
            if not voucher_no or not category or not summary or not used_at:
                raise LedgerError("结转批量中存在字段不完整的使用登记（凭证号/类别/摘要/日期均必填）")
            if not DATE_RE.match(used_at) or not used_at.startswith(month):
                raise LedgerError(f"凭证 {voucher_no} 的支出日期 {used_at} 不属于账期 {month}")
            if voucher_no in seen_in_batch:
                raise LedgerError(f"本批结转里凭证号 {voucher_no} 出现多次，拒绝登记")
            seen_in_batch.add(voucher_no)
            amount_cents = yuan_to_cents(raw.get("amountYuan", raw.get("amount_yuan")))
            prepared.append((month, voucher_no, category, summary, amount_cents, used_at))
            raw_payloads.append(
                {"month": month, "voucherNo": voucher_no, "category": category,
                 "summary": summary, "amountYuan": cents_yuan(amount_cents), "usedAt": used_at}
            )

        conn = connect()
        try:
            with transaction(conn):
                # 结转必须按月顺序走，避免期初来源出现空洞
                prior_months = {
                    r["month"] for r in conn.execute(
                        "SELECT month FROM sf_accrual WHERE month < ?", (month,)
                    ).fetchall()
                }
                prior_months.update(
                    r["month"] for r in conn.execute(
                        "SELECT month FROM sf_expenditure WHERE month < ?", (month,)
                    ).fetchall()
                )
                earlier_open = sorted(
                    m for m in prior_months
                    if conn.execute("SELECT id FROM sf_close WHERE month = ?", (m,)).fetchone() is None
                )
                if earlier_open:
                    raise LedgerError(
                        f"账期 {earlier_open[0]} 尚未结转，不能先结转 {month}，请按月顺序结转", status=409
                    )
                if conn.execute("SELECT id FROM sf_close WHERE month = ?", (month,)).fetchone():
                    raise LedgerError(f"账期 {month} 已结转封档，不能重复结转", status=409)
                accrual_row = conn.execute(
                    "SELECT * FROM sf_accrual WHERE month = ?", (month,)
                ).fetchone()
                if accrual_row is None:
                    raise LedgerError(f"账期 {month} 尚未计提，无法结转", status=409)

                # 批量里只要有一张凭证已登记过，整批失败回滚，原样退回
                for payload in raw_payloads:
                    dup = conn.execute(
                        "SELECT id, month FROM sf_expenditure WHERE voucher_no = ?",
                        (payload["voucherNo"],),
                    ).fetchone()
                    if dup is not None:
                        conn.execute(
                            "INSERT INTO sf_expenditure_rejections (month, voucher_no, payload_json, reason) "
                            "VALUES (?, ?, ?, ?)",
                            (month, payload["voucherNo"],
                             json.dumps(payload, ensure_ascii=False),
                             f"凭证号已于 {dup['month']} 登记，结转批量整体退回"),
                        )
                        raise LedgerError(
                            f"凭证号 {payload['voucherNo']} 已在 {dup['month']} 登记，"
                            "本批使用登记原样退回，结转未执行、结余未变动",
                            status=409,
                        )

                for entry in prepared:
                    conn.execute(
                        "INSERT INTO sf_expenditure (month, voucher_no, category, summary, amount_cents, used_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        entry,
                    )

                # 提交前复核：用唯一口径在同一事务内重算
                detail = self._month_detail_conn(conn, month)
                self._assert_invariants(conn, month, detail)
                detail_hash = expenditure_detail_hash(detail["items"])

                cur = conn.execute(
                    "INSERT INTO sf_close (month, accrued_cents, used_cents, balance_cents, detail_hash) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (month, detail["accruedCents"], detail["usedCents"], detail["balanceCents"], detail_hash),
                )
                close_id = cur.lastrowid

            # 提交后复核：换一个连接读已落库的结果，两边对不上就判失败
            check = connect()
            try:
                committed_detail = self._month_detail_conn(check, month)
                close_row = check.execute(
                    "SELECT * FROM sf_close WHERE id = ?", (close_id,)
                ).fetchone()
                if close_row is None:
                    raise LedgerError("结转记录提交后读取失败，判定本次结转失败", status=500)
                self._assert_invariants(check, month, committed_detail)
                if close_row["balance_cents"] != committed_detail["balanceCents"]:
                    raise LedgerError(
                        "落库后两边对不上：结转结余与台账推导结余不一致，判定结转失败", status=500
                    )
                if close_row["detail_hash"] != expenditure_detail_hash(committed_detail["items"]):
                    raise LedgerError(
                        "落库后两边对不上：使用明细与结转时留档不一致，判定结转失败", status=500
                    )
            finally:
                check.close()
            return committed_detail
        finally:
            conn.close()

    @staticmethod
    def _assert_invariants(conn: sqlite3.Connection, month: str, detail: dict[str, Any]) -> None:
        """独立推导一遍恒等式，与批量/明细结果交叉比对。"""
        prior = conn.execute(
            "SELECT balance_cents FROM sf_close WHERE month < ? ORDER BY month DESC LIMIT 1",
            (month,),
        ).fetchone()
        opening = prior["balance_cents"] if prior else 0
        accrued = conn.execute(
            "SELECT COALESCE(SUM(accrued_cents), 0) AS v FROM sf_accrual WHERE month = ?",
            (month,),
        ).fetchone()["v"]
        used = conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) AS v FROM sf_expenditure WHERE month = ?",
            (month,),
        ).fetchone()["v"]
        expected_balance = opening + accrued - used
        if detail["openingCents"] != opening:
            raise LedgerError("结转复核失败：期初结余与上一账期期末不一致")
        if detail["accruedCents"] != accrued:
            raise LedgerError("结转复核失败：计提合计与计提登记不一致")
        if detail["usedCents"] != used:
            raise LedgerError("结转复核失败：使用合计与逐笔明细不一致")
        if detail["balanceCents"] != expected_balance:
            raise LedgerError("结转复核失败：期初+计提-使用≠结余")

    # ---------------------------------------------------------------- 对账导出（与台账同源）
    def reconciliation(self, month: Any) -> dict[str, Any]:
        """月度对账文件数据：直接拿台账月明细，不另算一套口径。

        返回的 items 就是 _month_detail_conn 里的同一批对象，并在导出前再做一次
        口径自检（明细合计=使用、指纹=结转留档），不通过就报错而不是出假对账文件。
        """
        month = _valid_month(month)
        conn = connect()
        try:
            detail = self._month_detail_conn(conn, month)
        finally:
            conn.close()

        items_sum = sum(it["amountCents"] for it in detail["items"])
        if items_sum != detail["usedCents"]:
            raise LedgerError("对账自检失败：导出明细合计与台账使用金额不一致", status=500)
        if detail["status"] == "closed":
            conn = connect()
            try:
                close_row = conn.execute(
                    "SELECT detail_hash FROM sf_close WHERE month = ?", (month,)
                ).fetchone()
            finally:
                conn.close()
            if close_row and close_row["detail_hash"] != expenditure_detail_hash(detail["items"]):
                raise LedgerError("对账自检失败：导出明细与结转留档口径不一致", status=500)
        return detail


# 单例：路由层共享同一套口径
service = SafetyFundService()
