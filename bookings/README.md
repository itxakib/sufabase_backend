# bookings — service records (Hajj, Umrah, Tour, Ticketing, Hotel, Transport)

The bookings app owns every record of *something a customer bought from us for a
date*: a Hajj package for a season, an airline ticket, a hotel stay, a vehicle
job, a tour. It is the operational heart of the system — the tables that
commercial and delivery work is actually recorded against.

This pass is **schema only**: models, choices, migration and tests. No
serializers, no selectors, no API and no urls yet — see
[What this pass does not include](#what-this-pass-does-not-include).

## The shared base: `ServiceRecordBase`

Six of the seven models inherit `ServiceRecordBase(TenantScopedModel)`. It holds
everything common to "a thing a customer bought from us": the customer link, a
booking reference, a date range, an amount and currency, the selling agent, notes
and attachments.

The point is not brevity for its own sake — it is that these seven tables would
otherwise drift. A `start/end date` pair that means a different thing on each
model is fine; two pairs spelled differently in six places is how a report ends
up silently wrong.

`start_date` / `end_date` are reused per service line, deliberately:

| Model | `start_date` / `end_date` mean |
|---|---|
| `TicketingBooking` | departure / return |
| `HotelBooking` | check-in / check-out |
| `TransportBooking` | pickup date (return date for multi-day jobs) |
| `TourBooking` | departure / return |
| `HajjBooking`, `UmrahBooking` | left **null** — sold by year/season |

Hajj and Umrah are not dated products. A Hajj package spans a multi-week window
set by the lunar calendar, and the year lives on the trip record
(`hajj_year`, `umrah_year_season`). Inventing a departure/return date for them
would be a guess stored as fact, so those columns stay null.

## Models

### Component records — built first

| Model | Represents | Notes |
|---|---|---|
| `TicketingBooking` | One customer, one journey | `refund_status` is tracked separately from `status`: a cancelled ticket can still be awaiting money back, and that outstanding balance is what finance chases. |
| `HotelBooking` | One reservation, one stay window | Nights are *derived* from the dates, never stored. `supplier_agent` is free text — the counterparty is often an external agency that will never be a SUFABASE user. |
| `TransportBooking` | One vehicle job | `pickup_time` is required because a vehicle job without a time is not actionable. `flight_number_arrival_ref` is what makes airport pickups work when the driver needs to track delays. |

### `Package` — the booked bundle

The real `HotelBooking` / `TicketingBooking` / `TransportBooking` rows for one
customer's trip, linked through `PackageComponent`.

**This is not the sellable package.** The catalog item (room type, cabin, vehicle,
no guest and no ticket number) is `catalog.PackageTemplate`. This bundle may
optionally point at that template. It does not copy the template's specs and it
does not copy guest names or ticket numbers off the bookings it links.

Design decisions:

| Decision | Why |
|---|---|
| `PackageComponent`, one booking foreign key set | A trip routinely has more than one of each — two hotels, an outbound and a return ticket. Explicit foreign keys stay joinable. A check constraint rejects zero or two bookings on one link row. |
| No `customer` FK | The customer lives on the Hajj/Umrah/Tour record. |
| Trip reverses are `hajj_trips`, `umrah_trips`, `tour_trips` | Three foreign keys cannot share one reverse name. |
| Deleting a package deletes link rows only | `PackageComponent.package` is CASCADE. The booking foreign keys are PROTECT, so a linked hotel cannot be deleted until the link is removed. |
| Optional `template` FK, SET_NULL | A bundle can be assembled with no catalog item. Deleting the template unlinks bundles and does not delete them. |
| Carries its own `attachments` | Trip-wide paperwork (consolidated itinerary, group visa list) belongs to the bundle. Component documents stay on the component. |

### Trip records — built last (each FKs into `Package`)

| Model | Represents | Notes |
|---|---|---|
| `HajjBooking` | A customer's Hajj record for one year | `application_number` stores the external Hajj application identifier (separate from the internal `booking_reference`); `visa_status` is independent of `status`. |
| `UmrahBooking` | A customer's Umrah record for one season | `umrah_year_season` is free text because it must hold values like "Ramadan 2026". `room_occupancy_type` is free text rather than reusing `OccupancyTypeChoices`, because at this level staff record a package's advertised sharing basis, which does not always map onto one fixed occupancy value. |
| `TourBooking` | A domestic or international tour booking | Uses real dates (a tour has them) and `number_of_travelers` (tours are priced per head). |

### Build order

`base` → `ticketing` / `hotel` / `transport` → `package` (`PackageComponent`) → `hajj` / `umrah` / `tour`.

The sellable spec is not in this chain. It lives in the `catalog` app
(`PackageTemplate` / `PackageTemplateLine`). `Package.template` points at it
and is nullable.

Each layer references the one before it, and `bookings/models/__init__.py`
imports in exactly that order so the dependency graph is readable and an import
cycle would be obvious immediately.

## Fields that become required by status

`bookings/status_rules.py` holds the rule that a component field is required only
once the record reaches the status where it must exist. A record is created when
it is *sold*, not when it is *delivered*, and three fields provably cannot exist
at sale time:

| Model | Field | Required from | Why it cannot be required always |
|---|---|---|---|
| `TicketingBooking` | `pnr` | `ISSUED`, `REISSUED` | A PNR does not exist until the ticket is issued — yet the default status is `RESERVED`, the state that *means* "not issued yet". |
| `HotelBooking` | `lead_guest_name` | `CONFIRMED`, `COMPLETED` | A group booking goes in before the rooming list arrives. |
| `TransportBooking` | `pickup_time` | `DRIVER_ASSIGNED`, `COMPLETED` | The time is settled after the vehicle is booked; nobody can be *dispatched* without it. |

The alternative — requiring them outright — is worse than it looks: it does not
produce complete records, it produces records with `"PENDING"` typed into a PNR
column, which is indistinguishable from real data forever.

**One table, three enforcement layers**, so they cannot disagree:

| Layer | Entry point | Catches |
|---|---|---|
| Database | the `CheckConstraint` in each model's `Meta` | everything — `obj.save()`, admin, raw SQL through the ORM |
| Model | `ServiceRecordBase.clean()` via `full_clean()` | Django admin, which gets a field-level error instead of an `IntegrityError` page |
| API | `StatusRequiredFieldsMixin` in `common/serializers.py` | the frontend, with a `400` naming the field and the status |

Fields that determine the *price* stay required at every status — `room_type`,
`vehicle_type`, `number_of_passengers`, `origin`, `destination`, `airline`,
`passenger_name` — because a quote cannot be produced without them.
`confirmation_number` is deliberately **not** in the table: plenty of small hotels
never issue one.

`StatusRuleApiTests` / `DatabaseConstraintTests` are data-driven from the table,
so adding a rule automatically adds the tests that prove all three layers honour
it — including `test_every_rule_has_a_database_constraint`, which fails if a rule
is added to the table without the matching constraint.

## Delete rules

Link rows are the exception: deleting a `Package` deletes its `PackageComponent`
rows. That cascade removes the link, not the hotel, ticket, or transport.

| Edge | Rule | Why |
|---|---|---|
| `company` ← any booking | **PROTECT** (inherited) | A company holds live client business data. `company.delete()` must fail loudly, not wipe a tenant. Retire a tenant with `Company.is_active = False`. |
| `customer` ← any service record | **PROTECT** | A booking is unrecoverable once wiped. The realistic deletion triggers in a CRM — merging a duplicate, correcting a wrong entry, an erasure request — are all cases where someone should decide explicitly what happens to the booking history. Retire a customer with `record_status = ARCHIVED`. |
| `sales_agent` ← any service record | **SET_NULL** | An assignment is not part of a record's identity. Losing one must never block removing a departing staff account; the booking survives, unassigned. |
| `package` ← Hajj/Umrah/Tour | **SET_NULL** | An optional link to the booked bundle. Losing it must not block deleting the package. Reverses are `hajj_trips`, `umrah_trips`, `tour_trips`. |
| `template` ← `Package` | **SET_NULL** | Optional link to `catalog.PackageTemplate`. Deleting a sellable package unlinks bundles. |
| `PackageComponent.package` | **CASCADE** | Deleting a bundle deletes its link rows only. |
| booking ← `PackageComponent` | **PROTECT** | A hotel, ticket, or transport that is still linked cannot be deleted. Remove the link first. |

`ProtectedDeleteTests` covers all of this from both directions, including that a
customer with no bookings still deletes cleanly — which is what proves the
protection is conditional rather than a blanket block.

## `choices.py`

Fourteen `TextChoices` classes, per the project-wide convention that choices live
in their own module rather than as inline tuples.

Some are shared on purpose: Hajj, Umrah and Tour all run on
`BookingStageChoices`, so one pipeline report can read across all three service
lines. Others are deliberately *not* merged — Ticketing, Hotel and Transport each
have their own status flow because their real lifecycles differ. A ticket can be
refunded and a hotel stay cannot; Transport has `DRIVER_ASSIGNED` and `NO_SHOW`,
which nothing else needs. Collapsing them into one enum would hide real
operational states to save a few lines.

`test_every_choice_value_fits_its_column` walks every choice field on every
service record and fails if a value is longer than its column — a whole class of
"works in dev, rejected at write time in production" bug caught in one test.

## Deliberately omitted

Per the spec's own "hide by default" guidance, optional fields are **not** bulk
included. Left out, and to be added individually when SUFA actually needs them:

- seat number (ticketing)
- driver name / contact (transport)
- payment status (all)
- base fare / taxes breakdown (ticketing)

Add them one at a time, against a real requirement, rather than speculatively.

## Never stored

Following the same rule: nothing here duplicates what is already derivable or
already inherited.

- `created_at` / `updated_at` / `created_by` / `updated_by` — inherited from
  `BaseModel` via `TenantScopedModel`.
- "Number of nights" — derivable from `start_date` / `end_date`; a stored copy is
  a second source of truth that drifts the moment someone edits a date.
- "Customer ID / Customer Link" — that *is* the `customer` FK.
- Documents / Voucher — covered by the single `attachments` `GenericRelation` on
  `ServiceRecordBase`, so there is no per-model attachment field.

`GenericRelation` on an abstract base works because Django deep-copies private
fields into each concrete subclass, so all six service records get their own
`attachments` manager.

`Package` has its own `attachments` for trip-wide paperwork. Vouchers that belong
to one hotel or ticket stay on that booking.

## Tenant scoping

Every model inherits `TenantScopedModel`, so `company` is required and PROTECT and
the reverse accessor on `Company` is `company.bookings_<model>_set`.

Nothing here filters automatically. When selectors land, they must take `company`
as an explicit parameter — no thread-locals, no ambient context — exactly like
`customers`. The reverse accessor from `Customer` (`customer.ticketingbooking_set`,
`customer.hajjbooking_set`, …) is inherently same-tenant because a customer
belongs to one company, but a direct `TicketingBooking.objects.filter(...)` that
omits `company` returns every tenant's tickets. `TenantIsolationTests` states that
contract explicitly rather than leaving it implied.

## Admin

All seven models are registered. The six service records share a
`ServiceRecordAdmin` base class, so common presentation is defined once and each
subclass appends only its own columns. `customer` and `sales_agent` use
autocomplete rather than plain selects — both tables grow without bound in a live
CRM, and rendering every customer into a dropdown is how an admin page stops
loading.

## API

All seven resources are `ModelViewSet`s under `/api/v1/`: `hajj`, `umrah`, `tours`,
`ticketing`, `hotels`, `transport`, `packages`. Each supports full CRUD, uses
`TenantScopedViewSetMixin` for company scoping and audit stamping, returns a lean
list serializer on `list` and the full serializer on `retrieve`, and exposes the
generic document routes:

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/hajj/{id}/attachments/` | GET, POST | Documents for one Hajj record (`multipart`: `file`, optional `doc_type`) |
| `/api/v1/hajj/{id}/attachments/` | GET, POST | Same shape on every other resource |
| `/api/v1/attachments/` | GET, POST | The generic collection; filter by `content_type` + `object_id` |
| `/api/v1/attachments/{id}/` | GET, PATCH, DELETE | Relabel (`doc_type`), or delete. No `PUT`, and the target cannot be re-pointed |

`booking_reference` is **auto-generated** on create (`HJ-2026-000001`, per company,
per year, resetting each January) unless the caller supplies a real supplier
reference — see `bookings/utils.py` and `BookingReferenceMixin`. The frontend is
not expected to send one.

## What this pass does not include

- **No booking-level document *type* taxonomy.** Attachments are labelled with
  free-text `doc_type`; a controlled vocabulary per company is Module 02+.
- **No `ServiceLink` usage yet.** The "Linked X Record" fields on the service
  sheets are optional and hidden by default; the generic cross-reference model is
  already in `common` for when that feature is built. The `Package` M2M
  composition is the mechanism for the outbound+return ticket case today.
- **No indexes beyond the FK indexes Django creates.** The likely composite
  candidates (`(company, customer)` for "this customer's bookings",
  `(company, start_date)` for date-window reporting) were left out because
  guessing index strategy before the query patterns exist costs write throughput
  for nothing. Add them with the selectors that need them.

## Known gaps

- Nothing prevents a booking from pointing at a `Customer` belonging to a
  different company, or a `Package` from mixing components across tenants. The
  writing service owns that check — the same open gap already documented for
  `common.Attachment` and `common.ServiceLink`.
- `customer` being PROTECT means a GDPR-style erasure cannot be a single
  `delete()`. That is intended, but it does mean Module 07 needs a deliberate
  purge workflow.
- `amount` and `currency` are the only commercial fields here. Payments,
  instalments and receipts are not modelled yet.

## Tests

`bookings/tests/test_models.py` — 44 structural tests: app shape and model
inventory, choice/column widths, inherited field shapes and defaults, both PROTECT
edges and the SET_NULL edges, tenant isolation, `Package` composition and
unlinking, per-service field behaviour, and that a minimal record is actually
possible.

```bash
python manage.py test bookings
```
