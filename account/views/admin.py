import re

from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils.crypto import get_random_string

from submission.models import Submission
from utils.api import APIError, APIView, validate_serializer
from utils.shortcuts import CLASS_NAME_MAX_DIGITS, CLASS_NAME_MIN_DIGITS, is_valid_class_name, rand_str

from ..decorators import super_admin_required
from ..models import AdminType, ProblemPermission, User, UserProfile
from ..serializers import (
    EditUserSerializer,
    ImportUserSerializer,
    UserAdminSerializer,
)


# ks251XXX 或者 ks2510XX 返回 251 或者 2510。
# 不以 ks+数字 开头的（管理员、教师账号）返回 None。
# 位数不对就直接报错，不猜——猜错会把 class_name 存歪，
# 而剥前缀显示姓名、班级下拉、统计页都依赖它准确。
# 这里先用 \d+ 抓全再判位数，不能直接用 CLASS_NAME_RE 匹配：
# 那样 ks251001 会"匹配成功"并悄悄取前 4 位，正是要避免的猜测。
def get_class_name(username):
    result = re.match(r"ks(\d+)", username)
    if not result:
        return None
    class_name = result.group(1)
    if not is_valid_class_name(class_name):
        raise APIError(f"用户名 {username} 的班级号 {class_name} 是 {len(class_name)} 位，必须是 {CLASS_NAME_MIN_DIGITS}~{CLASS_NAME_MAX_DIGITS} 位数字")
    return class_name


class UserAdminAPI(APIView):
    @validate_serializer(ImportUserSerializer)
    @super_admin_required
    def post(self, request):
        """
        Import User
        """
        data = request.data["users"]

        user_list = []
        for user_data in data:
            if len(user_data) != 4 or len(user_data[0]) > 32:
                return self.error(f"Error occurred while processing data '{user_data}'")
            user_list.append(
                User(
                    username=user_data[0],
                    password=make_password(user_data[1]),
                    email=user_data[2],
                    raw_password=user_data[1],
                    class_name=get_class_name(user_data[0]),
                )
            )

        try:
            with transaction.atomic():
                ret = User.objects.bulk_create(user_list)
                UserProfile.objects.bulk_create([UserProfile(user=ret[i], real_name=data[i][3]) for i in range(len(ret))])
            return self.success()
        except IntegrityError as e:
            # Extract detail from exception message
            #    duplicate key value violates unique constraint "user_username_key"
            #    DETAIL:  Key (username)=(root11) already exists.
            return self.error(str(e).split("\n")[1])

    @validate_serializer(EditUserSerializer)
    @super_admin_required
    def put(self, request):
        """
        Edit user api
        """
        data = request.data
        try:
            user = User.objects.get(id=data["id"])
        except User.DoesNotExist:
            return self.error("User does not exist")
        if User.objects.filter(username=data["username"].lower()).exclude(id=user.id).exists():
            return self.error("Username already exists")
        if User.objects.filter(email=data["email"].lower()).exclude(id=user.id).exists():
            return self.error("Email already exists")

        pre_username = user.username
        user.username = data["username"].lower()
        user.class_name = get_class_name(data["username"])
        user.email = data["email"].lower()
        user.admin_type = data["admin_type"]
        user.is_disabled = data["is_disabled"]

        if data["admin_type"] == AdminType.STUDENT_ADMIN:
            user.problem_permission = data["problem_permission"] or ProblemPermission.OWN
        elif data["admin_type"] == AdminType.TEACHER_ADMIN:
            user.problem_permission = data["problem_permission"] or ProblemPermission.OWN
        elif data["admin_type"] == AdminType.SUPER_ADMIN:
            user.problem_permission = ProblemPermission.ALL
        else:
            user.problem_permission = ProblemPermission.NONE

        if data["password"]:
            user.set_password(data["password"])

        if data["open_api"]:
            # Avoid reset user appkey after saving changes
            if not user.open_api:
                user.open_api_appkey = rand_str()
        else:
            user.open_api_appkey = None
        user.open_api = data["open_api"]

        user.save()
        if pre_username != user.username:
            Submission.objects.filter(username=pre_username).update(username=user.username)

        UserProfile.objects.filter(user=user).update(real_name=data["real_name"])
        return self.success(UserAdminSerializer(user).data)

    @super_admin_required
    def get(self, request):
        """
        User list api / Get user by id
        """
        user_id = request.GET.get("id")
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return self.error("User does not exist")
            return self.success(UserAdminSerializer(user).data)

        # 获取排序参数
        order_by = request.GET.get("order_by", "")

        # 根据排序参数设置排序规则
        if order_by == "-last_login":
            # 最近登录，将 None 值放在最后
            user = User.objects.all().order_by(F("last_login").desc(nulls_last=True))
        else:
            # 默认按创建时间倒序
            user = User.objects.all().order_by("-create_time")

        type = request.GET.get("type", "")

        if type:
            user = user.filter(admin_type=type)

        keyword = request.GET.get("keyword", None)
        if keyword:
            user = user.filter(Q(username__icontains=keyword) | Q(userprofile__real_name__icontains=keyword) | Q(email__icontains=keyword))
        return self.success(self.paginate_data(request, user, UserAdminSerializer))

    @super_admin_required
    def delete(self, request):
        id = request.GET.get("id")
        if not id:
            return self.error("Invalid Parameter, id is required")
        ids = id.split(",")
        if str(request.user.id) in ids:
            return self.error("Current user can not be deleted")
        User.objects.filter(id__in=ids).delete()
        return self.success()


class ResetUserPasswordAPI(APIView):
    @super_admin_required
    def post(self, request):
        """
        重置用户密码为随机6位数字(不包括0)
        """
        data = request.data
        user_id = data["id"]

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return self.error("User does not exist")

        # 生成6位随机数字密码(不包括0)
        new_password = get_random_string(6, allowed_chars="123456789")

        # 设置新密码
        user.set_password(new_password)
        user.save()

        return self.success(new_password)
