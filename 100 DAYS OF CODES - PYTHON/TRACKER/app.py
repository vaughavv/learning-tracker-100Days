"""
100 Days of Code – Python Learning Tracker
==========================================
Pure Python standard library implementation.
No pip installs required.

Run with:  python app.py
Then open: http://127.0.0.1:8000
"""

import sqlite3
import json
import os
import shutil
import webbrowser
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path
from datetime import datetime, date

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR   = Path(__file__).parent          # TRACKER/
DB_DIR     = BASE_DIR / "database"
DB_PATH    = DB_DIR / "tracker.db"
BACKUP_DIR = DB_DIR / "backups"
STATIC_DIR = BASE_DIR / "static"
CODES_DIR  = BASE_DIR.parent / "CODES"     # ../CODES  (read-only)

DB_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

def get_db():
    """Open a SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row          # rows behave like dicts
    conn.execute("PRAGMA journal_mode=WAL")  # allow concurrent reads+writes
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")  # wait up to 30s on lock
    return conn


def init_db():
    """
    Create all tables on first run.
    If the database already exists this function is safe – it uses
    CREATE TABLE IF NOT EXISTS so existing data is never destroyed.
    """
    conn = get_db()
    cur  = conn.cursor()

    # --- course_days ---------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS course_days (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            day_number       INTEGER UNIQUE NOT NULL,
            title            TEXT    NOT NULL DEFAULT '',
            description      TEXT    NOT NULL DEFAULT '',
            status           TEXT    NOT NULL DEFAULT 'not_started'
                                     CHECK(status IN ('not_started','in_progress','completed')),
            completion_date  TEXT,
            difficulty       INTEGER CHECK(difficulty BETWEEN 1 AND 5),
            understanding    INTEGER CHECK(understanding BETWEEN 1 AND 5),
            confusion_notes  TEXT    NOT NULL DEFAULT '',
            revision_notes   TEXT    NOT NULL DEFAULT '',
            favorite_learning TEXT   NOT NULL DEFAULT '',
            needs_revision   INTEGER NOT NULL DEFAULT 0,
            revised_at       TEXT,
            created_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)

    # --- study_sessions ------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS study_sessions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            day_id           INTEGER NOT NULL REFERENCES course_days(id) ON DELETE CASCADE,
            started_at       TEXT    NOT NULL,
            ended_at         TEXT,
            duration_seconds INTEGER
        )
    """)

    # --- topics --------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE
        )
    """)

    # --- day_topics ----------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS day_topics (
            day_id   INTEGER NOT NULL REFERENCES course_days(id) ON DELETE CASCADE,
            topic_id INTEGER NOT NULL REFERENCES topics(id)      ON DELETE CASCADE,
            PRIMARY KEY (day_id, topic_id)
        )
    """)

    # --- day_files -----------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS day_files (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            day_id      INTEGER NOT NULL REFERENCES course_days(id) ON DELETE CASCADE,
            file_path   TEXT    NOT NULL,
            description TEXT    NOT NULL DEFAULT '',
            UNIQUE(day_id, file_path)
        )
    """)

    conn.commit()

    # Seed days 1-100 if they don't exist yet
    for n in range(1, 101):
        cur.execute(
            "INSERT OR IGNORE INTO course_days (day_number) VALUES (?)", (n,)
        )
    conn.commit()
    conn.close()
    print("[DB] Database ready:", DB_PATH)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row) if row else None


def rows_to_list(rows):
    """Convert a list of sqlite3.Row objects to a list of dicts."""
    return [dict(r) for r in rows]


def json_response(data, status=200):
    """Serialise data to JSON bytes ready for an HTTP response."""
    return json.dumps(data, default=str).encode("utf-8")


def parse_body(handler):
    """Read and parse a JSON request body."""
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}

# ---------------------------------------------------------------------------
# API handlers
# ---------------------------------------------------------------------------

def api_get_stats(query_params):
    """Dashboard statistics – computed entirely in Python / SQLite."""
    conn = get_db()
    cur  = conn.cursor()

    cur.execute("SELECT COUNT(*) AS n FROM course_days WHERE status='completed'")
    completed = cur.fetchone()["n"]

    cur.execute("SELECT COUNT(*) AS n FROM course_days WHERE needs_revision=1 AND revised_at IS NULL")
    needs_revision = cur.fetchone()["n"]

    cur.execute("SELECT COALESCE(SUM(duration_seconds),0) AS t FROM study_sessions WHERE ended_at IS NOT NULL")
    total_secs = cur.fetchone()["t"]

    cur.execute("SELECT COUNT(DISTINCT topic_id) AS n FROM day_topics")
    topic_count = cur.fetchone()["n"]

    cur.execute("""
        SELECT cd.day_number, cd.title,
               COALESCE(SUM(ss.duration_seconds),0) AS day_secs
        FROM course_days cd
        LEFT JOIN study_sessions ss ON ss.day_id=cd.id AND ss.ended_at IS NOT NULL
        WHERE cd.status='completed'
        GROUP BY cd.id
        ORDER BY day_secs DESC LIMIT 1
    """)
    longest_row = cur.fetchone()
    longest = row_to_dict(longest_row) if longest_row else None

    avg_secs = (total_secs // completed) if completed else 0

    # Recent completed days
    cur.execute("""
        SELECT cd.day_number, cd.title,
               COALESCE(SUM(ss.duration_seconds),0) AS day_secs
        FROM course_days cd
        LEFT JOIN study_sessions ss ON ss.day_id=cd.id AND ss.ended_at IS NOT NULL
        WHERE cd.status='completed'
        GROUP BY cd.id
        ORDER BY cd.completion_date DESC, cd.day_number DESC
        LIMIT 5
    """)
    recent = rows_to_list(cur.fetchall())

    # Revision queue
    cur.execute("""
        SELECT cd.day_number, cd.title, cd.revision_notes
        FROM course_days cd
        WHERE cd.needs_revision=1 AND cd.revised_at IS NULL
        ORDER BY cd.day_number
    """)
    revision_queue = rows_to_list(cur.fetchall())

    conn.close()

    def fmt_time(secs):
        h = secs // 3600
        m = (secs % 3600) // 60
        return f"{h}h {m:02d}m"

    return {
        "completed":       completed,
        "total":           100,
        "pct":             completed,
        "needs_revision":  needs_revision,
        "total_secs":      total_secs,
        "total_time":      fmt_time(total_secs),
        "avg_time":        fmt_time(avg_secs),
        "topic_count":     topic_count,
        "longest":         longest,
        "recent":          recent,
        "revision_queue":  revision_queue,
    }


def api_get_all_days(query_params):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        SELECT cd.*,
               COALESCE(SUM(ss.duration_seconds),0) AS total_secs
        FROM course_days cd
        LEFT JOIN study_sessions ss ON ss.day_id=cd.id AND ss.ended_at IS NOT NULL
        GROUP BY cd.id
        ORDER BY cd.day_number
    """)
    days = rows_to_list(cur.fetchall())
    conn.close()
    return days


