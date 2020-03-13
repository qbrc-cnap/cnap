import uuid
from django.db import models
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from helpers import storage_utils
from base.models import CurrentZone


class CustomUserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        """
        Create and save a user with the given email, and password.
        """
        if not email:
            raise ValueError('Email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password=password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """
    Custom model
    """
    email = models.EmailField(_('email address'), unique=True, null=False, max_length=100)
    user_uuid = models.UUIDField(primary_key=False, default=uuid.uuid4, editable=True)
    is_staff = models.BooleanField(
        _('staff status'),
        default=False,
        help_text=_('Designates whether the user can log into this admin site.'),
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_(
            'Designates whether this user should be treated as active. '
            'Unselect this instead of deleting accounts.'
        ),
    )
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')

    def clean(self):
        super().clean()
        print('in clean....')
        print('x'*200)
        self.email = self.__class__.objects.normalize_email(self.email)

    def get_full_name(self):
        """
        Return the first_name plus the last_name, with a space in between.
        """
        return self.email

    def get_short_name(self):
        """Return the short name for the user."""
        return self.email

    def email_user(self, subject, message, from_email=None, **kwargs):
        """Send an email to this user."""
        pass


@receiver(post_save, sender=CustomUser)
def user_saved(sender, instance, **kwargs):
    '''
    Actions to take when any user is saved.
    '''
    user_instance = instance
    bucketname_with_prefix = '%s-%s' % (settings.CONFIG_PARAMS['storage_bucket_prefix'], str(user_instance.user_uuid))
    bucketname = bucketname_with_prefix[len(settings.CONFIG_PARAMS['google_storage_gs_prefix']):]
    current_zone = CurrentZone.objects.all()[0] # something like "us-east1-c"
    current_region = '-'.join(current_zone.zone.zone.split('-')[:2])
    storage_utils.create_regional_bucket(bucketname, current_region)
