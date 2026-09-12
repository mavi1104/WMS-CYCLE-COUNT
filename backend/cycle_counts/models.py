import uuid

from django.db import models


class Warehouse(models.Model):
    id = models.BigIntegerField(primary_key=True)
    description = models.CharField(max_length=4000, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "warehouses"


class BinLocation(models.Model):
    id = models.BigIntegerField(primary_key=True)
    warehouse_id = models.BigIntegerField(null=True, blank=True)
    name = models.CharField(max_length=4000, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "bin_locations"


class ActiveInventory(models.Model):
    id = models.BigIntegerField(primary_key=True)
    warehouse = models.ForeignKey(
        Warehouse,
        db_column="warehouse_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        related_name="active_inventories",
    )
    bin_location = models.ForeignKey(
        BinLocation,
        db_column="bin_location_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        related_name="active_inventories",
    )
    item_number = models.CharField(max_length=4000, null=True, blank=True)
    uom = models.CharField(max_length=4000, null=True, blank=True)
    qty_case = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "active_inventories"


class InventoryMaster(models.Model):
    item_code = models.CharField(db_column="ItemCode", max_length=13, primary_key=True)
    description = models.CharField(db_column="Description", max_length=60)
    item_name = models.CharField(db_column="ItemName", max_length=240)
    # Existing WMS packing description and number of units in one package.
    packaging = models.CharField(db_column="Packaging", max_length=4000, null=True, blank=True)
    units_per_pack = models.IntegerField(db_column="UnitPerPackaging", null=True, blank=True)

    class Meta:
        managed = False
        db_table = "InventoryMaster"


class CycleCount(models.Model):
    id = models.BigIntegerField(primary_key=True)
    code = models.CharField(max_length=4000, null=True, blank=True)
    trans_date = models.DateField(null=True, blank=True)
    warehouse = models.ForeignKey(
        Warehouse,
        db_column="warehouse_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        related_name="cycle_counts",
    )
    location_1_id = models.BigIntegerField(null=True, blank=True)
    location_2_id = models.BigIntegerField(null=True, blank=True)
    remarks = models.CharField(max_length=4000, null=True, blank=True)
    status_id = models.IntegerField(null=True, blank=True)
    created_by = models.CharField(max_length=4000, null=True, blank=True)
    updated_by = models.CharField(max_length=4000, null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    cc_type = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "cycle_counts"
        ordering = ["-trans_date", "-id"]


class CycleCountDetail(models.Model):
    id = models.BigIntegerField(primary_key=True)
    cycle_count = models.ForeignKey(
        CycleCount,
        db_column="cycle_count_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="details",
    )

    active_inventory = models.ForeignKey(
        ActiveInventory,
        db_column="active_inventory_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        related_name="cycle_count_details",
    )

    # Current production date shown in Cycle Count; *_from stores its immediately previous value.
    production_date = models.DateField(null=True, blank=True)
    production_date_from = models.DateField(null=True, blank=True)
    # Current expiration date shown in Cycle Count; update history only when this value changes.
    expiry_date = models.DateField(null=True, blank=True)
    expiry_date_from = models.DateField(null=True, blank=True)
    # Current lot number; lot_no_from is populated by the backend and never trusted from the client.
    lot_no = models.CharField(max_length=4000, null=True, blank=True)
    lot_no_from = models.CharField(max_length=4000, null=True, blank=True)
    old_qty = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    fst_count_c = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    fst_count_pc = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    fst_count_total = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    fst_count_variance = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    sec_count_c = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    sec_count_pc = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    sec_count_total = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    sec_count_variance = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    fin_count_c = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    fin_count_pc = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    fin_count_total = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    fin_count_variance = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    inventory_status_id = models.BigIntegerField(null=True, blank=True)
    remarks = models.CharField(max_length=4000, null=True, blank=True)
    # Last successful mobile save; historical edits remain in CounterCountLog.
    counter_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "cycle_count_details"
        ordering = ["id"]


class CounterAccount(models.Model):
    """Shared WMS identity; existing counter IDs and audit relationships stay intact."""

    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        COUNTER = "counter", "Counter"

    id = models.BigAutoField(primary_key=True)
    counter_number = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.COUNTER)
    username = models.CharField(max_length=150, null=True, blank=True)
    password_hash = models.CharField(max_length=255, blank=True, default="")
    session_version = models.UUIDField(default=uuid.uuid4, editable=False)
    code_digest = models.CharField(max_length=64, unique=True)
    code_hash = models.CharField(max_length=255)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mobile_counter_accounts"
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["username"], condition=models.Q(username__isnull=False),
                name="mobile_account_username_unique",
            ),
        ]

    # Expose the account as an authenticated framework user; token validation is handled by StaffAuthentication.
    @property
    def is_authenticated(self):
        return True


class CycleCountAssignment(models.Model):
    """Locks one legacy Cycle Count to one mobile Counter."""

    id = models.BigAutoField(primary_key=True)
    cycle_count_id = models.BigIntegerField(unique=True)
    counter = models.ForeignKey(
        CounterAccount,
        on_delete=models.PROTECT,
        related_name="cycle_count_assignments",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mobile_cycle_count_assignments"
        ordering = ["cycle_count_id"]


class CounterCountLog(models.Model):
    """Django-owned immutable audit event for each legacy product count save."""

    id = models.BigAutoField(primary_key=True)
    counter = models.ForeignKey(
        CounterAccount,
        on_delete=models.PROTECT,
        related_name="count_logs",
    )
    cycle_count_id = models.BigIntegerField(db_index=True)
    cycle_count_code = models.CharField(max_length=4000, null=True, blank=True)
    cycle_count_detail_id = models.BigIntegerField(db_index=True)
    active_inventory_id = models.BigIntegerField(null=True, blank=True)
    description = models.CharField(max_length=240, null=True, blank=True)
    location = models.CharField(max_length=4000, null=True, blank=True)
    lot_no = models.CharField(max_length=4000, null=True, blank=True)
    lot_no_from = models.CharField(max_length=4000, null=True, blank=True)
    lot_no_changed = models.BooleanField(default=False)
    production_date = models.DateField(null=True, blank=True)
    production_date_from = models.DateField(null=True, blank=True)
    production_date_changed = models.BooleanField(default=False)
    expiry_date = models.DateField(null=True, blank=True)
    expiry_date_from = models.DateField(null=True, blank=True)
    expiry_date_changed = models.BooleanField(default=False)
    count_stage = models.CharField(max_length=20, default="final")
    actual_cs = models.DecimalField(max_digits=18, decimal_places=2)
    actual_pc = models.DecimalField(max_digits=18, decimal_places=2)
    actual_total = models.DecimalField(max_digits=18, decimal_places=2)
    variance = models.DecimalField(max_digits=18, decimal_places=2)
    counted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mobile_counter_count_logs"
        ordering = ["-counted_at", "-id"]
        indexes = [
            models.Index(
                fields=["cycle_count_detail_id", "-counted_at"],
                name="mobile_cc_detail_time_idx",
            ),
        ]
