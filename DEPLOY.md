# WMS Web UI Deployment

Target setup:

`Mobile/Desktop Browser -> IIS (Vue) -> Django REST API -> Existing SQL Server database`

This guide assumes deployment to a Windows Server on the company LAN. IIS serves
the Vue build and forwards `/api` requests to Django running locally on port 8000.
SQL Server must never be accessed directly by the browser.

## Authentication

Administrators sign in through Django with username/password.
All roles share `mobile_counter_accounts`; Counters use four-digit PINs.
Account management requires Administrator permissions, and activity logs require
Administrator permissions, regardless of `DJANGO_DEBUG`.

Use HTTPS and a stable, private `DJANGO_SECRET_KEY`. Staff tokens expire after
12 hours; logout revokes all sessions for the account. For multiple API workers,
configure a shared Django cache for the login rate limit (10 attempts/minute/IP).

## 1. Server requirements

Install these on the Windows Server:

- IIS with Static Content
- IIS URL Rewrite module
- IIS Application Request Routing (ARR), with proxy enabled
- Python compatible with Django 6
- Node.js LTS and npm (needed only when building on the server)
- Microsoft ODBC Driver 18 for SQL Server
- Git, or another method for copying the project to the server
- A valid HTTPS certificate trusted by the warehouse mobile phones

Recommended application folder:

```text
C:\apps\wms-web-ui
```

Open only ports `80` and `443` to client devices. Keep Django port `8000` bound
to `127.0.0.1`. Do not expose SQL Server port `1433` to warehouse phones.

## 2. Copy and prepare the project

From PowerShell on the server:

```powershell
Set-Location C:\apps\wms-web-ui

py -3 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
backend\.venv\Scripts\python.exe -m pip install "waitress>=3.0,<4.0"

npm --prefix frontend ci
```

Waitress is the Windows production WSGI server. Do not use Django's
`manage.py runserver` for deployment.

## 3. Configure Django

Copy the environment template:

```powershell
Copy-Item backend\.env.example backend\.env
```

Generate a secret key:

```powershell
py -3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Example `backend\.env` for a same-server SQL connection using Windows
Authentication:

```dotenv
DJANGO_SECRET_KEY=PASTE_THE_GENERATED_RANDOM_VALUE_HERE
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=YOUR_APP_HOSTNAME,127.0.0.1

DB_NAME=YOUR_DATABASE_NAME
DB_HOST=YOUR_SQL_SERVER_HOST
DB_PORT=1433
DB_USER=
DB_PASSWORD=
DB_DRIVER=ODBC Driver 18 for SQL Server
DB_TRUSTED_CONNECTION=true
DB_ENCRYPT=true
DB_TRUST_SERVER_CERTIFICATE=false

CORS_ALLOWED_ORIGINS=https://YOUR_APP_HOSTNAME
```

Replace the hostname and SQL Server details with the real values. For a named
SQL instance, confirm its actual host/instance and TCP port with the DBA.

If SQL Server Authentication is required instead:

```dotenv
DB_TRUSTED_CONNECTION=false
DB_USER=YOUR_DB_USERNAME
DB_PASSWORD=USE_A_STRONG_SECRET_FROM_A_SECURE_STORE
```

Do not commit `backend\.env` to source control.

### Windows Authentication note

When `DB_TRUSTED_CONNECTION=true`, SQL Server sees the Windows account running
Waitress. Run the service under a dedicated domain/service account that has the
required SQL permissions. `LocalSystem` will usually not have the intended
database access.

## 4. SQL Server permissions and migrations

The following are existing legacy WMS tables and must not be recreated or
altered except for the authorized nullable `counter_id`, `lot_no_from`,
`production_date_from`, and `expiry_date_from` additions:

- `dbo.cycle_counts`
- `dbo.cycle_count_details`
- `dbo.active_inventories`
- `dbo.bin_locations`
- `dbo.InventoryMaster`
- `dbo.warehouses`

Django owns only these mobile support tables:

- `dbo.mobile_counter_accounts`
- `dbo.mobile_counter_count_logs`
- `dbo.django_migrations` tracks applied Django migrations

Before the first deployment:

1. Back up the existing SQL Server database.
2. Ask the DBA to verify the database name, schema, relationships, and service
   account permissions.
3. Check the migration plan before applying it.

```powershell
Set-Location C:\apps\wms-web-ui\backend
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py showmigrations cycle_counts
.\.venv\Scripts\python.exe manage.py migrate --plan
```

If the plan is correct, apply it once:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py create_wms_admin --username admin --name "Administrator"
```

The Administrator command prompts for a password privately. Run it once for the
first admin, then manage accounts through `/admin/users`. No default password is
installed. Migration `0003` preserves existing counter accounts and audit links.

The existing legacy models use `managed = False`. Do not change them to
`managed = True`, and do not create replacement Cycle Count tables. If the
mobile tables already exist but the migration history does not match, stop and
have the DBA inspect it; do not blindly use `--fake` or delete tables.

Migration `0008` adds the three nullable previous-metadata columns to the
unmanaged detail table using explicit database operations. Migrations `0009`
and `0010` add current/previous metadata snapshots and changed flags to the
Django-owned immutable activity log. These migrations preserve existing rows.

