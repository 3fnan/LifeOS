from datetime import time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Count, Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import ai_draft, stats
from .forms import AutoScheduleForm, DraftPlanForm, GoalForm, PhaseForm, StepForm, TaskForm, TimeBlockForm
from .models import Goal, Phase, Step, Task, TimeBlock
from .scheduler import plan_goal

# Ownership lookups: every object is reached through its goal's user.
TASK_OWNER = "step__phase__goal__user"
BLOCK_OWNER = "task__step__phase__goal__user"


def owned_blocks(user):
    return TimeBlock.objects.filter(**{BLOCK_OWNER: user}).select_related("task__step__phase__goal")


def form_page(request, form, *, eyebrow, title, submit, cancel_url, description="", context=None):
    """Render the shared create/edit page."""
    page = {
        "form": form,
        "eyebrow": eyebrow,
        "title": title,
        "description": description,
        "submit": submit,
        "cancel_url": cancel_url,
    }
    page.update(context or {})
    return render(request, "core/form_page.html", page)


def confirm_delete(request, obj, *, kind, warning, cancel_url):
    return render(request, "core/confirm_delete.html", {
        "object": obj,
        "kind": kind,
        "warning": warning,
        "cancel_url": cancel_url,
    })


# ---------------------------------------------------------------------------
# Accounts and overview pages
# ---------------------------------------------------------------------------
def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Account created. Log in to start planning.")
            return redirect("login")
    else:
        form = UserCreationForm()
    return render(request, "core/registration/registration.html", {"form": form})


def goals_with_progress(user):
    goals = list(
        Goal.objects.filter(user=user)
        .annotate(
            task_count=Count("phases__steps__tasks"),
            done_count=Count("phases__steps__tasks", filter=Q(phases__steps__tasks__status=Task.DONE)),
        )
        .order_by("status", "target_date")
    )
    for goal in goals:
        goal.progress = round(goal.done_count / goal.task_count * 100) if goal.task_count else 0
    return goals


@login_required
def goal_list(request):
    return render(request, "core/goal_list.html", {"goals": goals_with_progress(request.user)})


@login_required
def dashboard(request):
    today = timezone.localdate()
    goals = goals_with_progress(request.user)

    blocks = owned_blocks(request.user)
    today_blocks = list(blocks.filter(date=today).order_by("start_time"))
    upcoming_blocks = blocks.filter(date__gt=today).order_by("date", "start_time")[:5]

    completed_today = sum(1 for b in today_blocks if b.task.status == Task.DONE)
    total_minutes = sum(b.duration_minutes for b in today_blocks)
    completed_minutes = sum(b.duration_minutes for b in today_blocks if b.task.status == Task.DONE)

    hour = timezone.localtime().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"

    week = stats.week_hours(request.user, today)
    return render(request, "core/dashboard.html", {
        "streak": stats.streak(request.user, today),
        "week": week,
        "week_percent": min(100, round(week["done"] / week["budget"] * 100)) if week["budget"] else 0,
        "risks": stats.goals_at_risk(request.user, today),
        "slipped": stats.skipped_and_missed(request.user, today),
        "greeting": greeting,
        "today": today,
        "active_goals": sum(1 for goal in goals if goal.status == "active"),
        "goals": goals,
        "today_schedules": today_blocks,
        "upcoming_schedules": upcoming_blocks,
        "total_today": len(today_blocks),
        "completed_today": completed_today,
        "total_minutes": total_minutes,
        "completed_minutes": completed_minutes,
        "progress": round(completed_today / len(today_blocks) * 100) if today_blocks else 0,
    })


@login_required
def calendar_view(request):
    today = timezone.localdate()
    current_monday = today - timedelta(days=today.weekday())

    # Weeks always run Monday to Sunday: any ?week= date snaps to its Monday.
    # Unparseable dates, or dates too close to date.min/date.max to build a
    # previous/next week, fall back to the current week instead of a 500.
    start_date = current_monday
    week_start = request.GET.get("week")
    if week_start:
        try:
            requested = timezone.datetime.strptime(week_start, "%Y-%m-%d").date()
            monday = requested - timedelta(days=requested.weekday())
            # Raises OverflowError if prev/next week would leave the date range.
            monday - timedelta(days=7)
            monday + timedelta(days=13)
            start_date = monday
        except (ValueError, OverflowError):
            pass

    end_date = start_date + timedelta(days=6)
    blocks = owned_blocks(request.user).filter(date__range=[start_date, end_date]).order_by("date", "start_time")

    by_date = {}
    for block in blocks:
        by_date.setdefault(block.date, []).append(block)

    days = []
    for i in range(7):
        date = start_date + timedelta(days=i)
        day_blocks = by_date.get(date, [])
        days.append({
            "date": date,
            "schedules": day_blocks,
            "minutes": sum(b.duration_minutes for b in day_blocks),
            "is_today": date == today,
        })

    return render(request, "core/calendar.html", {
        "days": days,
        "start_date": start_date,
        "end_date": end_date,
        "previous_week": start_date - timedelta(days=7),
        "next_week": start_date + timedelta(days=7),
        "is_current_week": start_date == current_monday,
        "week_minutes": sum(day["minutes"] for day in days),
        "week_blocks": sum(len(day["schedules"]) for day in days),
    })


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------
@login_required
def create_goal(request):
    if request.method == "POST":
        form = GoalForm(request.POST)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.user = request.user
            goal.save()
            messages.success(request, "Goal created. Now break it into phases.")
            return redirect("goal_detail", goal_id=goal.id)
    else:
        today = timezone.localdate()
        form = GoalForm(initial={"start_date": today, "days_per_week": 5, "hours_per_day": 1})
    return form_page(
        request, form, eyebrow="Today", title="Set a new goal",
        description="Give it a clear finish line and a realistic weekly time budget.",
        submit="Create goal", cancel_url=reverse("dashboard"),
    )


