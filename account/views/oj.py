import asyncio
import os
from importlib import import_module

from django.conf import settings
from django.contrib import auth
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from options.options import SysOptions
from problem.models import Problem
from submission.models import JudgeStatus, Submission
from utils.api import APIView, AsyncAPIView, CSRFExemptAPIView, validate_serializer
from utils.async_helpers import async_cache_get, async_cache_set
from utils.constants import CacheKey
from utils.shortcuts import datetime2str, rand_str

from ..decorators import login_required
from ..models import AdminType, User, UserProfile
from ..serializers import (
    EditUserProfileSerializer,
    ImageUploadForm,
    RankInfoSerializer,
    SSOSerializer,
    UserChangeEmailSerializer,
    UserChangePasswordSerializer,
    UserLoginSerializer,
    UsernameOrEmailCheckSerializer,
    UserProfileSerializer,
    UserRegisterSerializer,
)


class UserProfileAPI(AsyncAPIView):
    @method_decorator(ensure_csrf_cookie)
    async def get(self, request, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return self.success()
        show_real_name = False
        username = request.GET.get("username")
        try:
            if username:
                user = await User.objects.aget(username=username, is_disabled=False)
            else:
                user = request.user
                show_real_name = True
        except User.DoesNotExist:
            return self.error("User does not exist")
        profile = await UserProfile.objects.select_related("user").aget(user=user)
        return self.success(UserProfileSerializer(profile, show_real_name=show_real_name).data)

    @login_required
    @validate_serializer(EditUserProfileSerializer)
    async def put(self, request):
        data = request.data
        user_profile = await UserProfile.objects.select_related("user").aget(user=request.user)
        for k, v in data.items():
            setattr(user_profile, k, v)
        await user_profile.asave()
        return self.success(UserProfileSerializer(user_profile, show_real_name=True).data)


class Metrics(AsyncAPIView):
    async def get(self, request):
        userid = request.GET.get("userid")
        qs = Submission.objects.filter(user_id=userid, contest_id__isnull=True)
        count, latest, first = await asyncio.gather(
            qs.acount(),
            qs.order_by("-create_time").afirst(),
            qs.order_by("create_time").afirst(),
        )
        if count == 0 or not latest or not first:
            return self.error("暂无提交")
        return self.success(
            {
                "now": datetime2str(timezone.now()),
                "latest": datetime2str(latest.create_time),
                "first": datetime2str(first.create_time),
            }
        )


class AvatarUploadAPI(AsyncAPIView):
    request_parsers = ()

    @login_required
    async def post(self, request):
        form = ImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            avatar = form.cleaned_data["image"]
        else:
            return self.error("Invalid file content")
        if avatar.size > 2 * 1024 * 1024:
            return self.error("Picture is too large")
        suffix = os.path.splitext(avatar.name)[-1].lower()
        if suffix not in [".gif", ".jpg", ".jpeg", ".bmp", ".png"]:
            return self.error("Unsupported file format")

        name = rand_str(10) + suffix
        with open(os.path.join(settings.AVATAR_UPLOAD_DIR, name), "wb") as img:
            for chunk in avatar:
                img.write(chunk)
        user_profile = await UserProfile.objects.aget(user=request.user)

        user_profile.avatar = f"{settings.AVATAR_URI_PREFIX}/{name}"
        await user_profile.asave()
        return self.success("Succeeded")


class UserLoginAPI(AsyncAPIView):
    @validate_serializer(UserLoginSerializer)
    async def post(self, request):
        data = request.data
        user = await auth.aauthenticate(username=data["username"], password=data["password"])
        if user:
            if user.is_disabled:
                return self.error("Your account has been disabled")
            prev_login = user.last_login
            await auth.alogin(request, user)
            request.session["prev_login"] = datetime2str(prev_login) if prev_login else ""
            return self.success("Succeeded")
        else:
            return self.error("Invalid username or password")


class UserLogoutAPI(AsyncAPIView):
    async def get(self, request):
        await auth.alogout(request)
        return self.success()


# DEPRECATED: 前端未调用 (2026-05-26)
class UsernameOrEmailCheck(APIView):
    @validate_serializer(UsernameOrEmailCheckSerializer)
    def post(self, request):
        """
        check username or email is duplicate
        """
        data = request.data
        # True means already exist.
        result = {"username": False, "email": False}
        if data.get("username"):
            result["username"] = User.objects.filter(username=data["username"].lower()).exists()
        if data.get("email"):
            result["email"] = User.objects.filter(email=data["email"].lower()).exists()
        return self.success(result)


class UserRegisterAPI(AsyncAPIView):
    @validate_serializer(UserRegisterSerializer)
    async def post(self, request):
        if not await SysOptions.aget("allow_register"):
            return self.error("Register function has been disabled by admin")

        data = request.data
        data["username"] = data["username"].lower()
        data["email"] = data["email"].lower()
        if await User.objects.filter(username=data["username"]).aexists():
            return self.error("Username already exists")
        if await User.objects.filter(email=data["email"]).aexists():
            return self.error("Email already exists")
        user = await User.objects.acreate(username=data["username"], email=data["email"])
        user.set_password(data["password"])
        await user.asave()
        await UserProfile.objects.acreate(user=user)
        return self.success("Succeeded")


# DEPRECATED: 前端未调用 (2026-05-26)
class UserChangeEmailAPI(APIView):
    @validate_serializer(UserChangeEmailSerializer)
    @login_required
    def post(self, request):
        data = request.data
        user = auth.authenticate(username=request.user.username, password=data["password"])
        if user:
            data["new_email"] = data["new_email"].lower()
            if User.objects.filter(email=data["new_email"]).exists():
                return self.error("The email is owned by other account")
            user.email = data["new_email"]
            user.save()
            return self.success("Succeeded")
        else:
            return self.error("Wrong password")


# DEPRECATED: 前端未调用 (2026-05-26)
class UserChangePasswordAPI(APIView):
    @validate_serializer(UserChangePasswordSerializer)
    @login_required
    def post(self, request):
        """
        User change password api
        """
        data = request.data
        username = request.user.username
        user = auth.authenticate(username=username, password=data["old_password"])
        if user:
            user.set_password(data["new_password"])
            user.save()
            return self.success("Succeeded")
        else:
            return self.error("Invalid old password")


# DEPRECATED: 前端未调用 (2026-05-26)
class SessionManagementAPI(APIView):
    @login_required
    def get(self, request):
        engine = import_module(settings.SESSION_ENGINE)
        session_store = engine.SessionStore
        current_session = request.session.session_key
        session_keys = request.user.session_keys
        result = []
        modified = False
        for key in session_keys[:]:
            session = session_store(key)
            # session does not exist or is expiry
            if not session._session:
                session_keys.remove(key)
                modified = True
                continue

            s = {}
            if current_session == key:
                s["current_session"] = True
            s["ip"] = session["ip"]
            s["user_agent"] = session["user_agent"]
            s["last_activity"] = datetime2str(session["last_activity"])
            s["session_key"] = key
            result.append(s)
        if modified:
            request.user.save()
        return self.success(result)

    @login_required
    def delete(self, request):
        session_key = request.GET.get("session_key")
        if not session_key:
            return self.error("Parameter Error")
        request.session.delete(session_key)
        if session_key in request.user.session_keys:
            request.user.session_keys.remove(session_key)
            request.user.save()
            return self.success("Succeeded")
        else:
            return self.error("Invalid session_key")


class UserRankAPI(AsyncAPIView):
    async def get(self, request):
        username = request.GET.get("username", "")
        try:
            n = int(request.GET.get("n", "0"))
        except ValueError:
            n = 0

        profiles = (
            UserProfile.objects.filter(
                user__admin_type__in=[AdminType.REGULAR_USER, AdminType.STUDENT_ADMIN],
                user__is_disabled=False,
                user__username__icontains=username,
            )
            .select_related("user")
            .filter(accepted_number__gte=0)
            .order_by("-accepted_number", "submission_number")
        )
        if n > 0:
            profiles = profiles[:n]
        return self.success(await self.async_paginate_data(request, profiles, RankInfoSerializer))


class UserActivityRankAPI(AsyncAPIView):
    async def get(self, request):
        start = request.GET.get("start")
        if not start:
            return self.error("start time is required")
        cache_key = f"{CacheKey.user_activity_rank}:{start}"
        cached = await async_cache_get(cache_key)
        if cached is not None:
            return self.success(cached)

        hidden_names = User.objects.filter(Q(admin_type=AdminType.SUPER_ADMIN) | Q(is_disabled=True)).values_list("username", flat=True)
        submissions = Submission.objects.filter(
            contest_id__isnull=True,
            create_time__gte=start,
            result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED],
        ).exclude(username__in=hidden_names)
        data = [row async for row in submissions.values("username").annotate(count=Count("problem_id", distinct=True)).order_by("-count")[:10]]
        await async_cache_set(cache_key, data, 600)
        return self.success(data)


