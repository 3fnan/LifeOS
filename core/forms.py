from django import forms
from .models import Goal, Roadmap, Milestone, Checkpoint, Task, Schedule


class GoalForm(forms.ModelForm):
    class Meta:
        model = Goal
        fields = [
            "title",
            "goal_type",
            "start_date",
            "target_date",
            "status",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": "e.g. Become a Django Backend Developer"
                }
            ),
            "goal_type": forms.Select(),
            "start_date": forms.DateInput(
                attrs={"type": "date"}
            ),
            "target_date": forms.DateInput(
                attrs={"type": "date"}
            ),
            "status": forms.Select(),
        }

class CheckpointForm(forms.ModelForm):

    class Meta:
        model = Checkpoint

        fields = [
            "title",
            "description",
            "order",
            "status",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. Understand Django Models",
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-input form-textarea",
                    "rows": 5,
                    "placeholder": "Describe what should be achieved in this checkpoint...",
                }
            ),

            "order": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "min": 1,
                }
            ),

            "status": forms.Select(
                attrs={
                    "class": "form-input",
                }
            ),
        }

class RoadmapForm(forms.ModelForm):
    class Meta:
        model = Roadmap
        fields = [
            "title",
            "description",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": "e.g. Django Backend Development Roadmap"
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Describe what this roadmap will help you achieve..."
                }
            ),
        }

class MilestoneForm(forms.ModelForm):
    class Meta:
        model= Milestone
        fields = [ "title","description","order"]
        widgets={ 
            "title": forms.TextInput(
                attrs={
                    "placeholder":"e.g. Django Fundamentals"
                    }
            ),
            "description": forms.TextInput(
                attrs={
                    "rows": 4, 
                    "placeholder": "Describe what the milestone covers.."
                    }
            ),
            "order": forms.NumberInput(
                attrs={
                    "min":1        
                    }
            ),
        }
    
class TaskForm(forms.ModelForm):

    class Meta:
        model = Task

        fields = ["title","description","estimated_minutes","status"]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. Learn Django model relationships",
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-input form-textarea",
                    "rows": 5,
                    "placeholder": "Describe what needs to be completed...",
                }
            ),

            "estimated_minutes": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "min": 1,
                }
            ),

            "status": forms.Select(
                attrs={
                    "class": "form-input",
                }
            ),
        }
class ScheduleForm(forms.ModelForm):

    def __init__(self, *args, task=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.task = task

    class Meta:
        model = Schedule
        fields = [
            "date",
            "start_time",
            "end_time",
            "status",
            "notes",
        ]

        widgets = {
            "date": forms.DateInput(
                attrs={
                    "class": "form-input",
                    "type": "date",
                }
            ),
            "start_time": forms.TimeInput(
                attrs={
                    "class": "form-input",
                    "type": "time",
                }
            ),
            "end_time": forms.TimeInput(
                attrs={
                    "class": "form-input",
                    "type": "time",
                }
            ),
            "status": forms.Select(
                attrs={
                    "class": "form-input",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-input form-textarea",
                    "rows": 4,
                    "placeholder": "Add any notes for this scheduled task...",
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get("date")
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")

        if start_time and end_time and end_time <= start_time:
            raise forms.ValidationError("End time must be later than start time.")

        if date and start_time and end_time:
            overlapping = Schedule.objects.filter(
                date=date,
                task__checkpoint__milestone__roadmap__goal__user=self.task.checkpoint.milestone.roadmap.goal.user,
                start_time__lt=end_time,
                end_time__gt=start_time,
            )

        if self.instance.pk:
            overlapping = overlapping.exclude(pk=self.instance.pk)

        if overlapping.exists():
            raise forms.ValidationError(
                "This time overlaps with another scheduled task."
            )    
        return cleaned_data