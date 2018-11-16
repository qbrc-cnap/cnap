from django.contrib.auth.views import PasswordResetView

from custom_auth.forms import CustomPasswordResetForm

class CustomPasswordResetView(PasswordResetView): 
    form_class = CustomPasswordResetForm
    html_email_template_name = 'registration/password_reset_email.html'