@login_required
def goal_detail(request, goal_id):
    tasks = Task.objects.prefetch_related(
        Prefetch("blocks", queryset=TimeBlock.objects.order_by("date", "start_time"))
    )
    goal = get_object_or_404(
        Goal.objects.prefetch_related(
            Prefetch("phases__steps__tasks", queryset=tasks)
        ),
        id=goal_id,
        user=request.user,
    )
    phases = goal.phases.all()
    all_tasks = [task for phase in phases for task in phase.all_tasks()]
    total_tasks = len(all_tasks)
    completed_tasks = sum(1 for task in all_tasks if task.status == Task.DONE)

    return render(request, "core/goal_detail.html", {
        "goal": goal,
        "phases": phases,
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "progress": round(completed_tasks / total_tasks * 100) if total_tasks else 0,
    })


@login_required
def edit_goal(request, goal_id):
    goal = get_object_or_404(Goal, id=goal_id, user=request.user)
    if request.method == "POST":
        form = GoalForm(request.POST, instance=goal)
        if form.is_valid():
            form.save()
            messages.success(request, "Goal updated.")
            return redirect("goal_detail", goal_id=goal.id)
    else:
        form = GoalForm(instance=goal)
    return form_page(
        request, form, eyebrow=goal.title, title="Edit goal",
        submit="Save changes", cancel_url=reverse("goal_detail", args=[goal.id]),
    )


@login_required
def delete_goal(request, goal_id):
    goal = get_object_or_404(Goal, id=goal_id, user=request.user)
    if request.method == "POST":
        goal.delete()
        messages.success(request, f"Deleted “{goal.title}”.")
        return redirect("dashboard")
    return confirm_delete(
        request, goal, kind="goal",
        warning="This also deletes all of its phases, steps, tasks and time blocks.",
        cancel_url=reverse("goal_detail", args=[goal.id]),
    )


@login_required
def auto_schedule(request, goal_id):
    """Preview, then save, an automatic plan for the goal's unscheduled tasks."""
    goal = get_object_or_404(Goal, id=goal_id, user=request.user)
    today = timezone.localdate()
    plan = None
    if request.method == "POST":
        form = AutoScheduleForm(request.POST, goal=goal, today=today)
        if form.is_valid():
            plan = plan_goal(
                goal,
                start_date=form.cleaned_data["start_date"],
                window_start=form.cleaned_data["window_start"],
                window_end=form.cleaned_data["window_end"],
                now=timezone.localtime(),
            )
            if request.POST.get("then") == "save" and plan.blocks:
                TimeBlock.objects.bulk_create(plan.blocks)
                count = len(plan.blocks)
                messages.success(request, f"Added {count} time block{'s' if count != 1 else ''} to your calendar.")
                return redirect("goal_detail", goal_id=goal.id)
    else:
        form = AutoScheduleForm(goal=goal, today=today, initial={
            "start_date": max(today, goal.start_date),
            "window_start": time(18, 0),
            "window_end": time(21, 0),
        })
    return render(request, "core/auto_schedule.html", {
        "goal": goal,
        "form": form,
        "plan": plan,
        "plan_minutes": sum(b.duration_minutes for b in plan.blocks) if plan else 0,
    })


