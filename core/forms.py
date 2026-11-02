from datetime import timedelta

from django import forms

from .ai_draft import LEVELS
from .models import Goal, Phase, Step, Task, TimeBlock


def format_minutes(minutes):
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    return f"{hours}h" if hours else f"{mins}m"


class GoalForm(forms.ModelForm):
    class Meta:
        model = Goal
        fields = [
            "title",
            "description",
            "category",
            "priority",
            "days_per_week",
            "hours_per_day",
            "start_date",
            "target_date",
            "status",
        ]
        labels = {
            "title": "What do you want to achieve?",
            "days_per_week": "Days per week",
            "hours_per_day": "Hours per day",
        }
        help_texts = {
            "days_per_week": "How many days a week you can work on it (1-7).",
            "hours_per_day": "Your daily time budget for this goal.",
        }
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. Become a Django backend developer", "autofocus": True}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Why does this goal matter to you?"}),
            "days_per_week": forms.NumberInput(attrs={"min": 1, "max": 7}),
            "hours_per_day": forms.NumberInput(attrs={"min": 0.1, "max": 24, "step": 0.1}),
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "target_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


class PhaseForm(forms.ModelForm):
    class Meta:
        model = Phase
        fields = ["title", "description", "order"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. Django fundamentals", "autofocus": True}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "What does this phase cover?"}),
            "order": forms.NumberInput(attrs={"min": 1}),
        }


class StepForm(forms.ModelForm):
    class Meta:
        model = Step
        fields = ["title", "description", "order"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. Understand Django models", "autofocus": True}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "What should be achieved in this step?"}),
            "order": forms.NumberInput(attrs={"min": 1}),
        }


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "description", "estimated_minutes", "status"]
        labels = {"estimated_minutes": "Estimated minutes"}
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. Learn model relationships", "autofocus": True}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Any details or links?"}),
            "estimated_minutes": forms.NumberInput(attrs={"min": 1, "step": 5}),
        }


class AutoScheduleForm(forms.Form):
    start_date = forms.DateField(
        label="Start from",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    window_start = forms.TimeField(
        label="Earliest start",
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
    )
    window_end = forms.TimeField(
        label="Latest finish",
        help_text="Blocks are placed only between these two times.",
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
    )

    def __init__(self, *args, goal, today, **kwargs):
        super().__init__(*args, **kwargs)
        self.goal = goal
        self.today = today

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        window_start = cleaned_data.get("window_start")
        window_end = cleaned_data.get("window_end")

        if window_start and window_end and window_end <= window_start:
            raise forms.ValidationError("The latest finish must be later than the earliest start.")
        if start_date:
            if start_date < self.today:
                self.add_error("start_date", "Pick today or a later date.")
            elif start_date > self.goal.target_date:
                self.add_error("start_date", f"This goal's target date is {self.goal.target_date:%d %b %Y}.")
        return cleaned_data


class DraftPlanForm(forms.Form):
    level = forms.ChoiceField(label="Where are you starting from?", choices=LEVELS)
    outline = forms.CharField(
        label="Draft",
        required=False,
        help_text="Edit freely. “# ” starts a phase, “## ” a step, “- ” a task; "
                  "put the time at the end, like “(45 min)”.",
        widget=forms.Textarea(attrs={"rows": 18, "spellcheck": "true"}),
    )


class TimeBlockForm(forms.ModelForm):
    """Schedules a task. Overlaps are refused; exceeding the goal's daily hours
    or weekly days is a warning the user can override."""

    confirm_over_capacity = forms.BooleanField(
        required=False,
        label="Schedule anyway",
    )

    class Meta:
        model = TimeBlock
        fields = ["date", "start_time", "end_time", "status", "allow_overlap", "notes"]
        labels = {"allow_overlap": "Can overlap with other blocks"}
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "start_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "end_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Anything to remember for this session?"}),
        }

    def __init__(self, *args, task=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.task = task
        self.capacity_warnings = []

    def _other_blocks(self):
        """The user's other blocks that still occupy time (skipped ones don't)."""
        blocks = TimeBlock.objects.filter(
            task__step__phase__goal__user=self.task.goal.user,
        ).exclude(status=TimeBlock.SKIPPED)
        if self.instance.pk:
            blocks = blocks.exclude(pk=self.instance.pk)
        return blocks

    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get("date")
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")

        if start_time and end_time and end_time <= start_time:
            raise forms.ValidationError("End time must be later than start time.")

        # Field-level errors (missing/invalid date or time) are already reported
        # by Django; only run the checks below when all three values are valid.
        if not (date and start_time and end_time):
            return cleaned_data

        others = self._other_blocks()
        is_skipped = cleaned_data.get("status") == TimeBlock.SKIPPED

        if not cleaned_data.get("allow_overlap") and not is_skipped:
            overlapping = others.filter(
                date=date,
                allow_overlap=False,
                start_time__lt=end_time,
                end_time__gt=start_time,
            ).select_related("task").first()
            if overlapping:
                raise forms.ValidationError(
                    f"This time overlaps with “{overlapping.task.title}” "
                    f"({overlapping.start_time:%H:%M}–{overlapping.end_time:%H:%M}). "
                    "Pick another time, or tick “Can overlap with other blocks”."
                )

        if not is_skipped:
            self.capacity_warnings = self._capacity_warnings(others, date, start_time, end_time)
            if self.capacity_warnings and not cleaned_data.get("confirm_over_capacity"):
                raise forms.ValidationError(
                    "This goes over the plan for this goal. "
                    "Tick “Schedule anyway” to keep it."
                )

        return cleaned_data

    def _capacity_warnings(self, others, date, start_time, end_time):
        goal = self.task.goal
        goal_blocks = others.filter(task__step__phase__goal=goal)
        warnings = []

        new_minutes = TimeBlock(date=date, start_time=start_time, end_time=end_time).duration_minutes
        day_minutes = sum(b.duration_minutes for b in goal_blocks.filter(date=date)) + new_minutes
        if day_minutes > goal.daily_minutes:
            warnings.append(
                f"{format_minutes(day_minutes)} of “{goal.title}” on {date:%a %b %d} — "
                f"your plan is {format_minutes(goal.daily_minutes)} a day."
            )

        monday = date - timedelta(days=date.weekday())
        week_days = set(
            goal_blocks.filter(date__range=[monday, monday + timedelta(days=6)])
            .values_list("date", flat=True)
        )
        week_days.add(date)
        if len(week_days) > goal.days_per_week:
            warnings.append(
                f"{len(week_days)} days of “{goal.title}” in the week of {monday:%b %d} — "
                f"your plan is {goal.days_per_week} days a week."
            )
        return warnings
