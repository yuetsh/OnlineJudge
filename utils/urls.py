from django.urls import path

from .views import SimditorImageUploadAPIView

urlpatterns = [
    path("upload_image", SimditorImageUploadAPIView.as_view()),
]
