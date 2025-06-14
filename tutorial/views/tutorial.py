from rest_framework import viewsets, permissions
from ..models import Tutorial
from ..serializers import TutorialSerializer

class TutorialViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tutorial.objects.filter(is_public=True)
    serializer_class = TutorialSerializer
    permission_classes = [permissions.AllowAny] 