# 📖 KDP Novella

**Chat-driven memoir tool for OpenClaw.** Tell your story once, generate a publication-ready book as many times as you want.

> **Design Principle:** ONE pass on the trauma, MANY passes on the output.

---

## What It Does

KDP Novella turns a conversational interview into a ~150-page KDP-ready novella, delivered as a professional interior PDF you can upload directly to Amazon KDP.

The entire experience is **chat-driven** — users just talk, the agent handles everything.

---

## The Three Phases

### Phase 1 — The Interview
A gentle, one-pass interview captures your story. The agent asks one question at a time, reflects back what you share, and pursues meaningful threads. Your words are stored in a per-project SQLite database and **sealed** after the interview — the source material is immutable and never touched again.

- **SKIP / PAUSE / STOP** always available
- Goal: 25,000–35,000 words of raw material
- Consent gate: user must type **I AGREE** before anything begins

### Phase 2 — The Book
The sealed interview is structured into a full story arc (outline), then each chapter is generated sequentially by the best available LLM. Every chapter goes through built-in editing for publication quality.

- Full outline first, then chapter-by-chapter generation
- Each chapter: 2,500–4,500 words of narrative prose
- Regenerate any chapter (or the whole book) without re-interviewing

### Phase 3 — The PDF
A production-ready KDP interior PDF is generated with professional typography:

- **5.5" × 8.5"** trim size (standard novel)
- Title page, copyright page, table of contents
- Professional serif font (Liberation Serif / Noto Serif / DejaVu Serif / Times fallback)
- Chapter headings with decorative drop spacing and rules
- Justified body text with first-line indents
- Scene break ornaments (✦ ✦ ✦)
- Smart typography: curly quotes, em dashes, proper ellipses
- Centered page numbers (body only)

---

## Requirements

- **Python 3**
- **reportlab >= 4.0** (for PDF generation)

```bash
pip install reportlab
```

---

## Quick Start

```bash
# Start a new project
python3 skill.py start --title "My Story" --author "Jane Doe" --pages 150

# Log interview answers (agent orchestrates this in conversation)
python3 skill.py answer --project <id> --text "Here's what happened..."

# Check progress
python3 skill.py status --project <id>

# Seal the interview (locks source material)
python3 skill.py seal --project <id>

# Generate the book (call repeatedly — it walks you through outline → chapters)
python3 skill.py generate-book --project <id> --model "claude-sonnet-4-20250514"

# Build the PDF
python3 skill.py build-pdf --project <id>
```

---

## Commands Reference

### Phase 1: Interview

| Command | Description |
|---------|-------------|
| `start --title "..." --author "..." --pages N` | Create a new project |
| `answer --project <id> --text "..."` | Log a user response and get interviewer guidance |
| `status --project <id>` | Check interview progress and word count |
| `list` | List all projects |
| `seal --project <id>` | Seal the interview (makes source immutable) |

### Phase 2: Book Generation

| Command | Description |
|---------|-------------|
| `generate-book --project <id> --model "..."` | Smart orchestrator — call repeatedly to walk through generation |
| `apply-outline --project <id> --json '...'` | Save a generated outline |
| `apply-chapter --project <id> --num N --title "..." --content "..."` | Save a generated chapter |
| `book-stats --project <id>` | View book statistics (words, pages, per-chapter breakdown) |
| `reset-draft --project <id>` | Wipe generated content; source interview untouched |

### Phase 3: PDF

| Command | Description |
|---------|-------------|
| `build-pdf --project <id>` | Generate the KDP-ready interior PDF |
| `build-pdf --project <id> --out /path/` | Generate PDF to a custom output directory |

### Utility

| Command | Description |
|---------|-------------|
| `export --project <id> --out ./output` | Export project data |
| `chat --message "..." --project <id>` | Simplified single entry point (auto-routes intent) |

---

## Word Targets

| Metric | Words | Pages |
|--------|-------|-------|
| Raw material (minimum) | 20,000 | ~73 |
| Raw material (ideal) | 35,000 | ~127 |
| Generated book | ~41,250 | ~150 |
| Per chapter | 2,500–4,500 | 9–16 |

---

## Project Storage

Each project is stored as an independent SQLite file in `.data/`:

```
.data/kdp_<slug>_<id>.sqlite3
```

**Schema:**

| Table | Purpose |
|-------|---------|
| `meta` | Key-value pairs (title, author, phase, sealed_at, target_pages, etc.) |
| `turns` | Interview transcript — **immutable after seal** |
| `outline` | Versioned outlines (regenerable) |
| `chapters` | Versioned chapters (regenerable) |

---

## Non-Negotiables

1. **Consent Gate** — User must type "I AGREE" before any interview begins
2. **User Control** — SKIP / PAUSE / STOP always available during Phase 1
3. **No Diagnosis** — Never diagnose, never play therapist
4. **No Pushing** — If user hesitates, offer alternatives
5. **One Question** — Ask ONE question at a time during interviews
6. **Sacred Source** — Never modify sealed interview data
7. **Full Chapters** — Phase 2 produces full prose, not summaries
8. **Publication Quality** — Every chapter is publication-ready with built-in editing

---

## File Structure

```
kdp-novella/
├── skill.py           # Orchestrator — CLI entry point, interview logic, Phase 2 workflow
├── kdp_novella.py     # Backend — per-project SQLite storage and data operations
├── pdf_generator.py   # Phase 3 — KDP-ready PDF generation with ReportLab
├── SKILL.md           # OpenClaw skill manifest and agent instructions
├── requirements.txt   # Python dependencies (reportlab>=4.0)
└── .data/             # Per-project SQLite databases (created at runtime)
```

---

## License

Part of the [OpenClaw](https://github.com/openclaw) skill ecosystem.
