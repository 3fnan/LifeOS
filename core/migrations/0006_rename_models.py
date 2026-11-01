"""
Restructure, part 1 of 3: Goal gains a description (copied from its roadmap),
and Milestone/Checkpoint/Schedule are renamed to Phase/Step/TimeBlock.
Tables and rows are kept; only names change.

Parts 1-3 together turn  Goal > Roadmap > Milestone > Checkpoint > Task > Schedule
                   into  Goal > Phase > Step > Task > TimeBlock.
Back up db.sqlite3 before applying: part 2 cannot restore deleted roadmaps.
"""
from django.db import migrations, models


def copy_roadmap_description_to_goal(apps, schema_editor):
    Roadmap = apps.get_model("core", "Roadmap")
    for roadmap in Roadmap.objects.select_related("goal"):
        goal = roadmap.goal
        if roadmap.description and not goal.description:
            goal.description = roadmap.description
            goal.save(update_fields=["description"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_remove_goal_goal_type_goal_category_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="goal",
            name="description",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.RunPython(copy_roadmap_description_to_goal, migrations.RunPython.noop),
        # Leaf-first order so the renames can also be reversed cleanly.
        migrations.RenameModel("Schedule", "TimeBlock"),
        migrations.RenameModel("Checkpoint", "Step"),
        migrations.RenameModel("Milestone", "Phase"),
    ]
