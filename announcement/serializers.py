from utils.api import serializers
from utils.api._serializers import UsernameSerializer

from .models import Announcement


class CreateAnnouncementSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=64)
    tag = serializers.CharField()
    content = serializers.CharField(max_length=1024 * 1024 * 8)
    visible = serializers.BooleanField()
    top = serializers.BooleanField()


class AnnouncementSerializer(serializers.ModelSerializer):
    created_by = UsernameSerializer()

    class Meta:
        model = Announcement
        fields = "__all__"


class AnnouncementListSerializer(serializers.ModelSerializer):
    created_by = UsernameSerializer()

    class Meta:
        model = Announcement
        exclude = ['content']


class EditAnnouncementSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField(max_length=64)
    tag = serializers.CharField()
    content = serializers.CharField(max_length=1024 * 1024 * 8)
    visible = serializers.BooleanField()
    top = serializers.BooleanField()
