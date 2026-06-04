from account.decorators import teacher_admin_required
from utils.api import APIView

from ..models import AIAnalysis
from ..serializers import AIAnalysisDetailSerializer, AIAnalysisListSerializer


class AIAnalysisAdminAPI(APIView):
    @teacher_admin_required
    def get(self, request):
        report_id = request.GET.get("id")
        if report_id:
            try:
                report = AIAnalysis.objects.select_related("user").get(id=report_id)
            except AIAnalysis.DoesNotExist:
                return self.error("AIAnalysis not found")
            return self.success(AIAnalysisDetailSerializer(report).data)

        qs = AIAnalysis.objects.select_related("user").order_by("-create_time")

        username = request.GET.get("username")
        if username:
            qs = qs.filter(user__username__icontains=username)

        if request.GET.get("pinned_only") == "true":
            pinned = qs.filter(is_pinned=True)
            return self.success(AIAnalysisListSerializer(pinned, many=True).data)

        return self.success(self.paginate_data(request, qs, AIAnalysisListSerializer))

    @teacher_admin_required
    def post(self, request):
        report_id = request.data.get("id")
        try:
            report = AIAnalysis.objects.select_related("user").get(id=report_id)
        except AIAnalysis.DoesNotExist:
            return self.error("AIAnalysis not found")

        if report.is_pinned:
            report.is_pinned = False
        else:
            AIAnalysis.objects.filter(user=report.user, is_pinned=True).update(is_pinned=False)
            report.is_pinned = True
        report.save(update_fields=["is_pinned"])
        return self.success({"is_pinned": report.is_pinned})
