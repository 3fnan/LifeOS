from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render,redirect,get_object_or_404
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.http import JsonResponse
from .models import Goal, Task, Roadmap, Milestone, Checkpoint, Schedule
from .forms import GoalForm, RoadmapForm, MilestoneForm, CheckpointForm, TaskForm, ScheduleForm
from datetime import timedelta

def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect("login")

    else:
        form=UserCreationForm()

    return render(request,"core/registration/registration.html",{"form":form})   

@login_required
def dashboard(request):
    goals = Goal.objects.filter(user=request.user)

    today = timezone.localdate()

    today_schedules = Schedule.objects.filter(
        date=today,
        task__checkpoint__milestone__roadmap__goal__user=request.user
    ).order_by("start_time")

    upcoming_schedules = Schedule.objects.filter(
        date__gt=today,
        task__checkpoint__milestone__roadmap__goal__user=request.user
    ).order_by("date", "start_time")[:5]

    total_today = today_schedules.count()

    completed_today = today_schedules.filter(
        task__status="completed"
    ).count()

    total_minutes = sum(
        schedule.duration_minutes
        for schedule in today_schedules
    )

    completed_minutes = sum(
        schedule.duration_minutes
        for schedule in today_schedules
        if schedule.task.status == "completed"
    )

    progress = 0

    if total_today:
        progress = round(
            (completed_today / total_today) * 100
        )

    return render(
        request,
        "core/dashboard.html",
        {
            "goals": goals,
            "today_schedules": today_schedules,
            "upcoming_schedules": upcoming_schedules,
            "total_today": total_today,
            "completed_today": completed_today,
            "total_minutes": total_minutes,
            "completed_minutes": completed_minutes,
            "progress": progress,
        },
    )

@login_required
def create_goal(request):
    if request.method == "POST":
        form = GoalForm(request.POST)

        if form.is_valid():
            goal = form.save(commit=False)
            goal.user = request.user
            goal.save()

            return redirect("dashboard")
    else:
        form = GoalForm()

    return render(
        request,
        "core/create_goal.html",
        {"form": form}
    )


@login_required
def goal_detail(request, goal_id):
    goal = get_object_or_404(
        Goal,
        id=goal_id,
        user=request.user
    )

    roadmap = getattr(goal, "roadmap", None)

    tasks = Task.objects.filter(
        checkpoint__milestone__roadmap__goal=goal
    )

    total_tasks = tasks.count()
    completed_tasks = tasks.filter(
        status="completed"
    ).count()

    if total_tasks > 0:
        progress = round(
            (completed_tasks / total_tasks) * 100
        )
    else:
        progress = 0

    return render(
        request,
        "core/goal_detail.html",
        {
            "goal": goal,
            "roadmap": roadmap,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "progress": progress,
        }
    )

@login_required
@require_POST
def toggle_task(request, task_id):
    task = get_object_or_404(
        Task,
        id=task_id,
        checkpoint__milestone__roadmap__goal__user=request.user
    )

    if task.status == "completed":
        task.status = "pending"
        task.completed_at = None
    else:
        task.status = "completed"
        task.completed_at = timezone.now()

    task.save()
        
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "status": task.status,
            })

    if request.GET.get("from") == "dashboard":
        return redirect("dashboard")
    
    if request.GET.get("from") == "calendar":
        return redirect("calendar")

    return redirect(
        "goal_detail",
        goal_id=task.checkpoint.milestone.roadmap.goal.id
    )

@login_required
def edit_goal(request, goal_id):
    goal = get_object_or_404(
        Goal,
        id=goal_id,
        user=request.user
    )

    if request.method == "POST":
        form = GoalForm(request.POST, instance=goal)

        if form.is_valid():
            form.save()
            return redirect("goal_detail", goal_id=goal.id)

    else:
        form = GoalForm(instance=goal)

    return render(
        request,
        "core/edit_goal.html",
        {"form": form, "goal": goal}
    )


@login_required
def create_roadmap(request, goal_id):

    goal = get_object_or_404(
        Goal,
        id=goal_id,
        user=request.user
    )

    if hasattr(goal, "roadmap"):
        return redirect(
            "goal_detail",
            goal_id=goal.id
        )

    if request.method == "POST":
        form = RoadmapForm(request.POST)

        if form.is_valid():
            roadmap = form.save(commit=False)
            roadmap.goal = goal
            roadmap.save()
            return redirect(
                "goal_detail",
                goal_id=goal.id
            )

    else:
        form = RoadmapForm()

    return render(
        request,
        "core/create_roadmap.html",
        {
            "form": form,
            "goal": goal,
        }
    )

