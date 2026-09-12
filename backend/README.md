# WMS API

This backend is an isolated Django REST Framework service for using an existing
Microsoft SQL Server database. It does not create or own the legacy WMS schema.

## Safety boundary

- `cycle_counts` and `cycle_count_details` are mapped with `managed = False`.
- Cycle Count headers/details use `ReadOnlyModelViewSet`.
- One dedicated PATCH route updates Final Count CS/PC, calculated Total and
  Variance, editable Lot/Production/Expiration metadata and its server-owned
  previous values, `counter_id`, and `updated_at`.
- There are no generic POST, PUT, PATCH, or DELETE routes for legacy rows.
- The migration treats every legacy model as a no-op and creates only the
Django-owned `mobile_counter_accounts` and `mobile_counter_count_logs` tables.
- Migration `0005_detail_counter_id` is the explicitly authorized exception: it
  adds nullable `cycle_count_details.counter_id` and backfills it from the latest
  mobile log (ordered by counted time, then log ID). It does not recreate the table.
- Migration `0008` adds nullable `lot_no_from`, `production_date_from`, and
  `expiry_date_from` fields without recreating the unmanaged detail table.
- Migrations `0009` and `0010` extend the Django-owned immutable activity log
  with metadata snapshots and per-event changed flags.
- Never change an existing WMS model to `managed = True`.
- The SQL Server login needs narrowly scoped `SELECT` access, Final Count and
  approved metadata update access, plus access to the two Django-owned mobile tables.

## Local setup

