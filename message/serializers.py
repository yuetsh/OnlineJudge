from submission.serializers import SubmissionSafeModelSerializer
from utils.api import UsernameSerializer, serializers
from .models import Message



class MessageSerializer(serializers.ModelSerializer):
    sender = UsernameSerializer()
    submission = SubmissionSafeModelSerializer()

    class Meta:
        model = Message
        exclude = ["recipient"]


class CreateMessageSerializer(serializers.Serializer):
    recipient = serializers.IntegerField()
    submission = serializers.CharField()
    message = serializers.CharField()
