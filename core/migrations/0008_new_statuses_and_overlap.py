"""
Restructure, part 3 of 3: new status vocabularies, "can overlap" blocks and
default orderings.

Task:      pending -> todo, in_progress -> doing, completed -> done
TimeBlock: scheduled -> planned, completed -> done, skipped -> skipped
(reversible: the reverse mapping is applied when migrating back; "missed"
blocks go back to "scheduled").
"""
from django.db import migrations, models

TASK_STATUS = {"pending": "todo", "in_progress": "doing", "completed": "done"}
BLOCK_STATUS = {"scheduled": "planned", "completed": "done", "skipped": "skipped"}


def remap(apps, task_map, block_map):
    Task = apps.get_model("core", "Task")
    TimeBlock = apps.get_model("core", "TimeBlock")
    for old, new in task_map.items():
        Task.objects.filter(status=old).update(status=new)
    for old, new in block_map.items():
        TimeBlock.objects.filter(status=old).update(status=new)


def forwards(apps, schema_editor):
    remap(apps, TASK_STATUS, BLOCK_STATUS)


def backwards(apps, schema_editor):
    block_back = {new: old for old, new in BLOCK_STATUS.items()}
    block_back["missed"] = "scheduled"
    remap(apps, {new: old for old, new in TASK_STATUS.items()}, block_back)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_phases_belong_to_goals"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name="task",
            name="status",
            field=models.CharField(choices=[("todo", "To do"), ("doing", "Doing"), ("done", "Done")], default="todo", max_length=20),
        ),
        migrations.AlterField(
            model_name="timeblock",
            name="status",
            field=models.CharField(choices=[("planned", "Planned"), ("done", "Done"), ("missed", "Missed"), ("skipped", "Skipped")], default="planned", max_length=20),
        ),
        migrations.AddField(
            model_name="timeblock",
            name="allow_overlap",
            field=models.BooleanField(default=False, help_text="Can run alongside other blocks (e.g. an audiobook on your commute)."),
        ),
        migrations.AlterModelOptions(name="phase", options={"ordering": ["order", "id"]}),
        migrations.AlterModelOptions(name="step", options={"ordering": ["order", "id"]}),
        migrations.AlterModelOptions(name="task", options={"ordering": ["id"]}),
        migrations.AlterModelOptions(name="timeblock", options={"ordering": ["date", "start_time", "id"]}),
    ]