From `backend` in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` for the real SQL Server instance. For Windows Authentication, keep
`DB_TRUSTED_CONNECTION=true` and leave `DB_USER` and `DB_PASSWORD` empty. For SQL
Server Authentication, set it to `false` and provide both credentials.

The local machine needs Microsoft ODBC Driver 18 (or set `DB_DRIVER` to Driver 17).

Run checks and start the API:

```powershell
python manage.py check
python manage.py test --settings=wms_api.test_settings
python manage.py runserver 127.0.0.1:8000
```

`GET /api/health/` checks only the Django process. It deliberately does not query
SQL Server. The cycle-count routes query the configured legacy database.

## Shared accounts and first Administrator

Both roles use `mobile_counter_accounts`. Migration `0003_staff_accounts`
adds `role`, `username`, `password_hash`, and `session_version`, plus a filtered
unique username index. Existing IDs, counter numbers, PIN hashes, and audit
relationships are preserved; existing rows become `counter` accounts.

After applying migrations, create the first Administrator from `backend`:

```powershell
python manage.py migrate
python manage.py create_wms_admin --username admin --name "Administrator"
```

The command prompts for a password twice without displaying it. For local use,
administrator passwords may use any non-empty length. There is no default
password. Sign in at `/login`, then use User Management to create
Administrators and Counters. Usernames are case-insensitive and
accept letters, digits, dots, underscores, and hyphens.

Administrators manage accounts and view counts/logs. Counters use a four-digit-code counting flow and are
the only accounts shown in the Counter selector. Existing account roles cannot
be changed; create a separate account for another role. An Administrator cannot
delete or deactivate their own account. Accounts with count history cannot be
deleted. The existing unique number is allocated for every account internally;
staff accounts display their username instead of a Counter number.

The first Counter who successfully verifies access holds that Cycle Count through
`mobile_cycle_count_assignments`. Only that Counter can open it, save rows, and
make corrections while the lock exists. A different Counter receives HTTP 409;
an old or forged session from another Counter is rejected on reads and saves.
The counting screen's Back button calls `POST /api/cycle-counts/{id}/unlock/`,
then removes the local session and returns to the refreshed list. After release,
another Counter can continue the same Cycle Count. The active screen sends a
heartbeat every 3 seconds. Closing the browser stops that heartbeat, and the lock
expires after 10 seconds without a confirmed heartbeat. The selection screen
refreshes its locks every 1.5 seconds and whenever the browser tab becomes visible.
Migration `0006` backfills existing assignments from detail `counter_id` values;
migration `0007` adds the last-activity timestamp.

Staff sessions last 12 hours and use signed Bearer tokens held in browser
`sessionStorage`. The backend reloads active status and role for every protected
request. Logout revokes all staff sessions for that account; changing password,
username, or active status also revokes them. Names can be edited without ending
a session. Permissions are enforced with both `DEBUG=True` and `DEBUG=False`.
Use HTTPS for credentials and tokens and retain the configured secret key.

Login attempts are limited to 10 per minute per client IP using Django's cache.
The default local-memory cache limits each worker separately; configure a shared
cache for a shared limit across workers. Counter verification is also throttled.
CORS permits both `Authorization` and `X-Counter-Session` headers.

The isolated test settings use in-memory SQLite and never connect to SQL Server.
The counter save regression test creates temporary legacy-shaped tables only in
that test database.

## Routes

- `GET /api/cycle-counts/`
- `GET /api/cycle-counts/{id}/`
- `POST /api/counter-access/verify/`
- `GET /api/cycle-counts/{id}/details/` (requires `X-Counter-Session`)
- `PATCH /api/cycle-count-details/{id}/actual-count/` (requires `X-Counter-Session`)
- `POST /api/auth/login/` (username/password)
- `GET /api/auth/me/` (staff Bearer token)
- `POST /api/auth/logout/` (revokes all sessions for the staff account)
- `GET|POST|PATCH|DELETE /api/counter-accounts/` (Administrator only)
- `GET /api/counter-count-logs/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` (Administrator; inclusive)

Counter PINs contain exactly four digits and are stored only as secure
hashes/digests. Verification returns a signed, Cycle-Count-specific session valid
for 12 hours. The PATCH body accepts `actualCs`, `actualPc`, and optional
`lotNo`, `productionDate`, and `expiryDate`. It is
accepted only for Cycle Counts with `cc_type = D` and `status_id = 0`. A zero physical count is valid. The API
calculates and saves `fin_count_total` and `fin_count_variance`; clients cannot
supply them. The authenticated Counter session also supplies `counter_id`,
returned as read-only `counterId`; client-supplied attribution is ignored. The
same transaction adds an immutable mobile count audit event. Corrections remain
allowed: they replace the last counter ID and append another log. A failed log
insert rolls back both the count and counter ID. Rows without mobile logs remain
NULL after migration; zero counts are valid. The column is a logical reference
to `mobile_counter_accounts.id`, without a new database foreign-key constraint.

For metadata edits, the backend locks and reads the current detail row before
updating it. Only a real change moves the database value into the matching
`lot_no_from`, `production_date_from`, or `expiry_date_from` field. Each
immutable log snapshots current metadata, event-specific old values, and changed
flags so Activity Logs and CSV reports distinguish edits from count-only saves.

Optional list filters use known scalar fields only:

- `warehouse_id`
- `status_id`
- `cc_type`

Header, account, and log lists are paginated with 50 records per page.
Cycle Count details return the complete list for local product search.

## Verified inventory mappings

- `cycle_count_details.active_inventory_id` -> `active_inventories.id`
- `active_inventories.bin_location_id` -> `bin_locations.id` -> `name`
- `active_inventories.item_number` -> `InventoryMaster.ItemCode` -> `Description`
- `active_inventories.item_number` -> `InventoryMaster.ItemCode` -> `Packaging` and `UnitPerPackaging`
- `active_inventories.qty_case` -> Qty/Case
- `cycle_counts.warehouse_id` -> `warehouses.id` -> `description`

All mapped legacy models remain unmanaged and read-only.

## Remaining production requirements

1. Confirm the full lifecycle meaning of header `status_id` and detail
   `inventory_status_id`, and how
   a zero physical count is recorded as explicitly confirmed.
2. Confirm the timezone semantics of legacy `datetime` values.

The Vue Counter reads real header, warehouse, inventory, location, product, and
count values through the API. Based on the verified legacy screen/database values,
Actual C/PC writes to the legacy Final Count fields through the restricted endpoint.
The API returns Packaging and Units/Pack as read-only Counter guidance. Variance
continues to be calculated and audited but is displayed only in Administrator reports.
