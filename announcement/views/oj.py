from account.decorators import super_admin_required, login_required
from account.models import User
from submission.models import Submission
from utils.api import APIView

from announcement.models import Announcement, Message
from announcement.serializers import (AnnouncementSerializer, 
                                      AnnouncementListSerializer, 
                                      CreateMessageSerializer, MessageListSerializer, 
                                      MessageSerializer)
from utils.api.api import validate_serializer


class AnnouncementAPI(APIView):
    def get(self, request):
        id = request.GET.get("id")
        if id:
            try:
                announcement = Announcement.objects.get(id=id, visible=True)
                return self.success(AnnouncementSerializer(announcement).data)
            except Announcement.DoesNotExist:
                return self.error("Announcement does not exist")

        announcements = Announcement.objects.filter(visible=True)
        return self.success(self.paginate_data(request, announcements, AnnouncementListSerializer))


class MessageAPI(APIView):
    @login_required
    def get(self, request):
        message_id = request.GET.get("id")
        if message_id:
            try:
                message = Message.objects.filter(id=message_id, recipient=request.user)
                return self.success(MessageSerializer(message).data)
            except Message.DoesNotExist:
                return self.error("Message does not exist")
        else:
            messages = Message.objects.filter(recipient=request.user)
            return self.success(self.paginate_data(request, messages, MessageListSerializer))         
    
    @validate_serializer(CreateMessageSerializer)
    @super_admin_required
    def post(self, request):
        data = request.data
        try:
            recipient = User.objects.get(id=data["recipient"], is_disabled=False)
        except User.DoesNotExist:
            return self.error("User does not exist")
        try:
            submission = Submission.objects.get(id=data["submission"])
        except Submission.DoesNotExist:
            return self.error("Submission does not exist")
        Message.objects.create(submission=submission,
                               message=data["message"],
                               sender=request.user,
                               recipient=recipient)
        return self.success()
