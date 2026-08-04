from account.decorators import super_admin_required
from achievement.metrics import METRIC_REGISTRY
from achievement.models import Achievement, Rarity
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

        before = (achievement.metric, achievement.operator, achievement.threshold, achievement.visible)
        for field in ("name", "description", "icon", "rarity", "hidden", "metric", "operator", "threshold", "visible", "order"):
            if field in data:
                setattr(achievement, field, data[field])
        achievement.save()

        # 只要"谁能达成"这件事可能变了就补发，不去精细判断是否放宽。
        # 补发是幂等的后台任务（unlock 用 get_or_create），多跑一次只花一次扫描；
        # 漏跑却是学生已达标却拿不到，两个方向代价不对称。
        # 早先的 loosened 谓词只看 operator/threshold，会漏掉两种情况：
        # 换了 metric（换了维度）、以及从下架改成上架（草稿期已达标的人）。
        after = (achievement.metric, achievement.operator, achievement.threshold, achievement.visible)
        if achievement.visible and before != after:
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
    # rarity 不校验的话，一个乱填的值会让 AchievementSummaryAPI 的四档统计
    # 对不上：它按 Rarity.choices 遍历，野值算进总数却不出现在任何一档里
    if data["rarity"] not in Rarity.values:
        return "稀有度不合法"
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
        # 必须 isoformat()：这里是手写的 dict 而不是 DRF 序列化器，
        # 原始 datetime 交给 JSON 编码器会抛 TypeError，整个管理接口 500。
        # 表为空时列表接口看着正常（不进循环），一旦有数据就全挂。
        "create_time": a.create_time.isoformat() if a.create_time else None,
    }
