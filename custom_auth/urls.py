from django.contrib.auth import views as original_auth_views 
from django.urls import path
from django.conf import settings

from custom_auth import views as custom_auth_views



urlpatterns = [
    path('login/', original_auth_views.LoginView.as_view(extra_context={'reset_enabled': settings.EMAIL_ENABLED}), name='login'),
    path('logout/', original_auth_views.LogoutView.as_view(), name='logout'),

    path('password_change/', original_auth_views.PasswordChangeView.as_view(), name='password_change'),
    path('password_change/done/', original_auth_views.PasswordChangeDoneView.as_view(), name='password_change_done'),
]
if settings.EMAIL_ENABLED:
    urlpatterns.extend(
    [
        path('password_reset/', custom_auth_views.CustomPasswordResetView.as_view(), name='password_reset'),
        path('password_reset/done/', original_auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
        path('reset/<uidb64>/<token>/', original_auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
        path('reset/done/', original_auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
    ]
    )
