from django.db.models import Avg
from django.db.models.functions import Round
from comment.models import Comment
from problem.models import Problem
from utils.api import APIView
from account.decorators import login_required
from utils.api.api import validate_serializer
from comment.serializers import CreateCommentSerializer, CommentSerializer
from submission.models import Submission, JudgeStatus


class CommentAPI(APIView):
    @validate_serializer(CreateCommentSerializer)
    @login_required
    def post(self, request):
        data = request.data
        try:
            problem = Problem.objects.get(id=data["problem_id"], visible=True)
        except Problem.DoesNotExist:
            self.error("problem is not exists")

        try:
            submission = (
                Submission.objects.select_related("problem")
                .filter(
                    user_id=request.user.id,
                    problem_id=data["problem_id"],
                    result=JudgeStatus.ACCEPTED,
                )
                .first()
            )
        except Submission.DoesNotExist:
            self.error("submission is not exists or not accepted")

        language = submission.language
        if language == "Python3":
            language = "Python"

        Comment.objects.create(
            user=request.user,
            problem=problem,
            submission=submission,
            language=language,
            description_rating=data["description_rating"],
            difficulty_rating=data["difficulty_rating"],
            comprehensive_rating=data["comprehensive_rating"],
            content=data["content"],
        )
        return self.success()

    @login_required
    def get(self, request):
        problem_id = request.GET.get("problem_id")
        comment = (
            Comment.objects.select_related("problem")
            .filter(user=request.user, problem_id=problem_id)
            .first()
        )
        if comment:
            return self.success(CommentSerializer(comment).data)
        else:
            return self.success()


class CommentStatisticsAPI(APIView):
    def get(self, request):
        problem_id = request.GET.get("problem_id")
        comments = Comment.objects.select_related("problem").filter(
            problem_id=problem_id
        )
        if comments.count() == 0:
            return self.success()

        count = comments.count()
        rating = comments.aggregate(
            description=Round(Avg("description_rating"), 2),
            difficulty=Round(Avg("difficulty_rating"), 2),
            comprehensive=Round(Avg("comprehensive_rating"), 2),
        )
        contents = comments.exclude(content="").values_list("content", flat=True)
        return self.success(
            {
                "count": count,
                "rating": rating,
                "contents": list(contents),
            }
        )
