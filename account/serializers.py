from django import forms

from utils.api import UsernameSerializer, serializers

from .models import AdminType, ProblemPermission, User, UserProfile


class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class UsernameOrEmailCheckSerializer(serializers.Serializer):
    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)


class UserRegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=32)
    password = serializers.CharField(min_length=6)
    email = serializers.EmailField(max_length=64)
    captcha = serializers.CharField()


class UserChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(min_length=6)


class UserChangeEmailSerializer(serializers.Serializer):
    password = serializers.CharField()
    new_email = serializers.EmailField(max_length=64)


class GenerateUserSerializer(serializers.Serializer):
    prefix = serializers.CharField(max_length=16, allow_blank=True)
    suffix = serializers.CharField(max_length=16, allow_blank=True)
    number_from = serializers.IntegerField()
    number_to = serializers.IntegerField()
    password_length = serializers.IntegerField(max_value=16, default=8)


class ImportUserSerializer(serializers.Serializer):
    users = serializers.ListField(child=serializers.ListField(child=serializers.CharField(max_length=64)))


class UserAdminSerializer(serializers.ModelSerializer):
    real_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "admin_type",
            "problem_permission",
            "real_name",
            "create_time",
            "last_login",
            "open_api",
            "is_disabled",
            "raw_password",
            "class_name",
        ]

    def get_real_name(self, obj):
        return obj.userprofile.real_name

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.admin_type != AdminType.REGULAR_USER:
            data.pop("raw_password", None)
        return data


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "admin_type",
            "problem_permission",
            "create_time",
            "last_login",
            "open_api",
            "is_disabled",
            "class_name",
        ]


class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    real_name = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        self.show_real_name = kwargs.pop("show_real_name", False)
        super(UserProfileSerializer, self).__init__(*args, **kwargs)

    def get_real_name(self, obj):
        return obj.real_name if self.show_real_name else None


class EditUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField(max_length=32)
    real_name = serializers.CharField(max_length=32, allow_blank=True, allow_null=True)
    password = serializers.CharField(min_length=6, allow_blank=True, required=False, default=None)
    email = serializers.EmailField(max_length=64)
    admin_type = serializers.ChoiceField(choices=AdminType.choices)
    problem_permission = serializers.ChoiceField(choices=ProblemPermission.choices)
    open_api = serializers.BooleanField()
    is_disabled = serializers.BooleanField()
    class_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class EditUserProfileSerializer(serializers.Serializer):
    real_name = serializers.CharField(max_length=32, allow_null=True, required=False)
    avatar = serializers.CharField(max_length=256, allow_blank=True, required=False)
    blog = serializers.URLField(max_length=256, allow_blank=True, required=False)
    mood = serializers.CharField(max_length=256, allow_blank=True, required=False)
    github = serializers.URLField(max_length=256, allow_blank=True, required=False)
    school = serializers.CharField(max_length=64, allow_blank=True, required=False)
    major = serializers.CharField(max_length=64, allow_blank=True, required=False)
    language = serializers.CharField(max_length=32, allow_blank=True, required=False)


class SSOSerializer(serializers.Serializer):
    token = serializers.CharField()


class ImageUploadForm(forms.Form):
    image = forms.FileField()


class FileUploadForm(forms.Form):
    file = forms.FileField()


class RankInfoSerializer(serializers.ModelSerializer):
    user = UsernameSerializer()

    class Meta:
        model = UserProfile
        fields = ["user", "id", "accepted_number", "submission_number", "mood"]
