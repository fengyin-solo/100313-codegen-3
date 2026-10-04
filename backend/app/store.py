"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any

from app.seed import SEED_ROWS

SAFETY_FEE_TABLES = [
    "safetyfee_rates",
    "safetyfee_accruals",
    "safetyfee_usages",
    "safetyfee_closures",
]


class Transaction:
    """同一把锁内的内存事务：异常退出时整体恢复到事务前。"""

    def __init__(self, owner: "Store") -> None:
        self._owner = owner
        self._nested = False

    def __enter__(self) -> "Transaction":
        self._owner._lock.acquire()
        self._nested = self._owner._transaction_depth > 0
        if not self._nested:
            self._owner._snapshot = deepcopy(self._owner._tables)
        self._owner._transaction_depth += 1
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        try:
            if not self._nested:
                if exc_type is not None:
                    self._owner._tables = deepcopy(self._owner._snapshot)
                self._owner._snapshot = None
        finally:
            self._owner._transaction_depth -= 1
            self._owner._lock.release()


class Store:
    def __init__(self) -> None:
        self._lock = RLock()
        self._transaction_depth = 0
        self._snapshot: dict[str, list[dict[str, Any]]] | None = None
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        for name in SAFETY_FEE_TABLES:
            self._tables.setdefault(name, [])

    def transaction(self) -> Transaction:
        return Transaction(self)

    def module_names(self) -> list[str]:
        return sorted(name for name in self._tables if name not in SAFETY_FEE_TABLES)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        from app.services.safetyfee import service as safetyfee_service

        latest_summary = safetyfee_service.monthly_summary()
        cards.append({"label": "安全费用期末结余（元）", "value": latest_summary["closing_balance"]})
        return {"cards": cards, "modules": modules}


store = Store()
