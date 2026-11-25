"""SQLite:存每次报修诊断的品类、故障、结论与明细。"""

from __future__ import annotations

import json
import os
import sqlite3
import threading

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "jiadian.db")


class Database:
    def __init__(self, path=None):
        self.path = path or os.environ.get("JIADIAN_DB") or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    appliance TEXT, symptoms TEXT, verdict TEXT,
                    estimate REAL, detail TEXT,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
                """
            )
            self.conn.commit()

    def save(self, r):
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO cases (appliance, symptoms, verdict, estimate, detail) VALUES (?,?,?,?,?)",
                (r["fault"]["name"], "、".join(r["symptoms"]), r["decision"]["verdict"],
                 r["estimate"]["high"], json.dumps(r, ensure_ascii=False)),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def latest(self, limit=10):
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, appliance, symptoms, verdict, estimate, created_at "
                "FROM cases ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
