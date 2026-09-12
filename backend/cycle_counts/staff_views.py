import uuid

from django.contrib.auth.hashers import check_password, make_password
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import IsAdministrator, LoginThrottle, STAFF_SESSION_MAX_AGE, create_staff_session
from .models import CounterAccount


# Select public staff profile fields for the API. Troubleshoot: id, name, username, and role mapping.
def staff_profile(account):
    return {"id": account.pk, "name": account.name, "username": account.username, "role": account.role}


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(trim_whitespace=False, max_length=128, write_only=True)


class StaffLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginThrottle]
    http_method_names = ["post", "options"]

    # Validate the active administrator and password, then return a session. Troubleshoot: normalized username, password hash, HTTP 401, and login throttle.
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        account = CounterAccount.objects.filter(
            username=data["username"].lower(), active=True, role="admin",
        ).first()
        if account is None:
            make_password(data["password"])
        if account is None or not check_password(data["password"], account.password_hash):
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_401_UNAUTHORIZED)
        response = Response({
            "token": create_staff_session(account), "user": staff_profile(account),
            "expiresIn": STAFF_SESSION_MAX_AGE,
        })
        response["Cache-Control"] = "no-store"
        return response


class StaffMeView(APIView):
    permission_classes = [IsAdministrator]
    http_method_names = ["get", "options"]

    # Return the authenticated staff profile with caching disabled. Troubleshoot: Bearer token and administrator permission.
    def get(self, request):
        response = Response(staff_profile(request.user))
        response["Cache-Control"] = "no-store"
        return response


class StaffLogoutView(APIView):
    permission_classes = [IsAdministrator]
    http_method_names = ["post", "options"]

    # Replace session_version to invalidate all previous staff tokens. Troubleshoot: account updates and stale sessions.
    def post(self, request):
        CounterAccount.objects.filter(pk=request.user.pk).update(session_version=uuid.uuid4())
        return Response({"detail": "Signed out on all devices."})
