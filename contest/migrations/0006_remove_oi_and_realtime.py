from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("contest", "0005_alter_acmcontestrank_accepted_number_and_more"),
    ]

    operations = [
        migrations.DeleteModel(name="OIContestRank"),
        migrations.RemoveField(model_name="contest", name="real_time_rank"),
        migrations.RemoveField(model_name="contest", name="rule_type"),
    ]
