from utils.api import APIView

from announcement.models import Announcement
from announcement.serializers import (AnnouncementSerializer, 
                                      AnnouncementListSerializer)


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
