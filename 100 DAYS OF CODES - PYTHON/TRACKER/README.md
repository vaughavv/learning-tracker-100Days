# 100 Days of Code – Python Tracker

A local learning tracker for the 100 Days of Code Python course.
Built with Python standard library only. No pip installs required.

---

## How to Start

```
cd TRACKER
python app.py
```

Then open your browser at: http://127.0.0.1:8000

The browser opens automatically if `webbrowser` is available.

---

## How to Stop

Press `Ctrl+C` in the terminal.

---

## Requirements

- Python 3.7 or newer (standard library only)
- No pip installs needed
- SQLite is built into Python — no separate database installation required

---

## Project Structure

```
TRACKER/
  app.py              Python server + all API logic
  README.md           This file
  database/
    tracker.db        Your data (created automatically on first run)
    backups/          Manual backups stored here
  static/
    index.html        Dashboard / main page
    day.html          Day detail page
    style.css         All styling (dark developer theme)
    app.js            Dashboard JavaScript
    day.js            Day detail JavaScript
```

---

## Where My Data Is Saved

    TRACKER/database/tracker.db

This is a standard SQLite database file. You can open it with any
SQLite browser (e.g. DB Browser for SQLite) to inspect your data.

---

## Where Backups Are Saved

    TRACKER/database/backups/

Created only when you click the **Backup Data** button on the dashboard.
Format: `tracker-YYYY-MM-DD.db`

---

## Features

- Dashboard with progress stats, current day, revision queue
- All 100 days pre-loaded, compact grid view
- Day detail page: title, description, topics, files, reflection
- Study timer: start/stop with SQLite persistence (survives page refresh)
- Multiple study sessions per day with totals
- Normalized topics table (same topic can appear on multiple days)
- File references only (files are never uploaded or modified)
- Auto-scan of CODES/Day-NNN/ folder for Python files (read-only)
- Completion validation: requires description + topics + files
- Revision queue with mark-as-revised
- Global search across days, topics, and files
- JSON export of all progress data
- Manual database backup

---

## Safety

- Server listens only on 127.0.0.1 (localhost)
- Never modifies CODES/, NOTES/, or RESOURCES/
- Folder scanning is strictly read-only
- No external network requests
- No telemetry, no accounts, no cloud

---

## Database Tables

| Table         | Purpose                              |
|---------------|--------------------------------------|
| course_days   | One row per day (1–100)              |
| study_sessions| Timer start/stop records             |
| topics        | Unique topic names                   |
| day_topics    | Links days to topics (many-to-many)  |
| day_files     | File path references per day         |
