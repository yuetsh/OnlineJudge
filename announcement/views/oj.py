from announcement.models import Announcement
from announcement.serializers import AnnouncementListSerializer, AnnouncementSerializer
from utils.api import AsyncAPIView


class AnnouncementAPI(AsyncAPIView):
    async def get(self, request):
        id = request.GET.get("id")
        if id:
            try:
                announcement = await Announcement.objects.select_related("created_by").filter(id=id, visible=True).afirst()
                if announcement is None:
                    raise Announcement.DoesNotExist
                return self.success(await self.async_serialize_data(AnnouncementSerializer, announcement))
            except Announcement.DoesNotExist:
                return self.error("Announcement does not exist")

        announcements = Announcement.objects.select_related("created_by").filter(visible=True)
        return self.success(await self.async_paginate_data(request, announcements, AnnouncementListSerializer))
