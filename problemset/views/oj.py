from django.db.models import Avg, Count, Prefetch, Q
from django.utils import timezone

from account.decorators import login_required, teacher_admin_required
from account.models import User
from achievement.notify import notify_badges
from problem.models import Problem
from problemset.models import (
    BadgeConditionType,
    ProblemSet,
    ProblemSetBadge,
    ProblemSetProblem,
    ProblemSetProgress,
    ProblemSetStatus,
    ProblemSetSubmission,
    UserBadge,
)
from problemset.serializers import (
    JoinProblemSetSerializer,
    ProblemSetBadgeSerializer,
    ProblemSetListSerializer,
    ProblemSetProblemSerializer,
    ProblemSetProgressSerializer,
    ProblemSetSerializer,
    UpdateProgressSerializer,
    UserBadgeSerializer,
)
from submission.models import Submission, is_accepted
from utils.api import APIView, AsyncAPIView, validate_serializer


class ProblemSetAPI(AsyncAPIView):
    """题单API - 用户端"""

    async def get(self, request):
        """获取题单列表"""
        # 预加载创建者信息
        problem_sets = ProblemSet.objects.filter(visible=True).exclude(status=ProblemSetStatus.DRAFT).select_related("created_by")

        # 使用annotate在查询时计算题目数量，避免N+1查询
        problem_sets = problem_sets.annotate(problems_count=Count("problemsetproblem", distinct=True))

        # 过滤条件
        keyword = request.GET.get("keyword", "").strip()
        if keyword:
            problem_sets = problem_sets.filter(Q(title__icontains=keyword) | Q(description__icontains=keyword))

        difficulty = request.GET.get("difficulty")
        if difficulty:
            problem_sets = problem_sets.filter(difficulty=difficulty)

        status_filter = request.GET.get("status")
        if status_filter:
            problem_sets = problem_sets.filter(status=status_filter)

        # 排序
        sort = request.GET.get("sort")
        if sort:
            problem_sets = problem_sets.order_by(sort)
        else:
            problem_sets = problem_sets.order_by("-create_time")

        # 批量查询用户进度和已获得的奖章（如果用户已登录）
        # 注意：需要在应用prefetch_related之前获取ID列表，避免不必要的预加载
        user_progress_map = {}
        user_earned_badge_ids = set()
        if request.user.is_authenticated:
            # 先获取所有题单ID（不应用prefetch_related，只获取ID）
            problem_set_ids = [problem_set_id async for problem_set_id in problem_sets.values_list("id", flat=True)]

            if problem_set_ids:
                # 批量查询用户在这些题单中的进度
                user_progresses = ProblemSetProgress.objects.filter(problemset_id__in=problem_set_ids, user=request.user).select_related("problemset")
                # 构建映射：题单ID -> 进度对象
                user_progress_map = {progress.problemset_id: progress async for progress in user_progresses}

                # 批量查询用户已获得的奖章ID（这些题单相关的）
                user_earned_badge_ids = {
                    badge_id async for badge_id in UserBadge.objects.filter(user=request.user, badge__problemset_id__in=problem_set_ids).values_list("badge_id", flat=True)
                }

        # 预加载奖章信息（在获取ID之后应用，避免在获取ID时也预加载）
        problem_sets = problem_sets.prefetch_related(Prefetch("problemsetbadge_set", queryset=ProblemSetBadge.objects.all(), to_attr="badges"))

        # 将用户进度映射和已获得的奖章ID集合存储到request中，供序列化器使用
        request._user_progress_map = user_progress_map
        request._user_earned_badge_ids = user_earned_badge_ids

        data = await self.async_paginate_data(request, problem_sets, ProblemSetListSerializer)
        return self.success(data)


class ProblemSetDetailAPI(AsyncAPIView):
    """题单详情API - 用户端"""

    async def get(self, request, problem_set_id):
        """获取题单详情"""
        try:
            problem_set = await ProblemSet.objects.select_related("created_by").filter(id=problem_set_id, visible=True).exclude(status=ProblemSetStatus.DRAFT).aget()
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        return self.success(await self.async_serialize_data(ProblemSetSerializer, problem_set, context={"request": request}))


class ProblemSetProblemAPI(AsyncAPIView):
    """题单题目API - 用户端"""

    async def get(self, request, problem_set_id):
        """获取题单中的题目列表"""
        try:
            problem_set = await ProblemSet.objects.filter(id=problem_set_id, visible=True).exclude(status=ProblemSetStatus.DRAFT).aget()
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        problems = ProblemSetProblem.objects.filter(problemset=problem_set).select_related("problem__created_by").prefetch_related("problem__tags").order_by("order")
        # 预取当前用户的题单进度，供 get_is_completed 使用，避免 N+1
        user_progress = None
        if request.user.is_authenticated:
            user_progress = await ProblemSetProgress.objects.filter(problemset=problem_set, user=request.user).afirst()
        problem_list = [problem async for problem in problems]
        return self.success(
            await self.async_serialize_data(
                ProblemSetProblemSerializer,
                problem_list,
                many=True,
                context={"request": request, "user_progress": user_progress},
            )
        )


