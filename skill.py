#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
KDP Novella Skill Orchestrator

Trauma-informed interview system for documenting personal stories.
Phase 1: Gather raw material through persistent, gentle questioning (ONE pass)
Phase 2: Structure + generate a ~150-page KDP novella chapter by chapter (MANY passes)
Phase 3: Production-ready KDP interior PDF — stunning, publication-ready, downloadable

Design: ONE pass on the trauma, MANY passes on the output.
The interview is sealed after Phase 1 — source data is immutable.
Phases 2 and 3 can be re-run with different LLMs and settings without re-interviewing.

The entire experience is chat-driven — users just talk, the agent orchestrates.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import random
from typing import Any, Dict, List, Optional

try:
    from pdf_generator import generate_pdf as _gen_pdf
    HAS_PDF_GEN = True
except ImportError:
    HAS_PDF_GEN = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RAW_MATERIAL_MIN = 20000        # Minimum source words before allowing Phase 2
RAW_MATERIAL_TARGET = 35000     # Ideal source words
WORDS_PER_PAGE = 275
DEFAULT_TARGET_PAGES = 150
WORDS_PER_CHAPTER_MIN = 2500    # ~9 pages per chapter minimum
WORDS_PER_CHAPTER_MAX = 4500    # ~16 pages per chapter maximum

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_ts() -> int:
    return int(time.time())

def _unwrap(x: Any) -> str:
    return (x or "").strip() if isinstance(x, str) else str(x).strip()

def _base_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))

def _backend_path() -> str:
    return os.path.join(_base_dir(), "kdp_novella.py")

def _run_backend(args: List[str]) -> Dict[str, Any]:
    cmd = ["python3", _backend_path()] + args
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise SystemExit(json.dumps({
            "ok": False, "error": "backend_failed", "stderr": p.stderr
        }, ensure_ascii=False))
    try:
        return json.loads(p.stdout.strip() or "{}")
    except Exception:
        raise SystemExit(json.dumps({
            "ok": False, "error": "backend_non_json", "stdout": p.stdout
        }, ensure_ascii=False))

def _log_turn(pid: str, role: str, text: str) -> None:
    _run_backend(["log", "--project", pid, "--role", role, "--text", text])

def _get_word_count(pid: str) -> int:
    r = _run_backend(["word-count", "--project", pid])
    return int(r.get("total_words", 0))

def _get_project(pid: str) -> Dict[str, Any]:
    r = _run_backend(["show", "--project", pid])
    if not r.get("ok"):
        raise SystemExit(json.dumps(r, ensure_ascii=False))
    return r["project"]

def _set_meta(pid: str, key: str, value: str) -> None:
    _run_backend(["set-meta", "--project", pid, "--key", key, "--value", value])

# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------

CONSENT_MESSAGE = """**Before We Begin**

This tool helps you document your story into book form.

Important things to know:
- This is NOT therapy. I'm an AI helping you organize your thoughts.
- You control what you share. Say SKIP, PAUSE, or STOP anytime.
- Your responses are stored locally to build your book.
- Some questions may touch on difficult memories. You decide the depth.
- Your interview will be SEALED after completion — your words are sacred and will never be modified.
- The book generation (Phase 2) can be re-run as many times as needed without re-interviewing you.

If you understand and want to proceed, type: **I AGREE**"""

# ---------------------------------------------------------------------------
# Question Banks
# ---------------------------------------------------------------------------

OPENING_QUESTIONS = [
    {"id": "story_seed", "q": "Let's start simple. What's the story you want to tell? Just the headline version — we'll fill in details together."},
    {"id": "time_place", "q": "When and where does your story take place? Paint me a picture of the setting."},
    {"id": "who_you_were", "q": "Who were you when this story began? What was your life like before everything changed?"},
]

DEEPENING_QUESTIONS = [
    {"id": "key_people", "q": "Who are the important people in this story? Tell me about them — what they looked like, how they talked, their mannerisms."},
    {"id": "turning_point", "q": "What was the moment everything changed? Take me there — where were you, what time of day, what were you doing?"},
    {"id": "challenges", "q": "What was the hardest part? What did you have to face?"},
    {"id": "decisions", "q": "What choices did you have to make? Walk me through your thinking at the time."},
    {"id": "consequences", "q": "What happened because of those choices? How did things unfold?"},
    {"id": "relationships", "q": "How did the people around you react? Who surprised you? Who let you down?"},
    {"id": "daily_life", "q": "Walk me through a typical day during this period. Morning to night, what was the routine?"},
]

DETAIL_QUESTIONS = [
    {"id": "sensory", "q": "I want readers to feel like they're there. What did it look like? Sound like? Smell like? What was the weather?"},
    {"id": "dialogue", "q": "What did people say? Any conversations that stuck with you word-for-word?"},
    {"id": "internal", "q": "What was going through your mind during all this? What were you feeling in your body?"},
    {"id": "before_after", "q": "How were you different after? What changed in you that other people could see?"},
    {"id": "objects", "q": "Were there any objects, places, or songs that became important during this time? Things you still associate with it?"},
    {"id": "humor", "q": "Was there anything funny, absurd, or ironic that happened? Sometimes the hardest stories have unexpected humor."},
]

REFLECTION_QUESTIONS = [
    {"id": "meaning", "q": "Looking back now, what does this story mean to you? What did it teach you?"},
    {"id": "message", "q": "When someone reads your book, what do you want them to take away?"},
    {"id": "unfinished", "q": "Is there anything we haven't talked about that belongs in this story?"},
    {"id": "title_ideas", "q": "If you had to name this story in three words, what would they be?"},
    {"id": "audience", "q": "Who do you imagine reading this? Someone going through something similar? Your kids someday? The general public?"},
]

CONTINUATION_PROMPTS = [
    "Tell me more about that.",
    "What happened next?",
    "How did that make you feel?",
    "Who else was there?",
    "What were you thinking in that moment?",
    "And then?",
    "Can you describe that in more detail?",
    "What did they say exactly?",
    "Take your time. What else do you remember?",
    "That's important. Tell me more.",
    "Where were you when that happened?",
    "What did you do after that?",
    "How long did that last?",
    "Who did you tell about this?",
    "What was the first thing you thought when that happened?",
]

# Acknowledgments — brief, warm, non-therapeutic
_ACKS = [
    "Thank you for sharing that.",
    "That's powerful. Thank you.",
    "I hear you.",
    "That's important.",
    "Thank you for trusting me with that.",
    "I appreciate you telling me that.",
    "Got it. That helps me understand.",
    "Okay. Thank you.",
]

