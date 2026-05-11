from django.db import models


class ContestType(models.TextChoices):
    PUBLIC_CONTEST = "Public", "Public"
    PASSWORD_PROTECTED_CONTEST = "Password Protected", "Password Protected"


class ContestStatus(models.TextChoices):
    CONTEST_NOT_START = "1", "Not Started"
    CONTEST_ENDED = "-1", "Ended"
    CONTEST_UNDERWAY = "0", "Underway"


class ContestRuleType(models.TextChoices):
    ACM = "ACM", "ACM"
    OI = "OI", "OI"


class CacheKey:
    waiting_queue = "waiting_queue"
    contest_rank_cache = "contest_rank_cache"
    website_config = "website_config"
    problem_authors = "problem_authors"
    problem_tags = "problem_tags"
    comment_stats = "comment_stats"
    user_activity_rank = "user_activity_rank"
    problem_yearly_ac = "problem_yearly_ac"


class Difficulty(models.TextChoices):
    LOW = "Low", "Low"
    MID = "Mid", "Mid"
    HIGH = "High", "High"


CONTEST_PASSWORD_SESSION_KEY = "contest_password"
