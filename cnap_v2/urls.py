from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, re_path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('custom_auth.urls')),
    path('analysis/', include('analysis.urls')),
    re_path(r'^api-auth/', include('rest_framework.urls')),
    re_path(r'^', include('transfer_app.urls')),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
