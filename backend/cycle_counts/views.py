from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.core import signing
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .access import (
    counter_code_digest,
    create_counter_session,
    read_counter_session,
    verify_counter_code,
    verify_counter_digest,
)
from .calculations import calculate_final_count
from .authentication import IsAdministrator, LoginThrottle
from .models import (
    CounterAccount,
    CounterCountLog,
    CycleCount,
    CycleCountAssignment,
    CycleCountDetail,
    InventoryMaster,
)
from .serializers import (
    ActivityLogFilterSerializer,
    ActualCountUpdateSerializer,
    CounterAccessSerializer,
    CounterAccountSerializer,
    CounterCountLogSerializer,
    CycleCountDetailSerializer,
    CycleCountFilterSerializer,
    CycleCountSerializer,
)


COUNTER_CYCLE_COUNT_TYPE = "D"
COUNTER_CYCLE_COUNT_STATUS_ID = 0
COUNTER_LOCK_TIMEOUT = timedelta(seconds=10)


# Join details with inventory, descriptions, and the latest count log. Troubleshoot: foreign keys, item_code, and annotation fields.
def cycle_count_detail_queryset():
    inventory_description = InventoryMaster.objects.filter(
        item_code=OuterRef("active_inventory__item_number")
    ).values("description")[:1]
    inventory_packaging = InventoryMaster.objects.filter(
        item_code=OuterRef("active_inventory__item_number")
    ).values("packaging")[:1]
    inventory_units_per_pack = InventoryMaster.objects.filter(
        item_code=OuterRef("active_inventory__item_number")
    ).values("units_per_pack")[:1]
    latest_count = CounterCountLog.objects.filter(
        cycle_count_detail_id=OuterRef("pk")
    ).order_by("-counted_at", "-id")
    return (
        CycleCountDetail.objects
        .select_related("cycle_count", "active_inventory__bin_location")
        .annotate(
            description=Subquery(inventory_description),
            packaging=Subquery(inventory_packaging),
            units_per_pack=Subquery(inventory_units_per_pack),
            last_counted_by=Subquery(latest_count.values("counter__counter_number")[:1]),
            last_counted_at=Subquery(latest_count.values("counted_at")[:1]),
        )
    )


# Validate the counter token and assignment, then update last_seen_at. Troubleshoot: HTTP 403, IDs, active counter status, and lock ownership.
def authorize_counter_request(request, cycle_count_id, token=None):
    token = token or request.headers.get("X-Counter-Session", "")
    if not token:
        raise PermissionDenied("Enter a Counter access code before opening this Cycle Count.")
    try:
        payload = read_counter_session(token)
    except signing.SignatureExpired as error:
        raise PermissionDenied("Counter access expired. Enter the 4-digit code again.") from error
    except signing.BadSignature as error:
        raise PermissionDenied("Invalid Counter access. Enter the 4-digit code again.") from error

    if str(payload.get("cycle_count_id")) != str(cycle_count_id):
        raise PermissionDenied("This Counter access is for a different Cycle Count.")

    try:
        counter = CounterAccount.objects.get(
            pk=payload.get("counter_id"), active=True, role="counter"
        )
    except CounterAccount.DoesNotExist as error:
        raise PermissionDenied("This Counter account is inactive or unavailable.") from error

    assignment = CycleCountAssignment.objects.filter(
        cycle_count_id=cycle_count_id, counter_id=counter.pk
    ).first()
    if assignment is None:
        raise PermissionDenied("This Cycle Count is assigned to a different Counter.")
    assignment.save(update_fields=["last_seen_at"])
    return counter


# Return process health status. Troubleshoot: routing and server availability; this does not check the database connection.
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health_check(_request):
    """Process health only; intentionally does not query the legacy database."""
    return Response({"status": "ok"}, status=status.HTTP_200_OK)


