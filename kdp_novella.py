#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
KDP Novella Backend — Per-Project SQLite Storage

Each novella gets its OWN SQLite file so you can see the chat history plainly.
Interview data is SEALED after Phase 1 — never modified again.
Generated content (outline, chapters) can be regenerated unlimited times.

Design principle: ONE pass on the trauma, MANY passes on the output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

WORDS_PER_PAGE = 275
DEFAULT_TARGET_PAGES = 150

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_ts() -> int:
    return int(time.time())

def new_id() -> str:
    return uuid.uuid4().hex[:16]

def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))

def safe_slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40] or "untitled"

def _out(data: Dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False))

def _err(msg: str, **kw) -> None:
    _out({"ok": False, "error": msg, **kw})
    sys.exit(1)

# ---------------------------------------------------------------------------
# Per-project SQLite database
# ---------------------------------------------------------------------------

class ProjectDB:
    """One SQLite file per novella — inspectable, portable, sacred."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS turns (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    role       TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
                    text       TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outline (
                    version    INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_json  TEXT NOT NULL,
                    model_used TEXT DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chapters (
                    chapter_num INTEGER NOT NULL,
                    version     INTEGER NOT NULL DEFAULT 1,
                    title       TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    word_count  INTEGER NOT NULL DEFAULT 0,
                    model_used  TEXT DEFAULT '',
                    created_at  INTEGER NOT NULL,
                    PRIMARY KEY (chapter_num, version)
                );
            """)

    # ---- Meta (key-value) ----

    def get_meta(self, key: str, default: str = "") -> str:
        with self._conn() as c:
            row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)", (key, value))

    def get_all_meta(self) -> Dict[str, str]:
        with self._conn() as c:
            rows = c.execute("SELECT key, value FROM meta").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ---- Turns (interview transcript — sacred after seal) ----

    def is_sealed(self) -> bool:
        return bool(self.get_meta("sealed_at"))

    def add_turn(self, role: str, text: str) -> int:
        if self.is_sealed():
            _err("project_sealed",
                 detail="Interview is sealed. Source data is immutable. "
                        "Use reset-draft to regenerate the book, not re-interview.")
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO turns(role, text, created_at) VALUES(?,?,?)",
                (role, text, now_ts()),
            )
            return cur.lastrowid

    def get_turns(self, limit: int = 100000) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, role, text, created_at FROM turns ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_word_counts(self) -> Dict[str, int]:
        with self._conn() as c:
            rows = c.execute("SELECT role, text FROM turns").fetchall()
        user_w = sum(word_count(r["text"]) for r in rows if r["role"] == "user")
        asst_w = sum(word_count(r["text"]) for r in rows if r["role"] == "assistant")
        return {
            "user_words": user_w,
            "assistant_words": asst_w,
            "total_words": user_w,  # source material = user words only
            "total_turns": len(rows),
            "pages_raw": user_w // WORDS_PER_PAGE,
        }

    def seal(self) -> None:
        if self.is_sealed():
            _err("already_sealed", detail="Interview is already sealed.")
        self.set_meta("sealed_at", str(now_ts()))
        self.set_meta("phase", "sealed")

    # ---- Outline ----

    def save_outline(self, data: Dict[str, Any], model: str = "") -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO outline(data_json, model_used, created_at) VALUES(?,?,?)",
                (json.dumps(data, ensure_ascii=False), model, now_ts()),
            )
            return cur.lastrowid

    def get_latest_outline(self) -> Optional[Dict[str, Any]]:
        with self._conn() as c:
            row = c.execute(
                "SELECT version, data_json, model_used, created_at "
                "FROM outline ORDER BY version DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return {
            "version": row["version"],
            "data": json.loads(row["data_json"]),
            "model_used": row["model_used"],
            "created_at": row["created_at"],
        }

    # ---- Chapters (regenerable — many passes on the output) ----

    def save_chapter(self, chapter_num: int, title: str, content: str,
                     model: str = "") -> int:
        wc = word_count(content)
        with self._conn() as c:
            row = c.execute(
                "SELECT MAX(version) AS v FROM chapters WHERE chapter_num=?",
                (chapter_num,),
            ).fetchone()
            ver = (row["v"] or 0) + 1
            c.execute(
                "INSERT INTO chapters"
                "(chapter_num, version, title, content, word_count, model_used, created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (chapter_num, ver, title, content, wc, model, now_ts()),
            )
        return ver

    def get_latest_chapters(self) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("""
                SELECT c.chapter_num, c.version, c.title, c.content,
                       c.word_count, c.model_used, c.created_at
                FROM chapters c
                INNER JOIN (
                    SELECT chapter_num, MAX(version) AS max_ver
                    FROM chapters GROUP BY chapter_num
                ) latest
                  ON c.chapter_num = latest.chapter_num
                 AND c.version     = latest.max_ver
                ORDER BY c.chapter_num
            """).fetchall()
        return [dict(r) for r in rows]

    def get_chapter(self, chapter_num: int, version: int = 0) -> Optional[Dict[str, Any]]:
        with self._conn() as c:
            if version:
                row = c.execute(
                    "SELECT * FROM chapters WHERE chapter_num=? AND version=?",
                    (chapter_num, version),
                ).fetchone()
            else:
                row = c.execute(
                    "SELECT * FROM chapters WHERE chapter_num=? ORDER BY version DESC LIMIT 1",
                    (chapter_num,),
                ).fetchone()
        return dict(row) if row else None

    def clear_draft(self) -> int:
        """Wipe all generated chapters + outlines. Source interview untouched."""
        with self._conn() as c:
            n = c.execute("DELETE FROM chapters").rowcount
            c.execute("DELETE FROM outline")
            return n

    def get_book_stats(self) -> Dict[str, Any]:
        chapters = self.get_latest_chapters()
        total_words = sum(ch["word_count"] for ch in chapters)
        tp = int(self.get_meta("target_pages", str(DEFAULT_TARGET_PAGES)))
        return {
            "chapters": len(chapters),
            "total_words": total_words,
            "total_pages": total_words // WORDS_PER_PAGE,
            "target_pages": tp,
            "target_words": tp * WORDS_PER_PAGE,
            "per_chapter": [
                {"n": ch["chapter_num"], "title": ch["title"],
                 "words": ch["word_count"], "pages": ch["word_count"] // WORDS_PER_PAGE,
                 "model": ch["model_used"]}
                for ch in chapters
            ],
        }