def api_get_day(day_number):
    conn = get_db()
    cur  = conn.cursor()

    cur.execute("SELECT * FROM course_days WHERE day_number=?", (day_number,))
    day = row_to_dict(cur.fetchone())
    if not day:
        conn.close()
        return None

    # Topics
    cur.execute("""
        SELECT t.id, t.name FROM topics t
        JOIN day_topics dt ON dt.topic_id=t.id
        WHERE dt.day_id=?
        ORDER BY t.name
    """, (day["id"],))
    day["topics"] = rows_to_list(cur.fetchall())

    # Files
    cur.execute("SELECT * FROM day_files WHERE day_id=? ORDER BY file_path", (day["id"],))
    day["files"] = rows_to_list(cur.fetchall())

    # Study sessions
    cur.execute("""
        SELECT *, duration_seconds FROM study_sessions
        WHERE day_id=? ORDER BY started_at
    """, (day["id"],))
    day["sessions"] = rows_to_list(cur.fetchall())

    # Active session (started but not ended)
    cur.execute("""
        SELECT * FROM study_sessions
        WHERE day_id=? AND ended_at IS NULL
        ORDER BY started_at DESC LIMIT 1
    """, (day["id"],))
    day["active_session"] = row_to_dict(cur.fetchone())

    # Total study time
    cur.execute("""
        SELECT COALESCE(SUM(duration_seconds),0) AS t
        FROM study_sessions WHERE day_id=? AND ended_at IS NOT NULL
    """, (day["id"],))
    day["total_secs"] = cur.fetchone()["t"]

    conn.close()
    return day


