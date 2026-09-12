from datetime import datetime
from decimal import Decimal

from django.test import SimpleTestCase
from django.urls import resolve, reverse

from .access import counter_code_digest, hash_counter_code, verify_counter_code
from .calculations import calculate_final_count
from .models import ActiveInventory, BinLocation, CounterAccount, CounterCountLog, CycleCount, CycleCountAssignment, CycleCountDetail, InventoryMaster, Warehouse
from .serializers import CounterAccessSerializer, CycleCountDetailSerializer
from .views import CycleCountViewSet, health_check


class LegacyModelMappingTests(SimpleTestCase):
    # Test legacy cycle_counts mapping and managed=False; inspect the CycleCount model if it fails.
    def test_cycle_count_is_unmanaged_and_maps_existing_table(self):
        self.assertFalse(CycleCount._meta.managed)
        self.assertEqual(CycleCount._meta.db_table, "cycle_counts")

    # Test legacy cycle_count_details mapping and managed=False; inspect the CycleCountDetail model if it fails.
    def test_cycle_count_detail_is_unmanaged_and_maps_existing_table(self):
        self.assertFalse(CycleCountDetail._meta.managed)
        self.assertEqual(CycleCountDetail._meta.db_table, "cycle_count_details")

    # Test inventory/warehouse table names and unmanaged flags; inspect models.py if it fails.
    def test_verified_inventory_tables_are_unmanaged(self):
        expected_tables = {
            Warehouse: "warehouses",
            BinLocation: "bin_locations",
            ActiveInventory: "active_inventories",
            InventoryMaster: "InventoryMaster",
        }
        for model, table in expected_tables.items():
            with self.subTest(model=model.__name__):
                self.assertFalse(model._meta.managed)
                self.assertEqual(model._meta.db_table, table)

    # Test mobile account/log/assignment table names and managed flags.
    def test_mobile_counter_tables_are_django_managed_and_separate(self):
        self.assertTrue(CounterAccount._meta.managed)
        self.assertEqual(CounterAccount._meta.db_table, "mobile_counter_accounts")
        self.assertTrue(CounterCountLog._meta.managed)
        self.assertEqual(CounterCountLog._meta.db_table, "mobile_counter_count_logs")
        self.assertTrue(CycleCountAssignment._meta.managed)
        self.assertEqual(CycleCountAssignment._meta.db_table, "mobile_cycle_count_assignments")

    # Test the detail-to-inventory foreign key and its target ID field.
    def test_active_inventory_uses_confirmed_foreign_key(self):
        field = CycleCountDetail._meta.get_field("active_inventory")
        self.assertTrue(field.is_relation)
        self.assertEqual(field.target_field.name, "id")


class ReadOnlyRouteTests(SimpleTestCase):
    # Test health URL resolution and the HTTP 200 response; inspect urls.py and health_check if it fails.
    def test_health_route(self):
        match = resolve(reverse("health-check"))
        self.assertEqual(match.func, health_check)
        response = self.client.get(reverse("health-check"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    # Test read-only viewset methods and count/detail/update URL patterns.
    def test_cycle_count_routes_are_get_only(self):
        self.assertEqual(CycleCountViewSet.http_method_names, ["get", "head", "options"])
        self.assertEqual(reverse("cycle-count-list"), "/api/cycle-counts/")
        self.assertEqual(reverse("cycle-count-detail", args=[10]), "/api/cycle-counts/10/")
        self.assertEqual(reverse("cycle-count-details", args=[10]), "/api/cycle-counts/10/details/")
        self.assertEqual(
            reverse("cycle-count-detail-actual-count", args=[10]),
            "/api/cycle-count-details/10/actual-count/",
        )


class ActualCountCalculationTests(SimpleTestCase):
    # Test cases/pieces conversion and variance; inspect calculate_final_count if it fails.
    def test_calculates_total_and_variance_from_cases_and_pieces(self):
        total, variance = calculate_final_count(15, 0, 12, Decimal("180.00"))
        self.assertEqual(total, Decimal("180"))
        self.assertEqual(variance, Decimal("0.00"))

    # Test zero actual counts and negative variance; inspect the calculation helper if it fails.
    def test_zero_is_a_valid_physical_count(self):
        total, variance = calculate_final_count(0, 0, 12, Decimal("40.00"))
        self.assertEqual(total, Decimal("0"))
        self.assertEqual(variance, Decimal("-40.00"))


class CounterAccessSecurityTests(SimpleTestCase):
    # Test four-digit PIN validation; inspect CounterAccessSerializer if it fails.
    def test_access_code_requires_exactly_four_digits(self):
        valid = CounterAccessSerializer(data={"cycleCountId": 1, "counterId": 1, "accessCode": "1111"})
        invalid = CounterAccessSerializer(data={"cycleCountId": 1, "counterId": 1, "accessCode": "111"})
        self.assertTrue(valid.is_valid())
        self.assertFalse(invalid.is_valid())

    # Test PIN hashing, verification, and deterministic digests; inspect access.py if it fails.
    def test_code_is_hashed_and_verifiable(self):
        encoded = hash_counter_code("1111")
        self.assertNotIn("1111", encoded)
        self.assertTrue(verify_counter_code("1111", encoded))
        self.assertFalse(verify_counter_code("2222", encoded))
        self.assertEqual(counter_code_digest("1111"), counter_code_digest("1111"))


class DetailSerializerContractTests(SimpleTestCase):
    # Test detail serializer fields, count stages, and inventory mapping.
    def test_stage_values_are_explicit_and_unconfirmed_mappings_are_omitted(self):
        location = BinLocation(id=10, name="AISLE CAB")
        inventory = ActiveInventory(
            id=3,
            item_number="PERFEK1000A",
            qty_case=12,
            bin_location=location,
        )
        detail = CycleCountDetail(
            id=1,
            cycle_count_id=2,
            active_inventory=inventory,
            old_qty=Decimal("12.00"),
            fst_count_c=Decimal("1.00"),
            created_at=datetime(2026, 1, 1, 8, 0),
            updated_at=datetime(2026, 1, 1, 8, 0),
        )
        detail.description = "PERFEK 31.5EC 1000ML"

        data = CycleCountDetailSerializer(detail).data

        self.assertEqual(data["firstCountCases"], "1.00")
        self.assertNotIn("actualCs", data)
        self.assertNotIn("countStage", data)
        self.assertEqual(data["location"], "AISLE CAB")
        self.assertEqual(data["description"], "PERFEK 31.5EC 1000ML")
        self.assertEqual(data["qtyPerCase"], 12)
