import secrets
import uuid

from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from rest_framework import serializers

from .access import counter_code_digest, hash_counter_code
from .models import CounterAccount, CounterCountLog, CycleCount, CycleCountDetail


class CycleCountFilterSerializer(serializers.Serializer):
    warehouse_id = serializers.IntegerField(required=False)
    status_id = serializers.IntegerField(required=False)
    cc_type = serializers.CharField(required=False, max_length=255)


class ActivityLogFilterSerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    # Reject incomplete or reversed report periods before building the audit query.
    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")
        if bool(date_from) != bool(date_to):
            raise serializers.ValidationError("Enter both From and To dates.")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError("From date cannot be later than To date.")
        return attrs


class ActualCountUpdateSerializer(serializers.Serializer):
    # Validate current count and metadata values only; previous-value fields are intentionally excluded.
    actualCs = serializers.IntegerField(min_value=0, max_value=9999999999999999)
    actualPc = serializers.IntegerField(min_value=0, max_value=9999999999999999)
    # Metadata is optional for backward compatibility; null clears the corresponding database value.
    productionDate = serializers.DateField(required=False, allow_null=True)
    expiryDate = serializers.DateField(required=False, allow_null=True)
    lotNo = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=4000)


class CounterAccessSerializer(serializers.Serializer):
    cycleCountId = serializers.IntegerField(min_value=1)
    counterId = serializers.IntegerField(min_value=1)
    accessCode = serializers.RegexField(
        regex=r"^[0-9]{4}\Z",
        write_only=True,
        error_messages={"invalid": "Enter a valid 4-digit access code."},
    )


class CounterAccountSerializer(serializers.ModelSerializer):
    counterNumber = serializers.IntegerField(
        source="counter_number",
        min_value=1,
        required=False,
    )
    accessCode = serializers.RegexField(
        regex=r"^[0-9]{4}\Z",
        write_only=True,
        required=False,
        error_messages={"invalid": "Access code must contain exactly 4 digits."},
    )
    username = serializers.RegexField(regex=r"^[a-zA-Z0-9._-]+\Z", max_length=150, required=False, allow_null=True)
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False, max_length=128)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = CounterAccount
        fields = ["id", "counterNumber", "name", "active", "role", "username", "password", "accessCode", "createdAt", "updatedAt"]

    # Validate role-specific credentials and prevent self-deactivation. Troubleshoot: role, accessCode, username/password, and serializer errors.
    def validate(self, attrs):
        role = attrs.get("role", self.instance.role if self.instance else "counter")
        if self.instance and role != self.instance.role:
            raise serializers.ValidationError({"role": "Create a separate account to assign a different role."})
        if role == "counter":
            if attrs.get("username") or "password" in attrs:
                raise serializers.ValidationError("Counter accounts use a four-digit access code.")
            if self.instance is None and not attrs.get("accessCode"):
                raise serializers.ValidationError({"accessCode": "A 4-digit access code is required."})
        else:
            if "accessCode" in attrs:
                raise serializers.ValidationError({"accessCode": "Staff accounts use a password."})
            if not attrs.get("username", self.instance.username if self.instance else None):
                raise serializers.ValidationError({"username": "Username is required."})
            if self.instance is None and not attrs.get("password"):
                raise serializers.ValidationError({"password": "Password is required."})
        request = self.context.get("request")
        if (self.instance and request and request.user.pk == self.instance.pk
                and attrs.get("active") is False):
            raise serializers.ValidationError({"active": "You cannot deactivate your own account."})
        return attrs

    # Lowercase the username and reject duplicates. Troubleshoot: existing accounts and exclusion of the account being edited.
    def validate_username(self, value):
        if value is None:
            return None
        value = value.lower()
        duplicate = CounterAccount.objects.filter(username=value)
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError("This username is already assigned.")
        return value

    # Trim surrounding whitespace and reject blank names.
    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Counter name is required.")
        return value

    # Reject duplicate counter numbers. Troubleshoot: counter_number and the account currently being edited.
    def validate_counterNumber(self, value):
        duplicate = CounterAccount.objects.filter(counter_number=value)
        if self.instance is not None:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError(f"Counter {value} is already assigned.")
        return value

    # Check for duplicate PIN digests and set the digest/hash. Troubleshoot: accessCode validation and code_digest uniqueness.
    def _set_code(self, instance, code):
        digest = counter_code_digest(code)
        duplicate = CounterAccount.objects.filter(code_digest=digest).exclude(pk=instance.pk).exists()
        if duplicate:
            raise serializers.ValidationError({"accessCode": "This access code is already assigned."})
        instance.code_digest = digest
        instance.code_hash = hash_counter_code(code)

    # Create the account, number, and credential hashes in a transaction. Troubleshoot: unique constraints and serializer errors.
    def create(self, validated_data):
        code = validated_data.pop("accessCode", None)
        password = validated_data.pop("password", None)
        try:
            with transaction.atomic():
                requested_number = validated_data.pop("counter_number", None)
                if requested_number is None:
                    last_counter = CounterAccount.objects.select_for_update().order_by("-counter_number").first()
                    requested_number = (last_counter.counter_number if last_counter else 0) + 1
                instance = CounterAccount(counter_number=requested_number, **validated_data)
                if code:
                    self._set_code(instance, code)
                else:
                    # Unique internal placeholder; staff have no usable counter PIN.
                    instance.code_digest = secrets.token_hex(32)
                    instance.code_hash = make_password(None)
                instance.password_hash = make_password(password)
                instance.save()
            return instance
        except IntegrityError as error:
            raise serializers.ValidationError("Account number, username or access code is already assigned. Refresh and try again.") from error

    # Update the account and revoke staff sessions when credentials or active status change. Troubleshoot: session_version and unique constraints.
    def update(self, instance, validated_data):
        code = validated_data.pop("accessCode", None)
        password = validated_data.pop("password", None)
        try:
            with transaction.atomic():
                instance = CounterAccount.objects.select_for_update().get(pk=instance.pk)
                credentials_changed = password is not None or any(
                    field in validated_data and validated_data[field] != getattr(instance, field)
                    for field in ("active", "username")
                )
                for field, value in validated_data.items():
                    setattr(instance, field, value)
                if code:
                    self._set_code(instance, code)
                if password is not None:
                    instance.password_hash = make_password(password)
                if credentials_changed:
                    instance.session_version = uuid.uuid4()
                instance.save()
            return instance
        except IntegrityError as error:
            raise serializers.ValidationError("Account number, username or access code is already assigned.") from error


