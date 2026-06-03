import functools
import hashlib
import inspect
import time

from contest.models import Contest, ContestStatus, ContestType
from problem.models import Problem
from utils.api import APIError, JSONResponse
from utils.constants import CONTEST_PASSWORD_SESSION_KEY

from .models import ProblemPermission


class BasePermissionDecorator(object):
    def __init__(self, func):
        self.func = func

    def __get__(self, obj, obj_type):
        if inspect.iscoroutinefunction(self.func):
            return functools.partial(self._async_call, obj)
        return functools.partial(self.__call__, obj)

    def error(self, data, err="permission-denied"):
        return JSONResponse.response({"error": err, "data": data})

    def _permission_error(self, request):
        if not request.user.is_authenticated:
            return self.error("请先登录", err="login-required")
        return self.error("权限不足", err="permission-denied")

    def __call__(self, *args, **kwargs):
        request = args[1]

        if self.check_permission(request):
            if request.user.is_disabled:
                return self.error("账号已禁用")
            return self.func(*args, **kwargs)
        else:
            return self._permission_error(request)

    async def _async_call(self, *args, **kwargs):
        request = args[1]

        if self.check_permission(request):
            if request.user.is_disabled:
                return self.error("账号已禁用")
            return await self.func(*args, **kwargs)
        return self._permission_error(request)

    def check_permission(self, request):
        raise NotImplementedError()


class login_required(BasePermissionDecorator):
    def check_permission(self, request):
        return request.user.is_authenticated


class super_admin_required(BasePermissionDecorator):
    def check_permission(self, request):
        user = request.user
        return user.is_authenticated and user.is_super_admin()


class teacher_admin_required(BasePermissionDecorator):
    def check_permission(self, request):
        user = request.user
        return user.is_authenticated and user.is_teacher_or_above()


class admin_role_required(BasePermissionDecorator):
    def check_permission(self, request):
        user = request.user
        return user.is_authenticated and user.is_admin_role()


class problem_permission_required(admin_role_required):
    def check_permission(self, request):
        if not super().check_permission(request):
            return False
        if request.user.problem_permission == ProblemPermission.NONE:
            return False
        return True


def check_contest_password(password, contest_password):
    if not (password and contest_password):
        return False
    if password == contest_password:
        return True
    else:
        # sig#timestamp 这种形式的密码也可以，但是在界面上没提供支持
        # sig = sha256(contest_password + timestamp)[:8]
        if "#" in password:
            s = password.split("#")
            if len(s) != 2:
                return False
            sig, ts = s[0], s[1]

            if sig == hashlib.sha256((contest_password + ts).encode("utf-8")).hexdigest()[:8]:
                try:
                    ts = int(ts)
                except Exception:
                    return False
                return int(time.time()) < ts
            else:
                return False
        else:
            return False


def check_contest_permission(check_type="details"):
    """
    只供Class based view 使用，检查用户是否有权进入该contest, check_type 可选 details, problems, ranks, submissions
    若通过验证，在view中可通过self.contest获得该contest
    """

    def _get_contest_id(request):
        return request.data.get("contest_id") or request.GET.get("contest_id")

    def _check_access(self, request, user):
        if not user.is_authenticated:
            return self.error("请先登录", err="login-required")

        if user.is_contest_admin(self.contest):
            return None

        if self.contest.contest_type == ContestType.PASSWORD_PROTECTED_CONTEST:
            if not check_contest_password(request.session.get(CONTEST_PASSWORD_SESSION_KEY, {}).get(self.contest.id), self.contest.password):
                return self.error("Wrong password or password expired")

        if self.contest.status == ContestStatus.CONTEST_NOT_START and check_type != "details":
            return self.error("Contest has not started yet.")

        return None

    def decorator(func):
        @functools.wraps(func)
        async def _wrapper(*args, **kwargs):
            self = args[0]
            request = args[1]
            contest_id = _get_contest_id(request)
            if not contest_id:
                return self.error("Parameter error, contest_id is required")
            try:
                self.contest = await Contest.objects.select_related("created_by").aget(id=contest_id, visible=True)
            except Contest.DoesNotExist:
                return self.error("Contest %s doesn't exist" % contest_id)
            error = _check_access(self, request, request.user)
            if error:
                return error
            return await func(*args, **kwargs)
        return _wrapper
    return decorator


def ensure_created_by(obj, user):
    e = APIError(msg=f"{obj.__class__.__name__} does not exist")
    if not user.is_admin_role():
        raise e
    if user.is_super_admin():
        return
    if isinstance(obj, Problem):
        if not user.can_mgmt_all_problem() and obj.created_by != user:
            raise e
    elif obj.created_by != user:
        raise e
