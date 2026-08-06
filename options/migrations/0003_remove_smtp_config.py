# 邮件功能已整体移除，smtp_config 不再有读写方。_init_option 建过的那一行会留在
# 库里成为孤儿，且里面存着明文 SMTP 密码，这里一并删掉。

from django.db import migrations


def remove_smtp_config(apps, schema_editor):
    SysOptions = apps.get_model("options", "SysOptions")
    SysOptions.objects.filter(key="smtp_config").delete()


def restore_smtp_config(apps, schema_editor):
    SysOptions = apps.get_model("options", "SysOptions")
    SysOptions.objects.get_or_create(key="smtp_config", defaults={"value": {}})


class Migration(migrations.Migration):
    dependencies = [
        ("options", "0002_add_sql_language"),
    ]

    operations = [
        migrations.RunPython(remove_smtp_config, restore_smtp_config),
    ]