class UserProblemRankAPI(AsyncAPIView):
    async def get(self, request):
        problem_id = request.GET.get("problem_id")
        user = request.user
        if not user.is_authenticated:
            return self.error("User is not authenticated")

        problem = await Problem.objects.aget(_id__iexact=problem_id, contest_id__isnull=True, visible=True)
        submissions = Submission.objects.filter(problem=problem, result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED])

        all_ac_count = await submissions.values("user_id").distinct().acount()

        class_name = user.class_name or ""
        class_ac_count = 0

        if class_name:
            users = User.objects.filter(class_name=user.class_name, is_disabled=False).values_list("id", flat=True)
            user_ids = [user_id async for user_id in users]
            submissions = submissions.filter(user_id__in=user_ids)
            class_ac_count = await submissions.values("user_id").distinct().acount()

        my_submissions = submissions.filter(user_id=user.id)

        if not await my_submissions.aexists():
            return self.success(
                {
                    "class_name": class_name,
                    "rank": -1,
                    "class_ac_count": class_ac_count,
                    "all_ac_count": all_ac_count,
                }
            )

        my_first_submission = await my_submissions.order_by("create_time").afirst()
        rank = await submissions.filter(create_time__lte=my_first_submission.create_time).acount()
        return self.success(
            {
                "class_name": class_name,
                "rank": rank,
                "class_ac_count": class_ac_count,
                "all_ac_count": all_ac_count,
            }
        )


