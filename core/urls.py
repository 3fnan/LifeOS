from core.views import edit_checkpoint
from django.urls import path
from .views import dashboard,register,create_goal,goal_detail,edit_goal,delete_goal,toggle_task, edit_roadmap,edit_milestone,toggle_task,edit_task,schedule_task,delete_schedule, calendar_view
from .views import edit_schedule
urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("register/",register,name="register"),
    path("goals/create",create_goal,name="create_goal"),
    path("goals/<int:goal_id>/", goal_detail, name="goal_detail"),
    path("goals/<int:goal_id>/edit/", edit_goal, name="edit_goal"),
    path("goals/<int:goal_id>/delete/", delete_goal, name="delete_goal"),
    path("tasks/<int:task_id>/toggle/", toggle_task, name="toggle_task"),
    path("roadmaps/<int:roadmap_id>/edit/", edit_roadmap, name="edit_roadmap"),
    path("milestones/<int:milestone_id>/edit/", edit_milestone, name="edit_milestone"),
    path("checkpoints/<int:checkpoint_id>/edit/",edit_checkpoint,name="edit_checkpoint"),
    path("tasks/<int:task_id>/edit/",edit_task,name="edit_task"),
    path("schedule/<int:task_id>",schedule_task,name="schedule_task"),
    path("schedule/<int:schedule_id>/delete/",delete_schedule,name="delete_schedule"),
    path("calendar/",calendar_view,name="calendar"),
    path("schedules/<int:schedule_id>/edit/",edit_schedule,name="edit_schedule"),

]