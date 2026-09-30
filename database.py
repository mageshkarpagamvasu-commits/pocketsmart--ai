"""SQLite storage for users and recommendation history."""
import json
import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "pocketsmart.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            budget REAL NOT NULL,
            inputs TEXT NOT NULL,
            result TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")


def get_user(username):
    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def create_user(username, email, password_hash):
    with get_conn() as c:
        c.execute("INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                  (username, email, password_hash))


def save_rec(user_id, category, budget, inputs, result):
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO recommendations (user_id, category, budget, inputs, result) VALUES (?,?,?,?,?)",
            (user_id, category, budget, json.dumps(inputs), json.dumps(result)))
        return cur.lastrowid


def list_recs(user_id, limit=50):
    with get_conn() as c:
        rows = c.execute("SELECT * FROM recommendations WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                         (user_id, limit)).fetchall()
    return [dict(r) for r in rows]


def get_rec(user_id, rec_id):
    with get_conn() as c:
        row = c.execute("SELECT * FROM recommendations WHERE id = ? AND user_id = ?",
                        (rec_id, user_id)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["inputs"] = json.loads(d["inputs"])
    d["result"] = json.loads(d["result"])
    return d
