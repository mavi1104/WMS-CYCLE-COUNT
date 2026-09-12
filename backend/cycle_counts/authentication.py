from django.core import signing
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework.throttling import AnonRateThrottle

from .models import CounterAccount


STAFF_SESSION_SALT = "wms-staff-session-v1"
STAFF_SESSION_MAX_AGE = 12 * 60 * 60


# Sign a staff token containing the account ID and session version. Troubleshoot: session_version and signing settings.
def create_staff_session(account):
    return signing.dumps(
        {"id": account.pk, "version": str(account.session_version)},
        salt=STAFF_SESSION_SALT,
    )


class StaffAuthentication(BaseAuthentication):
    # Validate the Bearer token, active administrator, and session version. Troubleshoot: HTTP 401, token expiry, and account changes.
    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header:
            return None
        if len(header) != 2 or header[0].lower() != b"bearer":
            raise AuthenticationFailed("Invalid authentication header.")
        try:
            payload = signing.loads(
                header[1].decode("ascii"), salt=STAFF_SESSION_SALT,
                max_age=STAFF_SESSION_MAX_AGE,
            )
            account = CounterAccount.objects.get(
                pk=payload["id"], active=True,
                role=CounterAccount.Role.ADMIN,
            )
            if str(account.session_version) != payload["version"]:
                raise AuthenticationFailed("Session ended. Sign in again.")
        except (signing.BadSignature, UnicodeError, KeyError, TypeError, ValueError,
                CounterAccount.DoesNotExist) as error:
            raise AuthenticationFailed("Session expired or invalid. Sign in again.") from error
        return account, None

    # Return a Bearer challenge for authentication errors. Troubleshoot: WWW-Authenticate header.
    def authenticate_header(self, request):
        return "Bearer"


class IsAdministrator(BasePermission):
    # Allow only active administrators. Troubleshoot: request.user, active flag, and role when access is denied.
    def has_permission(self, request, view):
        return bool(request.user and request.user.active and request.user.role == "admin")


class LoginThrottle(AnonRateThrottle):
    scope = "staff_login"
    rate = "10/min"
