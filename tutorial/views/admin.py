from rest_framework import viewsets, permissions
from ..models import Tutorial
from ..serializers import TutorialSerializer


class IsSuperAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_super_admin())


class AdminTutorialViewSet(viewsets.ModelViewSet):
    queryset = Tutorial.objects.all()
    serializer_class = TutorialSerializer
    permission_classes = [IsSuperAdminUser]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user) 