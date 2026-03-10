---
name: kdp-novella
description: "Chat-driven memoir tool. Phase 1: gentle one-pass interview stored in per-project SQLite. Phase 2: LLM-powered chapter-by-chapter generation of a ~150-page KDP novella with built-in editing. Phase 3: production-ready KDP interior PDF with professional typography. One pass on the trauma, many passes on the output."
user-invocable: true
metadata: {"openclaw":{"emoji":"📖","os":["linux","darwin"],"requires":{"bins":["python3"],"pip":["reportlab>=4.0"]},"permissions":{"version":1,"declared_purpose":"Help victims and survivors document their life experiences into a publishable memoir. Interview once (sacred source), generate book many times with different LLMs, produce a KDP-ready PDF for download.","filesystem":["read:{baseDir}","write:{baseDir}/.data","write:{baseDir}/output"],"exec":["python3"],"network":[],"env":[]}}}
---

# KDP Novella: Your Story, Your Book

**Your entire book journey happens right here in this conversation.**

Tell me your story → I turn it into a novel → You download a publication-ready PDF.

**Design Principle: ONE pass on the trauma, MANY passes on the output.**

---

## The Three Phases

### Phase 1 — The Interview
Tell me your story. I ask questions, you answer. Take your time.
- SKIP / PAUSE / STOP always available
- Goal: 25,000+ words of raw material (~90 pages of conversation)
- Your words are sealed and protected forever after the interview

### Phase 2 — The Book
I turn your interview into a ~150-page novel, chapter by chapter.
- Outline first (full story arc), then each chapter sequentially
- Professional editing built into every chapter — publication-ready on first pass
- Regenerate as many times as you want — source interview is never touched

### Phase 3 — The PDF
Download a stunning, KDP-ready interior PDF.
- Professional serif typography (Liberation Serif / Noto Serif / Times)
- 5.5" × 8.5" trim (standard novel)
- Title page, copyright page, table of contents
- Chapter headings with decorative spacing
- Scene break ornaments, smart quotes, em dashes
- Ready to upload directly to Amazon KDP

---

## How To Drive This (for the Agent)

**The entire skill is chat-driven.** The user just talks. You orchestrate everything by calling the right commands based on conversational context.

### Setup Check
Before first use, ensure reportlab is installed for PDF generation:
```
pip install reportlab
```

### The Conversational Loop

**When a user first arrives or says "start a new book":**
```
python3 "{baseDir}/skill.py" start --title "<title>" --author "<author>" --pages 150
```
This creates the project and returns the consent message. Present it to the user and wait for "I AGREE".

**During the interview (Phase 1):**
Every time the user says something, log it and get guidance:
```
python3 "{baseDir}/skill.py" answer --project <id> --text "<their response>"
```
The response includes:
- `llm_guidance` — detailed interviewer instructions for you
- `question_bank` — categorized questions to draw from
- `word_count` / `progress_pct` — track progress
- `ready_for_phase2` — when true, you can suggest sealing

**YOUR JOB during Phase 1:** Be the world's best documentary interviewer.
- Ask ONE question at a time from the guidance
- Reflect back what they said to show you're listening
- Pursue threads — when they mention something in passing, come back to it
- When they give short answers, ask for specifics: "What did that look like?"
- When `ready_for_phase2` is true, gently suggest: "I think we have enough material. Ready to turn this into your book?"

**When the user says "I'm done" or "seal it":**
```
python3 "{baseDir}/skill.py" seal --project <id>
```

### Book Generation (Phase 2) — THE CRITICAL PART

**When the user says "generate my book" or "write it":**

Use the smart orchestrator — call it repeatedly and it tells you what to do next:
```
python3 "{baseDir}/skill.py" generate-book --project <id> --model "<best_available>"
```

**Step 1: Outline**
- `generate-book` returns `step: "generate_outline"` with a prompt and the full transcript
- Feed the prompt + transcript to the BEST available LLM (prefer the most capable model)
- The LLM returns a JSON outline
- Save it:
```
python3 "{baseDir}/skill.py" apply-outline --project <id> --json '<json>' --model "<model>"
```

**Steps 2-N: Chapters (one at a time, IN ORDER)**
- Call `generate-book` again — it returns `step: "generate_chapter"` with chapter number, prompt, and source material
- Feed the prompt + source material to the LLM
- **THE LLM MUST WRITE THE FULL CHAPTER** (2,500-4,500 words). Not a summary. Not an outline. The actual chapter text.
- Save it:
```
python3 "{baseDir}/skill.py" apply-chapter --project <id> --num <n> --title "<title>" --content "<full chapter text>" --model "<model>"
```
- Give the user a brief update: "Chapter 3 of 15 done — 'The Turning Point' (3,200 words)"
- Call `generate-book` again for the next chapter

**When all chapters are done:**
- `generate-book` returns `step: "complete"` with stats
- Tell the user their book is written and offer PDF generation

### CRITICAL: Chapter Generation Quality