class CounterCountLogSerializer(serializers.ModelSerializer):
    counterId = serializers.IntegerField(source="counter_id", read_only=True)
    counterNumber = serializers.IntegerField(source="counter.counter_number", read_only=True)
    counterName = serializers.CharField(source="counter.name", read_only=True)
    cycleCountId = serializers.IntegerField(source="cycle_count_id", read_only=True)
    cycleCountCode = serializers.CharField(source="cycle_count_code", read_only=True)
    detailId = serializers.IntegerField(source="cycle_count_detail_id", read_only=True)
    activeInventoryId = serializers.IntegerField(source="active_inventory_id", read_only=True)
    lotNo = serializers.CharField(source="lot_no", read_only=True)
    lotNoFrom = serializers.CharField(source="lot_no_from", read_only=True)
    lotNoChanged = serializers.BooleanField(source="lot_no_changed", read_only=True)
    productionDate = serializers.DateField(source="production_date", read_only=True)
    productionDateFrom = serializers.DateField(source="production_date_from", read_only=True)
    productionDateChanged = serializers.BooleanField(source="production_date_changed", read_only=True)
    expiryDate = serializers.DateField(source="expiry_date", read_only=True)
    expiryDateFrom = serializers.DateField(source="expiry_date_from", read_only=True)
    expiryDateChanged = serializers.BooleanField(source="expiry_date_changed", read_only=True)
    countStage = serializers.CharField(source="count_stage", read_only=True)
    actualCs = serializers.DecimalField(source="actual_cs", max_digits=18, decimal_places=2, read_only=True)
    actualPc = serializers.DecimalField(source="actual_pc", max_digits=18, decimal_places=2, read_only=True)
    actualTotal = serializers.DecimalField(source="actual_total", max_digits=18, decimal_places=2, read_only=True)
    oldCount = serializers.DecimalField(source="old_count", max_digits=18, decimal_places=2, read_only=True, allow_null=True)
    countedAt = serializers.DateTimeField(source="counted_at", read_only=True)

    class Meta:
        model = CounterCountLog
        fields = [
            "id", "counterId", "counterNumber", "counterName", "cycleCountId", "cycleCountCode",
            "detailId", "activeInventoryId", "description", "location",
            "lotNo", "lotNoFrom", "lotNoChanged",
            "productionDate", "productionDateFrom", "productionDateChanged",
            "expiryDate", "expiryDateFrom", "expiryDateChanged",
            "countStage", "oldCount", "actualCs", "actualPc", "actualTotal", "variance", "countedAt",
        ]
        read_only_fields = fields


