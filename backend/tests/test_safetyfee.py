"""安全生产费用台账的关键业务规则测试。"""
from __future__ import annotations

from typing import Any
from unittest import TestCase

from app.services.safetyfee import (
    ACCRUAL_TABLE,
    CLOSURE_TABLE,
    RATE_TABLE,
    USAGE_TABLE,
    SafetyFeeError,
    service,
)
from app.store import store

TABLES = [RATE_TABLE, ACCRUAL_TABLE, USAGE_TABLE, CLOSURE_TABLE]


def values(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


class SafetyFeeServiceTest(TestCase):
    def setUp(self) -> None:
        for table in TABLES:
            store.rows(table).clear()

    def tearDown(self) -> None:
        for table in TABLES:
            store.rows(table).clear()

    def test_monthly_extraction_uses_period_rate_and_keeps_history(self) -> None:
        rate, message = service.create_rate(values({
            "生效账期": "2026-01",
            "提取比例（%）": "1.5",
        }))
        self.assertIsNotNone(rate, message)

        january, message = service.accrue(values({
            "账期": "2026-01",
            "原煤产量（吨）": "10000",
        }))
        self.assertIsNotNone(january, message)
        self.assertEqual(january["提取比例（%）"], 1.5)
        self.assertEqual(january["计提金额（元）"], 150.0)

        self.assertIsNotNone(service.close_month(values({"账期": "2026-01"})))

        new_rate, _ = service.create_rate(values({
            "生效账期": "2026-02",
            "提取比例（%）": "2",
        }))
        self.assertIsNotNone(new_rate)

        duplicate_rate, _ = service.create_rate(values({
            "生效账期": "2026-01",
            "提取比例（%）": "3",
        }))
        self.assertIsNone(duplicate_rate)

        february, _ = service.accrue(values({
            "账期": "2026-02",
            "原煤产量（吨）": "5000",
        }))
        self.assertEqual(february["计提金额（元）"], 100.0)
        self.assertEqual(service.list_accruals("2026-01")[0]["计提金额（元）"], 150.0)

    def test_duplicate_voucher_is_rejected_without_changing_balance(self) -> None:
        self.assertIsNotNone(service.create_rate(values({
            "生效账期": "2026-01",
            "提取比例（%）": "1",
        }))[0])
        self.assertIsNotNone(service.accrue(values({
            "账期": "2026-01",
            "原煤产量（吨）": "10000",
        }))[0])

        first, message, _, existing = service.register_usage(values({
            "账期": "2026-01",
            "财务支出凭证号": "PZ-001",
            "专项用途": "瓦斯监测设备",
            "使用金额（元）": "30.50",
        }))
        self.assertIsNotNone(first, message)
        self.assertIsNone(existing)

        duplicate, message, received, existing = service.register_usage(values({
            "账期": "2026-01",
            "财务支出凭证号": "PZ-001",
            "专项用途": "重复提交",
            "使用金额（元）": "999",
        }))
        self.assertIsNone(duplicate)
        self.assertIn("原样退回", message)
        self.assertEqual(received["专项用途"], "重复提交")
        self.assertEqual(existing["专项用途"], "瓦斯监测设备")
        self.assertEqual(len(store.rows(USAGE_TABLE)), 1)
        self.assertEqual(service.monthly_summary("2026-01")["期末结余"], 69.5)

    def test_export_uses_same_snapshot_as_ledger_and_balance(self) -> None:
        self.assertIsNotNone(service.create_rate(values({
            "生效账期": "2026-01",
            "提取比例（%）": "1.5",
        }))[0])
        self.assertIsNotNone(service.accrue(values({
            "账期": "2026-01",
            "原煤产量（吨）": "10000",
        }))[0])
        self.assertIsNotNone(service.register_usage(values({
            "账期": "2026-01",
            "财务支出凭证号": "PZ-002",
            "专项用途": "防尘设施",
            "使用金额（元）": "20",
        }))[0])

        ledger = service.reconciliation("2026-01")
        exported = service.reconciliation("2026-01")
        balance = service.monthly_summary("2026-01")

        self.assertEqual(ledger["items"], exported["items"])
        self.assertEqual(ledger["summary"], balance)
        self.assertEqual(ledger["items"][-1]["结余（元）"], balance["期末结余"])

    def test_close_month_registers_usages_and_rolls_back_on_failure(self) -> None:
        self.assertIsNotNone(service.create_rate(values({
            "生效账期": "2026-01",
            "提取比例（%）": "1",
        }))[0])
        self.assertIsNotNone(service.accrue(values({
            "账期": "2026-01",
            "原煤产量（吨）": "10000",
        }))[0])

        with self.assertRaises(SafetyFeeError):
            service.close_month(values({
                "账期": "2026-01",
                "使用明细": [
                    {
                        "财务支出凭证号": "VALID",
                        "专项用途": "应急装备",
                        "使用金额（元）": "10",
                    },
                    {
                        "财务支出凭证号": "INVALID",
                        "专项用途": "错误支出",
                        "使用金额（元）": "-5",
                    },
                ],
            }))

        self.assertEqual(store.rows(USAGE_TABLE), [])
        self.assertEqual(store.rows(CLOSURE_TABLE), [])
        self.assertEqual(service.monthly_summary("2026-01")["期末结余"], 100.0)

        result = service.close_month(values({
            "账期": "2026-01",
            "使用明细": [
                {
                    "财务支出凭证号": "DUP",
                    "专项用途": "安全培训",
                    "使用金额（元）": "40",
                },
                {
                    "财务支出凭证号": "DUP",
                    "专项用途": "重复凭证",
                    "使用金额（元）": "80",
                },
            ],
        }))
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["registered"]), 1)
        self.assertEqual(len(result["rejected"]), 1)
        self.assertEqual(result["closure"]["closing_balance"], 60.0)


if __name__ == "__main__":
    from unittest import main

    main()
