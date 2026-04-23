from utils.api import APIView

from tutorial.models import Tutorial, Exercise
from tutorial.serializers import TutorialSerializer, ExerciseSerializer


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


class ExerciseAPI(APIView):
    def get(self, request):
        tutorial_id = request.GET.get("tutorial_id")
        if not tutorial_id:
            return self.error("tutorial_id is required")
        try:
            tutorial = Tutorial.objects.get(id=tutorial_id, is_public=True)
        except Tutorial.DoesNotExist:
            return self.error("Tutorial does not exist")
        exercises = Exercise.objects.filter(tutorial=tutorial)
        return self.success(ExerciseSerializer(exercises, many=True).data)