# ---------------------------------------------------------------------------
# Project discovery (scan .data/ for per-project DBs)
# ---------------------------------------------------------------------------

def data_dir(base: str) -> str:
    d = os.path.join(base, ".data")
    os.makedirs(d, exist_ok=True)
    return d

def project_db_path(base: str, pid: str, title: str = "") -> str:
    slug = safe_slug(title) if title else "project"
    return os.path.join(data_dir(base), f"kdp_{slug}_{pid}.sqlite3")

def find_project(base: str, pid: str) -> str:
    dd = data_dir(base)
    for f in os.listdir(dd):
        if f.startswith("kdp_") and f.endswith(".sqlite3") and pid in f:
            return os.path.join(dd, f)
    _err("project_not_found", project_id=pid)
    return ""

def list_projects(base: str) -> List[Dict[str, Any]]:
    dd = data_dir(base)
    projects: List[Dict[str, Any]] = []
    for f in sorted(os.listdir(dd)):
        if not (f.startswith("kdp_") and f.endswith(".sqlite3")):
            continue
        path = os.path.join(dd, f)
        try:
            db = ProjectDB(path)
            meta = db.get_all_meta()
            wc = db.get_word_counts()
            bs = db.get_book_stats()
            projects.append({
                "project_id": meta.get("project_id", "?"),
                "title": meta.get("title", "Untitled"),
                "author": meta.get("author", "Anonymous"),
                "phase": meta.get("phase", "interview"),
                "sealed": db.is_sealed(),
                "source_words": wc["total_words"],
                "source_pages": wc["pages_raw"],
                "book_chapters": bs["chapters"],
                "book_words": bs["total_words"],
                "book_pages": bs["total_pages"],
                "db_file": f,
            })
        except Exception:
            continue
    return projects

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_book(db: ProjectDB, out_dir: str) -> Dict[str, Any]:
    os.makedirs(out_dir, exist_ok=True)
    meta = db.get_all_meta()
    title = meta.get("title", "Untitled")
    author = meta.get("author", "Anonymous")
    slug = safe_slug(title)
    files: List[str] = []

    # 1. Full interview transcript (read-only source)
    turns = db.get_turns()
    tp = os.path.join(out_dir, f"{slug}_transcript.md")
    with open(tp, "w", encoding="utf-8") as f:
        f.write(f"# {title} — Interview Transcript\n\n")
        f.write(f"**Author**: {author}\n\n---\n\n")
        for t in turns:
            f.write(f"**{t['role'].upper()}**:\n\n{t['text']}\n\n---\n\n")
    files.append(tp)

    # 2. Book manuscript (if chapters exist)
    chapters = db.get_latest_chapters()
    if chapters:
        outline_row = db.get_latest_outline()
        outline = outline_row["data"] if outline_row else {}
        bp = os.path.join(out_dir, f"{slug}_manuscript.md")
        with open(bp, "w", encoding="utf-8") as f:
            f.write(f"# {outline.get('working_title', title)}\n\n")
            f.write(f"**By {author}**\n\n")
            if outline.get("content_warnings"):
                f.write(f"> **Content Note**: {outline['content_warnings']}\n\n")
            f.write("---\n\n")
            total_words = 0
            for ch in chapters:
                f.write(f"## Chapter {ch['chapter_num']}: {ch['title']}\n\n")
                f.write(ch["content"])
                f.write("\n\n---\n\n")
                total_words += ch["word_count"]
            f.write(f"\n\n*{total_words:,} words — approximately {total_words // WORDS_PER_PAGE} pages*\n")
        files.append(bp)

    # 3. Metadata JSON
    mp = os.path.join(out_dir, f"{slug}_meta.json")
    wc = db.get_word_counts()
    bs = db.get_book_stats()
    with open(mp, "w", encoding="utf-8") as f:
        json.dump({
            "title": title, "author": author,
            "project_id": meta.get("project_id"),
            "source_words": wc["total_words"], "source_pages": wc["pages_raw"],
            "book_words": bs["total_words"], "book_pages": bs["total_pages"],
            "book_chapters": bs["chapters"], "sealed": db.is_sealed(),
            "phase": meta.get("phase"),
        }, f, indent=2)
    files.append(mp)

    return {"ok": True, "files": files, "book_words": bs["total_words"], "book_pages": bs["total_pages"]}

# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_init(args, base: str):
    pid = new_id()
    title = (args.title or "").strip() or "Untitled"
    author = (args.author or "").strip() or "Anonymous"
    pages = int(args.pages) if args.pages else DEFAULT_TARGET_PAGES
    path = project_db_path(base, pid, title)
    db = ProjectDB(path)
    db.set_meta("project_id", pid)
    db.set_meta("title", title)
    db.set_meta("author", author)
    db.set_meta("created_at", str(now_ts()))
    db.set_meta("phase", "interview")
    db.set_meta("target_pages", str(pages))
    _out({"ok": True, "project_id": pid, "db_path": path, "title": title, "author": author})

def cmd_show(args, base: str):
    path = find_project(base, args.project)
    db = ProjectDB(path)
    meta = db.get_all_meta()
    wc = db.get_word_counts()
    bs = db.get_book_stats()
    outline = db.get_latest_outline()
    _out({"ok": True, "project": {
        "project_id": meta.get("project_id"), "title": meta.get("title"),
        "author": meta.get("author"), "phase": meta.get("phase", "interview"),
        "sealed": db.is_sealed(), "db_path": path, "source": wc, "book": bs,
        "has_outline": outline is not None,
        "outline_version": outline["version"] if outline else 0, "meta": meta,
    }})

def cmd_list(args, base: str):
    projects = list_projects(base)
    _out({"ok": True, "projects": projects, "count": len(projects)})

def cmd_log(args, base: str):
    path = find_project(base, args.project)
    db = ProjectDB(path)
    tid = db.add_turn(args.role, args.text)
    _out({"ok": True, "turn_id": tid})

def cmd_turns(args, base: str):
    path = find_project(base, args.project)
    db = ProjectDB(path)
    turns = db.get_turns(int(args.limit))
    _out({"ok": True, "turns": turns, "count": len(turns)})

def cmd_word_count(args, base: str):
    path = find_project(base, args.project)
    db = ProjectDB(path)
    wc = db.get_word_counts()
    _out({"ok": True, **wc})

def cmd_seal(args, base: str):
    path = find_project(base, args.project)
    db = ProjectDB(path)
    wc = db.get_word_counts()
    db.seal()
    _out({"ok": True, "sealed": True, "source_words": wc["total_words"], "source_pages": wc["pages_raw"]})

def cmd_set_meta(args, base: str):
    path = find_project(base, args.project)
    db = ProjectDB(path)
    db.set_meta(args.key, args.value)
    _out({"ok": True})

def cmd_save_outline(args, base: str):
    path = find_project(base, args.project)
    db = ProjectDB(path)
    json_str = args.json
    if args.json_file:
        with open(args.json_file, "r", encoding="utf-8") as f:
            json_str = f.read()
    data = json.loads(json_str)
    ver = db.save_outline(data, args.model or "")
    db.set_meta("phase", "outlining")
    _out({"ok": True, "version": ver, "chapters": len(data.get("chapter_outline", []))})

def cmd_get_outline(args, base: str):
    path = find_project(base, args.project)
    db = ProjectDB(path)
    outline = db.get_latest_outline()
    if not outline:
        _err("no_outline", detail="No outline has been generated yet.")
    _out({"ok": True, **outline})

