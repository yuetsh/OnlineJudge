from account.decorators import super_admin_required
from judge.tasks import judge_task
# from judge.dispatcher import JudgeDispatcher
from utils.api import APIView
from ..models import Submission, JudgeStatus
from problem.models import Problem


class SubmissionRejudgeAPI(APIView):
    @super_admin_required
    def get(self, request):
        id = request.GET.get("id")
        if not id:
            return self.error("Parameter error, id is required")
        try:
            submission = Submission.objects.select_related("problem").get(id=id, contest_id__isnull=True)
        except Submission.DoesNotExist:
            return self.error("Submission does not exists")
        submission.statistic_info = {}
        submission.save()

        judge_task.send(submission.id, submission.problem.id)
        return self.success()
    
class SubmissionStatisticsAPI(APIView):
    @super_admin_required
    def get(self, request):
        start = request.GET.get("start")
        end = request.GET.get("end")
        
        if not start or not end:
            return self.error("start and end is required")
        
        submissions = Submission.objects.filter(contest_id__isnull=True,
                                                create_time__gte=start,
                                                create_time__lte=end).select_related("problem__created_by")
        
        problem_id = request.GET.get("problem_id")
        
        if problem_id:
            try:
                problem = Problem.objects.get(_id=problem_id, contest_id__isnull=True, visible=True)
            except Problem.DoesNotExist:
                return self.error("Problem doesn't exist")
            submissions = submissions.filter(problem=problem)
        
        username = request.GET.get("username")
        
        if username:
            submissions = submissions.filter(username__icontains=username)
        
        total_count = submissions.count()
        accepted_count = submissions.filter(result=JudgeStatus.ACCEPTED).count()
        
        try:
            correct_rate = round(accepted_count/total_count*100, 2)
        except ZeroDivisionError:
            correct_rate = 0

        return self.success({
            "submission_count": total_count,
            "accepted_count": accepted_count,
            "correct_rate": f"{correct_rate}%",
        })
        