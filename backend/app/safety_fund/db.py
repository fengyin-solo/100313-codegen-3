"""安全生产费用台账的持久层。

其余业务模块目前还跑在内存 Store 上，但安全费用台账有几条硬性要求：
使用登记与月末结转必须在同一事务里落地、同一凭证号只能认第一次、落库后
两边对不上就算失败。这些要求必须有真正的事务和唯一约束兜底，所以这里单独
引入 SQLite（只依赖标准库），不改动既有模块的内存仓库。

金额一律以「整数分」落库（amount_cents / rate_cents，rate_cents 表示元/吨
×100），产量以吨的实数落库，从根上避免不同地方用不同浮点口径。
"""
from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "safety_fund.db")

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;

-- 提取比例按生效账期留档；同一账期至多一条，历史比例不覆盖。
CREATE TABLE IF NOT EXISTS sf_rate (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    effective_month TEXT NOT NULL UNIQUE,  -- 生效账期，YYYY-MM，自该月起适用
    rate_cents     INTEGER NOT NULL CHECK (rate_cents > 0),  -- 提取标准（分/吨）
    note           TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 月度计提：登记当月按当时比例算出的应提金额，并把当时比例快照下来。
-- (month) 唯一保证同一账期只提一次；rate_cents 是留档字段，比例之后调整
-- 也不允许回改历史账期的这两个数字。
CREATE TABLE IF NOT EXISTS sf_accrual (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    month            TEXT NOT NULL UNIQUE,
    output_tonnes    REAL NOT NULL CHECK (output_tonnes >= 0),
    rate_cents       INTEGER NOT NULL,        -- 计提时适用比例的快照（分/吨）
    accrued_cents    INTEGER NOT NULL CHECK (accrued_cents >= 0),
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 专项使用逐笔登记。voucher_no 是财务支出凭证号，UNIQUE 约束兜底
-- 「同一笔支出凭证只认第一次」：重复登记在数据库层就插不进去。
CREATE TABLE IF NOT EXISTS sf_expenditure (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    month         TEXT NOT NULL,               -- 入账账期 YYYY-MM
    voucher_no    TEXT NOT NULL UNIQUE,
    category      TEXT NOT NULL,
    summary       TEXT NOT NULL,
    amount_cents  INTEGER NOT NULL CHECK (amount_cents > 0),
    used_at       TEXT NOT NULL,               -- 实际支出日期 YYYY-MM-DD
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sf_expenditure_month ON sf_expenditure(month);

-- 月末结转：一个账期至多结转一次，结转金额是当时计算结果的落档。
CREATE TABLE IF NOT EXISTS sf_close (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    month         TEXT NOT NULL UNIQUE,
    accrued_cents INTEGER NOT NULL,
    used_cents    INTEGER NOT NULL,
    balance_cents INTEGER NOT NULL,            -- 期末结余 = 期初 + 计提 - 使用
    detail_hash   TEXT NOT NULL,               -- 使用明细的口径指纹，导出对账用
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 被退回的重复凭证留痕：原样记录，不进结余、不进使用明细。
CREATE TABLE IF NOT EXISTS sf_expenditure_rejections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    month         TEXT NOT NULL,
    voucher_no    TEXT NOT NULL,
    payload_json  TEXT NOT NULL,
    reason        TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def db_path() -> str:
    """每次取连接时读环境变量，方便测试用 SF_DB_PATH 指到临时库。"""
    return os.environ.get("SF_DB_PATH", DEFAULT_DB_PATH)


def connect(database: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(database or db_path())
    conn.row_factory = sqlite3.Row
    # 开启外键约束；金额为整数运算，不需要关心浮点
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(database: str | None = None) -> None:
    """建表（幂等）。SQLite 的 execute 默认在隐式事务里，先关掉再执行 DDL。"""
    conn = connect(database)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """立即开启写事务（BEGIN IMMEDIATE 拿写锁），保证结转与登记串行落地。

    正常退出提交；业务校验失败抛异常时回滚，调用方拿到异常即可确认
    「一笔都没进去」。
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
