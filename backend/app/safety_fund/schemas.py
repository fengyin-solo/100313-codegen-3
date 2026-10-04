"""安全生产费用台账接口出入参模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RatePayload(BaseModel):
    effectiveMonth: str = Field(description="生效账期 YYYY-MM，自该月起适用")
    rateYuan: float | str = Field(description="提取比例（元/吨）")
    note: str | None = None


class AccrualPayload(BaseModel):
    month: str
    outputTonnes: float | str = Field(description="当月原煤产量（吨）")


class ExpenditurePayload(BaseModel):
    month: str
    voucherNo: str = Field(description="财务支出凭证号")
    category: str = Field(description="专项类别")
    summary: str = Field(description="支出摘要")
    amountYuan: float | str
    usedAt: str = Field(description="实际支出日期 YYYY-MM-DD")


class ClosePayload(BaseModel):
    month: str
    # 随结转一起入账的使用明细；为空表示该月使用此前已逐笔登记完，仅做结转
    expenditures: list[dict[str, Any]] = Field(default_factory=list)
