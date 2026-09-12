# WMS Mobile Cycle Count

## System

`Vue 3 → Django REST Framework → Existing Microsoft SQL Server database`

Vue does not connect directly to SQL Server.

## Counter Flow

1. Select an available Cycle Count (`cc_type = D` and `status_id = 0`).
2. Select `Counter 1`, `Counter 2`, etc.
3. Enter the assigned 4-digit Counter PIN.
4. Review or edit Lot No., Production Date, and Expiration Date when needed.
5. Count products and save Actual CASE and Actual PC.
6. The Counter sees Packaging, Units/Pack, and Actual Total. The backend still
   calculates Variance, but exposes it only in Administrator logs/reports.
7. Previous/Next may be used to review nearby products without forcing a save.
   Completion appears only after every product has actually been saved.

Phones and touch tablets first show a compact list of every product. Counters
search by Product Name and select the item physically in front of them instead
of following a forced sequence. Only saved rows display `Counted`; rows without
that label still need a count. Tapping a row opens the existing count card, and
a successful save returns to the picker unless all products are complete.
Reopening a counted product loads its saved values for correction.
On phone and touch tablet card views, opening a Cycle Count whose products are
all saved shows a choice to `Review Counts` or return to `Cycle Counts`;
review never implies that the products must be counted again. Desktop/laptop
raw tables open directly without this popup.

## Admin Flow

Open `/login` and enter your staff username/password. Django supplies your role.
Administrators can use:

- **Counter Management** – create, activate, deactivate, or delete Counter accounts.
- **Activity Logs** – preview recent count events, generate an inclusive date-range
  report, page through results, and export the complete filtered CSV.

Create the first Administrator with `python manage.py create_wms_admin --username admin --name "Administrator"` from `backend`; the command prompts for a password.

## Existing WMS Tables

These tables already existed and remain Django `managed = False`:

| Table | Purpose |
| --- | --- |
| `cycle_counts` | Cycle Count header |
| `cycle_count_details` | Products and count values |
| `active_inventories` | Inventory details and Qty/Case |
| `bin_locations` | Product location |
| `warehouses` | Warehouse reference |
| `InventoryMaster` | Product description |

## New Mobile Counter Tables

| Table | Purpose |
| --- | --- |
| `mobile_counter_accounts` | Shared roles, name, staff username/password hash, Counter PIN hash, active status, and session version |
| `mobile_counter_count_logs` | Immutable count events, quantities, variance, timestamp, and event-specific old/new product metadata |

The existing WMS table schema was not replaced or recreated.

`cycle_count_details.counter_id` records the last mobile counter who saved the
actual count. Migration `0005` adds this nullable column and backfills from the
latest mobile logs. Every correction updates this ID and appends a log in the
same transaction. The API returns the ID as `counterId`.

The legacy detail also stores `lot_no_from`, `production_date_from`, and
`expiry_date_from`. The backend reads the current database row before an update
and changes only the matching `*_from` field when its current value actually
changes. The frontend never supplies previous values.

## Device and connection behavior

- Phones and touch tablets/iPads use the product-card flow in portrait and landscape.
- Laptops and desktops with a mouse or trackpad use the raw-data table.
- The active count sends a heartbeat every 3 seconds; its lock expires after 10
  seconds without a confirmed heartbeat.
- Device-offline notices ask the Counter to reconnect to warehouse Wi-Fi. Server
  failures direct the user to the IT Department.

Packaging comes from `InventoryMaster.Packaging`, and Units/Pack comes from
`InventoryMaster.UnitPerPackaging`. These fields are informational and do not
change the existing Qty/Case count formula.