class CycleCountSerializer(serializers.ModelSerializer):
    totalRows = serializers.IntegerField(
        source="total_rows",
        read_only=True,
    )
    countedRows = serializers.IntegerField(
        source="counted_rows",
        read_only=True,
    )
    assignedCounterId = serializers.IntegerField(
        source="assigned_counter_id",
        read_only=True,
        allow_null=True,
    )
    assignedCounterName = serializers.CharField(
        source="assigned_counter_name",
        read_only=True,
        allow_null=True,
    )
    assignedCounterNumber = serializers.IntegerField(
        source="assigned_counter_number",
        read_only=True,
        allow_null=True,
    )

    transDate = serializers.DateField(
        source="trans_date",
        allow_null=True,
    )
    warehouseId = serializers.IntegerField(
        source="warehouse_id",
        allow_null=True,
    )
    warehouseCode = serializers.CharField(
        source="warehouse.description",
        allow_null=True,
    )
    location1Id = serializers.IntegerField(
        source="location_1_id",
        allow_null=True,
    )
    location2Id = serializers.IntegerField(
        source="location_2_id",
        allow_null=True,
    )
    statusId = serializers.IntegerField(
        source="status_id",
        allow_null=True,
    )
    createdBy = serializers.CharField(
        source="created_by",
        allow_null=True,
    )
    updatedBy = serializers.CharField(
        source="updated_by",
        allow_null=True,
    )
    createdAt = serializers.DateTimeField(
        source="created_at",
    )
    updatedAt = serializers.DateTimeField(
        source="updated_at",
    )
    ccType = serializers.CharField(
        source="cc_type",
        allow_null=True,
    )

    class Meta:
        model = CycleCount

        fields = [
            "id",
            "code",
            "transDate",
            "warehouseId",
            "warehouseCode",
            "location1Id",
            "location2Id",
            "remarks",
            "statusId",
            "createdBy",
            "updatedBy",
            "createdAt",
            "updatedAt",
            "ccType",
            "totalRows",
            "countedRows",
            "assignedCounterId",
            "assignedCounterName",
            "assignedCounterNumber",
        ]

        read_only_fields = fields


class CycleCountDetailSerializer(serializers.ModelSerializer):
    counterId = serializers.IntegerField(source="counter_id", read_only=True, allow_null=True)
    detailId = serializers.IntegerField(source="id")
    cycleCountId = serializers.IntegerField(source="cycle_count_id")
    activeInventoryId = serializers.IntegerField(source="active_inventory_id", allow_null=True)
    itemNumber = serializers.CharField(source="active_inventory.item_number", allow_null=True)
    location = serializers.CharField(source="active_inventory.bin_location.name", allow_null=True)
    description = serializers.CharField(read_only=True, allow_null=True)
    packaging = serializers.CharField(read_only=True, allow_null=True)
    unitsPerPack = serializers.IntegerField(source="units_per_pack", read_only=True, allow_null=True)
    qtyPerCase = serializers.IntegerField(source="active_inventory.qty_case", allow_null=True)
    productionDate = serializers.DateField(source="production_date", allow_null=True)
    expiryDate = serializers.DateField(source="expiry_date", allow_null=True)
    lotNo = serializers.CharField(source="lot_no", allow_null=True)
    oldQty = serializers.DecimalField(source="old_qty", max_digits=18, decimal_places=2, allow_null=True)

    firstCountCases = serializers.DecimalField(source="fst_count_c", max_digits=18, decimal_places=2, allow_null=True)
    firstCountPieces = serializers.DecimalField(source="fst_count_pc", max_digits=18, decimal_places=2, allow_null=True)
    firstCountTotal = serializers.DecimalField(source="fst_count_total", max_digits=18, decimal_places=2, allow_null=True)
    firstCountVariance = serializers.DecimalField(source="fst_count_variance", max_digits=18, decimal_places=2, allow_null=True)

    secondCountCases = serializers.DecimalField(source="sec_count_c", max_digits=18, decimal_places=2, allow_null=True)
    secondCountPieces = serializers.DecimalField(source="sec_count_pc", max_digits=18, decimal_places=2, allow_null=True)
    secondCountTotal = serializers.DecimalField(source="sec_count_total", max_digits=18, decimal_places=2, allow_null=True)
    secondCountVariance = serializers.DecimalField(source="sec_count_variance", max_digits=18, decimal_places=2, allow_null=True)

    finalCountCases = serializers.DecimalField(source="fin_count_c", max_digits=18, decimal_places=2, allow_null=True)
    finalCountPieces = serializers.DecimalField(source="fin_count_pc", max_digits=18, decimal_places=2, allow_null=True)
    finalCountTotal = serializers.DecimalField(source="fin_count_total", max_digits=18, decimal_places=2, allow_null=True)
    finalCountVariance = serializers.DecimalField(source="fin_count_variance", max_digits=18, decimal_places=2, allow_null=True)

    inventoryStatusId = serializers.IntegerField(source="inventory_status_id", allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at")
    updatedAt = serializers.DateTimeField(source="updated_at")
    lastCountedBy = serializers.CharField(source="last_counted_by", read_only=True, allow_null=True)
    lastCountedAt = serializers.DateTimeField(source="last_counted_at", read_only=True, allow_null=True)

    class Meta:
        model = CycleCountDetail
        fields = [
            "detailId",
            "cycleCountId",
            "activeInventoryId",
            "itemNumber",
            "location",
            "description",
            "packaging",
            "unitsPerPack",
            "qtyPerCase",
            "productionDate",
            "expiryDate",
            "lotNo",
            "oldQty",
            "firstCountCases",
            "firstCountPieces",
            "firstCountTotal",
            "firstCountVariance",
            "secondCountCases",
            "secondCountPieces",
            "secondCountTotal",
            "secondCountVariance",
            "finalCountCases",
            "finalCountPieces",
            "finalCountTotal",
            "finalCountVariance",
            "inventoryStatusId",
            "remarks",
            "createdAt",
            "updatedAt",
            "lastCountedBy",
            "lastCountedAt",
            "counterId",
        ]
        read_only_fields = fields
