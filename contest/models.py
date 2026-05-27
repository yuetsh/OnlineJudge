from django.db import models
from django.utils.timezone import now
from utils.models import JSONField

from utils.constants import ContestStatus, ContestType
from account.models import User
from utils.models import RichTextField


class Contest(models.Model):
    title = models.TextField()
    description = RichTextField()
    tag = models.TextField()
    password = models.TextField(null=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    create_time = models.DateTimeField(auto_now_add=True)
    last_update_time = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    # 是否可见 false的话相当于删除
    visible = models.BooleanField(default=True)
    allowed_ip_ranges = JSONField(default=list)

    @property
    def status(self):
        if self.start_time > now():
            # 没有开始 返回1
            return ContestStatus.CONTEST_NOT_START
        elif self.end_time < now():
            # 已经结束 返回-1
            return ContestStatus.CONTEST_ENDED
        else:
            # 正在进行 返回0
            return ContestStatus.CONTEST_UNDERWAY

    @property
    def contest_type(self):
        if self.password:
            return ContestType.PASSWORD_PROTECTED_CONTEST
        return ContestType.PUBLIC_CONTEST

    # 是否有权查看problem 的一些统计信息 诸如submission_number, accepted_number 等
    def problem_details_permission(self, user):
        return self.status == ContestStatus.CONTEST_ENDED or user.is_authenticated and user.is_contest_admin(self)

    class Meta:
        db_table = "contest"
        ordering = ("-start_time",)


class AbstractContestRank(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE)
    submission_number = models.IntegerField(default=0, db_default=0)

    class Meta:
        abstract = True


class ACMContestRank(AbstractContestRank):
    accepted_number = models.IntegerField(default=0, db_default=0)
    # total_time is only for ACM contest, total_time =  ac time + none-ac times * 20 * 60
    total_time = models.IntegerField(default=0, db_default=0)
    # {"23": {"is_ac": True, "ac_time": 8999, "error_number": 2, "is_first_ac": True}}
    # key is problem id
    submission_info = JSONField(default=dict, db_default=models.Value({}, output_field=models.JSONField()))

    class Meta:
        db_table = "acm_contest_rank"
        constraints = [
            models.UniqueConstraint(fields=["user", "contest"], name="unique_acm_rank_user_contest"),
        ]
        indexes = [
            models.Index(fields=["contest", "accepted_number", "total_time"], name="acm_rank_order_idx"),
            models.Index(fields=["contest", "user"], name="acm_rank_contest_user_idx"),
        ]



class ContestAnnouncement(models.Model):
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE)
    title = models.TextField()
    content = RichTextField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    visible = models.BooleanField(default=True)
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contest_announcement"
        ordering = ("-create_time",)
