"""Draft a goal's phases, steps and tasks with Google Gemini (free tier).

Only the goal's title, description, the user's stated level and the goal's
time budget are sent. The draft comes back as an editable text outline; nothing
is saved until the user submits it.

Outline format, one item per line:
    # Phase title
    ## Step title
    - Task title (45 min)
"""
import json
import logging
import os
import re
import urllib.error
import urllib.request

from django.db import transaction

from .models import Phase, Step, Task

logger = logging.getLogger(__name__)

# Tried in order; the next one is used when one is busy or down. The free
# tier's models are often overloaded for a few minutes at a time.
MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.1-flash-lite"]
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT_SECONDS = 30
DEFAULT_TASK_MINUTES = 30

LEVELS = [
    ("beginner", "Complete beginner"),
    ("some", "Some experience"),
    ("experienced", "Experienced, want to go further"),
]

_TASK = {"type": "OBJECT", "properties": {
    "title": {"type": "STRING"}, "minutes": {"type": "INTEGER"},
}, "required": ["title", "minutes"]}
_STEP = {"type": "OBJECT", "properties": {
    "title": {"type": "STRING"}, "tasks": {"type": "ARRAY", "items": _TASK},
}, "required": ["title", "tasks"]}
_PHASE = {"type": "OBJECT", "properties": {
    "title": {"type": "STRING"}, "steps": {"type": "ARRAY", "items": _STEP},
}, "required": ["title", "steps"]}
SCHEMA = {"type": "OBJECT", "properties": {
    "phases": {"type": "ARRAY", "items": _PHASE},
}, "required": ["phases"]}


class DraftError(Exception):
    """Gemini couldn't produce a draft; the message is safe to show the user."""


def build_prompt(goal, level):
    weeks = max(1, (goal.target_date - goal.start_date).days // 7)
    total_hours = round(weeks * goal.days_per_week * float(goal.hours_per_day))
    return (
        "You are helping someone plan a personal goal. Break it into 2-5 phases "
        "(big stages, in order), each with 1-4 steps (concrete outcomes), each "
        "with 2-6 tasks (single sittings of 15-120 minutes, starting with a verb).\n"
        f"Goal: {goal.title}\n"
        f"Details: {goal.description or '(none)'}\n"
        f"Their level: {dict(LEVELS)[level]}\n"
        f"Time available: about {total_hours} hours in total over {weeks} weeks "
        f"({goal.days_per_week} days a week, {goal.hours_per_day:f} hours a day). "
        "Keep the total task time within that.\n"
        "Use short, plain titles under 80 characters, without numbering like \"Phase 1:\"."
    )


def _call(model, prompt, api_key):
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA},
    }
    request = urllib.request.Request(
        API_URL.format(model=model),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        data = json.load(response)
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)["phases"]


def draft_plan(goal, level):
    """Return a list of {title, steps: [{title, tasks: [{title, minutes}]}]}."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("AI drafting is off: the GEMINI_API_KEY environment variable is missing.")
        raise DraftError("AI drafting isn't available right now.")
    prompt = build_prompt(goal, level)
    for model in MODELS:
        try:
            phases = _call(model, prompt, api_key)
        except urllib.error.HTTPError as error:
            logger.warning("Gemini %s returned HTTP %s", model, error.code)
            if error.code in (429, 500, 503):
                continue  # busy or over the free quota: try the next model
            if error.code in (400, 401, 403):
                logger.error("Gemini rejected the API key (HTTP %s). Check GEMINI_API_KEY.", error.code)
            raise DraftError("AI drafting isn't available right now. Try again later.") from error
        except (urllib.error.URLError, TimeoutError) as error:
            logger.warning("Gemini %s unreachable: %s", model, error)
            continue  # network trouble or slow model: try the next one
        except (KeyError, IndexError, ValueError) as error:
            raise DraftError("The draft came back in a form that couldn't be read. Try again.") from error
        if phases:
            return phases
    raise DraftError("AI drafting is busy right now. Try again in a minute.")


def to_outline(phases):
    lines = []
    for phase in phases:
        lines.append(f"# {phase['title'].strip()}")
        for step in phase.get("steps", []):
            lines.append(f"## {step['title'].strip()}")
            for task in step.get("tasks", []):
                lines.append(f"- {task['title'].strip()} ({int(task['minutes'])} min)")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


_MINUTES = re.compile(r"\s*\((\d+)\s*(?:m|min|mins|minutes)\)\s*$", re.IGNORECASE)


def parse_outline(text):
    """Turn an outline back into phases. Returns (phases, errors)."""
    phases, errors = [], []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            if not phases:
                errors.append(f"Line {number}: a step (##) needs a phase (#) above it.")
                continue
            phases[-1]["steps"].append({"title": line[3:].strip(), "tasks": []})
        elif line.startswith("# "):
            phases.append({"title": line[2:].strip(), "steps": []})
        elif line.startswith("- "):
            if not phases or not phases[-1]["steps"]:
                errors.append(f"Line {number}: a task (-) needs a step (##) above it.")
                continue
            title, minutes = line[2:].strip(), DEFAULT_TASK_MINUTES
            match = _MINUTES.search(title)
            if match:
                title, minutes = title[:match.start()].strip(), int(match.group(1))
            if minutes < 1:
                errors.append(f"Line {number}: a task needs at least 1 minute.")
                continue
            phases[-1]["steps"][-1]["tasks"].append({"title": title, "minutes": minutes})
        else:
            errors.append(f"Line {number}: start the line with “# ”, “## ” or “- ”.")
    for phase in phases:
        for item in [phase, *phase["steps"], *(t for s in phase["steps"] for t in s["tasks"])]:
            if not item["title"]:
                errors.append("Every phase, step and task needs a title.")
            elif len(item["title"]) > 200:
                errors.append(f"“{item['title'][:40]}…” is longer than 200 characters.")
    if not phases and not errors:
        errors.append("The outline is empty.")
    return phases, errors


@transaction.atomic
def save_outline(goal, phases):
    """Add the phases after the goal's existing ones. Returns the task count."""
    first_order = goal.phases.count() + 1
    task_count = 0
    for phase_index, phase_data in enumerate(phases):
        phase = Phase.objects.create(goal=goal, title=phase_data["title"], order=first_order + phase_index)
        for step_index, step_data in enumerate(phase_data["steps"], start=1):
            step = Step.objects.create(phase=phase, title=step_data["title"], order=step_index)
            Task.objects.bulk_create(
                Task(step=step, title=t["title"], estimated_minutes=t["minutes"])
                for t in step_data["tasks"]
            )
            task_count += len(step_data["tasks"])
    return task_count
