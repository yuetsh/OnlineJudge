from account.decorators import super_admin_required
from utils.api import APIView, validate_serializer

from tutorial.models import Tutorial, Exercise
from tutorial.serializers import (
    TutorialSerializer,
    TutorialListSerializer,
    CreateTutorialSerializer,
    EditTutorialSerializer,
    ExerciseSerializer,
    CreateExerciseSerializer,
    EditExerciseSerializer,
)


class TutorialAdminAPI(APIView):
    @validate_serializer(CreateTutorialSerializer)
    @super_admin_required
    def post(self, request):
        """
        create tutorial
        """
        data = request.data
        tutorial = Tutorial.objects.create(**data, created_by=request.user)
        return self.success(TutorialSerializer(tutorial).data)

    @validate_serializer(EditTutorialSerializer)
    @super_admin_required
    def put(self, request):
        """
        edit tutorial
        """
        data = request.data
        try:
            tutorial = Tutorial.objects.get(id=data.pop("id"))
        except Tutorial.DoesNotExist:
            return self.error("Tutorial does not exist")

        for k, v in data.items():
            setattr(tutorial, k, v)
        tutorial.save()

        return self.success(TutorialSerializer(tutorial).data)

    @super_admin_required
    def get(self, request):
        """
        get tutorial list / get one tutorial
        """
        tutorial_id = request.GET.get("id")
        if tutorial_id:
            try:
                tutorial = Tutorial.objects.get(id=tutorial_id)
                return self.success(TutorialSerializer(tutorial).data)
            except Tutorial.DoesNotExist:
                return self.error("Tutorial does not exist")
                
        tutorials = Tutorial.objects.all().order_by("order", "-created_at")
        # 按 type 分组返回数据
        result = {
            "python": TutorialListSerializer(
                tutorials.filter(type="python"), 
                many=True
            ).data,
            "c": TutorialListSerializer(
                tutorials.filter(type="c"), 
                many=True
            ).data
        }
        return self.success(result)

    @super_admin_required
    def delete(self, request):
        if request.GET.get("id"):
            Tutorial.objects.filter(id=request.GET["id"]).delete()
        return self.success()


class TutorialVisibilityAPI(APIView):
    @super_admin_required
    def put(self, request):
        """
        change tutorial visibility
        """
        tutorial_id = request.data.get("id")
        is_public = request.data.get("is_public")
        if tutorial_id is None or is_public is None:
            return self.error("Invalid parameter")
        try:
            tutorial = Tutorial.objects.get(id=tutorial_id)
        except Tutorial.DoesNotExist:
            return self.error("Tutorial does not exist")
        tutorial.is_public = is_public
        tutorial.save()
        return self.success(TutorialSerializer(tutorial).data)


class ExerciseAdminAPI(APIView):
    @validate_serializer(CreateExerciseSerializer)
    @super_admin_required
    def post(self, request):
        data = request.data
        try:
            tutorial = Tutorial.objects.get(id=data["tutorial_id"])
        except Tutorial.DoesNotExist:
            return self.error("Tutorial does not exist")
        exercise = Exercise.objects.create(
            tutorial=tutorial,
            type=data["type"],
            data=data["data"],
            order=data.get("order", 0),
        )
        return self.success(ExerciseSerializer(exercise).data)

    @validate_serializer(EditExerciseSerializer)
    @super_admin_required
    def put(self, request):
        data = request.data
        try:
            exercise = Exercise.objects.get(id=data["id"])
        except Exercise.DoesNotExist:
            return self.error("Exercise does not exist")
        exercise.type = data["type"]
        exercise.data = data["data"]
        exercise.order = data.get("order", exercise.order)
        exercise.save()
        return self.success(ExerciseSerializer(exercise).data)

    @super_admin_required
    def get(self, request):
        tutorial_id = request.GET.get("tutorial_id")
        if not tutorial_id:
            return self.error("tutorial_id is required")
        exercises = Exercise.objects.filter(tutorial_id=tutorial_id)
        return self.success(ExerciseSerializer(exercises, many=True).data)

    @super_admin_required
    def delete(self, request):
        exercise_id = request.GET.get("id")
        if not exercise_id:
            return self.error("id is required")
        Exercise.objects.filter(id=exercise_id).delete()
        return self.success()