# ---------------------------------------------------------------------------
# Phase 1: Question selection
# ---------------------------------------------------------------------------

# Map interview phases to their question banks (in priority order)
_PHASE_BANKS = {
    "opening":    [OPENING_QUESTIONS, DEEPENING_QUESTIONS],
    "deepening":  [DEEPENING_QUESTIONS, DETAIL_QUESTIONS],
    "detail":     [DETAIL_QUESTIONS, REFLECTION_QUESTIONS],
    "reflection": [REFLECTION_QUESTIONS],
}


def _pick_next_question(wc: int, iv: Dict[str, Any]) -> str:
    """
    Select the next interviewer question, based on phase and topics already
    covered. Mutates iv["topics_covered"] when a new topic is picked.

    Returns a complete interviewer message: acknowledgment + question.
    This gets logged directly as an assistant turn — the skill owns its
    own transcript and never relies on the caller to round-trip it.
    """
    phase = iv.get("phase", "opening")
    covered = set(iv.get("topics_covered", []))
    banks = _PHASE_BANKS.get(phase, [DEEPENING_QUESTIONS])

    # Find the first uncovered question across the phase's banks
    for bank in banks:
        for q in bank:
            if q["id"] not in covered:
                iv.setdefault("topics_covered", []).append(q["id"])
                ack = random.choice(_ACKS)
                return f"{ack}\n\n{q['q']}"

    # All structured questions exhausted — use continuation prompts
    prompt = random.choice(CONTINUATION_PROMPTS)
    ack = random.choice(_ACKS)

    # If near target, nudge toward wrapping up
    if wc >= RAW_MATERIAL_TARGET:
        return (f"{ack}\n\nWe have a lot of great material — more than enough for your book. "
                f"Is there anything else you want to make sure is in the story? "
                f"If not, we can seal the interview and start building your book.")
    if wc >= RAW_MATERIAL_MIN:
        return (f"{ack}\n\n{prompt}\n\n"
                f"(By the way — we have enough material to start your book whenever you're ready. "
                f"Say **SEAL** when you want to lock in your interview and move to book generation.)")

    return f"{ack}\n\n{prompt}"

# ---------------------------------------------------------------------------
# Phase 1: Interview state management
# ---------------------------------------------------------------------------

def _get_interview_state(pid: str) -> Dict[str, Any]:
    proj = _get_project(pid)
    meta = proj.get("meta", {})
    raw = meta.get("interview_state", "")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {}

def _set_interview_state(pid: str, iv: Dict[str, Any]) -> None:
    _set_meta(pid, "interview_state", json.dumps(iv, ensure_ascii=False))

def _build_llm_guidance(wc: int, iv: Dict[str, Any]) -> str:
    phase = iv.get("phase", "opening")
    topics = iv.get("topics_covered", [])
    threads = iv.get("threads_to_explore", [])
    progress = min(100, int((wc / RAW_MATERIAL_TARGET) * 100))
    pages = wc // WORDS_PER_PAGE

    return f"""## Interview Guidance — Phase 1

**Progress**: {wc:,} words ({progress}%) ≈ {pages} pages raw material
**Phase**: {phase}
**Topics Covered**: {', '.join(topics) if topics else 'Starting'}
**Threads to Explore**: {', '.join(threads) if threads else 'Listen for new threads'}

### Your Role
Documentary interviewer. You are the world's best listener, helping them tell THEIR story. NOT therapy, NOT counseling.

### Technique
1. Ask ONE question, then wait. Never stack questions.
2. Use silence — let them think, don't rush to fill gaps
3. Reflect back — "So you're saying..." to show you're listening
4. Gentle probes — "What happened next?" "And then?"
5. Validate without analyzing — "That makes sense" "I can see why"
6. When they give short answers, ask for specifics — "What did that look like?" "What time of day?"
7. Pursue threads — when they mention something in passing, come back to it

### Phase Guidance
- **Opening** (0-5k words): Broad strokes, setting, who they were before
- **Deepening** (5k-15k): Key people, turning points, challenges, relationships, daily life
- **Detail** (15k-25k): Sensory details, dialogue, internal experience, objects, humor
- **Reflection** (25k+): Meaning, message, what's unfinished, audience, title ideas

### Red Lines
- NEVER diagnose or play therapist
- If distressed, offer: "We can skip this, pause, or change topic. You're in control."
- Don't push into trauma. If they hesitate: "We can come back to that, or not. Totally up to you."
- Never say "I understand how you feel" — you don't. Say "Thank you for sharing that."

{"### ⚠️ SUFFICIENT MATERIAL — Begin wrapping up Phase 1. Ask reflection questions. When done, suggest sealing the interview." if wc >= RAW_MATERIAL_MIN else ""}
{"### ✅ EXCELLENT MATERIAL — You have more than enough. Wrap up and seal." if wc >= RAW_MATERIAL_TARGET else ""}
"""

# ---------------------------------------------------------------------------
# Phase 2: Outline generation prompt
# ---------------------------------------------------------------------------