@login_required
def edit_roadmap(request, roadmap_id):
    roadmap = get_object_or_404(
        Roadmap,
        id=roadmap_id,
        goal__user=request.user
    )

    if request.method == "POST":
        form = RoadmapForm(
            request.POST,
            instance=roadmap
        )

        if form.is_valid():
            form.save()

            return redirect(
                "goal_detail",
                goal_id=roadmap.goal.id
            )

    else:
        form = RoadmapForm(instance=roadmap)

    return render(
        request,
        "core/edit_roadmap.html",
        {
            "form": form,
            "roadmap": roadmap,
        }
    )

@login_required
def delete_roadmap(request, roadmap_id):

    roadmap = get_object_or_404(
        Roadmap,
        id=roadmap_id,
        goal__user=request.user
    )

    goal_id = roadmap.goal.id

    if request.method == "POST":
        roadmap.delete()
        return redirect("goal_detail", goal_id=goal_id)

    return render(
        request,
        "core/delete_roadmap.html",
        {
            "roadmap": roadmap,
            "goal": roadmap.goal,
        }
    )

@login_required
def delete_goal(request, goal_id):
    goal = get_object_or_404(
        Goal,
        id=goal_id,
        user=request.user
    )

    if request.method == "POST":
        goal.delete()
        return redirect("dashboard")

    return render(
        request,
        "core/delete_goal.html",
        {"goal": goal}
    )

@login_required
def create_milestone(request, roadmap_id):

    roadmap = get_object_or_404(
        Roadmap,
        id=roadmap_id,
        goal__user=request.user
    )

    if request.method == "POST":

        form = MilestoneForm(request.POST)

        if form.is_valid():

            milestone = form.save(commit=False)
            milestone.roadmap = roadmap
            milestone.save()

            return redirect(
                "goal_detail",
                goal_id=roadmap.goal.id
            )

    else:

        next_order = roadmap.milestones.count() + 1

        form = MilestoneForm(
            initial={"order": next_order}
        )

    return render(
        request,
        "core/create_milestone.html",
        {
            "form": form,
            "roadmap": roadmap,
        }
    )

@login_required
def edit_milestone(request, milestone_id):

    milestone = get_object_or_404(
        Milestone,
        id=milestone_id,
        roadmap__goal__user=request.user
    )

    if request.method == "POST":

        form = MilestoneForm(
            request.POST,
            instance=milestone
        )

        if form.is_valid():

            form.save()

            return redirect(
                "goal_detail",
                goal_id=milestone.roadmap.goal.id
            )

    else:

        form = MilestoneForm(
            instance=milestone
        )

    return render(
        request,
        "core/edit_milestone.html",
        {
            "form": form,
            "milestone": milestone,
        }
    )

@login_required
def delete_milestone(request, milestone_id):

    milestone = get_object_or_404(
        Milestone,
        id=milestone_id,
        roadmap__goal__user=request.user
    )

    goal_id = milestone.roadmap.goal.id

    if request.method == "POST":
        milestone.delete()
        return redirect("goal_detail", goal_id=goal_id)

    return render(
        request,
        "core/delete_milestone.html",
        {
            "milestone": milestone,
            "goal": milestone.roadmap.goal,
        }
    )


@login_required
def create_checkpoint(request, milestone_id):

    milestone = get_object_or_404(
        Milestone,
        id=milestone_id,
        roadmap__goal__user=request.user
    )

    if request.method == "POST":

        form = CheckpointForm(request.POST)

        if form.is_valid():

            checkpoint = form.save(commit=False)
            checkpoint.milestone = milestone
            checkpoint.save()

            return redirect(
                "goal_detail",
                goal_id=milestone.roadmap.goal.id
            )

    else:

        next_order = milestone.checkpoints.count() + 1

        form = CheckpointForm(
            initial={
                "order": next_order
            }
        )

    return render(
        request,
        "core/create_checkpoint.html",
        {
            "form": form,
            "milestone": milestone,
        }
    )

@login_required
def edit_checkpoint(request, checkpoint_id):
    checkpoint = get_object_or_404(
        Checkpoint,
        id=checkpoint_id,
        milestone__roadmap__goal__user=request.user
    )

    if request.method == "POST":
        form = CheckpointForm(
            request.POST,
            instance=checkpoint
        )

        if form.is_valid():
            form.save()

            return redirect(
                "goal_detail",
                goal_id=checkpoint.milestone.roadmap.goal.id
            )

    else:
        form = CheckpointForm(instance=checkpoint)

    return render(
        request,
        "core/edit_checkpoint.html",
        {
            "form": form,
            "checkpoint": checkpoint,
        }
    )

