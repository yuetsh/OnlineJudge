from django.db.models import Count, F, Max, Q

from account.decorators import super_admin_required
from reaction.models import Reaction, ReactionType
from utils.api import APIView


class ReactionStatsAPI(APIView):
    @super_admin_required
    def get(self, request):
        queryset = (
            Reaction.objects.values(pid=F("problem___id"), title=F("problem__title"))
            .annotate(users=Count("user", distinct=True))
            .annotate(last_time=Max("create_time"))
            .annotate(**{t.value: Count("id", filter=Q(type=t.value)) for t in ReactionType})
            .order_by("-users")
        )

        problem_id = request.GET.get("problem")
        if problem_id:
            queryset = queryset.filter(problem___id__iexact=problem_id, problem__contest_id__isnull=True)

        data = self.paginate_data(request, queryset)
        data["results"] = list(data["results"])
        return self.success(data)
