from django.contrib import admin
from .models import Goal, Roadmap, Milestone,Checkpoint,Task,Schedule
# Register your models here.

admin.site.register(Goal)
admin.site.register(Roadmap)
admin.site.register(Milestone)
admin.site.register(Checkpoint)
admin.site.register(Task)
admin.site.register(Schedule)