from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from .views import UploadFileView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),

    path('uploads/<path:file_path>', UploadFileView.as_view(), name='serve_uploads'),
]

