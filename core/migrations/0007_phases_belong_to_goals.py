"""
Restructure, part 2 of 3: phases hang directly off their goal, the Roadmap
model is removed, parent links are renamed (milestone -> phase,
checkpoint -> step), and the manual Phase/Step statuses are dropped because
they are now derived from tasks.

Not reversible with data: deleted roadmaps cannot be recreated.
"""
import django.db.models.deletion
from django.db import migrations, models


def attach_phases_to_goals(apps, schema_editor):
    Phase = apps.get_model("core", "Phase")
    for phase in Phase.objects.select_related("roadmap"):
        phase.goal_id = phase.roadmap.goal_id
        phase.save(update_fields=["goal"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_rename_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="phase",
            name="goal",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name="phases", to="core.goal"),
        ),
        migrations.RunPython(attach_phases_to_goals, migrations.RunPython.noop),
        migrations.RemoveField(model_name="phase", name="roadmap"),
        migrations.AlterField(
            model_name="phase",
            name="goal",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="phases", to="core.goal"),
        ),
        migrations.DeleteModel(name="Roadmap"),

        migrations.RenameField(model_name="step", old_name="milestone", new_name="phase"),
        migrations.AlterField(
            model_name="step",
            name="phase",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="steps", to="core.phase"),
        ),
        migrations.RenameField(model_name="task", old_name="checkpoint", new_name="step"),
        migrations.AlterField(
            model_name="task",
            name="step",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tasks", to="core.step"),
        ),
        migrations.AlterField(
            model_name="timeblock",
            name="task",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="blocks", to="core.task"),
        ),

        migrations.RemoveField(model_name="phase", name="status"),
        migrations.RemoveField(model_name="step", name="status"),
    ]
