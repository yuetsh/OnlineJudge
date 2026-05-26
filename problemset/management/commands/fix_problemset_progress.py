from django.core.management.base import BaseCommand

from problemset.models import ProblemSetProblem, ProblemSetProgress, ProblemSetSubmission
from submission.models import JudgeStatus, Submission


class Command(BaseCommand):
    help = "根据实际提交记录修复题单进度数据"

    def add_arguments(self, parser):
        parser.add_argument("--problemset-id", type=int, help="只修复指定题单（不传则修复全部）")
        parser.add_argument("--dry-run", action="store_true", help="只检查，不写入数据库")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        problemset_id = options.get("problemset_id")

        progresses = ProblemSetProgress.objects.select_related("user", "problemset")
        if problemset_id:
            progresses = progresses.filter(problemset_id=problemset_id)

        total = progresses.count()
        self.stdout.write(f"共检查 {total} 条进度记录{'（dry-run 模式）' if dry_run else ''}")

        fixed_count = 0
        for progress in progresses:
            problemset_problems = ProblemSetProblem.objects.filter(
                problemset=progress.problemset
            ).select_related("problem")

            updated = False
            for psp in problemset_problems:
                problem_id = str(psp.problem_id)
                if problem_id in progress.progress_detail:
                    continue

                accepted = (
                    Submission.objects.filter(
                        user_id=progress.user_id,
                        problem_id=psp.problem_id,
                        result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED],
                    )
                    .order_by("create_time")
                    .first()
                )
                if not accepted:
                    continue

                self.stdout.write(
                    f"  用户 {progress.user.username} | 题单「{progress.problemset.title}」"
                    f" | 题目 {psp.problem._id} 已AC但进度未记录"
                )
                if dry_run:
                    continue

                progress.progress_detail[problem_id] = {
                    "score": psp.score,
                    "submit_time": accepted.create_time.isoformat(),
                }
                if not ProblemSetSubmission.objects.filter(
                    problemset=progress.problemset,
                    user=progress.user,
                    problem=psp.problem,
                ).exists():
                    ProblemSetSubmission.objects.create(
                        problemset=progress.problemset,
                        user=progress.user,
                        submission=accepted,
                        problem=psp.problem,
                    )
                updated = True

            if updated:
                progress.update_progress()
                fixed_count += 1

        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run 完成，未写入任何数据"))
        else:
            self.stdout.write(self.style.SUCCESS(f"修复完成，共更新 {fixed_count} 条进度记录"))