@login_required
def delete_checkpoint(request, checkpoint_id):

    checkpoint = get_object_or_404(
        Checkpoint,
        id=checkpoint_id,
        milestone__roadmap__goal__user=request.user
    )

    goal_id = checkpoint.milestone.roadmap.goal.id

    if request.method == "POST":
        checkpoint.delete()
        return redirect("goal_detail", goal_id=goal_id)

    return render(
        request,
        "core/delete_checkpoint.html",
        {
            "checkpoint": checkpoint,
            "goal": checkpoint.milestone.roadmap.goal,
        }
    )

@login_required
def create_task(request, checkpoint_id):

    checkpoint = get_object_or_404(
        Checkpoint,
        id=checkpoint_id,
        milestone__roadmap__goal__user=request.user
    )

    if request.method == "POST":

        form = TaskForm(request.POST)

        if form.is_valid():

            task = form.save(commit=False)
            task.checkpoint = checkpoint
            task.save()

            return redirect(
                "goal_detail",
                goal_id=checkpoint.milestone.roadmap.goal.id
            )

    else:

        form = TaskForm()

    return render(
        request,
        "core/create_task.html",
        {
            "form": form,
            "checkpoint": checkpoint,
        }
    )

@login_required
def edit_task(request, task_id):
    task = get_object_or_404(
        Task,
        id=task_id,
        checkpoint__milestone__roadmap__goal__user=request.user
    )

    if request.method == "POST":
        form = TaskForm(request.POST, instance=task)

        if form.is_valid():
            form.save()

            return redirect(
                "goal_detail",
                goal_id=task.checkpoint.milestone.roadmap.goal.id
            )

    else:
        form = TaskForm(instance=task)

    return render(
        request,
        "core/edit_task.html",
        {
            "form": form,
            "task": task,
        }
    )

@login_required
def delete_task(request, task_id):

    task = get_object_or_404(
        Task,
        id=task_id,
        checkpoint__milestone__roadmap__goal__user=request.user
    )

    goal_id = task.checkpoint.milestone.roadmap.goal.id

    if request.method == "POST":
        task.delete()
        return redirect("goal_detail", goal_id=goal_id)

    return render(
        request,
        "core/delete_task.html",
        {
            "task": task,
            "goal": task.checkpoint.milestone.roadmap.goal,
        }
    )

@login_required
def schedule_task(request, task_id):
    task = get_object_or_404(
        Task,
        id=task_id,
        checkpoint__milestone__roadmap__goal__user=request.user
    )

    if request.method == "POST":
        form = ScheduleForm(request.POST, task=task)

        if form.is_valid():
            schedule = form.save(commit=False)
            schedule.task = task
            schedule.save()

            return redirect(
                "goal_detail",
                goal_id=task.checkpoint.milestone.roadmap.goal.id
            )

    else:
        form = ScheduleForm(task=task)

    return render(
        request,
        "core/schedule_task.html",
        {
            "form": form,
            "task": task,
        }
    )

@login_required
@require_POST
def delete_schedule(request, schedule_id):
    schedule = get_object_or_404(
        Schedule,
        id=schedule_id,
        task__checkpoint__milestone__roadmap__goal__user=request.user
    )

    goal_id = schedule.task.checkpoint.milestone.roadmap.goal.id

    schedule.delete()

    return redirect("goal_detail", goal_id=goal_id)


@login_required
def calendar_view(request):
    today = timezone.localdate()

    week_start = request.GET.get("week")

    if week_start:
        try:
            start_date = timezone.datetime.strptime(
                week_start,
                "%Y-%m-%d"
            ).date()
        except ValueError:
            start_date = today - timedelta(days=today.weekday())
    else:
        start_date = today - timedelta(days=today.weekday())

    end_date = start_date + timedelta(days=6)

    schedules = Schedule.objects.filter(
        date__range=[start_date, end_date],
        task__checkpoint__milestone__roadmap__goal__user=request.user
    ).order_by("date", "start_time")

    days = []

    for i in range(7):
        date = start_date + timedelta(days=i)

        days.append({
            "date": date,
            "schedules": schedules.filter(date=date),
            "is_today": date == today,
        })

    previous_week = start_date - timedelta(days=7)
    next_week = start_date + timedelta(days=7)

    return render(
        request,
        "core/calendar.html",
        {
            "days": days,
            "start_date": start_date,
            "end_date": end_date,
            "previous_week": previous_week,
            "next_week": next_week,
        },
    )


@login_required
def edit_schedule(request, schedule_id):
    schedule = get_object_or_404(
        Schedule,
        id=schedule_id,
        task__checkpoint__milestone__roadmap__goal__user=request.user
    )

    if request.method == "POST":
        form = ScheduleForm(request.POST, instance=schedule, task=schedule.task)

        if form.is_valid():
            form.save()

            return redirect("calendar")
    else:
        form = ScheduleForm(instance=schedule, task=schedule.task)

    return render(
        request,
        "core/edit_schedule.html",
        {
            "form": form,
            "schedule": schedule,
        },
    )
