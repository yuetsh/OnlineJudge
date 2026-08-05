from collections import defaultdict

from django.db import migrations, models
from django.db.models.functions import Lower


def merge_duplicate_tags(apps, schema_editor):
    """加唯一约束前，把「去空格+转小写」后同名的标签合并成一个。

    每组保留关联题目数最多的（并列时保留 id 最小的）作为主标签，
    其余标签下的题目关系转移到主标签后删除。空名标签同样按此规则归并成一条，
    不做删除，留给管理员在标签管理页处理。
    """
    ProblemTag = apps.get_model("problem", "ProblemTag")
    Problem = apps.get_model("problem", "Problem")

    groups = defaultdict(list)
    for tag in ProblemTag.objects.all():
        groups[(tag.name or "").strip().lower()].append(tag)

    for tags in groups.values():
        counts = {tag.id: Problem.objects.filter(tags=tag).count() for tag in tags}
        tags.sort(key=lambda tag: (-counts[tag.id], tag.id))
        primary = tags[0]

        stripped = (primary.name or "").strip()
        if primary.name != stripped:
            primary.name = stripped
            primary.save(update_fields=["name"])

        for duplicate in tags[1:]:
            for problem in Problem.objects.filter(tags=duplicate):
                problem.tags.add(primary)
                problem.tags.remove(duplicate)
            duplicate.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("problem", "0013_remove_problem_io_mode_remove_problem_rule_type_and_more"),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_tags, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="problemtag",
            constraint=models.UniqueConstraint(Lower("name"), name="problem_tag_name_ci_unique"),
        ),
    ]
