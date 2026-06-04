from account.decorators import teacher_admin_required
from account.models import User
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
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                return self.error("User not found")
            qs = qs.filter(user=user)

        return self.success(self.paginate_data(request, qs, AIAnalysisListSerializer))
