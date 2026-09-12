from django.urls import include, path
from rest_framework.routers import DefaultRouter
from cycle_counts.staff_views import StaffLoginView, StaffLogoutView, StaffMeView

from cycle_counts.views import (
    ActualCountUpdateView,
    CounterAccessView,
    CounterAccountViewSet,
    CounterChoicesView,
    CounterCountLogViewSet,
    CycleCountUnlockView,
    CycleCountHeartbeatView,
    CycleCountViewSet,
    health_check,
)


# API router; changing this file also lets Django's development server reload routes.
router = DefaultRouter()
router.register("cycle-counts", CycleCountViewSet, basename="cycle-count")
router.register("counter-accounts", CounterAccountViewSet, basename="counter-account")
router.register("counter-count-logs", CounterCountLogViewSet, basename="counter-count-log")

urlpatterns = [
    path("api/auth/login/", StaffLoginView.as_view(), name="staff-login"),
    path("api/auth/me/", StaffMeView.as_view(), name="staff-me"),
    path("api/auth/logout/", StaffLogoutView.as_view(), name="staff-logout"),
    path("api/health/", health_check, name="health-check"),
    path("api/counter-access/verify/", CounterAccessView.as_view(), name="counter-access-verify"),
    path("api/counter-access/counters/", CounterChoicesView.as_view(), name="counter-access-counters"),
    path(
        "api/cycle-counts/<int:pk>/unlock/",
        CycleCountUnlockView.as_view(),
        name="cycle-count-unlock",
    ),
    path(
        "api/cycle-counts/<int:pk>/heartbeat/",
        CycleCountHeartbeatView.as_view(),
        name="cycle-count-heartbeat",
    ),
    path(
        "api/cycle-count-details/<int:pk>/actual-count/",
        ActualCountUpdateView.as_view(),
        name="cycle-count-detail-actual-count",
    ),
    path("api/", include(router.urls)),
]