def cmd_save_chapter(args, base: str):
    path = find_project(base, args.project)
    db = ProjectDB(path)
    content = args.content or ""
    if args.content_file:
        with open(args.content_file, "r", encoding="utf-8") as f:
            content = f.read()
    if not content.strip():
        _err("empty_content", detail="Chapter content cannot be empty.")
    ver = db.save_chapter(int(args.num), args.title, content, args.model or "")
    db.set_meta("phase", "drafting")
    _out({"ok": True, "chapter_num": int(args.num), "version": ver, "word_count": word_count(content)})

def cmd_get_chapters(args, base: str):
    path = find_project(base, args.project)
    db = ProjectDB(path)
    chapters = db.get_latest_chapters()
    bs = db.get_book_stats()
    _out({"ok": True, "chapters": chapters, "stats": bs})

def cmd_get_chapter(args, base: str):
    path = find_project(base, args.project)
    db = ProjectDB(path)
    ch = db.get_chapter(int(args.num), int(args.version) if args.version else 0)
    if not ch:
        _err("chapter_not_found", chapter_num=args.num)
    _out({"ok": True, **ch})

def cmd_reset_draft(args, base: str):
    path = find_project(base, args.project)
    db = ProjectDB(path)
    n = db.clear_draft()
    if db.is_sealed():
        db.set_meta("phase", "sealed")
    _out({"ok": True, "deleted": n, "message": "All generated content cleared. Source interview untouched."})

def cmd_export(args, base: str):
    path = find_project(base, args.project)
    db = ProjectDB(path)
    result = export_book(db, args.out)
    _out(result)

def cmd_book_stats(args, base: str):
    path = find_project(base, args.project)
    db = ProjectDB(path)
    bs = db.get_book_stats()
    _out({"ok": True, **bs})

# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kdp_novella.py",
                                description="KDP Novella Backend — per-project SQLite storage")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init"); s.add_argument("--title", required=True)
    s.add_argument("--author", default=""); s.add_argument("--pages", default=str(DEFAULT_TARGET_PAGES))
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("show"); s.add_argument("--project", required=True)
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("list"); s.set_defaults(func=cmd_list)

    s = sub.add_parser("log"); s.add_argument("--project", required=True)
    s.add_argument("--role", required=True, choices=["user", "assistant", "system"])
    s.add_argument("--text", required=True); s.set_defaults(func=cmd_log)

    s = sub.add_parser("turns"); s.add_argument("--project", required=True)
    s.add_argument("--limit", default="100000"); s.set_defaults(func=cmd_turns)

    s = sub.add_parser("word-count"); s.add_argument("--project", required=True)
    s.set_defaults(func=cmd_word_count)

    s = sub.add_parser("seal"); s.add_argument("--project", required=True)
    s.set_defaults(func=cmd_seal)

    s = sub.add_parser("set-meta"); s.add_argument("--project", required=True)
    s.add_argument("--key", required=True); s.add_argument("--value", required=True)
    s.set_defaults(func=cmd_set_meta)

    s = sub.add_parser("save-outline"); s.add_argument("--project", required=True)
    s.add_argument("--json", default=""); s.add_argument("--json-file", default="")
    s.add_argument("--model", default=""); s.set_defaults(func=cmd_save_outline)

    s = sub.add_parser("get-outline"); s.add_argument("--project", required=True)
    s.set_defaults(func=cmd_get_outline)

    s = sub.add_parser("save-chapter"); s.add_argument("--project", required=True)
    s.add_argument("--num", required=True, type=int); s.add_argument("--title", required=True)
    s.add_argument("--content", default=""); s.add_argument("--content-file", default="")
    s.add_argument("--model", default=""); s.set_defaults(func=cmd_save_chapter)

    s = sub.add_parser("get-chapters"); s.add_argument("--project", required=True)
    s.set_defaults(func=cmd_get_chapters)

    s = sub.add_parser("get-chapter"); s.add_argument("--project", required=True)
    s.add_argument("--num", required=True); s.add_argument("--version", default="")
    s.set_defaults(func=cmd_get_chapter)

    s = sub.add_parser("reset-draft"); s.add_argument("--project", required=True)
    s.set_defaults(func=cmd_reset_draft)

    s = sub.add_parser("export"); s.add_argument("--project", required=True)
    s.add_argument("--out", required=True); s.set_defaults(func=cmd_export)

    s = sub.add_parser("book-stats"); s.add_argument("--project", required=True)
    s.set_defaults(func=cmd_book_stats)

    return p

def main():
    base = os.path.dirname(os.path.abspath(__file__))
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args, base)
    except SystemExit:
        raise
    except Exception as e:
        _err(str(e))

if __name__ == "__main__":
    main()
