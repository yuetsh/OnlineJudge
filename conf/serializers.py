from utils.api import serializers
from utils.shortcuts import CLASS_NAME_MAX_DIGITS, CLASS_NAME_MIN_DIGITS, is_valid_class_name

from .models import JudgeServer


class CreateEditWebsiteConfigSerializer(serializers.Serializer):
    website_base_url = serializers.CharField(max_length=128)
    website_name = serializers.CharField(max_length=64)
    website_name_shortcut = serializers.CharField(max_length=64)
    website_footer = serializers.CharField(max_length=1024 * 1024)
    allow_register = serializers.BooleanField()
    submission_list_show_all = serializers.BooleanField()
    class_list = serializers.ListField(child=serializers.CharField(max_length=64))
    enable_maxkb = serializers.BooleanField()

    def validate_class_list(self, value):
        # 班级号要跟用户名里的 ks<班级号> 对得上：登录页拿它查该班学生，
        # 位数不对只会静默查不到人，所以在这里就拦掉。
        for item in value:
            if not is_valid_class_name(item):
                raise serializers.ValidationError(f"班级号 {item} 必须是 {CLASS_NAME_MIN_DIGITS}~{CLASS_NAME_MAX_DIGITS} 位数字")
        return value


class JudgeServerSerializer(serializers.ModelSerializer):
    status = serializers.CharField()

    class Meta:
        model = JudgeServer
        fields = "__all__"


class JudgeServerHeartbeatSerializer(serializers.Serializer):
    hostname = serializers.CharField(max_length=128)
    judger_version = serializers.CharField(max_length=32)
    cpu_core = serializers.IntegerField(min_value=1)
    memory = serializers.FloatField(min_value=0, max_value=100)
    cpu = serializers.FloatField(min_value=0, max_value=100)
    action = serializers.ChoiceField(choices=("heartbeat",))
    service_url = serializers.CharField(max_length=256)


class EditJudgeServerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    is_disabled = serializers.BooleanField()
