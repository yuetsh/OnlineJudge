from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("reaction", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS comment CASCADE;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
