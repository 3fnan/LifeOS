from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("register/", views.register, name="register"),
    path("calendar/", views.calendar_view, name="calendar"),

    path("goals/", views.goal_list, name="goal_list"),
    path("goals/new/", views.create_goal, name="create_goal"),
    path("goals/<int:goal_id>/", views.goal_detail, name="goal_detail"),
    path("goals/<int:goal_id>/edit/", views.edit_goal, name="edit_goal"),
    path("goals/<int:goal_id>/delete/", views.delete_goal, name="delete_goal"),
    path("goals/<int:goal_id>/phases/new/", views.create_phase, name="create_phase"),
    path("goals/<int:goal_id>/plan/", views.auto_schedule, name="auto_schedule"),
    path("goals/<int:goal_id>/draft/", views.draft_plan, name="draft_plan"),

    path("phases/<int:phase_id>/edit/", views.edit_phase, name="edit_phase"),
    path("phases/<int:phase_id>/delete/", views.delete_phase, name="delete_phase"),
    path("phases/<int:phase_id>/steps/new/", views.create_step, name="create_step"),

    path("steps/<int:step_id>/edit/", views.edit_step, name="edit_step"),
    path("steps/<int:step_id>/delete/", views.delete_step, name="delete_step"),
    path("steps/<int:step_id>/tasks/new/", views.create_task, name="create_task"),

    path("tasks/<int:task_id>/edit/", views.edit_task, name="edit_task"),
    path("tasks/<int:task_id>/delete/", views.delete_task, name="delete_task"),
    path("tasks/<int:task_id>/toggle/", views.toggle_task, name="toggle_task"),
    path("tasks/<int:task_id>/schedule/", views.schedule_task, name="schedule_task"),

    path("blocks/<int:block_id>/edit/", views.edit_block, name="edit_block"),
    path("blocks/<int:block_id>/delete/", views.delete_block, name="delete_block"),
]