The chapter prompts include built-in editing standards. But YOU must also verify:
1. **Word count**: Each chapter should be 2,500-4,500 words. If the LLM returns less than 2,000 words, regenerate it with stronger word-count emphasis.
2. **Content**: The chapter should be narrative prose, not a summary or outline.
3. **Continuity**: Each chapter should flow from the previous one.

If a chapter is too short or is clearly a summary instead of actual prose, tell the LLM to try again with emphasis on writing the FULL chapter with scenes, dialogue, and sensory detail.

### PDF Generation (Phase 3)

**When the user says "make the PDF" or "download my book":**
```
python3 "{baseDir}/skill.py" build-pdf --project <id>
```
Returns the file path. Present it to the user for download.

The PDF includes:
- Half-title page
- Full title page with decorative rule
- Copyright page (with content warnings if applicable)
- Table of contents
- All chapters with drop spacing, decorative rules, and proper page numbers
- Professional body text: justified, serif font, indented paragraphs
- Scene breaks with ornamental markers (✦ ✦ ✦)
- Smart typography: curly quotes, em dashes, proper ellipses

---

## The Chat Command (Simplified Interface)

For simpler integrations, there's a single chat entry point that auto-routes:
```
python3 "{baseDir}/skill.py" chat --message "<user message>" --project "<id>"
```
It detects intent (start, answer, seal, generate, pdf, status, etc.) and routes to the right handler. The `--project` is optional — it finds the most recent project if omitted.

---

## All Commands Reference

### Phase 1: Interview
```
python3 "{baseDir}/skill.py" start --title "<title>" --author "<author>" --pages 150
python3 "{baseDir}/skill.py" answer --project <id> --text "<response>"
python3 "{baseDir}/skill.py" status --project <id>
python3 "{baseDir}/skill.py" list
python3 "{baseDir}/skill.py" seal --project <id>
```

### Phase 2: Book Generation
```
python3 "{baseDir}/skill.py" generate-book --project <id> --model "<model>"
python3 "{baseDir}/skill.py" generate-outline --project <id> --model "<model>"
python3 "{baseDir}/skill.py" apply-outline --project <id> --json '<json>' --model "<model>"
python3 "{baseDir}/skill.py" apply-outline --project <id> --json-file outline.json --model "<model>"
python3 "{baseDir}/skill.py" generate-chapter --project <id> --num 1 --model "<model>"
python3 "{baseDir}/skill.py" apply-chapter --project <id> --num 1 --title "Title" --content "<text>" --model "<model>"
python3 "{baseDir}/skill.py" apply-chapter --project <id> --num 1 --title "Title" --content-file ch1.md --model "<model>"
python3 "{baseDir}/skill.py" book-stats --project <id>
python3 "{baseDir}/skill.py" reset-draft --project <id>
```

### Phase 3: PDF
```
python3 "{baseDir}/skill.py" build-pdf --project <id>
python3 "{baseDir}/skill.py" build-pdf --project <id> --out /custom/path/
```

### Utility
```
python3 "{baseDir}/skill.py" export --project <id> --out "{baseDir}/output"
python3 "{baseDir}/skill.py" chat --message "..." --project <id>
```

---

## Word Targets

| What | Words | Pages |
|------|-------|-------|
| Raw material (Phase 1 minimum) | 20,000 | ~73 |
| Raw material (ideal) | 35,000 | ~127 |
| Generated book | ~41,250 | ~150 |
| Per chapter | 2,500-4,500 | 9-16 |

---

## Non-Negotiables

1. **Consent Gate**: User must type "I AGREE" before any interview begins
2. **User Control**: SKIP / PAUSE / STOP always available during Phase 1
3. **No Diagnosis**: Never diagnose, never play therapist
4. **No Pushing**: If user hesitates, offer alternatives — "We can come back to that"
5. **One Question**: Ask ONE question at a time during interviews
6. **Sacred Source**: Never modify sealed interview data
7. **Full Chapters**: Phase 2 must produce full prose chapters, not summaries
8. **Publication Quality**: Every chapter should be publication-ready with built-in editing

---

## Phase 2 Workflow (Quick Reference for Agent Loop)

```
REPEAT:
    result = generate-book --project <id>

    IF result.step == "generate_outline":
        outline_json = LLM(result.prompt + result.transcript)
        apply-outline --project <id> --json outline_json

    ELIF result.step == "generate_chapter":
        chapter_text = LLM(result.prompt + result.source_material)
        apply-chapter --project <id> --num N --title "..." --content chapter_text
        Tell user: "Chapter N done — 'Title' (X words)"

    ELIF result.step == "complete":
        Tell user: "Book complete! X words, Y pages. Ready for PDF."
        BREAK

build-pdf --project <id>
Present download link to user.
```

---

## Database Schema (per-project SQLite)

Each novella is stored in `.data/kdp_<slug>_<id>.sqlite3` — open it directly to inspect.

- **meta**: key-value pairs (title, author, phase, sealed_at, target_pages, interview_state, pdf_path)
- **turns**: interview transcript (id, role, text, created_at) — IMMUTABLE after seal
- **outline**: versioned outlines (version, data_json, model_used, created_at)
- **chapters**: versioned chapters (chapter_num, version, title, content, word_count, model_used, created_at)