The runtime SQL account should use least privilege: read the verified legacy
tables, update only the approved Final Count columns, current Lot/Production/
Expiration fields, their `*_from` fields, `counter_id`, and `updated_at`, and read/write the two
mobile support tables. A separate temporary deployment account may be used for
the one-time migration if DDL permission is required.

## 5. Build Vue

Create `frontend\.env.production`:

```dotenv
VITE_API_BASE_URL=/api
```

Build the frontend:

```powershell
Set-Location C:\apps\wms-web-ui\frontend
npm run build
```

The IIS website's physical path should point to:

```text
C:\apps\wms-web-ui\frontend\dist
```

## 6. Run Django with Waitress

Test it first from PowerShell:

```powershell
Set-Location C:\apps\wms-web-ui\backend
.\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8000 wms_api.wsgi:application
```

From another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health/
```

Expected response:

```json
{"status":"ok"}
```

Install Waitress as a Windows service using the company's approved service
manager (for example NSSM or an equivalent tool). Configure:

- Working directory: `C:\apps\wms-web-ui\backend`
- Executable: `C:\apps\wms-web-ui\backend\.venv\Scripts\waitress-serve.exe`
- Arguments: `--listen=127.0.0.1:8000 wms_api.wsgi:application`
- Service identity: the dedicated account authorized in SQL Server
- Startup: Automatic
- Logs: a writable server log directory with rotation/retention

Store secrets only in `backend\.env` or the company's approved secret store.
Restrict file permissions so ordinary users cannot read it.

## 7. Configure IIS

Create the IIS site, bind its HTTPS hostname, and point it to the `frontend\dist` folder.
Enable ARR proxying at the server level.

Save the following as `frontend\public\web.config`, then run `npm run build`
from `frontend\` again. Vite will copy it into `frontend\dist\web.config`, so it
is preserved on later builds:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="Django API" stopProcessing="true">
          <match url="^api/(.*)" />
          <action type="Rewrite" url="http://127.0.0.1:8000/api/{R:1}" />
        </rule>

        <rule name="Vue history fallback" stopProcessing="true">
          <match url=".*" />
          <conditions logicalGrouping="MatchAll">
            <add input="{REQUEST_FILENAME}" matchType="IsFile" negate="true" />
            <add input="{REQUEST_FILENAME}" matchType="IsDirectory" negate="true" />
            <add input="{REQUEST_URI}" pattern="^/api/" negate="true" />
          </conditions>
          <action type="Rewrite" url="/index.html" />
        </rule>
      </rules>
    </rewrite>
    <httpProtocol>
      <customHeaders>
        <add name="X-Content-Type-Options" value="nosniff" />
        <add name="Referrer-Policy" value="same-origin" />
      </customHeaders>
    </httpProtocol>
  </system.webServer>
</configuration>
```

The API rule must appear before the Vue history fallback rule. Otherwise, API
requests may incorrectly return `index.html`.

## 8. Deployment verification

Test from the server and from an actual warehouse phone:

```text
https://YOUR_APP_HOSTNAME/api/health/
https://YOUR_APP_HOSTNAME/
https://YOUR_APP_HOSTNAME/login
```

Verify all of the following:

- The phone trusts the HTTPS certificate and can resolve the hostname.
- Only Cycle Counts with `cc_type = D` and `status_id = 0` appear in the Counter selection.
- Clicking a Cycle Count shows the Counter choices.
- Clicking a Counter reveals the four-digit PIN input.
- Wrong codes are rejected and correct codes open the selected Cycle Count.
- Phone/tablet users see all products in a compact Product Name search list and
  can choose the item physically in front of them.
- Product description, location, lot, dates, Qty/Case, and Old Count load.
- Packaging and Units/Pack load from the matching InventoryMaster product.
- Lot No., Production Date, Expiration Date, Actual CASE, and Actual PC can be edited.
- Total and variance are calculated correctly.
- Variance is hidden from Counters and remains available to Administrators in reports.
- Saving writes the approved fields, preserves changed metadata's previous values,
  and creates an immutable mobile count log with event-specific comparisons.
- A confirmed `0` cases and `0` pieces remains a valid physical count.
- The UI works at 320, 360, 375, 390, 430, 768, 1024, and 1366 pixels.
- Refreshing a Vue route does not produce an IIS 404.
- Port 8000 and SQL Server are not reachable directly from client devices.
- Turning off device Wi-Fi immediately shows the warehouse reconnection notice.
- A reachable network with an unavailable WMS server directs the user to IT.
- Activity Logs can generate an inclusive From/To report and export matching CSV.

## 9. Updating the deployment

Back up the database and current application folder, then:

```powershell
Set-Location C:\apps\wms-web-ui

backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build

Set-Location backend
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate --plan
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py create_wms_admin --username admin --name "Administrator"
```

The Administrator command prompts for a password privately. Run it once for the
first admin, then manage accounts through `/admin/users`. No default password is
installed. Migration `0003` preserves existing counter accounts and audit links.

Restart the Waitress Windows service and recycle the IIS application pool. Then
repeat the health check and a real Counter read/save smoke test.

For rollback, restore the previous application build and backend source. Do not
reverse or delete database migrations without a reviewed DBA rollback plan.
