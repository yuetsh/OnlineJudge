from django.apps import AppConfig


class AchievementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "achievement"

    def ready(self):
        # 导入以触发 @metric 装饰器把指标注册进 METRIC_REGISTRY
        import achievement.metrics  # noqa: F401
