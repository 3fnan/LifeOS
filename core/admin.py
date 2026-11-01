from django.contrib import admin

from .models import Goal, Phase, Step, Task, TimeBlock


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "status", "priority", "target_date")
    list_filter = ("status", "priority", "category")
    search_fields = ("title", "user__username")


@admin.register(Phase)
class PhaseAdmin(admin.ModelAdmin):
    list_display = ("title", "goal", "order")
    search_fields = ("title", "goal__title")


@admin.register(Step)
class StepAdmin(admin.ModelAdmin):
    list_display = ("title", "phase", "order")
    search_fields = ("title", "phase__title")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "step", "status", "estimated_minutes", "completed_at")
    list_filter = ("status",)
    search_fields = ("title",)


@admin.register(TimeBlock)
class TimeBlockAdmin(admin.ModelAdmin):
    list_display = ("task", "date", "start_time", "end_time", "status", "allow_overlap")
    list_filter = ("status", "allow_overlap")
    date_hierarchy = "date"
