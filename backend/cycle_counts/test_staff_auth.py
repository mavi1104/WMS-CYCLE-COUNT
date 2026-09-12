from datetime import date, datetime
from unittest.mock import patch

from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from .access import counter_code_digest, create_counter_session
from .authentication import create_staff_session
from .models import (ActiveInventory, BinLocation, CounterAccount, CounterCountLog,
                     CycleCount, CycleCountDetail, InventoryMaster, Warehouse)
from .serializers import CounterAccountSerializer, CounterAccessSerializer


# Test helper: create an administrator/counter fixture through the serializer. Troubleshoot: test credentials and role fields.
def create_account(role="admin", username="admin", **extra):
    data = {"role": role, "name": username, **extra}
    if role == "counter":
        data["accessCode"] = "1111"
    else:
        data.update(username=username, password="Warehouse-Strong-2026!")
    serializer = CounterAccountSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.save()


class StaffAuthenticationTests(TestCase):
    # Before each authentication test, clear the throttle cache and create the API client and account fixtures.
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin = create_account()
        self.other_admin = create_account("admin", "other-admin")
        self.counter = create_account("counter", "counter")

    # Test helper: attach a signed Bearer token to the API client for the selected account.
    def authenticate(self, account=None):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + create_staff_session(account or self.admin))

    # Test password rejection and use of the database role; inspect StaffLoginView if it fails.
    def test_login_checks_password_and_returns_database_role(self):
        response = self.client.post("/api/auth/login/", {"username": "ADMIN", "password": "wrong", "role": "admin"})
        self.assertEqual(response.status_code, 401)
        response = self.client.post("/api/auth/login/", {"username": "OTHER-ADMIN", "password": "Warehouse-Strong-2026!", "role": "admin"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["role"], "admin")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + response.data["token"])
        self.assertEqual(self.client.get("/api/auth/me/").data["id"], self.other_admin.pk)
        self.assertEqual(self.client.get("/api/counter-accounts/").status_code, 200)

    # Test rejection of anonymous account/log access with DEBUG both enabled and disabled.
    def test_anonymous_management_is_denied_in_both_debug_modes(self):
        for debug in (True, False):
            with override_settings(DEBUG=debug):
                for method, path in [("get", "/api/counter-accounts/"), ("post", "/api/counter-accounts/"),
                                     ("patch", f"/api/counter-accounts/{self.counter.pk}/"),
                                     ("delete", f"/api/counter-accounts/{self.counter.pk}/"),
                                     ("get", "/api/counter-count-logs/")]:
                    self.assertEqual(getattr(self.client, method)(path).status_code, 401)

    # Test account creation and exclusion of password/PIN fields from responses.
    def test_admin_can_create_all_roles_without_exposing_credentials(self):
        self.authenticate()
        for role in ("admin", "counter"):
            data = {"name": "New employee", "role": role}
            data.update({"accessCode": "2222"} if role == "counter" else {"username": "new-" + role, "password": "Another-Strong-2026!"})
            response = self.client.post("/api/counter-accounts/", data)
            self.assertEqual(response.status_code, 201, response.data)
            self.assertFalse({"password", "password_hash", "accessCode", "code_hash", "code_digest", "session_version"} & response.data.keys())
            account = CounterAccount.objects.get(pk=response.data["id"])
            self.assertEqual(account.role, role)
            if role != "counter":
                self.assertTrue(check_password(data["password"], account.password_hash))

    # Test rejection of the removed supervisor role during creation and authentication.
    def test_removed_supervisor_role_cannot_be_created_or_authenticated(self):
        self.authenticate()
        response = self.client.post("/api/counter-accounts/", {
            "name": "Removed role", "role": "supervisor", "username": "removed",
            "password": "Warehouse-Strong-2026!",
        })
        self.assertEqual(response.status_code, 400)
        CounterAccount.objects.filter(pk=self.other_admin.pk).update(role="supervisor")
        self.other_admin.refresh_from_db()
        self.authenticate(self.other_admin)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        response = self.client.post("/api/auth/login/", {
            "username": self.other_admin.username, "password": "Warehouse-Strong-2026!",
        })
        self.assertEqual(response.status_code, 401)

    # Test that choices contain only active counters; inspect CounterChoicesView if it fails.
    def test_counter_choices_exclude_staff_and_inactive_counters(self):
        response = self.client.get("/api/counter-access/counters/")
        self.assertEqual([row["id"] for row in response.data], [self.counter.pk])
        self.counter.active = False
        self.counter.save()
        self.assertEqual(self.client.get("/api/counter-access/counters/").data, [])

    # Test rejection of old tokens after a password change; inspect session_version if it fails.
    def test_password_change_revokes_old_session(self):
        old_token = create_staff_session(self.other_admin)
        self.authenticate()
        response = self.client.patch(f"/api/counter-accounts/{self.other_admin.pk}/", {"password": "Replacement-Strong-2026!"})
        self.assertEqual(response.status_code, 200, response.data)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + old_token)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    # Test that an unchanged username preserves the session.
    def test_unchanged_username_does_not_revoke_session(self):
        self.authenticate()
        response = self.client.patch(f"/api/counter-accounts/{self.admin.pk}/", {"username": "admin", "name": "Updated name"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

    # Test that reactivating an account does not restore an old token.
    def test_deactivate_then_reactivate_does_not_restore_old_token(self):
        old_token = create_staff_session(self.other_admin)
        self.authenticate()
        for active in (False, True):
            response = self.client.patch(f"/api/counter-accounts/{self.other_admin.pk}/", {"active": active}, format="json")
            self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + old_token)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    # Test session revocation after logout; inspect StaffLogoutView if it fails.
    def test_logout_revokes_token(self):
        self.authenticate()
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    # Test self-deletion and self-deactivation guards in the viewset and serializer.
    def test_self_delete_and_deactivate_are_rejected(self):
        self.authenticate()
        path = f"/api/counter-accounts/{self.admin.pk}/"
        self.assertEqual(self.client.delete(path).status_code, 409)
        self.assertEqual(self.client.patch(path, {"active": False}, format="json").status_code, 400)

    # Test rejection of role changes and counter access to staff endpoints.
    def test_roles_are_immutable_and_counter_cannot_use_staff_token(self):
        self.authenticate()
        self.assertEqual(self.client.patch(f"/api/counter-accounts/{self.counter.pk}/", {"role": "admin"}).status_code, 400)
        self.authenticate(self.counter)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    # Test rejection of expired, tampered, and counter tokens by StaffAuthentication.
    def test_expired_and_tampered_tokens_are_rejected(self):
        with patch("django.core.signing.time.time", return_value=1):
            expired = create_staff_session(self.admin)
        for token in (expired, create_staff_session(self.admin) + "bad", create_counter_session(self.counter.pk, 1)):
            self.client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
            self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    # Test current short-password acceptance and case-insensitive username uniqueness.
    def test_short_password_is_allowed_and_duplicate_username_is_rejected(self):
        self.authenticate()
        short_password = self.client.post("/api/counter-accounts/", {
            "name": "Other", "role": "admin", "username": "other", "password": "123",
        })
        self.assertEqual(short_password.status_code, 201)
        duplicate_username = self.client.post("/api/counter-accounts/", {
            "name": "Duplicate", "role": "admin", "username": "ADMIN", "password": "123",
        })
        self.assertEqual(duplicate_username.status_code, 400)

    # Test HTTP 429 after the login attempt limit; inspect LoginThrottle and the cache if it fails.
    def test_login_is_throttled(self):
        for _ in range(10):
            self.assertEqual(self.client.post("/api/auth/login/", {"username": "admin", "password": "wrong"}).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login/", {"username": "admin", "password": "wrong"}).status_code, 429)

    # Test rejection of the Unicode-digit PIN fixture before hashing; inspect the access serializer regex if it fails.
    def test_unicode_pin_is_rejected_before_digest(self):
        serializer = CounterAccessSerializer(data={"cycleCountId": 1, "counterId": 1, "accessCode": "\u0661\u0662\u0663\u0664\u0665\u0666"})
        self.assertFalse(serializer.is_valid())

    # Test CORS preflight for X-Counter-Session; inspect CORS_ALLOW_HEADERS if it fails.
    def test_counter_header_is_allowed_by_cors(self):
        with override_settings(CORS_ALLOWED_ORIGINS=["http://localhost:5173"]):
            response = self.client.options("/api/cycle-counts/1/details/", HTTP_ORIGIN="http://localhost:5173", HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET", HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-counter-session")
        self.assertIn("x-counter-session", response["Access-Control-Allow-Headers"])


class CounterFlowRegressionTests(TransactionTestCase):
    legacy_models = [Warehouse, BinLocation, ActiveInventory, InventoryMaster, CycleCount, CycleCountDetail]

    # Test setup: create unmanaged legacy tables in the isolated test database.
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.schema_editor() as editor:
            for model in cls.legacy_models:
                editor.create_model(model)

    # Test cleanup: remove temporary legacy tables in reverse dependency order.
    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            for model in reversed(cls.legacy_models):
                editor.delete_model(model)
        super().tearDownClass()

    # Test counter access, locks, saves, attribution, audit rollback, and staff log permissions; inspect views.py if it fails.
    def test_counter_save_and_staff_audit_permissions(self):
        cache.clear()
        counter = create_account("counter", "Counter")
        admin = create_account()
        warehouse = Warehouse.objects.create(id=1, description="Warehouse")
        location = BinLocation.objects.create(id=1, name="A1", warehouse_id=1)
        inventory = ActiveInventory.objects.create(id=1, warehouse=warehouse, bin_location=location, item_number="ITEM", qty_case=12)
        InventoryMaster.objects.create(
            item_code="ITEM", description="Product", item_name="Product",
            packaging="Bottle", units_per_pack=24,
        )
        count = CycleCount.objects.create(id=1, code="CC1", warehouse=warehouse, status_id=0, cc_type="D", created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1))
        CycleCount.objects.create(id=2, code="CC2", warehouse=warehouse, status_id=0, cc_type="D", created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1))
        detail = CycleCountDetail.objects.create(
            id=1, cycle_count=count, active_inventory=inventory, old_qty=24,
            production_date=date(2026, 1, 1), expiry_date=date(2027, 1, 1), lot_no="LOT001",
            created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
        )
        client = APIClient()
        login = client.post("/api/counter-access/verify/", {"cycleCountId": 1, "counterId": counter.pk, "accessCode": "1111"})
        self.assertEqual(login.status_code, 200, login.data)
        second_cycle_login = client.post("/api/counter-access/verify/", {
            "cycleCountId": 2, "counterId": counter.pk, "accessCode": "1111",
        })
        self.assertEqual(second_cycle_login.status_code, 409)
        choices = client.get("/api/counter-access/counters/")
        selected_choice = next(item for item in choices.data if item["id"] == counter.pk)
        self.assertEqual(selected_choice["activeCycleCountId"], count.pk)
        client.credentials(HTTP_X_COUNTER_SESSION=login.data["token"])
        details_response = client.get("/api/cycle-counts/1/details/")
        self.assertEqual(details_response.status_code, 200)
        self.assertEqual(details_response.data[0]["packaging"], "Bottle")
        self.assertEqual(details_response.data[0]["unitsPerPack"], 24)
        response = client.patch("/api/cycle-count-details/1/actual-count/", {
            "actualCs": 2, "actualPc": 1,
            "productionDate": "2026-02-01", "expiryDate": "2027-02-01", "lotNo": "LOT002",
        })
        self.assertEqual(response.status_code, 200, response.data)
        detail.refresh_from_db()
        self.assertEqual(detail.counter_id, counter.pk)
        self.assertEqual(response.data["counterId"], counter.pk)
        self.assertEqual(detail.fin_count_total, 25)
        self.assertEqual(detail.fin_count_variance, 1)
        self.assertEqual(detail.production_date_from, date(2026, 1, 1))
        self.assertEqual(detail.production_date, date(2026, 2, 1))
        self.assertEqual(detail.expiry_date_from, date(2027, 1, 1))
        self.assertEqual(detail.expiry_date, date(2027, 2, 1))
        self.assertEqual(detail.lot_no_from, "LOT001")
        self.assertEqual(detail.lot_no, "LOT002")
        first_log = CounterCountLog.objects.get()
        self.assertEqual(first_log.counter_id, counter.pk)
        self.assertTrue(first_log.lot_no_changed)
        self.assertEqual(first_log.lot_no_from, "LOT001")
        self.assertEqual(first_log.lot_no, "LOT002")
        self.assertTrue(first_log.production_date_changed)
        self.assertEqual(first_log.production_date_from, date(2026, 1, 1))
        self.assertEqual(first_log.production_date, date(2026, 2, 1))
        self.assertTrue(first_log.expiry_date_changed)
        self.assertEqual(first_log.expiry_date_from, date(2027, 1, 1))
        self.assertEqual(first_log.expiry_date, date(2027, 2, 1))
        second = CounterAccountSerializer(data={"name": "Second Counter", "accessCode": "2222"})
        second.is_valid(raise_exception=True)
        second_counter = second.save()
        second_login = client.post("/api/counter-access/verify/", {
            "cycleCountId": count.pk,
            "counterId": second_counter.pk,
            "accessCode": "2222",
        })
        self.assertEqual(second_login.status_code, 409)
        client.credentials(HTTP_X_COUNTER_SESSION=create_counter_session(second_counter.pk, count.pk))
        self.assertEqual(client.get("/api/cycle-counts/1/details/").status_code, 403)
        client.credentials(HTTP_X_COUNTER_SESSION=login.data["token"])
        response = client.patch("/api/cycle-count-details/1/actual-count/", {
            "actualCs": 0, "actualPc": 0, "counterId": admin.pk, "counter_id": admin.pk,
            "productionDate": "2026-02-01", "expiryDate": "2027-02-01", "lotNo": "LOT002",
        })
        self.assertEqual(response.status_code, 200, response.data)
        detail.refresh_from_db()
        self.assertEqual(detail.counter_id, counter.pk)
        self.assertEqual(response.data["counterId"], counter.pk)
        self.assertEqual(detail.fin_count_total, 0)
        self.assertEqual(CounterCountLog.objects.count(), 2)
        self.assertEqual(list(CounterCountLog.objects.order_by("id").values_list("counter_id", flat=True)), [counter.pk, counter.pk])
        unchanged_log = CounterCountLog.objects.order_by("id")[1]
        self.assertFalse(unchanged_log.lot_no_changed)
        self.assertFalse(unchanged_log.production_date_changed)
        self.assertFalse(unchanged_log.expiry_date_changed)

        # Changing only Lot No. to null must not overwrite either date-history field.
        response = client.patch("/api/cycle-count-details/1/actual-count/", {
            "actualCs": 0, "actualPc": 0,
            "productionDate": "2026-02-01", "expiryDate": "2027-02-01", "lotNo": None,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        detail.refresh_from_db()
        self.assertIsNone(detail.lot_no)
        self.assertEqual(detail.lot_no_from, "LOT002")
        self.assertEqual(detail.production_date_from, date(2026, 1, 1))
        self.assertEqual(detail.expiry_date_from, date(2027, 1, 1))
        reloaded = client.get("/api/cycle-counts/1/details/")
        self.assertEqual(reloaded.status_code, 200, reloaded.data)
        self.assertIsNone(reloaded.data[0]["lotNo"])
        self.assertEqual(reloaded.data[0]["productionDate"], "2026-02-01")
        self.assertEqual(reloaded.data[0]["expiryDate"], "2027-02-01")
        self.assertEqual(CounterCountLog.objects.count(), 3)
        self.assertEqual(list(CounterCountLog.objects.order_by("id").values_list("counter_id", flat=True)), [counter.pk, counter.pk, counter.pk])
        lot_only_log = CounterCountLog.objects.order_by("id")[2]
        self.assertTrue(lot_only_log.lot_no_changed)
        self.assertEqual(lot_only_log.lot_no_from, "LOT002")
        self.assertIsNone(lot_only_log.lot_no)
        self.assertFalse(lot_only_log.production_date_changed)
        self.assertFalse(lot_only_log.expiry_date_changed)

        # A failed audit insert must roll back both quantities and attribution.
        client.credentials(HTTP_X_COUNTER_SESSION=create_counter_session(counter.pk, count.pk))
        with patch("cycle_counts.views.CounterCountLog.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                client.patch("/api/cycle-count-details/1/actual-count/", {"actualCs": 9, "actualPc": 1})
        detail.refresh_from_db()
        self.assertEqual(detail.counter_id, counter.pk)
        self.assertEqual(detail.fin_count_total, 0)
        self.assertEqual(detail.production_date_from, date(2026, 1, 1))
        self.assertEqual(detail.expiry_date_from, date(2027, 1, 1))
        self.assertEqual(detail.lot_no_from, "LOT002")
        self.assertEqual(CounterCountLog.objects.count(), 3)

        # Back/unlock releases occupancy so a different Counter can continue.
        client.credentials()
        unlock = client.post(
            "/api/cycle-counts/1/unlock/",
            {"counterSession": login.data["token"]},
            format="json",
        )
        self.assertEqual(unlock.status_code, 200, unlock.data)
        self.assertEqual(client.get("/api/cycle-counts/1/details/").status_code, 403)
        second_login = client.post("/api/counter-access/verify/", {
            "cycleCountId": count.pk,
            "counterId": second_counter.pk,
            "accessCode": "2222",
        })
        self.assertEqual(second_login.status_code, 200, second_login.data)

        client.credentials(HTTP_AUTHORIZATION="Bearer " + create_staff_session(admin))
        self.assertEqual(client.get("/api/counter-count-logs/").status_code, 200)
        today = date.today().isoformat()
        dated_logs = client.get(f"/api/counter-count-logs/?date_from={today}&date_to={today}")
        self.assertEqual(dated_logs.status_code, 200, dated_logs.data)
        self.assertEqual(dated_logs.data["count"], 3)
        self.assertEqual(client.get("/api/counter-count-logs/?date_from=2099-01-01&date_to=2099-01-01").data["count"], 0)
        self.assertEqual(client.get("/api/counter-count-logs/?date_from=2026-02-01").status_code, 400)
        self.assertEqual(client.get("/api/counter-count-logs/?date_from=2026-02-02&date_to=2026-02-01").status_code, 400)
        client.credentials(HTTP_AUTHORIZATION="Bearer " + create_staff_session(admin))
        self.assertEqual(client.delete(f"/api/counter-accounts/{counter.pk}/").status_code, 409)

    def test_counter_pin_survives_secret_key_rotation(self):
        counter = create_account("counter", "Counter")
        original_digest = counter.code_digest

        with override_settings(SECRET_KEY="replacement-secret-key-for-rotation-test"):
            response = APIClient().post("/api/counter-access/verify/", {
                "cycleCountId": 1,
                "counterId": counter.pk,
                "accessCode": "1111",
            })

            # PIN authentication reaches Cycle Count validation rather than
            # being rejected merely because its lookup digest used the old key.
            self.assertNotEqual(response.status_code, 403, response.data)
            counter.refresh_from_db()
            self.assertNotEqual(counter.code_digest, original_digest)
            self.assertEqual(counter.code_digest, counter_code_digest("1111"))