@login_required
def draft_plan(request, goal_id):
    """Ask Gemini for phases/steps/tasks, let the user edit the outline, then save it."""
    goal = get_object_or_404(Goal, id=goal_id, user=request.user)
    draft_error, outline_errors = None, []
    if request.method == "POST":
        form = DraftPlanForm(request.POST)
        if form.is_valid():
            if request.POST.get("then") == "save":
                phases, outline_errors = ai_draft.parse_outline(form.cleaned_data["outline"])
                if not outline_errors:
                    count = ai_draft.save_outline(goal, phases)
                    messages.success(
                        request,
                        f"Added {len(phases)} phase{'s' if len(phases) != 1 else ''} and "
                        f"{count} task{'s' if count != 1 else ''}. Use “Plan my weeks” to put them on your calendar.",
                    )
                    return redirect("goal_detail", goal_id=goal.id)
            else:
                try:
                    phases = ai_draft.draft_plan(goal, form.cleaned_data["level"])
                except ai_draft.DraftError as error:
                    draft_error = str(error)
                else:
                    data = request.POST.copy()
                    data["outline"] = ai_draft.to_outline(phases)
                    form = DraftPlanForm(data)
    else:
        form = DraftPlanForm()
    return render(request, "core/draft_plan.html", {
        "goal": goal,
        "form": form,
        "has_draft": bool(form["outline"].value()),
        "draft_error": draft_error,
        "outline_errors": outline_errors,
    })


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------
@login_required
def create_phase(request, goal_id):
    goal = get_object_or_404(Goal, id=goal_id, user=request.user)
    if request.method == "POST":
        form = PhaseForm(request.POST)
        if form.is_valid():
            phase = form.save(commit=False)
            phase.goal = goal
            phase.save()
            messages.success(request, "Phase added.")
            return redirect("goal_detail", goal_id=goal.id)
    else:
        form = PhaseForm(initial={"order": goal.phases.count() + 1})
    return form_page(
        request, form, eyebrow=goal.title, title="Add a phase",
        description="Phases are the big stages of your goal, like chapters.",
        submit="Add phase", cancel_url=reverse("goal_detail", args=[goal.id]),
    )


@login_required
def edit_phase(request, phase_id):
    phase = get_object_or_404(Phase, id=phase_id, goal__user=request.user)
    if request.method == "POST":
        form = PhaseForm(request.POST, instance=phase)
        if form.is_valid():
            form.save()
            messages.success(request, "Phase updated.")
            return redirect("goal_detail", goal_id=phase.goal_id)
    else:
        form = PhaseForm(instance=phase)
    return form_page(
        request, form, eyebrow=phase.goal.title, title="Edit phase",
        submit="Save changes", cancel_url=reverse("goal_detail", args=[phase.goal_id]),
    )


@login_required
def delete_phase(request, phase_id):
    phase = get_object_or_404(Phase, id=phase_id, goal__user=request.user)
    if request.method == "POST":
        phase.delete()
        messages.success(request, f"Deleted phase “{phase.title}”.")
        return redirect("goal_detail", goal_id=phase.goal_id)
    return confirm_delete(
        request, phase, kind="phase",
        warning="This also deletes its steps, tasks and time blocks.",
        cancel_url=reverse("goal_detail", args=[phase.goal_id]),
    )


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------
@login_required
def create_step(request, phase_id):
    phase = get_object_or_404(Phase, id=phase_id, goal__user=request.user)
    if request.method == "POST":
        form = StepForm(request.POST)
        if form.is_valid():
            step = form.save(commit=False)
            step.phase = phase
            step.save()
            messages.success(request, "Step added.")
            return redirect("goal_detail", goal_id=phase.goal_id)
    else:
        form = StepForm(initial={"order": phase.steps.count() + 1})
    return form_page(
        request, form, eyebrow=phase.goal.title, title="Add a step",
        description="Steps are concrete outcomes inside a phase.",
        submit="Add step", cancel_url=reverse("goal_detail", args=[phase.goal_id]),
    )


@login_required
def edit_step(request, step_id):
    step = get_object_or_404(Step, id=step_id, phase__goal__user=request.user)
    goal_id = step.phase.goal_id
    if request.method == "POST":
        form = StepForm(request.POST, instance=step)
        if form.is_valid():
            form.save()
            messages.success(request, "Step updated.")
            return redirect("goal_detail", goal_id=goal_id)
    else:
        form = StepForm(instance=step)
    return form_page(
        request, form, eyebrow=step.phase.goal.title, title="Edit step",
        submit="Save changes", cancel_url=reverse("goal_detail", args=[goal_id]),
    )