class ProblemSetProgressAPI(APIView):
    """题单进度API"""

    @login_required
    @validate_serializer(JoinProblemSetSerializer)
    def post(self, request):
        """加入题单"""
        data = request.data
        try:
            problem_set = ProblemSet.objects.filter(id=data["problemset_id"], visible=True).exclude(status=ProblemSetStatus.DRAFT).get()
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        if ProblemSetProgress.objects.filter(problemset=problem_set, user=request.user).exists():
            return self.error("已经加入该题单")

        # 创建进度记录
        progress = ProblemSetProgress.objects.create(problemset=problem_set, user=request.user)
        progress.update_progress()

        return self.success("成功加入题单")

    @login_required
    def get(self, request, problem_set_id):
        """获取题单进度"""
        try:
            problem_set = ProblemSet.objects.filter(id=problem_set_id, visible=True).exclude(status=ProblemSetStatus.DRAFT).get()
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        try:
            progress = ProblemSetProgress.objects.get(problemset=problem_set, user=request.user)
        except ProblemSetProgress.DoesNotExist:
            return self.error("未加入该题单")

        serializer = ProblemSetProgressSerializer(progress)
        return self.success(serializer.data)

    @login_required
    @validate_serializer(UpdateProgressSerializer)
    def put(self, request):
        """更新进度"""
        data = request.data
        try:
            problem_set = ProblemSet.objects.filter(id=data["problemset_id"], visible=True).exclude(status=ProblemSetStatus.DRAFT).get()
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        try:
            progress = ProblemSetProgress.objects.get(problemset=problem_set, user=request.user)
        except ProblemSetProgress.DoesNotExist:
            return self.error("未加入该题单")

        problem_id = str(data["problem_id"])
        submission_id = data.get("submission_id")

        if not submission_id:
            return self.error("需要提供提交记录ID")

        try:
            submission = Submission.objects.get(id=submission_id, user_id=request.user.id)
        except Submission.DoesNotExist:
            return self.error("提交记录不存在")

        if not is_accepted(submission.result):
            return self.error("只有通过的提交才能更新进度")

        try:
            problemset_problem = ProblemSetProblem.objects.get(problemset=problem_set, problem_id=problem_id)
            problem_score = problemset_problem.score
        except ProblemSetProblem.DoesNotExist:
            problem_score = 0

        progress.progress_detail[problem_id] = {
            "score": problem_score,
            "submit_time": timezone.now().isoformat(),
        }
        progress.update_progress()

        try:
            problem = Problem.objects.get(id=problem_id)
            if not ProblemSetSubmission.objects.filter(problemset=problem_set, user=request.user, problem=problem).exists():
                ProblemSetSubmission.objects.create(
                    problemset=problem_set,
                    user=request.user,
                    submission=submission,
                    problem=problem,
                )
        except Problem.DoesNotExist:
            pass

        self._check_badges(progress)
        return self.success("进度已更新")

    def _check_badges(self, progress):
        """检查是否获得奖章。

        一次查询取出全部已获奖章 id，内存比对，避免逐条 exists()（原来的 N+1）。
        用 get_or_create 避免并发重复提交撞 unique constraint 抛异常。
        新获得的奖章推送给用户——接入前奖章是静默入库的，学生根本不知道自己拿到了。
        """
        badges = list(ProblemSetBadge.objects.filter(problemset=progress.problemset))
        if not badges:
            return

        owned = set(UserBadge.objects.filter(user=progress.user, badge__in=badges).values_list("badge_id", flat=True))

        earned = []
        for badge in badges:
            if badge.id in owned:
                continue

            if badge.condition_type == BadgeConditionType.ALL_PROBLEMS:
                hit = progress.total_problems_count > 0 and progress.completed_problems_count == progress.total_problems_count
            elif badge.condition_type == BadgeConditionType.PROBLEM_COUNT:
                hit = progress.completed_problems_count >= badge.condition_value
            elif badge.condition_type == BadgeConditionType.SCORE:
                hit = progress.total_score >= badge.condition_value
            else:
                hit = False

            if hit:
                _, created = UserBadge.objects.get_or_create(user=progress.user, badge=badge)
                if created:
                    earned.append(badge)

        if earned:
            notify_badges(progress.user_id, earned)


# DEPRECATED: 前端未调用 (2026-05-26)
class UserProgressAPI(APIView):
    """用户进度API"""

    @login_required
    def get(self, request):
        """获取用户的题单进度列表"""
        progress_list = ProblemSetProgress.objects.filter(user=request.user).order_by("-join_time")
        serializer = ProblemSetProgressSerializer(progress_list, many=True)
        return self.success(serializer.data)


