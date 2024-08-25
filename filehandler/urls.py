from django.urls import path
from .views import FileUploadView, FileTransformView

urlpatterns = [
    path('upload/', FileUploadView.as_view(), name='file-upload'),
    path('transform/', FileTransformView.as_view(), name='file-transform'),
]
