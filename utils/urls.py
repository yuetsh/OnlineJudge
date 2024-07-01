from django.urls import path

from .views import SimditorImageUploadAPIView, SimditorFileUploadAPIView

urlpatterns = [
    path("upload_image", SimditorImageUploadAPIView.as_view()),
    path("upload_file", SimditorFileUploadAPIView.as_view()),
]
