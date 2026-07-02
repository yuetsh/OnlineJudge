# SysOptions.languages 存在数据库里，_init_option 只在 key 缺失时写入默认值，
# 因此新增 SQL 语言必须用数据迁移追加到已部署库；不用 reset_languages()（会覆盖管理员的自定义配置）。

from django.db import migrations

SQL_LANGUAGE = {
    "config": {"template": ""},
    "name": "SQL",
    "description": "SQLite 3",
    "content_type": "text/x-sql",
}


def add_sql_language(apps, schema_editor):
    SysOptions = apps.get_model("options", "SysOptions")
    try:
        option = SysOptions.objects.get(key="languages")
    except SysOptions.DoesNotExist:
        # 库还没初始化过 languages，留给 _init_option 用代码默认值（已含 SQL）创建
        return
    if not any(item.get("name") == "SQL" for item in option.value):
        option.value.append(SQL_LANGUAGE)
        option.save(update_fields=["value"])


def remove_sql_language(apps, schema_editor):
    SysOptions = apps.get_model("options", "SysOptions")
    try:
        option = SysOptions.objects.get(key="languages")
    except SysOptions.DoesNotExist:
        return
    option.value = [item for item in option.value if item.get("name") != "SQL"]
    option.save(update_fields=["value"])


class Migration(migrations.Migration):
    dependencies = [
        ("options", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_sql_language, remove_sql_language),
    ]