class CycleCountViewSet(viewsets.ReadOnlyModelViewSet):
    """GET-only access to existing cycle count headers and their details."""

    serializer_class = CycleCountSerializer
    http_method_names = ["get", "head", "options"]
    lookup_value_regex = r"\d+"
    permission_classes = [AllowAny]
    authentication_classes = []

    # Fetch headers, progress, and active locks with validated filters. Troubleshoot: query parameters and the ten-second lock timeout.
    def get_queryset(self):
        assignment = CycleCountAssignment.objects.filter(
            cycle_count_id=OuterRef("pk"),
            last_seen_at__gte=timezone.now() - COUNTER_LOCK_TIMEOUT,
        )
        queryset = CycleCount.objects.select_related("warehouse").annotate(
            total_rows=Count("details"),
            counted_rows=Count("details", filter=Q(details__counter_id__isnull=False)),
            assigned_counter_id=Subquery(assignment.values("counter_id")[:1]),
            assigned_counter_name=Subquery(assignment.values("counter__name")[:1]),
            assigned_counter_number=Subquery(assignment.values("counter__counter_number")[:1]),
        )

        # These filters expose only known scalar columns; status meanings are not inferred.
        filter_serializer = CycleCountFilterSerializer(data=self.request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        filters = filter_serializer.validated_data

        if "warehouse_id" in filters:
            queryset = queryset.filter(warehouse_id=filters["warehouse_id"])
        if "status_id" in filters:
            queryset = queryset.filter(status_id=filters["status_id"])
        if "cc_type" in filters:
            queryset = queryset.filter(cc_type=filters["cc_type"])

        return queryset

    # Validate access and return the complete product list. Troubleshoot: token, cycle count ID, and detail serializer.
    @action(detail=True, methods=["get"], url_path="details")
    def details(self, request, pk=None):
        self.get_object()
        authorize_counter_request(request, pk)
        queryset = cycle_count_detail_queryset().filter(cycle_count_id=pk)
        # The counter needs the complete product list before local search and
        # filtering can work. Returning it in one response avoids several
        # sequential page requests for a single Cycle Count.
        serializer = CycleCountDetailSerializer(queryset, many=True)
        return Response(serializer.data)


class CounterAccessView(APIView):
    http_method_names = ["post", "options"]
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginThrottle]

    # Validate the PIN and acquire the count assignment in a transaction. Troubleshoot: HTTP 403 for PIN errors, 409 for busy counters or locks, and type D/status 0 eligibility.
    def post(self, request):
        serializer = CounterAccessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cycle_count_id = serializer.validated_data["cycleCountId"]
        counter_id = serializer.validated_data["counterId"]
        code = serializer.validated_data["accessCode"]

        # Use the keyed digest for the normal fast path. Fall back to the
        # password hash after SECRET_KEY rotation, when the digest is stale.
        counter = CounterAccount.objects.filter(
            pk=counter_id,
            active=True,
            role="counter",
        ).first()
        digest_matches = counter is not None and verify_counter_digest(
            code, counter.code_digest
        )
        password_matches = (
            counter is not None
            and not digest_matches
            and verify_counter_code(code, counter.code_hash)
        )
        if counter is None or not (digest_matches or password_matches):
            return Response(
                {"detail": "Invalid or inactive 4-digit Counter access code."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Refresh the keyed digest when the password-hash fallback confirms a
        # valid PIN after SECRET_KEY rotation.
        current_digest = counter_code_digest(code)
        if counter.code_digest != current_digest:
            CounterAccount.objects.filter(pk=counter.pk).update(code_digest=current_digest)
            counter.code_digest = current_digest

        with transaction.atomic():
            # Serialize access attempts made with the same Counter account.
            counter = CounterAccount.objects.select_for_update().get(pk=counter.pk)
            active_elsewhere = CycleCountAssignment.objects.filter(
                counter=counter,
                last_seen_at__gte=timezone.now() - COUNTER_LOCK_TIMEOUT,
            ).exclude(cycle_count_id=cycle_count_id).exists()
            if active_elsewhere:
                return Response(
                    {"detail": "This Counter is already active in another Cycle Count."},
                    status=status.HTTP_409_CONFLICT,
                )
            cycle_count = get_object_or_404(
                CycleCount.objects.select_for_update(),
                pk=cycle_count_id,
                cc_type__iexact=COUNTER_CYCLE_COUNT_TYPE,
                status_id=COUNTER_CYCLE_COUNT_STATUS_ID,
            )
            assignment = CycleCountAssignment.objects.filter(
                cycle_count_id=cycle_count.id
            ).first()
            lock_is_active = (
                assignment is not None
                and assignment.last_seen_at >= timezone.now() - COUNTER_LOCK_TIMEOUT
            )
            if lock_is_active and assignment.counter_id != counter.id:
                return Response(
                    {"detail": "This Cycle Count is already assigned to another Counter."},
                    status=status.HTTP_409_CONFLICT,
                )
            if assignment is None:
                CycleCountAssignment.objects.create(
                    cycle_count_id=cycle_count.id, counter=counter
                )
            else:
                assignment.counter = counter
                assignment.assigned_at = timezone.now()
                assignment.save(update_fields=["counter", "assigned_at", "last_seen_at"])

        return Response({
            "token": create_counter_session(counter.id, cycle_count.id),
            "counter": {
                "id": counter.id,
                "counterNumber": counter.counter_number,
                "name": counter.name,
            },
            "cycleCountId": cycle_count.id,
            "expiresIn": 12 * 60 * 60,
        })


class CounterChoicesView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [AllowAny]
    authentication_classes = []

    # Return active counters and their active cycle count IDs. Troubleshoot: roles, active flags, and assignment last_seen_at.
    def get(self, request):
        active_assignment = CycleCountAssignment.objects.filter(
            counter_id=OuterRef("pk"),
            last_seen_at__gte=timezone.now() - COUNTER_LOCK_TIMEOUT,
        )
        counters = (
            CounterAccount.objects.filter(active=True, role="counter")
            .annotate(
                active_cycle_count_id=Subquery(
                    active_assignment.values("cycle_count_id")[:1]
                )
            )
            .order_by("counter_number")
            .values("id", "counter_number", "name", "active_cycle_count_id")
        )
        return Response([
            {
                "id": counter["id"],
                "counterNumber": counter["counter_number"],
                "name": counter["name"],
                "activeCycleCountId": counter["active_cycle_count_id"],
            }
            for counter in counters
        ])


class CycleCountUnlockView(APIView):
    """Release the current Counter's lock when leaving the counting screen."""

    http_method_names = ["post", "options"]
    permission_classes = [AllowAny]
    authentication_classes = []

    # Remove the authorized counter's assignment. Troubleshoot: header/body token, ownership, and /unlock/ response.
    def post(self, request, pk):
        body_token = request.data.get("counterSession", "")
        if not isinstance(body_token, str):
            body_token = ""
        counter = authorize_counter_request(request, pk, token=body_token)
        with transaction.atomic():
            assignment = get_object_or_404(
                CycleCountAssignment.objects.select_for_update(),
                cycle_count_id=pk,
                counter_id=counter.pk,
            )
            assignment.delete()
        return Response({"detail": "Cycle Count lock released."})


class CycleCountHeartbeatView(APIView):
    """Keep an occupied Cycle Count locked while its counting page is active."""

    http_method_names = ["post", "options"]
    permission_classes = [AllowAny]
    authentication_classes = []

    # Refresh the lock timestamp through authorization. Troubleshoot: counter token and last_seen_at.
    def post(self, request, pk):
        authorize_counter_request(request, pk)
        return Response({"detail": "Cycle Count lock active."})


class CounterAccountViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdministrator]
    queryset = CounterAccount.objects.all()
    serializer_class = CounterAccountSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    # Prevent deletion of the current account or accounts with count logs. Troubleshoot: HTTP 409 and count_logs.
    def destroy(self, request, *args, **kwargs):
        counter = self.get_object()
        if counter.pk == request.user.pk:
            return Response({"detail": "You cannot delete your own account."}, status=status.HTTP_409_CONFLICT)
        if counter.count_logs.exists():
            return Response(
                {"detail": "This Counter has count history and cannot be deleted. Deactivate it instead."},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)


class CounterCountLogViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdministrator]
    serializer_class = CounterCountLogSerializer
    http_method_names = ["get", "head", "options"]

    # Fetch audit logs with counter data and old quantity. Troubleshoot: cycle_count_id filter and detail reference.
    def get_queryset(self):
        old_count = CycleCountDetail.objects.filter(
            pk=OuterRef("cycle_count_detail_id")
        ).values("old_qty")[:1]
        queryset = (
            CounterCountLog.objects
            .select_related("counter")
            .annotate(old_count=Subquery(old_count))
        )
        cycle_count_id = self.request.query_params.get("cycle_count_id")
        if cycle_count_id:
            queryset = queryset.filter(cycle_count_id=cycle_count_id)
        # Apply an inclusive date range to both the on-screen report and CSV source data.
        filter_serializer = ActivityLogFilterSerializer(data=self.request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        filters = filter_serializer.validated_data
        if filters.get("date_from"):
            queryset = queryset.filter(counted_at__date__gte=filters["date_from"])
            queryset = queryset.filter(counted_at__date__lte=filters["date_to"])
        return queryset


class ActualCountUpdateView(APIView):
    """Update only the verified legacy Final Count CS/PC fields."""

    http_method_names = ["patch", "options"]
    permission_classes = [AllowAny]
    authentication_classes = []

    # Save final counts, counter attribution, and the audit log in one transaction. Troubleshoot: input serializer, token, Qty/Case, old_qty, and rollback errors.
    def patch(self, request, pk):
        input_serializer = ActualCountUpdateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            detail = get_object_or_404(
                CycleCountDetail.objects
                .select_for_update()
                .select_related("cycle_count", "active_inventory__bin_location"),
                pk=pk,
            )

            counter = authorize_counter_request(request, detail.cycle_count_id)

            if (
                (detail.cycle_count.cc_type or "").upper() != COUNTER_CYCLE_COUNT_TYPE
                or detail.cycle_count.status_id != COUNTER_CYCLE_COUNT_STATUS_ID
            ):
                return Response(
                    {"detail": "Only Cycle Counts with CC Type D and status ID 0 can be edited."},
                    status=status.HTTP_409_CONFLICT,
                )
            if detail.active_inventory is None or detail.active_inventory.qty_case is None:
                return Response(
                    {"detail": "Qty/Case is unavailable for this inventory record."},
                    status=status.HTTP_409_CONFLICT,
                )
            if detail.old_qty is None:
                return Response(
                    {"detail": "Old Count is unavailable for this detail record."},
                    status=status.HTTP_409_CONFLICT,
                )

            actual_cs = input_serializer.validated_data["actualCs"]
            actual_pc = input_serializer.validated_data["actualPc"]
            try:
                total, variance = calculate_final_count(
                    actual_cs,
                    actual_pc,
                    detail.active_inventory.qty_case,
                    detail.old_qty,
                )
            except ValueError as error:
                return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

            detail.fin_count_c = actual_cs
            detail.fin_count_pc = actual_pc
            detail.fin_count_total = total
            detail.fin_count_variance = variance
            detail.counter_id = counter.pk
            detail.updated_at = timezone.now()
            update_fields = [
                "fin_count_c",
                "fin_count_pc",
                "fin_count_total",
                "fin_count_variance",
                "counter_id",
                "updated_at",
            ]

            # Map API names only to server-owned model fields. Troubleshoot: the frontend must never send *_from.
            metadata_fields = {
                "productionDate": ("production_date", "production_date_from"),
                "expiryDate": ("expiry_date", "expiry_date_from"),
                "lotNo": ("lot_no", "lot_no_from"),
            }
            # Keep event-specific old values for the immutable activity report.
            # A null entry means that metadata field did not change during this save.
            changed_metadata = {}
            # Compare against the row selected with select_for_update(), ensuring the old value comes from the database.
            for input_name, (current_field, previous_field) in metadata_fields.items():
                # Omitted metadata remains untouched for older clients and count-only saves.
                if input_name not in input_serializer.validated_data:
                    continue
                new_value = input_serializer.validated_data[input_name]
                old_value = getattr(detail, current_field)
                # Preserve the immediate previous value only for a real change, including value-to-null changes.
                if new_value != old_value:
                    changed_metadata[current_field] = old_value
                    setattr(detail, previous_field, old_value)
                    setattr(detail, current_field, new_value)
                    update_fields.extend([previous_field, current_field])

            # update_fields contains only changed metadata pairs plus the existing final-count fields.
            detail.save(update_fields=update_fields)

            description = InventoryMaster.objects.filter(
                item_code=detail.active_inventory.item_number
            ).values_list("description", flat=True).first()
            CounterCountLog.objects.create(
                counter=counter,
                cycle_count_id=detail.cycle_count_id,
                cycle_count_code=detail.cycle_count.code,
                cycle_count_detail_id=detail.id,
                active_inventory_id=detail.active_inventory_id,
                description=description,
                location=(
                    detail.active_inventory.bin_location.name
                    if detail.active_inventory.bin_location_id
                    else None
                ),
                lot_no=detail.lot_no,
                lot_no_from=changed_metadata.get("lot_no"),
                lot_no_changed="lot_no" in changed_metadata,
                production_date=detail.production_date,
                production_date_from=changed_metadata.get("production_date"),
                production_date_changed="production_date" in changed_metadata,
                expiry_date=detail.expiry_date,
                expiry_date_from=changed_metadata.get("expiry_date"),
                expiry_date_changed="expiry_date" in changed_metadata,
                count_stage="final",
                actual_cs=actual_cs,
                actual_pc=actual_pc,
                actual_total=total,
                variance=variance,
            )

        refreshed_detail = get_object_or_404(cycle_count_detail_queryset(), pk=pk)
        return Response(CycleCountDetailSerializer(refreshed_detail).data)
