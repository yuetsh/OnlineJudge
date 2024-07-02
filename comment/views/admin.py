from account.decorators import super_admin_required
from comment.serializers import CommentListSerializer
from problem.models import Problem
from utils.api import APIView
from comment.models import Comment


class CommentAPI(APIView):
    @super_admin_required
    def get(self, request):
        comments = Comment.objects.select_related("problem").exclude(content="")
        problem_id = request.GET.get("problem_id")
        if problem_id:
            try:
                # 这里如果题目不可见，也需要显示该题目的评论
                problem = Problem.objects.get(_id=problem_id, contest_id__isnull=True)
            except Problem.DoesNotExist:
                return self.error("Problem doesn't exist")
        comments = comments.filter(problem=problem)
        return self.success(
            self.paginate_data(request, comments, CommentListSerializer)
        )

    @super_admin_required
    def delete(self, request):
        id = request.GET.get("id")
        if id:
            Comment.objects.filter(id=id).delete()
        return self.success()
