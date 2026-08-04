from account.decorators import super_admin_required
from achievement.metrics import METRIC_REGISTRY
from achievement.models import Achievement
from achievement.tasks import rescan_achievement
from utils.api import APIView
from utils.shortcuts import check_is_id


class AchievementAdminAPI(APIView):
    @super_admin_required
    def get(self, request):
        achievement_id = request.GET.get("id")
        if achievement_id:
            try:
                achievement = Achievement.objects.get(id=achievement_id)
            except Achievement.DoesNotExist:
                return self.error("成就不存在")
            return self.success(_serialize(achievement))
        return self.success([_serialize(a) for a in Achievement.objects.all()])

    @super_admin_required
    def post(self, request):
        data = request.data
        error = _validate(data)
        if error:
            return self.error(error)
        achievement = Achievement.objects.create(
            name=data["name"],
            description=data["description"],
            icon=data["icon"],
            rarity=data["rarity"],
            hidden=data.get("hidden", False),
            metric=data["metric"],
            operator=data["operator"],
            threshold=data["threshold"],
            visible=data.get("visible", True),
            order=data.get("order", 0),
        )
        # 新建成就需要补发给已达标的存量用户
        rescan_achievement.send(achievement.id)
        return self.success(_serialize(achievement))

    @super_admin_required
    def put(self, request):
        data = request.data
        if not check_is_id(data.get("id")):
            return self.error("参数错误")
        try:
            achievement = Achievement.objects.get(id=data["id"])
        except Achievement.DoesNotExist:
            return self.error("成就不存在")
        error = _validate(data)
        if error:
            return self.error(error)

        old_threshold = achievement.threshold
        old_operator = achievement.operator
        for field in ("name", "description", "icon", "rarity", "hidden", "metric", "operator", "threshold", "visible", "order"):
            if field in data:
                setattr(achievement, field, data[field])
        achievement.save()

        # 条件放宽（gte 调低阈值 / lte 调高阈值 / 换了比较符）时补发
        loosened = (
            achievement.operator != old_operator
            or (achievement.operator == "gte" and achievement.threshold < old_threshold)
            or (achievement.operator == "lte" and achievement.threshold > old_threshold)
        )
        if loosened and achievement.visible:
            rescan_achievement.send(achievement.id)
        return self.success(_serialize(achievement))

    @super_admin_required
    def delete(self, request):
        achievement_id = request.GET.get("id")
        if not check_is_id(achievement_id):
            return self.error("参数错误")
        Achievement.objects.filter(id=achievement_id).delete()
        return self.success("删除成功")


class AchievementMetricAdminAPI(APIView):
    @super_admin_required
    def get(self, request):
        """供后台指标下拉框使用。这里的列表就是代码里注册了什么。"""
        return self.success([{"key": key, "name": m.name, "help_text": m.help_text} for key, m in METRIC_REGISTRY.items()])


def _validate(data):
    for field in ("name", "description", "icon", "rarity", "metric", "operator"):
        if not data.get(field):
            return f"{field} 不能为空"
    if data["metric"] not in METRIC_REGISTRY:
        return "指标不存在"
    if data["operator"] not in ("gte", "lte"):
        return "比较符不合法"
    if not isinstance(data.get("threshold"), int):
        return "阈值必须是整数"
    return None


def _serialize(a):
    return {
        "id": a.id,
        "name": a.name,
        "description": a.description,
        "icon": a.icon,
        "rarity": a.rarity,
        "hidden": a.hidden,
        "metric": a.metric,
        "metric_name": METRIC_REGISTRY[a.metric].name if a.metric in METRIC_REGISTRY else a.metric,
        "operator": a.operator,
        "threshold": a.threshold,
        "visible": a.visible,
        # 后台列表必须显示这个：阈值配错时学生永远拿不到也永远不会来问，
        # 这个计数器是唯一的仪表盘
        "unlock_count": a.unlock_count,
        "order": a.order,
        "create_time": a.create_time,
    }