def _build_outline_prompt(wc: int, target_pages: int) -> str:
    target_words = target_pages * WORDS_PER_PAGE
    num_chapters = max(10, min(20, target_pages // 10))  # ~10 pages per chapter
    words_per_ch = target_words // num_chapters

    return f"""## Phase 2A: Create the Book Outline

You are a literary editor reading an interview transcript from a trauma survivor / personal story.
Your job: extract the narrative structure and plan a {target_pages}-page book (~{target_words:,} words).

### Requirements
- Plan exactly {num_chapters} chapters, each approximately {words_per_ch:,} words (~{words_per_ch // WORDS_PER_PAGE} pages)
- Total MUST hit approximately {target_words:,} words for a {target_pages}-page KDP novella
- Preserve their authentic voice — this is THEIR story, not yours
- Use scenes (show-don't-tell) wherever the transcript provides enough detail
- Note where dialogue can be reconstructed from their quotes
- Identify where names/places should be changed for privacy
- Each chapter must end with momentum — a reason to turn the page

### Output JSON (strict format):
```json
{{
  "working_title": "Title of the book",
  "core_narrative": "One paragraph — what is this book really about?",
  "target_pages": {target_pages},
  "target_words": {target_words},
  "chapter_outline": [
    {{
      "n": 1,
      "title": "Chapter Title",
      "summary": "2-3 sentences: what happens in this chapter",
      "opens_with": "First line or opening scene description",
      "closes_with": "Final image or cliffhanger to maintain page-to-page continuity",
      "key_scenes": ["Scene 1 description", "Scene 2 description"],
      "source_quotes": ["Direct quotes from transcript to use/adapt"],
      "target_words": {words_per_ch},
      "emotional_arc": "Where the reader's emotions should be at the end of this chapter"
    }}
  ],
  "themes": ["Theme 1", "Theme 2"],
  "voice_notes": "Specific notes on how to preserve their authentic voice — speech patterns, vocabulary, rhythm",
  "content_warnings": "Any content warnings needed for the book",
  "privacy_notes": "Names/places that should be changed",
  "missing_pieces": ["Things that the transcript doesn't cover well — we won't re-interview, so fill gaps with narration"]
}}
```

### CRITICAL: Page-to-page continuity
Each chapter's "closes_with" must connect to the next chapter's "opens_with".
The reader must never feel a gap between chapters. Plan the transitions explicitly.

### Voice Analysis (include in voice_notes)
Before outlining, analyze the narrator's voice from the transcript:
- How do they speak? (formal/informal, vocabulary level, sentence patterns)
- What metaphors or comparisons do they use naturally?
- What's their emotional default? (angry, reflective, dark humor, matter-of-fact)
- How do they describe people? (physical details, behavior, dialogue patterns)
- What words or phrases do they repeat?
Capture ALL of this in "voice_notes" — every chapter must sound like them, not like a writer.

### Quality Planning (built into the outline)
- Each chapter must have ENOUGH planned material for its target word count of immersive narrative
- Plan specific SCENES (not summaries) for each chapter — location, characters, action, emotional beat
- Plan dialogue opportunities wherever the transcript supports them
- Note sensory details available in the transcript for each chapter
- Address pacing: the book should accelerate through the middle and land with emotional weight
- The outline IS the editing plan — get the structure right and the chapters write themselves

### Missing Material Strategy
The transcript won't cover everything. For gaps:
- Bridge with reflective first-person narration ("I don't remember exactly, but...")
- Use time-skip transitions ("Three years later...")
- Never fabricate events — bridge with the narrator's emotional truth
- List all gaps in "missing_pieces" so the chapter writer knows where to bridge
"""

# ---------------------------------------------------------------------------
# Phase 2: Chapter generation prompt
# ---------------------------------------------------------------------------

def _build_chapter_prompt(chapter: Dict[str, Any], outline: Dict[str, Any],
                          prev_chapter_ending: str, next_chapter_opening: str,
                          target_words: int) -> str:
    ch_num = chapter.get("n", "?")
    total_chs = len(outline.get("chapter_outline", []))

    return f"""## Phase 2B: Write Chapter {ch_num} of {total_chs}

You are ghostwriting a chapter of a first-person memoir/novella based on interview material.

### Book Context
- **Title**: {outline.get('working_title', 'Untitled')}
- **Core Narrative**: {outline.get('core_narrative', '')}
- **Voice Notes**: {outline.get('voice_notes', 'Write in their authentic voice')}
- **Privacy Notes**: {outline.get('privacy_notes', 'Change names as needed')}

### This Chapter
- **Chapter {ch_num}**: {chapter.get('title', 'Untitled')}
- **Summary**: {chapter.get('summary', '')}
- **Opens with**: {chapter.get('opens_with', '')}
- **Closes with**: {chapter.get('closes_with', '')}
- **Key scenes**: {json.dumps(chapter.get('key_scenes', []))}
- **Source quotes to weave in**: {json.dumps(chapter.get('source_quotes', []))}
- **Emotional arc**: {chapter.get('emotional_arc', '')}
- **Target length**: {target_words:,} words (THIS IS CRITICAL — hit the target)

### Continuity
{"- **Previous chapter ended with**: " + prev_chapter_ending if prev_chapter_ending else "- This is the FIRST chapter. Open strong."}
{"- **Next chapter opens with**: " + next_chapter_opening + " — so end this chapter leading into that." if next_chapter_opening else "- This is the LAST chapter. End the book with resonance."}

### Writing Rules
1. First person POV — you ARE the narrator telling their story
2. SHOW don't tell — use scenes with sensory detail, dialogue, internal monologue
3. Preserve their voice — use their vocabulary, speech patterns, rhythm
4. Hit approximately {target_words:,} words. Do NOT write a summary or outline — write the FULL chapter
5. End with momentum connecting to the next chapter
6. Weave in source quotes naturally — they should feel like memory, not quotation
7. Where the transcript is thin, bridge with reflective narration in their voice
8. Do NOT add content warnings or meta-commentary — just write the story
9. Mark scene breaks (time/location jumps within the chapter) with: * * *
10. Vary paragraph length — short punches mixed with flowing passages
11. Dialogue must sound natural and character-specific. Use contractions. Real people don't speak in complete sentences
12. Every scene must MOVE: reveal character, advance the story, or build the world. Cut anything that doesn't

### Publication-Ready Quality (editing is BUILT IN — not a separate pass)
This chapter must be INDISTINGUISHABLE from a professionally edited memoir:
- ZERO typos, grammar errors, or punctuation mistakes
- Proper em dashes (\u2014) not hyphens for interrupted thoughts
- Proper ellipses (\u2026) for trailing off
- Consistent verb tense: past tense for narration, present for reflection passages
- No purple prose — clean, muscular sentences that serve the story
- Cut every unnecessary adverb. Show the emotion instead of naming it
- No info dumps — weave backstory into action and dialogue

### Self-Editing Checklist (verify ALL before returning)
\u2713 Word count within 10% of target ({target_words:,} words)
\u2713 Opens exactly as specified in the outline
\u2713 Closes with momentum toward the next chapter
\u2713 All assigned source quotes woven in naturally
\u2713 Character names consistent with outline
\u2713 Timeline consistent with previous chapters
\u2713 Scene breaks marked with * * *
\u2713 First person POV maintained — no slips
\u2713 Voice matches the narrator's natural speech patterns
\u2713 Sensory details in every scene (sight, sound, smell, touch)
\u2713 Dialogue sounds like real speech, not written prose

RETURN ONLY THE CHAPTER TEXT. No word counts, notes, meta-commentary, or markdown headers.
The output should be ready to paste directly into a book.
"""

# ---------------------------------------------------------------------------
# CLI: start (create project, show consent)
# ---------------------------------------------------------------------------

def cmd_start(args) -> Dict[str, Any]:
    pages = int(args.pages) if args.pages else DEFAULT_TARGET_PAGES
    r = _run_backend(["init", "--title", args.title, "--author", args.author or "", "--pages", str(pages)])
    if not r.get("ok"):
        return r

    pid = r["project_id"]
    iv = {
        "phase": "consent",
        "created_at": _now_ts(),
        "topics_covered": [],
        "threads_to_explore": [],
        "consent_given": False,
    }
    _set_interview_state(pid, iv)
    _log_turn(pid, "assistant", CONSENT_MESSAGE)

    return {
        "ok": True,
        "project_id": pid,
        "phase": "consent",
        "message": CONSENT_MESSAGE,
        "waiting_for": "User to type 'I AGREE'",
    }

# ---------------------------------------------------------------------------
# CLI: answer (interview loop)
# ---------------------------------------------------------------------------

def cmd_answer(args) -> Dict[str, Any]:
    pid = args.project
    answer = _unwrap(args.text)

    # Log the PREVIOUS assistant response if the caller passed it back.
    # This captures LLM-generated interviewer questions that the skill
    # itself can't know about — the calling agent generates them from
    # llm_guidance and must round-trip them here on the next call.
    prev_response = _unwrap(getattr(args, 'assistant_response', '') or '')
    if prev_response:
        _log_turn(pid, "assistant", prev_response)

    if not answer:
        return {"ok": True, "project_id": pid, "message": "I didn't catch that. Could you say more?"}

    _log_turn(pid, "user", answer)

    iv = _get_interview_state(pid)
    wc = _get_word_count(pid)

    # Check if project is already sealed
    proj = _get_project(pid)
    if proj.get("sealed"):
        return {
            "ok": False,
            "error": "project_sealed",
            "message": "This interview is sealed. Source data is protected. "
                       "Use 'generate-outline' and 'generate-chapter' to create the book, "
                       "or 'reset-draft' to start a fresh generation pass.",
            "word_count": wc,
        }

    # Consent phase
    if iv.get("phase") == "consent":
        if "AGREE" in answer.upper():
            iv["phase"] = "opening"
            iv["consent_given"] = True
            iv["consent_ts"] = _now_ts()
            _set_interview_state(pid, iv)

            first_q = OPENING_QUESTIONS[0]
            msg = f"Thank you. Let's begin.\n\nRemember: SKIP, PAUSE, or STOP anytime. You're in control.\n\n{first_q['q']}"
            _log_turn(pid, "assistant", msg)
            iv["topics_covered"].append(first_q["id"])
            _set_interview_state(pid, iv)

            return {"ok": True, "project_id": pid, "phase": "opening", "message": msg, "word_count": wc}
        else:
            return {"ok": True, "project_id": pid, "phase": "consent",
                    "message": "Type 'I AGREE' to proceed, or close this window if you'd rather not.", "waiting_for": "consent"}

    # Control words
    upper = answer.upper().strip()
    if upper == "STOP":
        iv["phase"] = "stopped"
        _set_interview_state(pid, iv)
        msg = f"Stopped. Your {wc:,} words of material are saved safely. Resume anytime with: status --project {pid}"
        _log_turn(pid, "assistant", msg)
        return {"ok": True, "project_id": pid, "phase": "stopped", "message": msg, "word_count": wc}

    if upper == "PAUSE":
        iv["paused"] = True
        _set_interview_state(pid, iv)
        msg = f"Paused. Your {wc:,} words are saved. Take all the time you need."
        _log_turn(pid, "assistant", msg)
        return {"ok": True, "project_id": pid, "phase": iv.get("phase"), "paused": True, "message": msg, "word_count": wc}

    if upper == "SKIP":
        msg = "No problem. " + random.choice([
            "What else feels important to this story?",
            "Is there another part you'd like to explore?",
            "What haven't we talked about yet?",
            "What's a part of this story you actually want to tell?",
        ])
        _log_turn(pid, "assistant", msg)
        return {"ok": True, "project_id": pid, "phase": iv.get("phase"), "message": msg,
                "word_count": wc, "llm_guidance": _build_llm_guidance(wc, iv)}

    # Resume if paused
    if iv.get("paused"):
        iv["paused"] = False
        _set_interview_state(pid, iv)

    # Update phase based on word count
    if wc < 5000:
        iv["phase"] = "opening"
    elif wc < 15000:
        iv["phase"] = "deepening"
    elif wc < 25000:
        iv["phase"] = "detail"
    else:
        iv["phase"] = "reflection"

    # ── Select and LOG the next interviewer question ──
    # The skill owns its own transcript. We always pick a question,
    # log it, and return it. The LLM can enhance delivery via
    # llm_guidance, but the core question is always in the DB.
    next_q = _pick_next_question(wc, iv)
    _log_turn(pid, "assistant", next_q)
    _set_interview_state(pid, iv)  # _pick_next_question may update topics_covered

    return {
        "ok": True,
        "project_id": pid,
        "phase": iv["phase"],
        "message": next_q,
        "word_count": wc,
        "pages_estimate": wc // WORDS_PER_PAGE,
        "progress_pct": min(100, int((wc / RAW_MATERIAL_TARGET) * 100)),
        "ready_for_phase2": wc >= RAW_MATERIAL_MIN,
        "llm_guidance": _build_llm_guidance(wc, iv),
    }

# ---------------------------------------------------------------------------
# CLI: status
# ---------------------------------------------------------------------------

def cmd_status(args) -> Dict[str, Any]:
    pid = args.project
    proj = _get_project(pid)
    iv = _get_interview_state(pid)
    wc = _get_word_count(pid)
    meta = proj.get("meta", {})

    return {
        "ok": True,
        "project_id": pid,
        "title": meta.get("title", "Untitled"),
        "phase": meta.get("phase", iv.get("phase", "unknown")),
        "consent_given": iv.get("consent_given", False),
        "paused": iv.get("paused", False),
        "sealed": proj.get("sealed", False),
        "word_count": wc,
        "pages_estimate": wc // WORDS_PER_PAGE,
        "progress_pct": min(100, int((wc / RAW_MATERIAL_TARGET) * 100)),
        "ready_for_phase2": wc >= RAW_MATERIAL_MIN,
        "topics_covered": iv.get("topics_covered", []),
        "book_stats": proj.get("book", {}),
    }

# ---------------------------------------------------------------------------
# CLI: list
# ---------------------------------------------------------------------------

def cmd_list(args) -> Dict[str, Any]:
    return _run_backend(["list"])

# ---------------------------------------------------------------------------
# CLI: seal (lock interview, protect source data)
# ---------------------------------------------------------------------------

def cmd_seal(args) -> Dict[str, Any]:
    pid = args.project
    wc = _get_word_count(pid)

    if wc < RAW_MATERIAL_MIN:
        return {
            "ok": False,
            "error": "insufficient_material",
            "word_count": wc,
            "needed": RAW_MATERIAL_MIN,
            "message": f"Only {wc:,} words. Need at least {RAW_MATERIAL_MIN:,} before sealing. Keep interviewing.",
        }

    r = _run_backend(["seal", "--project", pid])
    if r.get("ok"):
        iv = _get_interview_state(pid)
        iv["phase"] = "sealed"
        iv["sealed_ts"] = _now_ts()
        _set_interview_state(pid, iv)

    return {
        "ok": True,
        "project_id": pid,
        "sealed": True,
        "source_words": wc,
        "source_pages": wc // WORDS_PER_PAGE,
        "message": f"Interview sealed. {wc:,} words of source material locked and protected. "
                   f"Now use 'generate-outline' to plan the book. "
                   f"You can regenerate the book as many times as needed — the source is safe.",
    }

# ---------------------------------------------------------------------------
# CLI: generate-outline (Phase 2A prompt)
# ---------------------------------------------------------------------------

def cmd_generate_outline(args) -> Dict[str, Any]:
    pid = args.project
    proj = _get_project(pid)
    wc = _get_word_count(pid)

    if wc < RAW_MATERIAL_MIN:
        return {"ok": False, "error": "insufficient_material", "word_count": wc, "needed": RAW_MATERIAL_MIN}

    r = _run_backend(["turns", "--project", pid, "--limit", "100000"])
    turns = r.get("turns", [])

    meta = proj.get("meta", {})
    target_pages = int(meta.get("target_pages", str(DEFAULT_TARGET_PAGES)))

    prompt = _build_outline_prompt(wc, target_pages)

    # Format transcript for the LLM
    transcript_text = ""
    for t in turns:
        if t["role"] in ("user", "assistant"):
            transcript_text += f"**{t['role'].upper()}**: {t['text']}\n\n"

    return {
        "ok": True,
        "project_id": pid,
        "word_count": wc,
        "target_pages": target_pages,
        "model_hint": args.model or "",
        "prompt": prompt,
        "transcript": transcript_text,
        "instruction": "Feed the prompt + transcript to your chosen LLM. "
                       "Save the resulting JSON with: apply-outline --project {pid} --json '<json>' --model '<model_name>'"
    }

# ---------------------------------------------------------------------------
# CLI: apply-outline (save LLM-generated outline)
# ---------------------------------------------------------------------------

def cmd_apply_outline(args) -> Dict[str, Any]:
    pid = args.project
    json_str = args.json
    if args.json_file:
        with open(args.json_file, "r", encoding="utf-8") as f:
            json_str = f.read()

    r = _run_backend([
        "save-outline", "--project", pid,
        "--json", json_str,
        "--model", args.model or "",
    ])
    return r

# ---------------------------------------------------------------------------
# CLI: generate-chapter (Phase 2B prompt for one chapter)
# ---------------------------------------------------------------------------

def cmd_generate_chapter(args) -> Dict[str, Any]:
    pid = args.project
    chapter_num = int(args.num)

    # Get outline
    r = _run_backend(["get-outline", "--project", pid])
    if not r.get("ok"):
        return {"ok": False, "error": "no_outline", "message": "Generate an outline first with 'generate-outline'."}

    outline = r["data"]
    chapters = outline.get("chapter_outline", [])

    if chapter_num < 1 or chapter_num > len(chapters):
        return {"ok": False, "error": "invalid_chapter", "message": f"Chapter {chapter_num} not in outline (1-{len(chapters)})."}

    chapter = chapters[chapter_num - 1]
    target_words = chapter.get("target_words", outline.get("target_words", DEFAULT_TARGET_PAGES * WORDS_PER_PAGE) // len(chapters))

    # Get previous chapter ending for continuity
    prev_ending = ""
    if chapter_num > 1:
        prev_ch = chapters[chapter_num - 2]
        prev_ending = prev_ch.get("closes_with", "")
        # Also check if we have an actual written chapter to pull the real ending from
        prev_written = _run_backend(["get-chapter", "--project", pid, "--num", str(chapter_num - 1)])
        if prev_written.get("ok") and prev_written.get("content"):
            # Use last 200 chars of actual written chapter for better continuity
            prev_ending = prev_written["content"].strip()[-500:]

    # Get next chapter opening for forward continuity
    next_opening = ""
    if chapter_num < len(chapters):
        next_ch = chapters[chapter_num]
        next_opening = next_ch.get("opens_with", "")

    # Get transcript for reference
    tr = _run_backend(["turns", "--project", pid, "--limit", "100000"])
    transcript_text = ""
    for t in tr.get("turns", []):
        if t["role"] == "user":
            transcript_text += f"{t['text']}\n\n"

    prompt = _build_chapter_prompt(chapter, outline, prev_ending, next_opening, target_words)

    return {
        "ok": True,
        "project_id": pid,
        "chapter_num": chapter_num,
        "chapter_title": chapter.get("title", ""),
        "target_words": target_words,
        "model_hint": args.model or "",
        "prompt": prompt,
        "source_material": transcript_text,
        "instruction": f"Feed the prompt + source material to your chosen LLM. "
                       f"Save the result with: apply-chapter --project {pid} --num {chapter_num} "
                       f"--title \"{chapter.get('title', '')}\" --content '<text>' --model '<model>'"
    }

# ---------------------------------------------------------------------------
# CLI: apply-chapter (save LLM-generated chapter)
# ---------------------------------------------------------------------------

def cmd_apply_chapter(args) -> Dict[str, Any]:
    pid = args.project
    content = args.content or ""
    if args.content_file:
        with open(args.content_file, "r", encoding="utf-8") as f:
            content = f.read()

    r = _run_backend([
        "save-chapter", "--project", pid,
        "--num", str(args.num),
        "--title", args.title,
        "--content", content,
        "--model", args.model or "",
    ])
    return r

# ---------------------------------------------------------------------------
# CLI: reset-draft (wipe generated content, keep sacred source)
# ---------------------------------------------------------------------------

def cmd_reset_draft(args) -> Dict[str, Any]:
    return _run_backend(["reset-draft", "--project", args.project])

# ---------------------------------------------------------------------------
# CLI: book-stats
# ---------------------------------------------------------------------------

def cmd_book_stats(args) -> Dict[str, Any]:
    return _run_backend(["book-stats", "--project", args.project])

# ---------------------------------------------------------------------------
# CLI: export
# ---------------------------------------------------------------------------

def cmd_export(args) -> Dict[str, Any]:
    return _run_backend(["export", "--project", args.project, "--out", args.out])

# ---------------------------------------------------------------------------
# CLI: build-pdf (Phase 3 — production KDP PDF)
# ---------------------------------------------------------------------------

def cmd_build_pdf(args) -> Dict[str, Any]:
    """Generate a production-ready KDP interior PDF."""
    pid = args.project

    if not HAS_PDF_GEN:
        return {
            "ok": False,
            "error": "pdf_dependencies_missing",
            "message": "PDF generation requires reportlab. Install it:\n"
                       "  pip install reportlab\n"
                       "Then try again.",
        }

    proj = _get_project(pid)
    meta = proj.get("meta", {})

    # Get chapters
    chapters_r = _run_backend(["get-chapters", "--project", pid])
    if not chapters_r.get("ok") or not chapters_r.get("chapters"):
        return {
            "ok": False,
            "error": "no_chapters",
            "message": "No chapters written yet. Generate the book first with 'generate-book'.",
        }
    chapters = chapters_r["chapters"]

    # Get outline for metadata
    outline_r = _run_backend(["get-outline", "--project", pid])
    outline = outline_r.get("data", {}) if outline_r.get("ok") else {}

    # Output path
    title = outline.get("working_title", meta.get("title", "Untitled"))
    author = meta.get("author", "Anonymous")
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40] or "book"
    out_dir = getattr(args, 'out', '') or os.path.join(_base_dir(), "output")
    out_path = os.path.join(out_dir, f"{slug}_kdp_interior.pdf")

    # Generate PDF
    result = _gen_pdf(
        title=title,
        author=author,
        chapters=chapters,
        output_path=out_path,
        dedication=meta.get("dedication", ""),
        content_warnings=outline.get("content_warnings", ""),
        about_author=meta.get("about_author", ""),
    )

    if result.get("ok"):
        _set_meta(pid, "phase", "complete")
        _set_meta(pid, "pdf_path", result["path"])
        result["project_id"] = pid
        result["message"] = (
            f"\u2728 PDF generated! {result.get('chapters', 0)} chapters, "
            f"~{result.get('total_pages_est', 0)} pages.\n"
            f"Font: {result.get('font_used', 'Times')}\n"
            f"Trim: {result.get('trim_size', '5.5x8.5')}\n"
            f"File: {result['path']}\n\n"
            f"This PDF is ready to upload to Amazon KDP as your interior file."
        )

    return result

# ---------------------------------------------------------------------------
# CLI: generate-book (orchestrate full Phase 2 — resumable)
# ---------------------------------------------------------------------------

def cmd_generate_book(args) -> Dict[str, Any]:
    """
    Smart Phase 2 orchestrator. Call this repeatedly — it figures out
    what needs to happen next and returns the appropriate prompt.

    Flow: seal check → outline → chapters (1..N) → done (offer PDF).
    Resumable: skips already-completed steps.
    """
    pid = args.project
    proj = _get_project(pid)
    meta = proj.get("meta", {})
    wc = _get_word_count(pid)

    # Check sealed
    if not proj.get("sealed"):
        if wc < RAW_MATERIAL_MIN:
            return {
                "ok": False,
                "error": "insufficient_material",
                "word_count": wc,
                "needed": RAW_MATERIAL_MIN,
                "message": f"Only {wc:,} words of source material. "
                           f"Need at least {RAW_MATERIAL_MIN:,} before generating. Keep interviewing.",
            }
        return {
            "ok": False,
            "error": "not_sealed",
            "word_count": wc,
            "message": f"Interview has {wc:,} words — enough material! "
                       f"Seal the interview first to protect your source data, then generate.",
            "action": f"seal --project {pid}",
        }

    # Check outline
    outline_r = _run_backend(["get-outline", "--project", pid])
    has_outline = outline_r.get("ok", False)

    if not has_outline:
        # Need outline first — return outline prompt
        target_pages = int(meta.get("target_pages", str(DEFAULT_TARGET_PAGES)))
        tr = _run_backend(["turns", "--project", pid, "--limit", "100000"])
        turns = tr.get("turns", [])
        transcript_text = ""
        for t in turns:
            if t["role"] in ("user", "assistant"):
                transcript_text += f"**{t['role'].upper()}**: {t['text']}\n\n"

        return {
            "ok": True,
            "project_id": pid,
            "step": "generate_outline",
            "step_num": 1,
            "total_steps": "1 + N chapters",
            "word_count": wc,
            "target_pages": target_pages,
            "prompt": _build_outline_prompt(wc, target_pages),
            "transcript": transcript_text,
            "model_hint": getattr(args, 'model', '') or "",
            "instruction": (
                "Feed the prompt + transcript to the BEST available LLM.\n"
                "Parse the resulting JSON and save it with:\n"
                f"  apply-outline --project {pid} --json '<json>' --model '<model>'\n"
                "Then call generate-book again for the next step."
            ),
        }

    # Have outline — check which chapters still need writing
    outline = outline_r["data"]
    total_chapters = len(outline.get("chapter_outline", []))

    chapters_r = _run_backend(["get-chapters", "--project", pid])
    written = set()
    if chapters_r.get("ok"):
        for ch in chapters_r.get("chapters", []):
            written.add(ch["chapter_num"])

    # Find next unwritten chapter
    next_ch = None
    for i in range(1, total_chapters + 1):
        if i not in written:
            next_ch = i
            break

    if next_ch is None:
        # All chapters done!
        stats = _run_backend(["book-stats", "--project", pid])
        return {
            "ok": True,
            "project_id": pid,
            "step": "complete",
            "step_num": total_chapters + 1,
            "total_chapters": total_chapters,
            "written": sorted(written),
            "stats": stats,
            "message": (
                f"\u2705 All {total_chapters} chapters are written!\n"
                f"Total: {stats.get('total_words', 0):,} words "
                f"(~{stats.get('total_pages', 0)} pages).\n\n"
                f"Ready to generate your KDP PDF. Say 'make the PDF' or run:\n"
                f"  build-pdf --project {pid}"
            ),
        }

    # Generate prompt for next chapter
    chapter_info = outline["chapter_outline"][next_ch - 1]
    target_words = chapter_info.get(
        "target_words",
        outline.get("target_words", DEFAULT_TARGET_PAGES * WORDS_PER_PAGE) // total_chapters,
    )

    # Previous chapter ending for continuity
    prev_ending = ""
    if next_ch > 1:
        prev_outline = outline["chapter_outline"][next_ch - 2]
        prev_ending = prev_outline.get("closes_with", "")
        prev_written = _run_backend(["get-chapter", "--project", pid, "--num", str(next_ch - 1)])
        if prev_written.get("ok") and prev_written.get("content"):
            prev_ending = prev_written["content"].strip()[-500:]

    # Next chapter opening for forward continuity
    next_opening = ""
    if next_ch < total_chapters:
        next_outline = outline["chapter_outline"][next_ch]
        next_opening = next_outline.get("opens_with", "")

    # Source material
    tr = _run_backend(["turns", "--project", pid, "--limit", "100000"])
    transcript_text = ""
    for t in tr.get("turns", []):
        if t["role"] == "user":
            transcript_text += f"{t['text']}\n\n"

    prompt = _build_chapter_prompt(chapter_info, outline, prev_ending, next_opening, target_words)

    return {
        "ok": True,
        "project_id": pid,
        "step": "generate_chapter",
        "step_num": len(written) + 2,  # +1 for outline, +1 for 1-based
        "chapter_num": next_ch,
        "chapter_title": chapter_info.get("title", ""),
        "total_chapters": total_chapters,
        "written": sorted(written),
        "remaining": total_chapters - len(written),
        "target_words": target_words,
        "prompt": prompt,
        "source_material": transcript_text,
        "model_hint": getattr(args, 'model', '') or "",
        "message": (
            f"Writing chapter {next_ch} of {total_chapters}: "
            f"\"{chapter_info.get('title', '')}\" "
            f"({len(written)}/{total_chapters} done)"
        ),
        "instruction": (
            f"Feed the prompt + source material to the LLM.\n"
            f"Save the result with:\n"
            f"  apply-chapter --project {pid} --num {next_ch} "
            f"--title \"{chapter_info.get('title', '')}\" --content '<text>' --model '<model>'\n"
            f"Then call generate-book again for the next chapter."
        ),
    }

# ---------------------------------------------------------------------------
# CLI: chat (universal conversational entry point)
# ---------------------------------------------------------------------------

def _detect_intent(msg: str) -> str:
    """Simple intent detection from user message."""
    upper = msg.upper().strip()
    m = msg.lower().strip()

    # Explicit control words
    if upper in ("STOP", "PAUSE", "SKIP"):
        return upper.lower()

    # Start a new project
    if re.search(r"(start|new|begin|create)\b.*(book|project|story|novella|memoir)", m):
        return "start"

    # List projects
    if re.search(r"(list|show|my)\b.*(project|book|stori|novella)", m):
        return "list"

    # Seal interview
    if re.search(r"(seal|done|finish|lock)\b.*(interview|source|story|talking)", m):
        return "seal"
    if m in ("seal", "seal it", "i'm done", "im done", "done talking"):
        return "seal"

    # Generate book / outline / chapters
    if re.search(r"(generate|write|create|make|build)\b.*(book|novel|outline|chapter)", m):
        return "generate"
    if m in ("generate", "write it", "write my book", "make the book"):
        return "generate"

    # PDF
    if re.search(r"(pdf|download|publish|print|export|kindle|kdp)", m):
        return "pdf"
    if m in ("pdf", "make pdf", "get pdf", "download"):
        return "pdf"

    # Reset draft
    if re.search(r"(reset|redo|start.?over|wipe|clear)\b.*(draft|book|chapter|generation)", m):
        return "reset"

    # Status
    if re.search(r"(status|progress|where|how.*(far|much|going))", m):
        return "status"

    # Default: treat as interview answer or general conversation
    return "answer"


def _extract_title_from_msg(msg: str) -> str:
    """Try to extract a book title from a natural language message."""
    patterns = [
        r'(?:called?|titled?|named?)\s+["\'](.+?)["\']',
        r'(?:called?|titled?|named?)\s+(.+?)(?:\s+by\s|$)',
        r'(?:about|story of|memoir of)\s+(.+?)$',
    ]
    for pat in patterns:
        m = re.search(pat, msg, re.I)
        if m:
            return m.group(1).strip().rstrip('.')
    return ""


def cmd_chat(args) -> Dict[str, Any]:
    """
    Universal chat interface. Detects intent, manages state,
    routes to the right handler. The primary way to use this skill.
    """
    msg = (getattr(args, 'message', '') or "").strip()
    pid = (getattr(args, 'project', '') or "").strip()

    if not msg:
        return {
            "ok": True,
            "message": "I'm here. What would you like to do?",
            "suggestions": [
                "Start a new book",
                "List my projects",
                "Check my status",
            ],
        }

    intent = _detect_intent(msg)

    # ── No project context ──
    if not pid:
        if intent == "start":
            title = _extract_title_from_msg(msg) or "My Story"
            # Create a lightweight args-like object
            class _Args: pass
            a = _Args()
            a.title = title
            a.author = ""
            a.pages = str(DEFAULT_TARGET_PAGES)
            return cmd_start(a)

        if intent == "list":
            return _run_backend(["list"])

        # Try to find most recent active project
        projects = _run_backend(["list"]).get("projects", [])
        if projects:
            # Use the most recent (last) project
            pid = projects[-1]["project_id"]
        else:
            if intent in ("answer",):
                return {
                    "ok": True,
                    "message": "No projects found. Say something like:\n"
                               "  'Start a new book called My Life Story'\n"
                               "Or: 'List my projects'",
                }
            return {
                "ok": True,
                "message": "No projects yet. Tell me the title of your story and we'll begin.",
                "waiting_for": "title",
            }

    # ── With project context ──
    proj = _get_project(pid)
    meta = proj.get("meta", {})
    phase = meta.get("phase", "unknown")
    sealed = proj.get("sealed", False)

    # Route by intent + state
    if intent == "status":
        class _A: pass
        a = _A(); a.project = pid
        return cmd_status(a)

    if intent == "list":
        return _run_backend(["list"])

    if intent == "seal":
        class _A: pass
        a = _A(); a.project = pid
        return cmd_seal(a)

    if intent == "generate":
        class _A: pass
        a = _A(); a.project = pid; a.model = ""
        return cmd_generate_book(a)

    if intent == "pdf":
        class _A: pass
        a = _A(); a.project = pid; a.out = ""
        return cmd_build_pdf(a)

    if intent == "reset":
        class _A: pass
        a = _A(); a.project = pid
        return cmd_reset_draft(a)

    # Default: interview answer (Phase 1)
    if not sealed and phase in ("consent", "interview", "opening", "deepening", "detail", "reflection"):
        class _A: pass
        a = _A(); a.project = pid; a.text = msg
        a.assistant_response = getattr(args, 'assistant_response', '') or ''
        return cmd_answer(a)

    # Sealed but user is just talking — guide them
    if sealed and phase in ("sealed",):
        return {
            "ok": True,
            "project_id": pid,
            "phase": phase,
            "message": "Your interview is sealed and protected. Ready to create your book!\n\n"
                       "Say 'generate my book' to start writing, or\n"
                       "'check status' to see where things stand.",
        }

    if phase in ("outlining", "drafting"):
        return {
            "ok": True,
            "project_id": pid,
            "phase": phase,
            "message": "Your book is being generated. Say:\n"
                       "  'generate my book' — to continue writing chapters\n"
                       "  'check status' — to see progress\n"
                       "  'make the PDF' — if all chapters are done",
        }

    if phase == "complete":
        pdf_path = meta.get("pdf_path", "")
        return {
            "ok": True,
            "project_id": pid,
            "phase": phase,
            "message": "Your book is complete! \u2728\n\n"
                       + (f"PDF: {pdf_path}\n\n" if pdf_path else "")
                       + "Say 'make the PDF' to generate a fresh PDF, or\n"
                         "'reset draft' to rewrite with different settings.",
        }

    # Fallback
    return {
        "ok": True,
        "project_id": pid,
        "phase": phase,
        "message": "I'm not sure what you'd like to do. Try:\n"
                   "  'check status' — see where your project stands\n"
                   "  'generate my book' — start or continue book generation\n"
                   "  'make the PDF' — create the downloadable PDF",
    }

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skill.py",
                                description="KDP Novella — one pass trauma, many passes output")
    sub = p.add_subparsers(dest="cmd", required=True)

    # -- Phase 1: Interview --
    s = sub.add_parser("start", help="Create project and start interview")
    s.add_argument("--title", required=True)
    s.add_argument("--author", default="")
    s.add_argument("--pages", default=str(DEFAULT_TARGET_PAGES), help="Target page count (default: 150)")
    s.set_defaults(func=cmd_start)

    s = sub.add_parser("answer", help="Submit interview answer")
    s.add_argument("--project", required=True)
    s.add_argument("--text", required=True)
    s.add_argument("--assistant-response", default="",
                   help="The LLM-generated assistant response from the PREVIOUS turn. "
                        "Pass this so interviewer questions are recorded in the transcript.")
    s.set_defaults(func=cmd_answer)

    s = sub.add_parser("status", help="Check project status")
    s.add_argument("--project", required=True)
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("list", help="List all projects")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("seal", help="Lock interview — source becomes immutable")
    s.add_argument("--project", required=True)
    s.set_defaults(func=cmd_seal)

    # -- Phase 2: Book Generation --
    s = sub.add_parser("generate-outline", help="Get outline generation prompt for LLM")
    s.add_argument("--project", required=True)
    s.add_argument("--model", default="", help="Hint which LLM to use")
    s.set_defaults(func=cmd_generate_outline)

    s = sub.add_parser("apply-outline", help="Save LLM-generated outline")
    s.add_argument("--project", required=True)
    s.add_argument("--json", default="")
    s.add_argument("--json-file", default="")
    s.add_argument("--model", default="")
    s.set_defaults(func=cmd_apply_outline)

    s = sub.add_parser("generate-chapter", help="Get chapter generation prompt for LLM")
    s.add_argument("--project", required=True)
    s.add_argument("--num", required=True, type=int, help="Chapter number")
    s.add_argument("--model", default="", help="Hint which LLM to use")
    s.set_defaults(func=cmd_generate_chapter)

    s = sub.add_parser("apply-chapter", help="Save LLM-generated chapter")
    s.add_argument("--project", required=True)
    s.add_argument("--num", required=True, type=int)
    s.add_argument("--title", required=True)
    s.add_argument("--content", default="")
    s.add_argument("--content-file", default="")
    s.add_argument("--model", default="")
    s.set_defaults(func=cmd_apply_chapter)

    s = sub.add_parser("reset-draft", help="Wipe generated book, keep sacred source")
    s.add_argument("--project", required=True)
    s.set_defaults(func=cmd_reset_draft)

    s = sub.add_parser("book-stats", help="Show generated book statistics")
    s.add_argument("--project", required=True)
    s.set_defaults(func=cmd_book_stats)

    s = sub.add_parser("export", help="Export transcript + manuscript to files")
    s.add_argument("--project", required=True)
    s.add_argument("--out", default=os.path.join(_base_dir(), "output"))
    s.set_defaults(func=cmd_export)

    # -- Phase 3: PDF --
    s = sub.add_parser("build-pdf", help="Generate production-ready KDP interior PDF")
    s.add_argument("--project", required=True)
    s.add_argument("--out", default="", help="Output directory (default: {baseDir}/output)")
    s.set_defaults(func=cmd_build_pdf)

    # -- Orchestration --
    s = sub.add_parser("generate-book", help="Smart Phase 2 orchestrator — call repeatedly, it does the next step")
    s.add_argument("--project", required=True)
    s.add_argument("--model", default="", help="Preferred LLM for generation")
    s.set_defaults(func=cmd_generate_book)

    # -- Chat (universal entry point) --
    s = sub.add_parser("chat", help="Conversational interface — the primary way to use this skill")
    s.add_argument("--project", default="")
    s.add_argument("--message", required=True)
    s.add_argument("--assistant-response", default="",
                   help="The LLM-generated assistant response from the PREVIOUS turn. "
                        "Pass this so interviewer questions are recorded in the transcript.")
    s.set_defaults(func=cmd_chat)

    return p

def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        out = args.func(args)
        print(json.dumps(out, ensure_ascii=False))
    except SystemExit as e:
        print(str(e))
        raise
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        raise

if __name__ == "__main__":
    main()
