"""Dashboard numbers: streak, this week's hours, goals at risk, skipped/missed.

A block counts as "done" only when its status is DONE (ticking a task marks
its blocks up to today done, see Task completion in views.toggle_task).
"""
from datetime import timedelta

from django.db.models import Sum

from .models import Goal, Task, TimeBlock

STREAK_LOOKBACK_DAYS = 366


def streak(user, today):
    """Consecutive days with at least one done block, counting back from today.

    Days with nothing scheduled are rest days: they neither count nor break
    the streak. A past day with blocks but none done breaks it. Today never
    breaks it, because the day isn't over yet.
    """
    since = today - timedelta(days=STREAK_LOOKBACK_DAYS)
    days = {}  # date -> has a done block
    for date, status in (
        TimeBlock.objects.filter(task__step__phase__goal__user=user, date__range=[since, today])
        .values_list("date", "status")
    ):
        days[date] = days.get(date, False) or status == TimeBlock.DONE

    count = 0
    for offset in range(STREAK_LOOKBACK_DAYS + 1):
        day = today - timedelta(days=offset)
        if day not in days:
            continue  # rest day
        if days[day]:
            count += 1
        elif day != today:
            break
    return count


def week_hours(user, today):
    """Per active goal: minutes done this Monday-Sunday week against the budget."""
    monday = today - timedelta(days=today.weekday())
    done = TimeBlock.objects.filter(
        task__step__phase__goal__user=user,
        task__step__phase__goal__status="active",
        date__range=[monday, monday + timedelta(days=6)],
        status=TimeBlock.DONE,
    ).select_related("task__step__phase")
    minutes = {}
    for block in done:
        goal_id = block.task.step.phase.goal_id
        minutes[goal_id] = minutes.get(goal_id, 0) + block.duration_minutes

    rows = []
    for goal in Goal.objects.filter(user=user, status="active").order_by("target_date", "id"):
        budget = goal.daily_minutes * goal.days_per_week
        done_minutes = minutes.get(goal.id, 0)
        rows.append({
            "goal": goal,
            "done": done_minutes,
            "budget": budget,
            "percent": min(100, round(done_minutes / budget * 100)) if budget else 0,
        })
    return {
        "rows": rows,
        "done": sum(r["done"] for r in rows),
        "budget": sum(r["budget"] for r in rows),
    }


def goals_at_risk(user, today):
    """Active goals whose unfinished work won't fit in their budget before the target date."""
    remaining = dict(
        Task.objects.filter(step__phase__goal__user=user, step__phase__goal__status="active")
        .exclude(status=Task.DONE)
        .values_list("step__phase__goal")
        .annotate(minutes=Sum("estimated_minutes"))
        .values_list("step__phase__goal", "minutes")
    )
    risks = []
    for goal in Goal.objects.filter(user=user, status="active", id__in=remaining):
        needed = remaining[goal.id]
        days_left = max(0, (goal.target_date - today).days + 1)
        capacity = round(days_left * goal.days_per_week / 7 * goal.daily_minutes)
        if needed > capacity:
            risks.append({
                "goal": goal,
                "needed": needed,
                "capacity": capacity,
                "short": needed - capacity,
                "overdue": goal.target_date < today,
            })
    return sorted(risks, key=lambda r: -r["short"])


def skipped_and_missed(user, today):
    """This week's blocks that were skipped, or whose time passed undone."""
    monday = today - timedelta(days=today.weekday())
    blocks = (
        TimeBlock.objects.filter(
            task__step__phase__goal__user=user,
            date__range=[monday, today],
            status__in=[TimeBlock.SKIPPED, TimeBlock.PLANNED],
        )
        .select_related("task__step__phase__goal")
        .order_by("date", "start_time")
    )
    return [b for b in blocks if b.effective_status in (TimeBlock.SKIPPED, TimeBlock.MISSED)]
