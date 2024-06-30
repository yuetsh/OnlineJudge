from django.db.models import Avg
from django.db.models.functions import Round
from comment.models import Comment
from problem.models import Problem
from utils.api import APIView
from account.decorators import login_required
from utils.api.api import validate_serializer
from comment.serializers import CreateCommentSerializer
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

        language = None
        submission = None
        problem_solved = False

        submission = (
            Submission.objects.select_related("problem")
            .filter(
                user_id=request.user.id,
                problem_id=data["problem_id"],
                result=JudgeStatus.ACCEPTED,
            )
            .first()
        )

        if submission:
            problem_solved = True
            language = submission.language
            if language == "Python3":
                language = "Python"

        Comment.objects.create(
            user=request.user,
            problem=problem,
            submission=submission,
            problem_solved=problem_solved,
            language=language,
            description_rating=data["description_rating"],
            difficulty_rating=data["difficulty_rating"],
            comprehensive_rating=data["comprehensive_rating"],
            content=data["content"],
        )
        return self.success()

    def get(self, request):
        problem_id = request.GET.get("problem_id")
        comments = Comment.objects.select_related("problem").filter(
            problem_id=problem_id, visible=True
        )
        if comments.count() == 0:
            return self.success()
        rating = comments.aggregate(
            description=Round(Avg("description_rating"), 2),
            difficulty=Round(Avg("difficulty_rating"), 2),
            comprehensive=Round(Avg("comprehensive_rating"), 2),
        )
        contents = comments.exclude(content="").values_list("content", flat=True)
        return self.success({"rating": rating, "contents": list(contents)})
