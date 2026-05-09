from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.db import models

from utils.models import JSONField


class AdminType(models.TextChoices):
    REGULAR_USER = "Regular User", "Regular User"
    ADMIN = "Admin", "Admin"
    SUPER_ADMIN = "Super Admin", "Super Admin"


class ProblemPermission(models.TextChoices):
    NONE = "None", "None"
    OWN = "Own", "Own"
    ALL = "All", "All"


class UserManager(models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, username):
        return self.get(**{f"{self.model.USERNAME_FIELD}__iexact": username})


class User(AbstractBaseUser):
    username = models.TextField(unique=True)
    class_name = models.TextField(null=True)
    email = models.TextField(null=True)
    create_time = models.DateTimeField(auto_now_add=True, null=True)
    # One of UserType
    admin_type = models.TextField(default=AdminType.REGULAR_USER, choices=AdminType.choices)
    problem_permission = models.TextField(default=ProblemPermission.NONE, choices=ProblemPermission.choices)
    reset_password_token = models.TextField(null=True)
    reset_password_token_expire_time = models.DateTimeField(null=True)
    # SSO auth token
    auth_token = models.TextField(null=True)
    two_factor_auth = models.BooleanField(default=False, db_default=False)
    tfa_token = models.TextField(null=True)
    session_keys = JSONField(default=list, db_default=models.Value([]))
    # open api key
    open_api = models.BooleanField(default=False, db_default=False)
    open_api_appkey = models.TextField(null=True)
    is_disabled = models.BooleanField(default=False, db_default=False)
    raw_password = models.CharField(max_length=20, null=True, blank=True, verbose_name="明文密码")

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def is_regular_user(self):
        return self.admin_type == AdminType.REGULAR_USER

    def is_admin(self):
        return self.admin_type == AdminType.ADMIN

    def is_super_admin(self):
        return self.admin_type == AdminType.SUPER_ADMIN

    def is_admin_role(self):
        return self.admin_type in [AdminType.ADMIN, AdminType.SUPER_ADMIN]

    def can_mgmt_all_problem(self):
        return self.problem_permission == ProblemPermission.ALL

    def is_contest_admin(self, contest):
        return self.is_authenticated and (contest.created_by == self or self.admin_type == AdminType.SUPER_ADMIN)

    def set_password(self, raw_password):
        super().set_password(raw_password)
        self.raw_password = raw_password

    class Meta:
        db_table = "user"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    # acm_problems_status examples:
    # {
    #     "problems": {
    #         "1": {
    #             "status": JudgeStatus.ACCEPTED,
    #             "_id": "1000"
    #         }
    #     },
    #     "contest_problems": {
    #         "1": {
    #             "status": JudgeStatus.ACCEPTED,
    #             "_id": "1000"
    #         }
    #     }
    # }
    acm_problems_status = JSONField(default=dict, db_default=models.Value({}))
    # like acm_problems_status, merely add "score" field
    oi_problems_status = JSONField(default=dict, db_default=models.Value({}))

    real_name = models.TextField(null=True)
    avatar = models.TextField(default=f"{settings.AVATAR_URI_PREFIX}/default.png")
    blog = models.URLField(null=True)
    mood = models.TextField(null=True)
    github = models.TextField(null=True)
    school = models.TextField(null=True)
    major = models.TextField(null=True)
    language = models.TextField(null=True)
    # for ACM
    accepted_number = models.IntegerField(default=0, db_default=0)
    # for OI
    total_score = models.BigIntegerField(default=0, db_default=0)
    submission_number = models.IntegerField(default=0, db_default=0)

    def add_accepted_problem_number(self):
        self.accepted_number = models.F("accepted_number") + 1
        self.save(update_fields=["accepted_number"])

    def add_submission_number(self):
        self.submission_number = models.F("submission_number") + 1
        self.save(update_fields=["submission_number"])

    # 计算总分时， 应先减掉上次该题所得分数， 然后再加上本次所得分数
    def add_score(self, this_time_score, last_time_score=None):
        last_time_score = last_time_score or 0
        self.total_score = models.F("total_score") - last_time_score + this_time_score
        self.save(update_fields=["total_score"])

    class Meta:
        db_table = "user_profile"
