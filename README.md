# WMS Web UI

Vue 3 + Vite mobile Counter UI with a Django REST Framework API connected to the
existing Microsoft SQL Server WMS database.

## Active source

Run frontend commands from this project root (`C:\proj\wms-web-ui`).
`src/` is the active Vue application and `backend/` is the Django API.
The unused mock application and local demo account store are retained in
[`archive/`](archive/README.md) and are not part of the active build.

Counter session storage and API lock operations live in
`src/services/counterSession.js`; `src/composables/useCounterLock.js` owns the
heartbeat lifecycle and release state. The selection page permits one list
request at a time and stops processing refreshes after it unmounts.

## Refactor checks

- `npm test` runs isolated frontend session, unlock, heartbeat, verification, and
  refresh lifecycle tests using Node's test runner and VM modules. Browser APIs
  and network responses are simulated; this is not a browser end-to-end test.
- `npm run build` compiles the production frontend.
- From `backend/`, run
  `python manage.py test cycle_counts --settings=wms_api.test_settings` for the
  existing backend regression tests against an isolated SQLite database.

The first refactor preserves the UI templates/styles, backend code, API paths,
session storage keys, four-digit counter code validation, 3-second heartbeat,
and 1.5-second selection refresh interval. Overlapping list/heartbeat requests
are skipped, and selection refresh responses are ignored after unmount.

## Included
- Direct Active Cycle Count selection for mobile Counters
- Admin Daily Cycle Count List
- Shared Administrator and Counter accounts with backend role permissions
- Staff username/password login and Counter four-digit PINs
- One Counter assignment per Cycle Count, while allowing that Counter to correct rows
- Counter product-count Activity Logs with date-range generation, pagination, and CSV export
- Editable Lot No., Production Date, Expiration Date, Actual CASE, and Actual PC
- Backend-maintained previous metadata values and immutable old/new audit snapshots
- InventoryMaster Packaging and Units/Pack guidance on every Counter product
- Actual Total and Variance auto-calculate; Variance is reserved for Admin reports
- Mobile cards and fitted desktop table with pagination
- Searchable compact Product Name picker for phone/tablet warehouse counting

## Run
```bash
npm install
npm run dev
```

Open: http://localhost:5173

Counter entry opens at `/`. Admin login remains available at `/login`.
## First Administrator

The backend must have its migrations applied. From `backend`, run:

```powershell

python manage.py migrate
python manage.py create_wms_admin --username admin --name "Administrator"
```

Enter your password at the private terminal prompts, then open `/login`.
See [backend setup](backend/README.md) for permissions, sessions, and testing.
