from account.decorators import login_required, super_admin_required
from account.models import User
from message.models import Message
from message.serializers import CreateMessageSerializer, MessageSerializer
from submission.models import Submission
from utils.api import AsyncAPIView
from utils.api.api import validate_serializer


class MessageAPI(AsyncAPIView):
    @login_required
    async def get(self, request):
        messages = Message.objects.select_related(
            "recipient", "sender", "submission", "submission__problem"
        ).filter(recipient=request.user)
        return self.success(await self.async_paginate_data(request, messages, MessageSerializer))

    @super_admin_required
    @validate_serializer(CreateMessageSerializer)
    async def post(self, request):
        data = request.data
        if data["recipient"] == request.user.id:
            return self.error("Can not send a message to youself")
        try:
            recipient = await User.objects.aget(id=data["recipient"], is_disabled=False)
        except User.DoesNotExist:
            return self.error("User does not exist")
        try:
            submission = await Submission.objects.aget(id=data["submission"])
        except Submission.DoesNotExist:
            return self.error("Submission does not exist")
        await Message.objects.acreate(
            submission=submission,
            message=data["message"],
            sender=request.user,
            recipient=recipient,
        )
        return self.success()
