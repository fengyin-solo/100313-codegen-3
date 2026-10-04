"""矿山安全监测管理平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ROUTERS
from app.safety_fund.router import router as safety_fund_router
from app.safety_fund.seed import seed_if_empty
from app.safety_fund.service import service as safety_fund_service
from app.store import store


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # 安全费用台账走独立 SQLite 库，启动时建表并在空库时播种示例账期
    seed_if_empty()
    yield


app = FastAPI(title="矿山安全监测管理平台", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)

app.include_router(safety_fund_router)


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    return {"ok": True, "app": settings.app_name, "modules": len(store.module_names())}


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。"""
    data = store.overview()
    # 安全费用当前结余卡片：数值取自台账唯一口径，与台账页、对账文件同源
    balance = safety_fund_service.current_balance()
    data["cards"] = [
        {"label": "安全费用当前结余(元)", "value": balance["balanceYuan"]},
        *data["cards"],
    ]
    data["safetyFund"] = balance
    return data
