from django.core.management.base import BaseCommand

from problem.models import Problem
from problem.utils import generate_sql_display


class Command(BaseCommand):
    help = "为存量 SQL 题目重新生成 sql_display 展示数据（新建/编辑题目时会自动生成，此命令用于回填老题）"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="只检查并打印结果，不写数据库")
        parser.add_argument("--force", action="store_true", help="已有 sql_display 的题目也重新生成（默认跳过）")

    def handle(self, *args, **options):
        qs = Problem.objects.filter(sql_config__isnull=False).order_by("id")
        ok = failed = skipped = 0
        for p in qs:
            label = f"id={p.id} _id={p._id}" + (f" contest={p.contest_id}" if p.contest_id else "") + f" {p.title}"
            if p.sql_display is not None and not options["force"]:
                skipped += 1
                self.stdout.write(f"SKIP  {label}（已有 sql_display，--force 可强制重建）")
                continue
            display, error = generate_sql_display(p.test_case_id, p.answers, p.sql_config)
            if error:
                failed += 1
                self.stderr.write(self.style.ERROR(f"FAIL  {label}: {error}"))
                continue
            if not options["dry_run"]:
                p.sql_display = display
                p.save(update_fields=["sql_display"])
            ok += 1
            self.stdout.write(self.style.SUCCESS(f"OK    {label}"))
        summary = f"完成：成功 {ok}，失败 {failed}，跳过 {skipped}，共 {qs.count()} 道 SQL 题"
        if options["dry_run"]:
            summary += "（dry-run，未写库）"
        self.stdout.write(summary)
