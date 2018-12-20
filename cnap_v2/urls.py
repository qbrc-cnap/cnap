from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, re_path, include

import views as base_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('users/', include('custom_auth.user_urls')),
    path('resources/', include('base.urls')),
    path('auth/', include('custom_auth.urls')),
    path('analysis/', include('analysis.urls')),
    re_path(r'^api/$', base_views.api_root),
    re_path(r'^api-auth/', include('rest_framework.urls')),
    path(r'transfers/', include('transfer_app.urls')),
    re_path(r'^$', base_views.index),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
