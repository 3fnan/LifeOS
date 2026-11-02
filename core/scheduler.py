"""Automatic scheduling: spread a goal's unscheduled tasks across the calendar.

The plan respects the goal's budget (hours per day, days per Monday-Sunday
week), a daily time window chosen by the user, the goal's target date, and
never overlaps the user's other blocks. Nothing is saved here; the caller
decides whether to keep the proposed blocks.
"""
from dataclasses import dataclass, field
from datetime import time, timedelta

from .models import Task, TimeBlock

# Don't create slivers: a piece of a longer task is at least this long.
MIN_CHUNK_MINUTES = 30


@dataclass
class Plan:
    blocks: list = field(default_factory=list)      # unsaved TimeBlocks
    unplaced: list = field(default_factory=list)    # tasks that didn't (fully) fit


def _minutes(t):
    return t.hour * 60 + t.minute


def _time(minutes):
    return time(minutes // 60, minutes % 60)


def has_active_block(task):
    """A task counts as scheduled if it has a done block or an upcoming planned one.
    Missed and skipped blocks don't count, so those tasks get a new slot."""
    return any(
        block.status == TimeBlock.DONE or block.effective_status == TimeBlock.PLANNED
        for block in task.blocks.all()
    )


def tasks_to_schedule(goal):
    """Unfinished, unscheduled tasks in phase -> step -> task order."""
    tasks = (
        Task.objects.filter(step__phase__goal=goal)
        .exclude(status=Task.DONE)
        .select_related("step__phase")
        .prefetch_related("blocks")
        .order_by("step__phase__order", "step__phase__id", "step__order", "step__id", "id")
    )
    return [task for task in tasks if not has_active_block(task)]


def free_intervals(window_start, window_end, busy):
    """Gaps in [window_start, window_end) minutes not covered by busy intervals."""
    gaps, cursor = [], window_start
    for start, end in sorted(busy):
        if start > cursor:
            gaps.append((cursor, min(start, window_end)))
        cursor = max(cursor, end)
        if cursor >= window_end:
            break
    if cursor < window_end:
        gaps.append((cursor, window_end))
    return [(s, e) for s, e in gaps if e > s]


def plan_goal(goal, *, start_date, window_start, window_end, now):
    """Propose time blocks for the goal's unscheduled tasks.

    `now` is the current local datetime; nothing is placed in the past.
    """
    queue = [[task, task.estimated_minutes] for task in tasks_to_schedule(goal)]
    plan = Plan()
    if not queue:
        return plan

    start_date = max(start_date, goal.start_date, now.date())
    end_date = goal.target_date

    # Everything already on the user's calendar in the planning range.
    existing = list(
        TimeBlock.objects.filter(
            task__step__phase__goal__user=goal.user,
            date__range=[start_date - timedelta(days=6), end_date],
        )
        .exclude(status=TimeBlock.SKIPPED)
        .select_related("task__step__phase")
    )
    busy = {}          # date -> [(start, end)] that new blocks may not overlap
    goal_minutes = {}  # date -> minutes of this goal already planned
    goal_days = set()  # dates this goal already uses
    for block in existing:
        if not block.allow_overlap:
            busy.setdefault(block.date, []).append((_minutes(block.start_time), _minutes(block.end_time)))
        if block.task.step.phase.goal_id == goal.id:
            goal_minutes[block.date] = goal_minutes.get(block.date, 0) + block.duration_minutes
            goal_days.add(block.date)

    # Tasks up to this length are never split across days.
    whole_limit = min(goal.daily_minutes, _minutes(window_end) - _minutes(window_start))

    day = start_date
    while queue and day <= end_date:
        monday = day - timedelta(days=day.weekday())
        days_this_week = {d for d in goal_days if monday <= d <= monday + timedelta(days=6)}
        if day not in days_this_week and len(days_this_week) >= goal.days_per_week:
            day += timedelta(days=1)
            continue

        capacity = goal.daily_minutes - goal_minutes.get(day, 0)
        earliest = _minutes(window_start)
        if day == now.date():
            # Round the current time up to the next 5 minutes.
            earliest = max(earliest, -(-(now.hour * 60 + now.minute + 1) // 5) * 5)

        for gap_start, gap_end in free_intervals(earliest, _minutes(window_end), busy.get(day, [])):
            cursor = gap_start
            while queue and capacity > 0 and cursor < gap_end:
                task, remaining = queue[0]
                room = min(capacity, gap_end - cursor)
                if task.estimated_minutes <= whole_limit:
                    # Fits in one sitting: place it whole or not at all.
                    if remaining > room:
                        break  # try the next gap, then the next day
                    length = remaining
                else:
                    # Longer than a day allows: split, but not into slivers.
                    length = min(remaining, room)
                    if length < remaining and length < MIN_CHUNK_MINUTES:
                        break
                plan.blocks.append(TimeBlock(
                    task=task, date=day,
                    start_time=_time(cursor), end_time=_time(cursor + length),
                ))
                busy.setdefault(day, []).append((cursor, cursor + length))
                goal_minutes[day] = goal_minutes.get(day, 0) + length
                goal_days.add(day)
                cursor += length
                capacity -= length
                queue[0][1] -= length
                if queue[0][1] == 0:
                    queue.pop(0)
            if not queue or capacity <= 0:
                break
        day += timedelta(days=1)

    plan.unplaced = [task for task, _ in queue]
    return plan