class ProfileProblemDisplayIDRefreshAPI(AsyncAPIView):
    @login_required
    async def get(self, request):
        profile = await UserProfile.objects.aget(user=request.user)
        acm_problems = profile.acm_problems_status.get("problems", {})
        ids = list(acm_problems.keys())
        if not ids:
            return self.success()
        display_ids = [did async for did in Problem.objects.filter(id__in=ids, visible=True).values_list("_id", flat=True)]
        id_map = dict(zip(ids, display_ids))
        for k, v in acm_problems.items():
            v["_id"] = id_map[k]
        await profile.asave(update_fields=["acm_problems_status"])
        return self.success()


# DEPRECATED: 前端未调用 (2026-05-26)
class OpenAPIAppkeyAPI(APIView):
    @login_required
    def post(self, request):
        user = request.user
        if not user.open_api:
            return self.error("OpenAPI function is truned off for you")
        api_appkey = rand_str()
        user.open_api_appkey = api_appkey
        user.save()
        return self.success({"appkey": api_appkey})


# DEPRECATED: 前端未调用 (2026-05-26)
class SSOAPI(CSRFExemptAPIView):
    @login_required
    def get(self, request):
        token = rand_str()
        request.user.auth_token = token
        request.user.save()
        return self.success({"token": token})

    @method_decorator(csrf_exempt)
    @validate_serializer(SSOSerializer)
    def post(self, request):
        try:
            user = User.objects.get(auth_token=request.data["token"])
        except User.DoesNotExist:
            return self.error("User does not exist")
        return self.success(
            {
                "username": user.username,
                "avatar": user.userprofile.avatar,
                "admin_type": user.admin_type,
            }
        )
