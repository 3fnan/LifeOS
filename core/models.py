from datetime import datetime

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


def summarize_status(tasks):
    """Derive a Phase/Step status from its tasks: not_started, in_progress or done."""
    tasks = list(tasks)
    if tasks and all(task.status == Task.DONE for task in tasks):
        return "done"
    if any(task.status in (Task.DOING, Task.DONE) for task in tasks):
        return "in_progress"
    return "not_started"


DERIVED_STATUS_LABELS = {
    "not_started": "Not started",
    "in_progress": "In progress",
    "done": "Done",
}


class ProgressMixin:
    """Progress helpers for anything that exposes all_tasks()."""

    @property
    def total_tasks(self):
        return len(self.all_tasks())

    @property
    def completed_tasks(self):
        return sum(1 for task in self.all_tasks() if task.status == Task.DONE)

    @property
    def progress(self):
        total = self.total_tasks
        return round(self.completed_tasks / total * 100) if total else 0

    @property
    def status(self):
        return summarize_status(self.all_tasks())

    @property
    def status_label(self):
        return DERIVED_STATUS_LABELS[self.status]


class Goal(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="goals")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=[("active", "Active"), ("completed", "Completed"), ("paused", "Paused")], default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    category = models.CharField(max_length=30, choices=[("personal", "Personal"), ("career", "Career"), ("education", "Education"), ("health", "Health & Fitness"), ("finance", "Finance"), ("projects", "Projects"), ("skills", "Skills"), ("other", "Other")], default="other")
    priority = models.CharField(max_length=20, choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")], default="medium")
    days_per_week = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(7)])
    hours_per_day = models.DecimalField(max_digits=4, decimal_places=1, validators=[MinValueValidator(0.1), MaxValueValidator(24)])
    start_date = models.DateField()
    target_date = models.DateField()

    def clean(self):
        # A missing/invalid date is already reported as a field error.
        if self.start_date is None or self.target_date is None:
            return
        if self.target_date <= self.start_date:
            raise ValidationError(
                {"target_date": "Target date must be after the start date."}
            )

    @property
    def daily_minutes(self):
        return int(self.hours_per_day * 60)

    @property
    def pigment(self):
        """One of 8 fixed, muted swatches (CSS .pg-0 … .pg-7), stable per goal."""
        return (self.id or 0) % 8

    def __str__(self):
        return self.title


class Phase(ProgressMixin, models.Model):
    """A major stage of a goal (formerly Milestone)."""
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="phases")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def all_tasks(self):
        return [task for step in self.steps.all() for task in step.tasks.all()]

    def __str__(self):
        return self.title


class Step(ProgressMixin, models.Model):
    """A concrete step inside a phase (formerly Checkpoint)."""
    phase = models.ForeignKey(Phase, on_delete=models.CASCADE, related_name="steps")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def all_tasks(self):
        return list(self.tasks.all())

    def __str__(self):
        return self.title


class Task(models.Model):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"
    STATUS_CHOICES = [(TODO, "To do"), (DOING, "Doing"), (DONE, "Done")]

    step = models.ForeignKey(Step, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    estimated_minutes = models.PositiveIntegerField(default=30)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=TODO)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    @property
    def goal(self):
        return self.step.phase.goal

    def save(self, *args, **kwargs):
        # Keep completed_at consistent with status no matter which path saved
        # the task (toggle, edit form, admin).
        if self.status == self.DONE:
            if self.completed_at is None:
                self.completed_at = timezone.now()
        else:
            self.completed_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class TimeBlock(models.Model):
    """A slot on the calendar for working on a task (formerly Schedule)."""
    PLANNED = "planned"
    DONE = "done"
    MISSED = "missed"
    SKIPPED = "skipped"
    STATUS_CHOICES = [(PLANNED, "Planned"), (DONE, "Done"), (MISSED, "Missed"), (SKIPPED, "Skipped")]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="blocks")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PLANNED)
    allow_overlap = models.BooleanField(
        default=False,
        help_text="Can run alongside other blocks (e.g. an audiobook on your commute).",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "start_time", "id"]

    @property
    def duration_minutes(self):
        start = datetime.combine(self.date, self.start_time)
        end = datetime.combine(self.date, self.end_time)
        return int((end - start).total_seconds() / 60)

    @property
    def effective_status(self):
        """A planned block whose time has passed while its task is unfinished counts as missed."""
        if self.status == self.PLANNED and self.task.status != Task.DONE:
            now = timezone.localtime()
            if (self.date, self.end_time) < (now.date(), now.time()):
                return self.MISSED
        return self.status

    @property
    def effective_status_label(self):
        return dict(self.STATUS_CHOICES)[self.effective_status]

    def __str__(self):
        return f"{self.task.title} - {self.date}"