@login_required
def delete_step(request, step_id):
    step = get_object_or_404(Step, id=step_id, phase__goal__user=request.user)
    goal_id = step.phase.goal_id
    if request.method == "POST":
        step.delete()
        messages.success(request, f"Deleted step “{step.title}”.")
        return redirect("goal_detail", goal_id=goal_id)
    return confirm_delete(
        request, step, kind="step",
        warning="This also deletes its tasks and time blocks.",
        cancel_url=reverse("goal_detail", args=[goal_id]),
    )


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
@login_required
def create_task(request, step_id):
    step = get_object_or_404(Step, id=step_id, phase__goal__user=request.user)
    goal_id = step.phase.goal_id
    if request.method == "POST":
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.step = step
            task.save()
            messages.success(request, "Task added.")
            if request.POST.get("then") == "schedule":
                return redirect("schedule_task", task_id=task.id)
            return redirect("goal_detail", goal_id=goal_id)
    else:
        form = TaskForm()
    return form_page(
        request, form, eyebrow=step.phase.goal.title, title="Add a task",
        description="Tasks are the small actions you can actually put on your calendar.",
        submit="Add task", cancel_url=reverse("goal_detail", args=[goal_id]),
        context={"secondary_submit": ("schedule", "Add & schedule")},
    )


@login_required
def edit_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, **{TASK_OWNER: request.user})
    goal_id = task.goal.id
    if request.method == "POST":
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            messages.success(request, "Task updated.")
            return redirect("goal_detail", goal_id=goal_id)
    else:
        form = TaskForm(instance=task)
    return form_page(
        request, form, eyebrow=task.goal.title, title="Edit task",
        submit="Save changes", cancel_url=reverse("goal_detail", args=[goal_id]),
    )


@login_required
def delete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, **{TASK_OWNER: request.user})
    goal_id = task.goal.id
    if request.method == "POST":
        task.delete()
        messages.success(request, f"Deleted task “{task.title}”.")
        return redirect("goal_detail", goal_id=goal_id)
    return confirm_delete(
        request, task, kind="task",
        warning="This also deletes its time blocks.",
        cancel_url=reverse("goal_detail", args=[goal_id]),
    )


@login_required
@require_POST
def toggle_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, **{TASK_OWNER: request.user})
    task.status = Task.TODO if task.status == Task.DONE else Task.DONE
    task.save()
    # The task's sessions up to today follow the tick, so streaks and weekly
    # hours count them. Future sessions are left alone.
    past_blocks = task.blocks.filter(date__lte=timezone.localdate())
    if task.status == Task.DONE:
        past_blocks.filter(status=TimeBlock.PLANNED).update(status=TimeBlock.DONE)
    else:
        past_blocks.filter(status=TimeBlock.DONE).update(status=TimeBlock.PLANNED)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True, "status": task.status})

    if request.GET.get("from") == "dashboard":
        return redirect("dashboard")
    if request.GET.get("from") == "calendar":
        return redirect("calendar")
    return redirect("goal_detail", goal_id=task.goal.id)


# ---------------------------------------------------------------------------
# Time blocks
# ---------------------------------------------------------------------------
def time_block_page(request, form, task, *, title, submit, cancel_url, crumb):
    goal = task.goal
    return form_page(
        request, form, eyebrow=crumb, title=title,
        description="Pick when you'll work on this task.",
        submit=submit, cancel_url=cancel_url,
        context={
            "task": task,
            "plan_hint": f"Plan for “{goal.title}”: {goal.hours_per_day.normalize():f}h a day, "
                         f"{goal.days_per_week} days a week.",
        },
    )


@login_required
def schedule_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, **{TASK_OWNER: request.user})
    if request.method == "POST":
        form = TimeBlockForm(request.POST, task=task)
        if form.is_valid():
            block = form.save(commit=False)
            block.task = task
            block.save()
            messages.success(request, f"Scheduled for {block.date:%a %b %d}, {block.start_time:%H:%M}.")
            return redirect("goal_detail", goal_id=task.goal.id)
    else:
        form = TimeBlockForm(task=task, initial={"date": timezone.localdate()})
    return time_block_page(
        request, form, task, title="Schedule task", submit="Schedule", crumb=task.goal.title,
        cancel_url=reverse("goal_detail", args=[task.goal.id]),
    )


@login_required
def edit_block(request, block_id):
    block = get_object_or_404(TimeBlock, id=block_id, **{BLOCK_OWNER: request.user})
    if request.method == "POST":
        form = TimeBlockForm(request.POST, instance=block, task=block.task)
        if form.is_valid():
            form.save()
            messages.success(request, "Time block updated.")
            return redirect(f"{reverse('calendar')}?week={block.date:%Y-%m-%d}")
    else:
        form = TimeBlockForm(instance=block, task=block.task)
    return time_block_page(
        request, form, block.task, title="Edit time block", submit="Save changes", crumb="Calendar",
        cancel_url=f"{reverse('calendar')}?week={block.date:%Y-%m-%d}",
    )


@login_required
@require_POST
def delete_block(request, block_id):
    block = get_object_or_404(TimeBlock, id=block_id, **{BLOCK_OWNER: request.user})
    goal_id = block.task.goal.id
    block.delete()
    messages.success(request, "Time block removed.")
    return redirect("goal_detail", goal_id=goal_id)
