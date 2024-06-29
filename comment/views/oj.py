from django.db.models import Avg
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
            problem = Problem.objects.get(id=data.problem_id, visible=True)
        except Problem.DoesNotExist:
            self.error("problem is not exists")

        submission = None
        if data.problem_solved and data.submission_id:
            try:
                data.submission_id
                submission = Submission.objects.select_related("problem").get(
                    id=data.submission_id,
                    problem_id=data.problem_id,
                    result=JudgeStatus.ACCEPTED,
                )
            except Submission.DoesNotExist:
                self.error("submission is not exists or not accepted")

        if not data.problem_solved:
            data.language = None

        Comment.objects.create(
            user=request.user,
            problem=problem,
            submission=submission,
            problem_solved=data.problem_solved,
            language=data.language,
            description_rating=data.description_rating,
            difficulty_rating=data.difficulty_rating,
            comprehensive_rating=data.comprehensive_rating,
            content=data.content,
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
            description=Avg("description_rating"),
            difficulty=Avg("difficulty_rating"),
            comprehensive=Avg("comprehensive_rating"),
        )
        contents = comments.filter(content__isnull=False).values_list(
            "content", flat=True
        )
        return self.success({rating: rating, contents: contents})