def api_update_day(day_number, data):
    """Update editable fields on a course day."""
    allowed = [
        "title", "description", "difficulty", "understanding",
        "confusion_notes", "revision_notes", "favorite_learning",
        "needs_revision"
    ]
    fields  = {k: data[k] for k in allowed if k in data}
    if not fields:
        return {"error": "No valid fields provided"}

    fields["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k}=?" for k in fields)
    values     = list(fields.values()) + [day_number]

    conn = get_db()
    conn.execute(
        f"UPDATE course_days SET {set_clause} WHERE day_number=?", values
    )
    conn.commit()
    conn.close()
    return {"ok": True}


def api_complete_day(day_number):
    """
    Mark a day as completed.
    Validates that description, topics, and files all exist first.
    """
    conn = get_db()
    cur  = conn.cursor()

    cur.execute("SELECT * FROM course_days WHERE day_number=?", (day_number,))
    day = row_to_dict(cur.fetchone())
    if not day:
        conn.close()
        return {"error": f"Day {day_number} not found"}

    missing = []
    if not day["description"].strip():
        missing.append("Description")

    cur.execute("SELECT COUNT(*) AS n FROM day_topics WHERE day_id=?", (day["id"],))
    if cur.fetchone()["n"] == 0:
        missing.append("Topics Learned")

    cur.execute("SELECT COUNT(*) AS n FROM day_files WHERE day_id=?", (day["id"],))
    if cur.fetchone()["n"] == 0:
        missing.append("Code File")

    if missing:
        conn.close()
        return {"error": f"Cannot complete Day {day_number}. Missing: " + ", ".join(missing)}

    today = date.today().isoformat()
    conn.execute("""
        UPDATE course_days
        SET status='completed', completion_date=?, updated_at=?
        WHERE day_number=?
    """, (today, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), day_number))
    conn.commit()
    conn.close()
    return {"ok": True, "completion_date": today}


def api_set_status(day_number, status):
    """Directly set status (used for in_progress, not_started)."""
    conn = get_db()
    conn.execute(
        "UPDATE course_days SET status=?, updated_at=? WHERE day_number=?",
        (status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), day_number)
    )
    conn.commit()
    conn.close()
    return {"ok": True}


def api_mark_revised(day_number):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    conn.execute(
        "UPDATE course_days SET revised_at=?, updated_at=? WHERE day_number=?",
        (ts, ts, day_number)
    )
    conn.commit()
    conn.close()
    return {"ok": True, "revised_at": ts}


# --- Topics -----------------------------------------------------------------

def api_add_topic(day_number, topic_name):
    topic_name = topic_name.strip()
    if not topic_name:
        return {"error": "Topic name is empty"}

    conn = get_db()
    try:
        cur = conn.cursor()

        cur.execute("SELECT id FROM course_days WHERE day_number=?", (day_number,))
        day_row = cur.fetchone()
        if not day_row:
            return {"error": "Day not found"}
        day_id = day_row["id"]

        # Upsert topic + link in one transaction
        cur.execute("INSERT OR IGNORE INTO topics (name) VALUES (?)", (topic_name,))
        cur.execute("SELECT id FROM topics WHERE name=? COLLATE NOCASE", (topic_name,))
        topic_id = cur.fetchone()["id"]
        cur.execute("INSERT OR IGNORE INTO day_topics (day_id, topic_id) VALUES (?,?)",
                    (day_id, topic_id))
        conn.commit()
        return {"ok": True, "topic_id": topic_id, "name": topic_name}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


def api_remove_topic(day_number, topic_id):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT id FROM course_days WHERE day_number=?", (day_number,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {"error": "Day not found"}
    conn.execute("DELETE FROM day_topics WHERE day_id=? AND topic_id=?",
                 (row["id"], topic_id))
    conn.commit()
    conn.close()
    return {"ok": True}


# --- Files ------------------------------------------------------------------

def api_add_file(day_number, file_path, description=""):
    file_path = file_path.strip()
    if not file_path:
        return {"error": "File path is empty"}

    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT id FROM course_days WHERE day_number=?", (day_number,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {"error": "Day not found"}

    try:
        cur.execute(
            "INSERT OR IGNORE INTO day_files (day_id, file_path, description) VALUES (?,?,?)",
            (row["id"], file_path, description)
        )
        conn.commit()
        file_id = cur.lastrowid
    except Exception as e:
        conn.close()
        return {"error": str(e)}

    conn.close()
    return {"ok": True, "file_id": file_id}


