from django.db.models import Count, F, FloatField, Q
from django.db.models.functions import Cast

from account.decorators import super_admin_required
from reaction.models import Reaction, ReactionType
from utils.api import APIView

MIN_USERS_FOR_RATIO = 3
DEFAULT_ORDERING = "-users"


class ReactionStatsAPI(APIView):
    @super_admin_required
    def get(self, request):
        queryset = (
            Reaction.objects.values(pid=F("problem___id"), title=F("problem__title"))
            .annotate(users=Count("user", distinct=True))
            .annotate(**{t.value: Count("id", filter=Q(type=t.value)) for t in ReactionType})
            .annotate(**{f"{t.value}_ratio": Cast(t.value, FloatField()) / Cast("users", FloatField()) for t in ReactionType})
        )

        problem_id = request.GET.get("problem")
        if problem_id:
            queryset = queryset.filter(problem___id__iexact=problem_id, problem__contest_id__isnull=True)

        ordering = request.GET.get("ordering") or DEFAULT_ORDERING
        prefix = "-" if ordering.startswith("-") else ""
        field = ordering.lstrip("-")
        if field == "users":
            order_by = f"{prefix}users"
        elif field in ReactionType.values:
            # 按占比排序时过滤低样本，避免 1 人点 1 个就冲到 100%
            queryset = queryset.filter(users__gte=MIN_USERS_FOR_RATIO)
            order_by = f"{prefix}{field}_ratio"
        else:
            order_by = DEFAULT_ORDERING

        queryset = queryset.order_by(order_by)
        return self.success(self.paginate_data(request, queryset))
