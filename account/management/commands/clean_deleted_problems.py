from django.core.management.base import BaseCommand

from account.models import UserProfile
from problem.models import Problem
from submission.models import JudgeStatus

ACCEPTED_STATUSES = {JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED}


class Command(BaseCommand):
    help = "从用户 Profile 中移除已被删除的题目记录，并同步修正 accepted_number"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="只检查，不写入数据库")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # 所有现存非比赛题目的 PK 集合
        existing_ids = set(
            Problem.objects.filter(contest__isnull=True).values_list("id", flat=True)
        )
        self.stdout.write(f"现存题库题目数: {len(existing_ids)}")

        profiles = UserProfile.objects.select_related("user").exclude(
            acm_problems_status={}
        )
        total = profiles.count()
        self.stdout.write(f"检查用户数: {total}{'（dry-run 模式）' if dry_run else ''}")

        fixed_count = 0
        for profile in profiles:
            problems = profile.acm_problems_status.get("problems", {})
            if not problems:
                continue

            stale_keys = [k for k in problems if int(k) not in existing_ids]
            if not stale_keys:
                continue

            removed_accepted = sum(
                1
                for k in stale_keys
                if problems[k].get("status") in ACCEPTED_STATUSES
            )

            stale_display = [problems[k].get("_id", k) for k in stale_keys]
            self.stdout.write(
                f"  用户 {profile.user.username}"
                f" | 删除 {len(stale_keys)} 题: {', '.join(stale_display)}"
                f"{f' | 其中已AC {removed_accepted} 题' if removed_accepted else ''}"
            )

            if dry_run:
                continue

            for k in stale_keys:
                del profile.acm_problems_status["problems"][k]

            if removed_accepted:
                # 防止 accepted_number 变为负数
                profile.accepted_number = max(0, profile.accepted_number - removed_accepted)

            profile.save(update_fields=["acm_problems_status", "accepted_number"])
            fixed_count += 1

        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run 完成，未写入任何数据"))
        else:
            self.stdout.write(self.style.SUCCESS(f"完成，共修复 {fixed_count} 个用户 Profile"))
