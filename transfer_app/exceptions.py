from rest_framework import status
from rest_framework.exceptions import APIException, _get_error_details
from django.utils.translation import ugettext_lazy as _

class RequestError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('Invalid input.')
    default_code = 'invalid'

    def __init__(self, detail=None):
        if detail is None:
            detail = self.default_detail
        code = self.default_code

        # For failures, we may collect many errors together,
        # so the details should always be coerced to a list if not already.
        if not isinstance(detail, dict) and not isinstance(detail, list):
            detail = [detail]

        self.detail = _get_error_details(detail, code)


class ExceptionWithMessage(Exception):
    def __init__(self, message):
        self.message = message

class FilenameException(ExceptionWithMessage):
    pass


