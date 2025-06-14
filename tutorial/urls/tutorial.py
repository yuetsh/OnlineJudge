from django.urls import path, include
from rest_framework.routers import DefaultRouter
from ..views.tutorial import TutorialViewSet

router = DefaultRouter()
router.register(r'tutorials', TutorialViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 