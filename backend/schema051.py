"""MVP 0.5.1: nondestructive compatibility migration for older exercise fixtures.

Real AgentChess CDB databases already contain tree_json. Earlier unit-test
SQLite fixtures may omit it. Never invent or overwrite author solution data.
"""
from __future__ import annotations
import sqlite3


def ensure_tree_json_column(db):
    """Add nullable CDB tree column if missing; preserve all existing records.

    Safe to call repeatedly on the same file. Only schema is changed; it does
    not backfill or manufacture author variations.
    """
    with sqlite3.connect(str(db), timeout=60) as c:
        columns = {row[1] for row in c.execute('PRAGMA table_info(cdb_records)')}
        if not columns:
            raise RuntimeError('Не знайдено таблицю cdb_records')
        if 'tree_json' not in columns:
            c.execute('ALTER TABLE cdb_records ADD COLUMN tree_json TEXT')
            return True
    return False
