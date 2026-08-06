from django.db.models import Count

from reaction.models import Reaction, ReactionType

# 并列票数时按 ReactionType 的定义顺序取靠前的那个，跟前端 REACTIONS 的顺序一致
TYPE_ORDER = {t.value: index for index, t in enumerate(ReactionType)}


def get_top_reactions(problem_ids):
    """返回 {problem_id: {"type": ..., "count": ...}}，只包含有评价的题目。"""
    if not problem_ids:
        return {}
    top = {}
    rows = Reaction.objects.filter(problem_id__in=problem_ids).values("problem_id", "type").annotate(count=Count("id"))
    for row in rows:
        current = top.get(row["problem_id"])
        if current is None or (-row["count"], TYPE_ORDER[row["type"]]) < (-current["count"], TYPE_ORDER[current["type"]]):
            top[row["problem_id"]] = {"type": row["type"], "count": row["count"]}
    return top
