from django.db import migrations


def migrate_mcq_answers(apps, schema_editor):
    Exercise = apps.get_model("tutorial", "Exercise")
    for ex in Exercise.objects.filter(type="mcq"):
        if isinstance(ex.data.get("answer"), int):
            ex.data["answer"] = [ex.data["answer"]]
            ex.save()


def reverse_migrate_mcq_answers(apps, schema_editor):
    Exercise = apps.get_model("tutorial", "Exercise")
    for ex in Exercise.objects.filter(type="mcq"):
        if isinstance(ex.data.get("answer"), list) and len(ex.data["answer"]) == 1:
            ex.data["answer"] = ex.data["answer"][0]
            ex.save()


class Migration(migrations.Migration):

    dependencies = [
        ('tutorial', '0005_alter_exercise_type'),
    ]

    operations = [
        migrations.RunPython(migrate_mcq_answers, reverse_migrate_mcq_answers),
    ]
