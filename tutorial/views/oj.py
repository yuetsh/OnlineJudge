from utils.api import APIView

from tutorial.models import Tutorial
from tutorial.serializers import TutorialSerializer


class TutorialAPI(APIView):
    def get(self, request):
        id = request.GET.get("id")
        try:
            tutorial = Tutorial.objects.get(id=id, is_public=True)
            return self.success(TutorialSerializer(tutorial).data)
        except Tutorial.DoesNotExist:
            return self.error("Tutorial does not exist")


class TutorialTitlesAPI(APIView):
    def get(self, request):
        type = request.GET.get("type") or "python"
        tutorials = Tutorial.objects.filter(is_public=True, type=type).values(
            "id", "title"
        )
        return self.success(list(tutorials))