def api_remove_file(file_id):
    conn = get_db()
    conn.execute("DELETE FROM day_files WHERE id=?", (file_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


def api_scan_codes_folder(day_number):
    """
    READ-ONLY scan of ../CODES/Day-NNN/ for Python files.
    Never modifies anything in CODES.
    """
    folder_name = f"Day-{day_number:03d}"
    target = CODES_DIR / folder_name
    if not target.exists():
        return {"files": [], "folder": str(folder_name), "exists": False}

    py_files = sorted(
        str(p.relative_to(CODES_DIR.parent))          # relative to workspace root
        for p in target.rglob("*.py")
    )
    return {"files": py_files, "folder": str(folder_name), "exists": True}


# --- Study Sessions ---------------------------------------------------------

def api_start_session(day_number):
    conn = get_db()
    cur  = conn.cursor()

    cur.execute("SELECT id FROM course_days WHERE day_number=?", (day_number,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {"error": "Day not found"}
    day_id = row["id"]

    # Prevent duplicate active session
    cur.execute(
        "SELECT id FROM study_sessions WHERE day_id=? AND ended_at IS NULL",
        (day_id,)
    )
    if cur.fetchone():
        conn.close()
        return {"error": "A study session is already active for this day"}

    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "INSERT INTO study_sessions (day_id, started_at) VALUES (?,?)",
        (day_id, started_at)
    )
    # Mark day as in_progress if not already completed
    cur.execute(
        "UPDATE course_days SET status=CASE WHEN status='not_started' THEN 'in_progress' ELSE status END, updated_at=? WHERE id=?",
        (started_at, day_id)
    )
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    return {"ok": True, "session_id": session_id, "started_at": started_at}


def api_stop_session(session_id):
    conn = get_db()
    cur  = conn.cursor()

    cur.execute("SELECT * FROM study_sessions WHERE id=?", (session_id,))
    session = row_to_dict(cur.fetchone())
    if not session:
        conn.close()
        return {"error": "Session not found"}
    if session["ended_at"]:
        conn.close()
        return {"error": "Session already ended"}

    ended_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    started  = datetime.strptime(session["started_at"], "%Y-%m-%d %H:%M:%S")
    ended    = datetime.strptime(ended_at,              "%Y-%m-%d %H:%M:%S")
    duration = int((ended - started).total_seconds())

    conn.execute("""
        UPDATE study_sessions
        SET ended_at=?, duration_seconds=?
        WHERE id=?
    """, (ended_at, duration, session_id))
    conn.commit()
    conn.close()
    return {"ok": True, "ended_at": ended_at, "duration_seconds": duration}


def api_get_active_session():
    """Return any globally active (unfinished) study session."""
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        SELECT ss.*, cd.day_number
        FROM study_sessions ss
        JOIN course_days cd ON cd.id=ss.day_id
        WHERE ss.ended_at IS NULL
        ORDER BY ss.started_at DESC LIMIT 1
    """)
    row = row_to_dict(cur.fetchone())
    conn.close()
    return row


# --- Search -----------------------------------------------------------------

def api_search(query):
    query = query.strip()
    if not query:
        return []

    like = f"%{query}%"
    conn = get_db()
    cur  = conn.cursor()

    # Days matching title or description
    cur.execute("""
        SELECT DISTINCT cd.day_number, cd.title, cd.status
        FROM course_days cd
        WHERE cd.title LIKE ? OR cd.description LIKE ?
              OR CAST(cd.day_number AS TEXT) LIKE ?
    """, (like, like, like))
    results = rows_to_list(cur.fetchall())
    seen    = {r["day_number"] for r in results}

    # Days via topics
    cur.execute("""
        SELECT DISTINCT cd.day_number, cd.title, cd.status
        FROM course_days cd
        JOIN day_topics dt ON dt.day_id=cd.id
        JOIN topics t      ON t.id=dt.topic_id
        WHERE t.name LIKE ?
    """, (like,))
    for r in rows_to_list(cur.fetchall()):
        if r["day_number"] not in seen:
            results.append(r)
            seen.add(r["day_number"])

    # Days via files
    cur.execute("""
        SELECT DISTINCT cd.day_number, cd.title, cd.status
        FROM course_days cd
        JOIN day_files df ON df.day_id=cd.id
        WHERE df.file_path LIKE ? OR df.description LIKE ?
    """, (like, like))
    for r in rows_to_list(cur.fetchall()):
        if r["day_number"] not in seen:
            results.append(r)
            seen.add(r["day_number"])

    conn.close()
    results.sort(key=lambda x: x["day_number"])
    return results


# --- Export -----------------------------------------------------------------

def api_export():
    """Build a complete JSON export using only standard library."""
    conn = get_db()
    cur  = conn.cursor()

    cur.execute("SELECT * FROM course_days ORDER BY day_number")
    days = rows_to_list(cur.fetchall())

    for d in days:
        cur.execute("""
            SELECT t.name FROM topics t
            JOIN day_topics dt ON dt.topic_id=t.id WHERE dt.day_id=?
        """, (d["id"],))
        d["topics"] = [r["name"] for r in cur.fetchall()]

        cur.execute("SELECT file_path, description FROM day_files WHERE day_id=?", (d["id"],))
        d["files"] = rows_to_list(cur.fetchall())

        cur.execute("""
            SELECT started_at, ended_at, duration_seconds
            FROM study_sessions WHERE day_id=? ORDER BY started_at
        """, (d["id"],))
        d["study_sessions"] = rows_to_list(cur.fetchall())

    cur.execute("SELECT * FROM topics ORDER BY name")
    all_topics = rows_to_list(cur.fetchall())

    # Stats summary
    cur.execute("SELECT COUNT(*) AS n FROM course_days WHERE status='completed'")
    completed = cur.fetchone()["n"]
    cur.execute("SELECT COALESCE(SUM(duration_seconds),0) AS t FROM study_sessions WHERE ended_at IS NOT NULL")
    total_secs = cur.fetchone()["t"]

    conn.close()

    export = {
        "exported_at":  datetime.now().isoformat(),
        "statistics": {
            "completed_days": completed,
            "total_days":     100,
            "total_study_seconds": total_secs,
        },
        "topics":  all_topics,
        "days":    days,
    }

    filename = f"progress-export-{date.today().isoformat()}.json"
    out_path = BASE_DIR / filename
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, default=str)

    return {"ok": True, "file": filename}


# --- Backup -----------------------------------------------------------------

def api_backup():
    """Copy tracker.db to database/backups/ with today's date."""
    dest = BACKUP_DIR / f"tracker-{date.today().isoformat()}.db"
    shutil.copy2(str(DB_PATH), str(dest))
    return {"ok": True, "file": str(dest.relative_to(BASE_DIR))}


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

class TrackerHandler(BaseHTTPRequestHandler):
    """
    Single handler class for both static files and the /api/ routes.
    We avoid Flask by implementing our own minimal routing here.
    """

    # Silence default request logs (we print our own)
    def log_message(self, fmt, *args):
        pass

    def send_json(self, data, status=200):
        body = json_response(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, msg, status=400):
        self.send_json({"error": msg}, status)

    def serve_static(self, filepath):
        """Serve a file from the static/ directory."""
        try:
            ext = filepath.suffix.lower()
            types = {
                ".html": "text/html; charset=utf-8",
                ".css":  "text/css",
                ".js":   "application/javascript",
                ".ico":  "image/x-icon",
            }
            content_type = types.get(ext, "application/octet-stream")
            data = filepath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    # -----------------------------------------------------------------------
    # GET
    # -----------------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/") or "/"
        qs     = parse_qs(parsed.query)

        # --- Static files ---------------------------------------------------
        if path == "/" or path == "/index.html":
            return self.serve_static(STATIC_DIR / "index.html")
        if path == "/day.html":
            return self.serve_static(STATIC_DIR / "day.html")
        if path in ("/style.css", "/app.js", "/day.js"):
            return self.serve_static(STATIC_DIR / path.lstrip("/"))

        # --- API routes -----------------------------------------------------
        if path == "/api/stats":
            return self.send_json(api_get_stats(qs))

        if path == "/api/days":
            return self.send_json(api_get_all_days(qs))

        if path.startswith("/api/days/"):
            try:
                day_num = int(path.split("/")[3])
            except (IndexError, ValueError):
                return self.send_error_json("Invalid day number")

            # Sub-routes
            rest = "/".join(path.split("/")[4:])

            if rest == "scan":
                return self.send_json(api_scan_codes_folder(day_num))

            day = api_get_day(day_num)
            if day is None:
                return self.send_error_json("Day not found", 404)
            return self.send_json(day)

        if path == "/api/active-session":
            return self.send_json(api_get_active_session() or {})

        if path == "/api/search":
            q = qs.get("q", [""])[0]
            return self.send_json(api_search(q))

        self.send_response(404)
        self.end_headers()

    # -----------------------------------------------------------------------
    # POST
    # -----------------------------------------------------------------------
    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")
        data   = parse_body(self)

        # /api/days/<n>/update
        if path.startswith("/api/days/") and path.endswith("/update"):
            try:
                day_num = int(path.split("/")[3])
            except (IndexError, ValueError):
                return self.send_error_json("Invalid day number")
            return self.send_json(api_update_day(day_num, data))

        # /api/days/<n>/complete
        if path.startswith("/api/days/") and path.endswith("/complete"):
            try:
                day_num = int(path.split("/")[3])
            except (IndexError, ValueError):
                return self.send_error_json("Invalid day number")
            return self.send_json(api_complete_day(day_num))

        # /api/days/<n>/status
        if path.startswith("/api/days/") and path.endswith("/status"):
            try:
                day_num = int(path.split("/")[3])
            except (IndexError, ValueError):
                return self.send_error_json("Invalid day number")
            status = data.get("status", "")
            if status not in ("not_started", "in_progress"):
                return self.send_error_json("Invalid status")
            return self.send_json(api_set_status(day_num, status))

        # /api/days/<n>/topics/add
        if path.startswith("/api/days/") and path.endswith("/topics/add"):
            try:
                day_num = int(path.split("/")[3])
            except (IndexError, ValueError):
                return self.send_error_json("Invalid day number")
            return self.send_json(api_add_topic(day_num, data.get("name", "")))

        # /api/days/<n>/topics/<id>/remove
        if path.startswith("/api/days/") and "/topics/" in path and path.endswith("/remove"):
            parts = path.split("/")
            try:
                day_num  = int(parts[3])
                topic_id = int(parts[5])
            except (IndexError, ValueError):
                return self.send_error_json("Invalid parameters")
            return self.send_json(api_remove_topic(day_num, topic_id))

        # /api/days/<n>/files/add
        if path.startswith("/api/days/") and path.endswith("/files/add"):
            try:
                day_num = int(path.split("/")[3])
            except (IndexError, ValueError):
                return self.send_error_json("Invalid day number")
            return self.send_json(
                api_add_file(day_num, data.get("file_path",""), data.get("description",""))
            )

        # /api/files/<id>/remove
        if path.startswith("/api/files/") and path.endswith("/remove"):
            try:
                file_id = int(path.split("/")[3])
            except (IndexError, ValueError):
                return self.send_error_json("Invalid file id")
            return self.send_json(api_remove_file(file_id))

        # /api/days/<n>/sessions/start
        if path.startswith("/api/days/") and path.endswith("/sessions/start"):
            try:
                day_num = int(path.split("/")[3])
            except (IndexError, ValueError):
                return self.send_error_json("Invalid day number")
            return self.send_json(api_start_session(day_num))

        # /api/sessions/<id>/stop
        if path.startswith("/api/sessions/") and path.endswith("/stop"):
            try:
                session_id = int(path.split("/")[3])
            except (IndexError, ValueError):
                return self.send_error_json("Invalid session id")
            return self.send_json(api_stop_session(session_id))

        # /api/days/<n>/revised
        if path.startswith("/api/days/") and path.endswith("/revised"):
            try:
                day_num = int(path.split("/")[3])
            except (IndexError, ValueError):
                return self.send_error_json("Invalid day number")
            return self.send_json(api_mark_revised(day_num))

        # /api/export
        if path == "/api/export":
            return self.send_json(api_export())

        # /api/backup
        if path == "/api/backup":
            return self.send_json(api_backup())

        self.send_response(404)
        self.end_headers()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    init_db()

    HOST = "127.0.0.1"
    PORT = 8000
    server = HTTPServer((HOST, PORT), TrackerHandler)

    url = f"http://{HOST}:{PORT}"
    print()
    print("  100 Days of Code – Python Tracker")
    print(f"  Running locally at: {url}")
    print("  Press Ctrl+C to stop.")
    print()

    # Open browser after a short delay so the server is ready
    def open_browser():
        import time
        time.sleep(0.8)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Tracker stopped.")


if __name__ == "__main__":
    main()
