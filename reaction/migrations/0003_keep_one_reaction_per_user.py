from django.db import migrations, models
from django.db.models import Min, Subquery


def keep_earliest(apps, schema_editor):
    """一人一题只保留最早的一条表情，多余的删掉。

    以前上限是 3 个，改成单选后这些老数据仍在给全站计数贡献数字。
    同一次提交的 create_time 相同，所以按自增 id 认「最早」。
    """
    Reaction = apps.get_model("reaction", "Reaction")
    keep_ids = Reaction.objects.values("user_id", "problem_id").annotate(keep=Min("id")).values("keep")
    Reaction.objects.exclude(id__in=Subquery(keep_ids)).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("reaction", "0002_delete_comment"),
    ]

    operations = [
        # 删掉的数据回不来，回滚只当无事发生
        migrations.RunPython(keep_earliest, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name="reaction",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="reaction",
            constraint=models.UniqueConstraint(fields=("problem", "user"), name="reaction_problem_user_unique"),
        ),
    ]