class UserBadgeAPI(AsyncAPIView):
    """用户奖章API"""

    async def get(self, request):
        """获取用户的奖章列表"""
        # 支持通过username参数获取指定用户的徽章
        username = request.GET.get("username")

        if username:
            # 获取指定用户的徽章
            try:
                target_user = await User.objects.aget(username=username, is_disabled=False)
                badges = UserBadge.objects.select_related("badge__problemset").filter(user=target_user).order_by("-earned_time")
            except User.DoesNotExist:
                return self.error("用户不存在")
        else:
            # 获取当前用户的徽章
            badges = UserBadge.objects.select_related("badge__problemset").filter(user=request.user).order_by("-earned_time")

        badge_list = [badge async for badge in badges]
        return self.success(await self.async_serialize_data(UserBadgeSerializer, badge_list, many=True))


class ProblemSetBadgeAPI(AsyncAPIView):
    """题单奖章API - 用户端"""

    async def get(self, request, problem_set_id):
        """获取题单的奖章列表"""
        try:
            problem_set = await ProblemSet.objects.filter(id=problem_set_id, visible=True).exclude(status=ProblemSetStatus.DRAFT).aget()
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        badges = ProblemSetBadge.objects.filter(problemset=problem_set)
        badge_list = [badge async for badge in badges]
        return self.success(await self.async_serialize_data(ProblemSetBadgeSerializer, badge_list, many=True))


class ProblemSetUserProgressAPI(AsyncAPIView):
    """题单用户进度列表API"""

    @teacher_admin_required
    async def get(self, request, problem_set_id: int):
        """获取题单的用户进度列表"""
        try:
            problem_set = await ProblemSet.objects.filter(id=problem_set_id, visible=True).exclude(status=ProblemSetStatus.DRAFT).aget()
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        # 获取所有参与该题单的用户进度，使用 select_related 预加载用户信息
        progresses = ProblemSetProgress.objects.filter(problemset=problem_set).select_related("user")

        # 班级过滤
        class_name = request.GET.get("class_name", "").strip()
        if class_name:
            progresses = progresses.filter(user__username__icontains=class_name)

        # 完成度筛选
        completion_status = request.GET.get("completion_status", "").strip()
        if completion_status == "completed":
            # 已完成：所有题目都已完成
            progresses = progresses.filter(is_completed=True)
        elif completion_status == "in_progress":
            # 进行中：未完成且已开始（至少完成了一道题，排除未开始的用户）
            progresses = progresses.filter(is_completed=False, completed_problems_count__gt=0)
        elif completion_status == "not_started":
            # 未开始：还没有完成任何题目
            progresses = progresses.filter(completed_problems_count=0)

        # 排序
        progresses = progresses.order_by("-is_completed", "-progress_percentage", "join_time")

        # 计算统计数据（基于所有数据，而非分页数据）
        # 使用一次查询获取所有统计数据
        stats = await progresses.aaggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(is_completed=True)),
            avg_progress=Avg("progress_percentage"),
        )
        total_count = stats["total"]
        completed_count = stats["completed"]
        avg_progress = stats["avg_progress"] or 0

        # 获取分页参数
        try:
            limit = int(request.GET.get("limit", "10"))
        except ValueError:
            limit = 10
        try:
            offset = int(request.GET.get("offset", "0"))
        except ValueError:
            offset = 0
        if offset < 0:
            offset = 0

        # 提前获取题单的所有题目（用于前端显示未完成题目和序列化器）
        # 使用 select_related 和 only 优化查询，只选择需要的字段
        all_problemset_problems = (
            ProblemSetProblem.objects.filter(problemset=problem_set).select_related("problem").only("problem__id", "problem___id", "problem__title", "order").order_by("order")
        )

        # 构建题单所有题目的数据结构和映射
        all_problems_list = []
        all_problems_map = {}
        async for psp in all_problemset_problems:
            problem_data = {
                "id": psp.problem.id,
                "_id": psp.problem._id,
                "title": psp.problem.title,
            }
            all_problems_list.append(problem_data)
            # 用于序列化器查找，key 使用字符串格式（与 progress_detail 的 key 格式一致）
            all_problems_map[str(psp.problem.id)] = psp.problem

        # 从当前页的数据中收集已完成的问题ID，用于序列化器
        paginated_progresses = [progress async for progress in progresses[offset : offset + limit]]
        completed_problem_ids = set()
        for progress in paginated_progresses:
            if progress.progress_detail:
                # progress_detail 的 key 是字符串格式的 problem_id
                completed_problem_ids.update(progress.progress_detail.keys())

        # 从已加载的题单题目中构建 problems_dict，避免重复查询
        problems_dict = {pid: all_problems_map[pid] for pid in completed_problem_ids if pid in all_problems_map}

        # 将预加载的问题字典存储到 request 中，供序列化器使用
        request._problems_dict_cache = problems_dict

        # 使用分页
        data = await self.async_paginate_data(request, progresses, ProblemSetProgressSerializer)

        # 添加统计数据
        data["statistics"] = {
            "total": total_count,
            "completed": completed_count,
            "avg_progress": round(avg_progress, 2),
        }

        # 返回题单的所有题目
        data["problems"] = all_problems_list

        return self.success(data)
