from django.urls import path, include
from rest_framework.routers import DefaultRouter
from ..views.admin import AdminTutorialViewSet

router = DefaultRouter()
router.register(r'tutorials', AdminTutorialViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 