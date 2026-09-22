# SUFABASE — Frontend API Integration Guide

**Module 01 — Foundation Release.** Everything the frontend needs to build against
this API: authentication, the response envelope, every endpoint, every payload,
every filter, every choice value, and the file-upload flows.

Written to be read top-to-bottom once, then used as a reference.

| | |
|---|---|
| **Base URL (local)** | `http://localhost:8000` |
| **Interactive docs (Swagger UI)** | `http://localhost:8000/api/docs/` |
| **Raw OpenAPI 3.0 schema** | `http://localhost:8000/api/schema/` |
| **Schema files in the repo** | `docs/openapi-schema.yml`, `docs/openapi-schema.json` |
| **API version prefix** | `/api/v1/` |

> The Swagger UI at `/api/docs/` is generated from the same code these tables
> describe, and it is always current. Where this document and Swagger disagree,
> Swagger is right — regenerate the schema files (see §15) and tell the backend.

---

## 1. The three things that break integrations first

Read these before anything else. Almost every "the API is broken" report in this
project so far has been one of these three.

1. **Every tenant endpoint needs `X-Company-ID`.** A valid token without that
   header is rejected with `403`, on purpose. See §4.
2. **Every response is wrapped in `{success, message, data, errors}`.** The
   payload is under `data`, not at the top level. See §5.
3. **Every list is paginated with a fixed page size of 10.** The rows are under
   `data.results`. See §6.

---

## 2. Getting a token (staff login)

```
POST /api/v1/token/
Content-Type: application/json
```

```json
{ "username": "admin", "password": "Sufa@2024!" }
```

`200 OK` — `data` contains:

```json
{
  "refresh": "eyJhbGciOi...",
  "access": "eyJhbGciOi..."
}
```

The **access token** is a JWT carrying four custom claims the frontend can read
without a second request:

| Claim | Type | Meaning |
|---|---|---|
| `user_id` | `string` | Staff user id |
| `username` | `string` | Login name |
| `company_id` | `string` | **The value to send as `X-Company-ID`** |
| `role` | `string` | `admin` \| `manager` \| `agent` |
| `is_staff` | `bool` | Django staff flag |

> `company_id` and `user_id` are **strings** because SimpleJWT stringifies its own
> `user_id` claim. Compare with `String(companyId)`, never with `===` against a
> number. This is pinned by tests on the backend side; it will not change.

**Refresh** — access tokens live 7 minutes by default, refresh tokens 1 day:

```
POST /api/v1/token/refresh/
{ "refresh": "<refresh token>" }
```
Returns a new `access` **and** a new `refresh` (rotation is on), so always store
the returned `refresh` over the one you sent.

**Logout** — blacklists the refresh token server-side:

```
POST /api/v1/token/logout/
{ "refresh": "<refresh token>" }
```

---

## 3. Two headers on every request after login

```
Authorization: Bearer <access token>
X-Company-ID: <company_id from the token claim>
```

Why both:

- `Authorization` proves **who** you are.
- `X-Company-ID` proves **which tenant's data** this request is for, and it is
  checked against your own `company_id`. Sending another company's id is rejected
  — it is not a "view as" switch, and there is no way to widen your scope from
  the client.

Rules of thumb:

- A missing or mismatched `X-Company-ID` returns `403` with
  `{"success": false, "message": "Permission denied", ...}`.
- You do **not** send `company` in any request body or query string. Tenant
  scoping is server-side only; every `?company=` you might see in the schema is
  advisory for platform-level callers and is not needed by the frontend.
- CORS is already configured for `http://localhost:5173` and
  `http://127.0.0.1:5173`, with `x-company-id` in the allowed headers.

**Recommended client wrapper** (fetch):

```ts
const API = 'http://localhost:8000';

async function api<T>(path: string, init: RequestInit = {}): Promise<ApiResponse<T>> {
  const token = sessionStorage.getItem('access');
  const companyId = sessionStorage.getItem('companyId');

  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      // Never set Content-Type manually for FormData — the browser must add
      // the multipart boundary itself.
      ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      Authorization: `Bearer ${token}`,
      'X-Company-ID': companyId ?? '',
      ...(init.headers ?? {}),
    },
  });

  const json = await res.json();
  if (!json.success) throw new ApiError(res.status, json.message, json.errors);
  return json;
}
```

---

## 4. The response envelope

Every JSON response — success or failure — has exactly this shape. There are no
exceptions to plan around.

```ts
type ApiResponse<T> = {
  success: boolean;
  message: string;
  data: T | null;
  errors: Record<string, string[]> | { detail: string } | null;
};
```

**Success (GET):**

```json
{ "success": true, "message": "Success", "data": { "id": 12, "full_name": "Ahmed Khan" }, "errors": null }
```

**Success (POST / PATCH / DELETE):**

```json
{ "success": true, "message": "Created successfully", "data": { "id": 12 }, "errors": null }
```

**Validation failure (400)** — `errors` is a field → messages map, ready to render
next to the inputs:

```json
{
  "success": false,
  "message": "Validation failed",
  "data": null,
  "errors": { "phone": ["This field is required."] }
}
```

**Not found / forbidden / unauthenticated (404 / 403 / 401)** — `errors` is
`{ "detail": "..." }`:

```json
{ "success": false, "message": "Not found", "data": null, "errors": { "detail": "Not found." } }
```

### `message` values

| Situation | `message` |
|---|---|
| `GET` success | `Success` |
| `POST` success | `Created successfully` |
| `PUT` / `PATCH` success | `Updated successfully` |
| `DELETE` success | `Deleted successfully` |
| `400` | `Validation failed` |
| `401` | `Authentication required` |
| `403` | `Permission denied` |
| `404` | `Not found` |
| `500` | `Something went wrong` |

`message` is a convenience for toasts. **Branch on `success` and on field keys
inside `errors`, never on `message`** — the text is not part of the contract.

### The one exception: the CSV template download

`GET /api/v1/customers/template/` returns a **raw CSV file** (`text/csv`,
`Content-Disposition: attachment`), not a JSON envelope. Handle it as a blob
download. Every other endpoint follows the envelope.

---

## 5. Pagination

Every list endpoint is paginated, fixed page size **10**:

```
GET /api/v1/customers/?page=2
```

```json
{
  "success": true,
  "message": "Success",
  "data": {
    "count": 240,
    "next": "http://localhost:8000/api/v1/customers/?page=3",
    "previous": "http://localhost:8000/api/v1/customers/?page=2",
    "results": [ { "id": 12, "full_name": "Ahmed Khan" } ]
  },
  "errors": null
}
```

- `next` / `previous` are absolute URLs or `null`.
- The page size is **not** client-configurable in Module 01 — `?page_size=` is
  ignored. Build list UIs with server-side pagination from the start.
- **The two exceptions:** the nested attachment list
  (`/<resource>/{id}/attachments/`) returns a plain array in `data`, not a
  paginated envelope. It is bounded by how many documents one record has.

---

## 6. Filtering, search and ordering

Uniform across every list endpoint:

| Parameter | Example | Notes |
|---|---|---|
| `?page=` | `?page=3` | Pagination |
| `?search=` | `?search=ahmed` | Substring across that endpoint's search fields (§7 lists them per endpoint) |
| `?ordering=` | `?ordering=-created_at` | Prefix `-` for descending. An unknown field is **silently dropped** (the default order wins) — validate against the per-endpoint ordering list |
| field filters | `?status=CONFIRMED&city=Lahore` | Per endpoint, listed in §7 |

Conventions inside filters:

| Spelling | Meaning |
|---|---|
| `?name=ali` | Substring match (`icontains`) — the default |
| `?name_exact=ali` | Whole-value match, for identifiers people paste |
| `?field=a,b,c` | Any of several values (OR) |
| `?field_not=a,b` | Not any of those values |
| `?has_x=true` / `false` | Presence filter. **A bad value is a `400`**, never a silently unfiltered list |
| `?created_after=2026-01-01T00:00:00Z` | Available on every endpoint, paired with `created_before`, `updated_after`, `updated_before` |

---

## 7. Endpoint reference

Tenant-scoped endpoints (`everything except Auth`) require both headers and return
`403` without them.

### 7.1 Auth — tag `Auth`

| Method | Path | Body | Notes |
|---|---|---|---|
| `POST` | `/api/v1/token/` | `{username, password}` | No auth required. Returns `access`, `refresh` |
| `POST` | `/api/v1/token/refresh/` | `{refresh}` | No auth required. Returns rotated `access` + `refresh` |
| `POST` | `/api/v1/token/logout/` | `{refresh}` | Blacklists the refresh token |

### 7.2 Users — tag `Users`

Read-only in Module 01. Creating staff accounts is a Module 02 concern; until
then accounts come from `createsuperuser` / Django admin.

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/v1/users/` | Staff directory, company-scoped |
| `GET` | `/api/v1/users/{id}/` | One staff member |
| `GET` | `/api/v1/users/me/` | **The logged-in user's own profile** — use this to hydrate the nav/avatar |

**User object** (`UserSerializer`):

```json
{
  "id": 22, "username": "admin", "email": "admin@sufainternational.com",
  "first_name": "", "last_name": "", "phone": "", "role": "admin",
  "is_active": true, "is_staff": true,
  "company": 21, "company_name": "SUFA International",
  "date_joined": "2026-09-14T10:00:00Z",
  "created_at": "...", "updated_at": "..."
}
```

**User mini object** — used nested wherever a staff member is referenced
(`sales_agent`, `assigned_counselor`, `assigned_agent`, `uploaded_by`):

```json
{ "id": 22, "username": "admin", "full_name": "Admin User", "email": "admin@sufainternational.com" }
```

**Filters:** `company`, `username`, `username_exact`, `email`, `email_exact`,
`full_name`, `first_name`, `last_name`, `phone`, `phone_exact`, `role`,
`role_in`, `role_not`, `is_active`, `is_staff`, `is_superuser`, `never_logged_in`,
`date_joined_after` / `date_joined_before`, `last_login_after` / `last_login_before`,
`created_after` / `created_before`, `updated_after` / `updated_before`.

**Search:** `username`, `email`, `first_name`, `last_name`, `phone`, `company__name`.
**Ordering:** `username` (default), `email`, `first_name`, `last_name`, `role`,
`is_active`, `date_joined`, `last_login`, `created_at`, `updated_at`, `company__name`.

### 7.3 Tenant directory — tag `Tenants`

Read-only. Company create/edit is Module 07 platform-admin work.

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/v1/companies/` | Company list |
| `GET` | `/api/v1/companies/{id}/` | One company |

Fields: `id`, `name`, `slug`, `legal_name`, `registration_number`, `tax_number`,
`contact_email`, `contact_phone`, `website`, `address`, `address_line1`,
`address_line2`, `city`, `state`, `postal_code`, `country`, `currency`,
`timezone`, `logo_url`, `plan`, `is_active`, `onboarded_at`, `created_at`,
`updated_at`. All read-only.

**Filters:** `name`, `slug`, `legal_name`, `contact_email`, `contact_phone`,
`city`, `country`, `plan`, `is_active` + the standard timestamp ranges.

### 7.4 Company settings — tag `Settings`

This is the endpoint the settings screen uses. It always acts on **your own
company** — there is no id in the path.

| Method | Path | Body |
|---|---|---|
| `GET` | `/api/v1/settings/company/` | — |
| `PATCH` | `/api/v1/settings/company/` | Any subset of the fields below |

```json
{
  "id": 21,
  "name": "SUFA International",
  "legal_name": "SUFA International (Pvt) Ltd",
  "slug": "sufa-international",
  "registration_number": "REG-001",
  "tax_number": "NTN-1234567",
  "email": "info@sufainternational.com",
  "phone": "+92-42-35780001",
  "website": "https://sufainternational.com",
  "address_line1": "Office 12, 3rd Floor, Al-Faisal Plaza",
  "address_line2": "Main Boulevard, Gulberg III",
  "city": "Lahore",
  "state": "Punjab",
  "postal_code": "54000",
  "country": "Pakistan",
  "currency": "PKR",
  "timezone": "Asia/Karachi",
  "logo_url": "https://sufainternational.com/logo.png"
}
```

- Field names here are the **frontend-facing** ones: `email` maps to the model's
  `contact_email`, and `phone` to `contact_phone`. Send and read the names above.
- `PATCH` (not `PUT`) — send only what changed. `email`, `phone`, `website`,
  `logo_url`, `currency`, `timezone` may be empty strings.
- `id` and `slug` are read-only. `slug` is the stable identifier; changing it is a
  deliberate later operation, not a settings-panel action.

### 7.5 Dashboard — tag `Dashboard`

```
GET /api/v1/dashboard/summary/
```

Everything is already scoped to your company, so no parameters are needed.

```json
{
  "total_customers": 128,
  "new_customers_this_month": 14,
  "total_revenue": "4820000.00",
  "currency": "PKR",
  "service_totals": [
    { "service_type": "hajj", "count": 12, "amount": "1800000.00" },
    { "service_type": "umrah", "count": 31, "amount": "1240000.00" },
    { "service_type": "tour", "count": 9, "amount": "540000.00" },
    { "service_type": "ticketing", "count": 44, "amount": "660000.00" },
    { "service_type": "hotel", "count": 18, "amount": "310000.00" },
    { "service_type": "transport", "count": 22, "amount": "150000.00" },
    { "service_type": "visa_consultancy", "count": 16, "amount": "90000.00" },
    { "service_type": "study_visa", "count": 7, "amount": "30000.00" }
  ],
  "upcoming_departures": [
    {
      "id": 8, "service_type": "hajj", "customer_name": "Ahmed Khan",
      "destination": "Jeddah", "start_date": "2026-05-20",
      "booking_reference": "HJ-2026-000008", "status": "CONFIRMED",
      "amount": "150000.00"
    }
  ],
  "recent_activity": [
    {
      "id": 41, "service_type": "ticketing", "customer_name": "Fatima Khan",
      "action": "created", "description": "Ticketing TK-2026-000041",
      "timestamp": "2026-09-21T19:40:00Z"
    }
  ]
}
```

Notes that matter for rendering:

- **`service_totals` always has all 8 rows**, including zeros, in the order above.
  Do not build the legend from the response length.
- **Money is a string**, not a number (`"4820000.00"`). Parse it or format it
  directly — do not `Number()` it into a float if you care about paisa.
- `currency` is the company's currency, so label totals with it rather than
  hardcoding `PKR`.
- `upcoming_departures` is capped at the next 10 by `start_date`; `recent_activity`
  is the last 10 records created across all eight services.

### 7.6 Customers — tag `Customers`

| Method | Path | Serializer | Notes |
|---|---|---|---|
| `GET` | `/api/v1/customers/` | List | Table view — 9 fields only |
| `POST` | `/api/v1/customers/` | Write | Create |
| `GET` | `/api/v1/customers/{id}/` | Detail | Full profile + `service_summary` |
| `PATCH` | `/api/v1/customers/{id}/` | Write | Partial update |
| `PUT` | `/api/v1/customers/{id}/` | Write | Full update |
| `DELETE` | `/api/v1/customers/{id}/` | — | `204`, or `409` if the customer still has bookings — see below |
| `GET` | `/api/v1/customers/{id}/attachments/` | — | §7.12 |
| `POST` | `/api/v1/customers/{id}/attachments/` | — | §7.12 |
| `GET` | `/api/v1/customers/template/` | — | CSV template download (raw file) |
| `POST` | `/api/v1/customers/bulk-upload/` | — | CSV import |

**Deleting a customer that still has bookings is a `409`, not a delete.**

```json
{
  "success": false,
  "message": "Cannot delete: other records depend on this one",
  "data": null,
  "errors": {
    "detail": "This record cannot be deleted because other records depend on it. Blocking records: HajjBooking (1). Deactivate or archive it instead, or clear those records first.",
    "blocking_records": { "HajjBooking": 1 }
  }
}
```

Render `blocking_records` as the list of things standing in the way, and offer
`record_status = ARCHIVED` as the alternative — that is the intended path. The
same `409` shape applies to deleting a company that still holds data.

**List object** (`9 fields` — deliberately lean):

```json
{
  "id": 12, "avatar": "http://localhost:8000/media/customers/avatars/2026/09/a.png",
  "full_name": "Ahmed Khan", "phone": "03001234567", "city": "Lahore",
  "profession": "Doctor", "stage": "NEW", "record_status": "ACTIVE",
  "tags": [{ "id": 3, "name": "VIP", "color": "#FFD700" }]
}
```

**Detail object** adds every profile field plus derived data:

| Group | Fields |
|---|---|
| Identity | `full_name`, `father_husband_name`, `gender`, `date_of_birth`, `cnic_number`, `cnic_expiry_date`, `passport_number`, `passport_issue_date`, `passport_expiry_date`, `nationality`, `marital_status` |
| Contact | `phone`, `whatsapp_number`, `alt_phone`, `email` |
| Location | `country`, `city`, `location_area`, `sub_location`, `complete_address` |
| Professional | `profession`, `business_type`, `company_name`, `designation`, `business_address`, `business_contact_number` |
| CRM | `customer_source`, `referred_by`, `preferred_contact_method`, `preferred_language`, `assigned_agent`, `notes` |
| Status | `stage`, `record_status` |
| Marketing | `marketing_contact_permission` |
| Emergency | `emergency_contact_name`, `emergency_contact_relationship`, `emergency_contact_number` |
| Relations | `family_group_reference`, `tags`, **`service_summary`**, `attachments` endpoint |
| Derived / inherited | `avatar`, `company`, `created_at`, `updated_at` |

`assigned_agent` is a **nested user mini object** (or `null`), not an id.
`tags` is a nested array of tag objects, not ids.

**`service_summary`** — the per-service record counts, so the profile page does
not need eight extra calls:

```json
{ "hajj": 2, "umrah": 1, "tour": 0, "ticketing": 3,
  "hotel": 2, "transport": 4, "visa_consultancy": 1, "study_visa": 0 }
```

**Creating a customer** — only `full_name` and `phone` are required:

```json
POST /api/v1/customers/
{
  "full_name": "Ahmed Khan",
  "phone": "03001234567",
  "whatsapp_number": "03001234567",
  "gender": "Male",
  "date_of_birth": "1990-05-15",
  "cnic_number": "35202-1234567-1",
  "passport_number": "AB1234567",
  "passport_expiry_date": "2030-01-01",
  "city": "Lahore",
  "country": "Pakistan",
  "profession": "Doctor",
  "stage": "NEW",
  "record_status": "ACTIVE",
  "assigned_agent": 22,
  "tags": [3, 7]
}
```

- **Never send** `company`, `created_by`, `updated_by`, `created_at`, `updated_at`
  — the server sets or owns all of them. Sending `company` is ignored, not an error.
- `tags` takes **tag ids** on write and returns **tag objects** on read.
- `assigned_agent` takes a **user id** on write (must belong to your company —
  another company's id is a `400`, not a silent cross-tenant link).
- Dates are `YYYY-MM-DD`; timestamps are ISO 8601 with `Z`.
- Empty optional fields: send `""` for text, `null` for dates/ids.

#### Customer field filters (all of them)

**Identity:** `full_name`, `full_name_exact`, `father_husband_name`, `gender`,
`nationality`, `marital_status`, `date_of_birth_after`, `date_of_birth_before`

**Documents:** `cnic_number`, `cnic_number_exact`, `passport_number`,
`passport_number_exact`, `cnic_expiry_after`, `cnic_expiry_before`,
`passport_expiry_after`, `passport_expiry_before`, `passport_issued_after`,
`passport_issued_before`

**Contact:** `phone`, `phone_exact`, `whatsapp_number`, `alt_phone`, `email`,
`email_exact`, `has_email`, `has_whatsapp`, `has_avatar`

**Location:** `country`, `city`, `location_area`, `sub_location`, `address`

**Professional:** `profession`, `business_type`, `company_name` (the customer's
*employer*, not your tenant), `designation`, `business_address`,
`business_contact_number`

**CRM:** `customer_source`, `referred_by`, `preferred_contact_method`,
`preferred_language`, `assigned_agent`, `assigned_agent_in`, `unassigned`,
`has_notes`

**Status:** `stage`, `stage_in`, `stage_not`, `record_status`,
`record_status_in`, `record_status_not`

**Tags:** `tags` (any of these tag ids), `all_tags` (must have **all** of them),
`tag_name` (substring on the tag name), `has_tags`

**Other:** `family_group_reference`, `has_attachments`,
`marketing_contact_permission`, `emergency_contact_name`,
`emergency_contact_relationship`, `emergency_contact_number`

**Search:** `full_name`, `father_husband_name`, `phone`, `whatsapp_number`,
`alt_phone`, `email`, `cnic_number`, `passport_number`, `city`, `location_area`,
`sub_location`, `company_name`, `profession`, `designation`, `customer_source`,
`referred_by`, `family_group_reference`, `emergency_contact_name`,
`assigned_agent__username`, `notes`.

**Ordering:** `full_name` (default), `phone`, `city`, `country`, `stage`,
`record_status`, `date_of_birth`, `passport_expiry_date`, `created_at`,
`updated_at`, `assigned_agent__username`.

Examples:

```
GET /api/v1/customers/?stage=NEW&city=Lahore&has_avatar=false
GET /api/v1/customers/?profession=doctor&record_status=ACTIVE&ordering=-created_at
GET /api/v1/customers/?all_tags=3,5&has_attachments=false
GET /api/v1/customers/?search=03001234567
GET /api/v1/customers/?stage_not=ARCHIVED&unassigned=true
```

### 7.7 Tags — tag `Customers`

| Method | Path |
|---|---|
| `GET` | `/api/v1/tags/` |
| `POST` | `/api/v1/tags/` |
| `GET` | `/api/v1/tags/{id}/` |
| `PATCH` | `/api/v1/tags/{id}/` |
| `DELETE` | `/api/v1/tags/{id}/` |

```json
{ "id": 3, "name": "VIP", "color": "#FFD700" }
```

- `name` is required and unique **per company**. A duplicate returns `400` with
  `{"errors": {"name": ["A tag with this name already exists for your company."]}}`
  — it is not a `500`.
- `color` is a free string; the `#RRGGBB` convention is a frontend decision, not
  enforced by the API.
- These are the ids you put in a customer's `tags` array.

### 7.8 Customer CSV — template + bulk upload

**Download the template:**

```
GET /api/v1/customers/template/
→ text/csv, attachment; filename="customer_import_template.csv"
```

Raw file, no JSON envelope. 37 columns with one example row.

**Upload a CSV:**

```
POST /api/v1/customers/bulk-upload/
Content-Type: multipart/form-data
Body: file=<the .csv>
```

```json
{
  "total_rows": 5,
  "created": 3,
  "errors": [
    { "row": 3, "errors": { "full_name": "full_name is required." } },
    { "row": 5, "errors": { "stage": "Invalid value \"PENDING\". Must be one of: NEW, OLD" } }
  ],
  "tags_created_or_linked": 4
}
```

Behaviour to build UI around:

- **Required columns:** `full_name`, `phone`. Missing columns → `400` for the whole
  file (nothing is imported). Missing values in a row → that row is rejected.
- **Every other column is optional.** Empty cells become blank/null. You can
  import a file with only the two required columns filled in.
- **Partial success is the norm.** Good rows are created, bad rows are reported by
  row number together with the field and the reason. `created + errors.length`
  equals `total_rows`.
- Dates must be `YYYY-MM-DD`. `stage` must be `NEW` or `OLD`. `record_status` must
  be one of `ACTIVE` / `INACTIVE` / `ARCHIVED`.
- `tags` is one cell with comma-separated names (`"VIP, Hajj-2026"`); tags that do
  not exist yet are created automatically.
- Rows set `created_by` to the uploading user and `company` to your tenant. There
  is no way to import into another company.
- Row numbers in `errors` are **data rows**, counting from 1 after the header.

### 7.9 Bookings — tag `Bookings`

Six service records share one API shape. The trip bundle and the sellable
package are separate resources, documented after the six.

Every service record:

- supports `GET` list, `POST`, `GET {id}`, `PATCH {id}`, `PUT {id}`, `DELETE {id}`
- supports `GET {id}/attachments/` and `POST {id}/attachments/` (§7.12)
- is company-scoped, and **filters + search always include the customer's name and
  phone** so a single search box can find "Ahmed Khan's Hajj"
- returns a **lean list serializer** on list and the **full write serializer** on
  retrieve, so detail pages have everything and tables stay small
- has a nested `customer` (mini) and `sales_agent` (user mini) in every list row

| Resource | Path | Prefix for `booking_reference` |
|---|---|---|
| Hajj | `/api/v1/hajj/` | `HJ-YYYY-NNNNNN` |
| Umrah | `/api/v1/umrah/` | `UM-YYYY-NNNNNN` |
| Tours | `/api/v1/tours/` | `TR-YYYY-NNNNNN` |
| Ticketing | `/api/v1/ticketing/` | `TK-YYYY-NNNNNN` |
| Hotels | `/api/v1/hotels/` | `HT-YYYY-NNNNNN` |
| Transport | `/api/v1/transport/` | `TP-YYYY-NNNNNN` |
| Packages (booked bundle) | `/api/v1/packages/` | — |
| Package components (links) | `/api/v1/package-components/` | — |
| Package templates (sellable spec) | `/api/v1/package-templates/` | — |

#### `booking_reference` is auto-generated

**Do not send it.** If you leave it out, the server assigns the next value for
your company and that year:

```json
POST /api/v1/hajj/  { "customer": 12, "hajj_year": "2026", "package_name": "Economy Hajj" }
→ 201  "booking_reference": "HJ-2026-000001"
```

If you *do* send one (a supplier's or agent's own reference), the server keeps it
verbatim. Sequences are per company, per year, and reset each January — so always
display the full string, never just the number.

#### Fields shared by all six service records

`id`, `customer`, `booking_reference`, `start_date`, `end_date`, `amount`,
`currency` (default `PKR`), `sales_agent`, `status`, `notes`, `created_at`,
`updated_at`.

`start_date` / `end_date` are reused per service line:

| Service | `start_date` / `end_date` mean |
|---|---|
| Tour, Ticketing | departure / return |
| Hotel | check-in / check-out |
| Transport | pickup date / drop-off date |
| Hajj, Umrah | *unused* — null. Those are sold by year/season |

#### Fields that become required by status

Some component fields **provably cannot be known when the record is created** — a
record is created the moment it is *sold*, not the moment it is *delivered*.
Rather than forcing staff to type a placeholder (a `"PENDING"` sitting in a PNR
column is indistinguishable from a real PNR forever), those fields are required
only once the record reaches the status where they must exist:

| Endpoint | Field | Required from | Why not always |
|---|---|---|---|
| `/api/v1/ticketing/` | `pnr` | `ISSUED`, `REISSUED` | A PNR does not exist until the ticket is issued — yet the default status is `RESERVED`, which means "not issued yet" |
| `/api/v1/hotels/` | `lead_guest_name` | `CONFIRMED`, `COMPLETED` | A group booking goes in before the rooming list arrives |
| `/api/v1/transport/` | `pickup_time` | `DRIVER_ASSIGNED`, `COMPLETED` | The time is settled after the vehicle is booked; nobody can be *dispatched* without it |

What this means for the frontend:

- **Create succeeds without them.** `POST /api/v1/ticketing/` with no `pnr` returns
  `201` and `pnr: ""`. Same for the other two (`null` for `pickup_time`).
- **Driving the status forward is what triggers the check.** `PATCH {"status": "ISSUED"}`
  on a PNR-less ticket returns:
  ```json
  { "success": false, "message": "Validation failed", "data": null,
    "errors": { "pnr": ["This field is required once status is \"ISSUED\"."] } }
  ```
- **Send both together** and it passes in one call —
  `PATCH {"pnr": "ABC123", "status": "ISSUED"}`.
- **Setting the field alone never forces the status.** `PATCH {"pnr": "ABC123"}` on
  a `RESERVED` ticket is a `200`; the rule is one-directional.
- **Render the form accordingly.** Enable/require the field when the status select
  is on or past the demanding status, rather than marking it required always —
  otherwise the UI will block a sale the API is perfectly happy to accept.
- **The rule is enforced by the database too**, so a record cannot reach those
  statuses by any route without the value. The required-field error is always a
  `400`, never a `500`.

Fields that determine the *price* stay required at every status — you cannot
quote without them: `room_type`, `vehicle_type`, `number_of_passengers`, `origin`,
`destination`, `airline`, `passenger_name`. `confirmation_number` is optional
deliberately: plenty of small hotels never issue one.

#### Hajj — `/api/v1/hajj/`

**Required:** `customer`, `hajj_year`, `package_name`

```
hajj_year, application_number, package_name, package_type, stay_in_ksa_days, group_name,
departure_city, status, visa_status, maktab_service_provider,
qurbani_arrangement, room_type, package
```

`status` → `BookingStageChoices`. `visa_status` → `VisaStatusChoices`.
`qurbani_arrangement` → `QurbaniArrangementChoices`.

`application_number` is optional (maximum 100 characters) and holds the external
Hajj application identifier. It is separate from the internally generated
`booking_reference`.

**Filters:** `status`, `customer`, `hajj_year`, `application_number`
**Search:** `booking_reference`, `application_number`, `hajj_year`, `group_name`, `package_name`, `departure_city`, `customer__full_name`, `customer__phone`
**Ordering:** `hajj_year`, `status`, `created_at`, `updated_at`

**Bulk import (CSV)** — match existing customers by passport, one Hajj booking per row:

| Method | Path | Body |
|--------|------|------|
| GET | `/api/v1/hajj/import-template/` | — (plain CSV download, not enveloped) |
| POST | `/api/v1/hajj/import/` | `multipart/form-data`: `file` (CSV), `hajj_year` (one season for the whole file) |

CSV columns: `application_number`, `passport_number` (header aliases such as `hajj_application_id` / `passport` are accepted). Each row creates a Hajj booking for the customer whose passport matches (spaces and case ignored). Rows with no matching customer are listed in `errors` and skipped. Duplicate application ids for the same customer are counted in `skipped`. Response shape: `{ total_rows, created, skipped, hajj_year, errors: [{ row, errors: { field: message } }] }`.

#### Umrah — `/api/v1/umrah/`

**Required:** `customer`, `umrah_year_season`, `package_name`

```
umrah_year_season, package_name, package_category, total_duration_nights,
status, visa_status, room_occupancy_type, package
```

**Filters:** `status`, `customer`, `umrah_year_season`
**Search:** `booking_reference`, `umrah_year_season`, `package_name`, `customer__full_name`, `customer__phone`
**Ordering:** `umrah_year_season`, `status`, `created_at`, `updated_at`

#### Tours — `/api/v1/tours/`

**Required:** `customer`, `tour_name`, `destination_country`

```
tour_name, tour_type, destination_country, destination_city,
number_of_travelers, package_name, itinerary_summary, package
```

`tour_type` → `TourTypeChoices`.

**Filters:** `status`, `customer`, `tour_type`, `destination_country`
**Search:** `booking_reference`, `tour_name`, `destination_country`, `destination_city`, `package_name`, `customer__full_name`, `customer__phone`
**Ordering:** `start_date`, `destination_country`, `status`, `created_at`, `updated_at`

#### Ticketing — `/api/v1/ticketing/`

**Required:** `customer`, `passenger_name`, `airline`, `origin`, `destination`
(**+ `pnr`** from `ISSUED` onwards — see the table above)

```
passenger_name, passenger_type, pnr, e_ticket_number, airline, flight_number,
trip_type, origin, destination, departure_time, arrival_time, cabin_class,
baggage_allowance, ticket_issue_date, refund_status
```

`passenger_type` → `PassengerTypeChoices`, `trip_type` → `TripTypeChoices`,
`cabin_class` → `CabinClassChoices`, `refund_status` → `RefundStatusChoices`.
`pnr` is `""` until the ticket is issued — render it as "not issued yet", not as
missing data.
`status` → `TicketStatusChoices` (default `RESERVED`). `departure_time` /
`arrival_time` are `HH:MM:SS`.

**Filters:** `status`, `customer`, `airline`
**Search:** `booking_reference`, `pnr`, `passenger_name`, `airline`, `origin`, `destination`, `customer__full_name`, `customer__phone`
**Ordering:** `ticket_issue_date`, `status`, `created_at`, `updated_at`

#### Hotels — `/api/v1/hotels/`

**Required:** `customer`, `hotel_name`, `city`, `room_type`
(**+ `lead_guest_name`** from `CONFIRMED` onwards — see the table above)

```
lead_guest_name, hotel_name, country, city, number_of_rooms, room_type,
occupancy_type, number_of_guests, meal_plan, confirmation_number,
supplier_agent, cancellation_deadline
```

`occupancy_type` → `OccupancyTypeChoices`, `meal_plan` → `MealPlanChoices`.
`status` → `HotelStatusChoices` (default `INQUIRY`).

**Filters:** `status`, `customer`, `city`
**Search:** `booking_reference`, `hotel_name`, `lead_guest_name`, `city`, `country`, `confirmation_number`, `customer__full_name`, `customer__phone`
**Ordering:** `start_date`, `city`, `status`, `created_at`, `updated_at`

#### Transport — `/api/v1/transport/`

**Required:** `customer`, `service_type`, `pickup_location`, `dropoff_location`,
`number_of_passengers`, `vehicle_type`
(**+ `pickup_time`** from `DRIVER_ASSIGNED` onwards — see the table above)

```
lead_passenger_name, service_type, trip_type, pickup_location, dropoff_location,
pickup_time, number_of_passengers, vehicle_type, number_of_vehicles,
supplier_vendor, flight_number_arrival_ref
```

`service_type` → `TransportServiceTypeChoices`. `status` →
`TransportStatusChoices` (default `INQUIRY`). `pickup_time` is `HH:MM:SS`.

**Filters:** `status`, `customer`, `service_type`
**Search:** `booking_reference`, `pickup_location`, `dropoff_location`, `vehicle_type`, `supplier_vendor`, `customer__full_name`, `customer__phone`
**Ordering:** `service_type`, `status`, `created_at`, `updated_at`

#### Packages — `/api/v1/packages/` and `/api/v1/package-components/`

A **booked bundle** for one trip. It is not the sellable package. It has a name
and notes, an optional `template` id, and read-only `components` that point at
hotel, ticket, and transport rows created on their own endpoints. It does not
ask for a ticket number, a guest name, or a passenger count.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/packages/` | List |
| `POST` | `/api/v1/packages/` | Create. `name` is required. `template` is an optional id |
| `GET` | `/api/v1/packages/{id}/` | Bundle plus read-only `components` |
| `PATCH` | `/api/v1/packages/{id}/` | Update name, notes, or template. Does not write components |
| `DELETE` | `/api/v1/packages/{id}/` | Deletes the bundle and its link rows. Bookings stay |
| `GET`/`POST` | `/api/v1/packages/{id}/attachments/` | Documents for the whole trip |
| `POST` | `/api/v1/package-components/` | Link an existing booking. Send the package id and exactly one booking id |
| `DELETE` | `/api/v1/package-components/{id}/` | Remove the link. The booking stays |
| `GET` | `/api/v1/package-components/?package={id}` | Links for one bundle |

```json
POST /api/v1/packages/
{ "name": "Family of 4 — Hajj July 2026", "notes": "", "template": 3 }

POST /api/v1/package-components/
{ "package": 5, "hotel_booking": 11 }
```

A component read back on the package looks like:

```json
{
  "id": 9,
  "hotel_booking": 11,
  "ticketing_booking": null,
  "transport_booking": null,
  "label": "Hilton Makkah (Makkah)"
}
```

- Send exactly one of `hotel_booking`, `ticketing_booking`, `transport_booking`,
  and send it as an id. A nested booking object is a `400`. This route never
  creates a hotel, ticket, or transport.
- Create those rows first at `/api/v1/hotels/`, `/api/v1/ticketing/`, or
  `/api/v1/transport/`, then link them.
- The booking must belong to the same company as the package. Another company's
  id is a `400`.
- Several links of the same kind are normal. The same booking cannot be linked
  twice on one package.
- **A bundle has no `customer` and no `price`.** The customer lives on the
  Hajj/Umrah/Tour record. Link the bundle with `package` on that payload.
- Trip-wide paperwork goes on the package attachments. A voucher for one hotel
  goes on that hotel.

**Search:** `name`. **Ordering:** `name`, `created_at`, `updated_at`.

#### Package templates — `/api/v1/package-templates/`

The **sellable package**, written before anyone is booked. A name, notes, and
spec lines. No price, no customer, no ticket number, no guest name, no passenger
count.

| `kind` | Fields you send | Fields you do not send |
|---|---|---|
| `HOTEL` | `city`, `room_type`, `meal_plan`, `nights` | cabin, route, vehicle, guest |
| `FLIGHT` | `cabin_class`, `route` | city, room, meal, nights, vehicle, PNR |
| `TRANSPORT` | `vehicle_type` | hotel fields, cabin, route, passenger count |

`meal_plan` uses the hotel meal-plan choices (`ROOM_ONLY`, `BREAKFAST`,
`HALF_BOARD`, `FULL_BOARD`). `cabin_class` uses `ECONOMY`, `PREMIUM_ECONOMY`,
`BUSINESS`, `FIRST`. Two hotel lines are normal (Makkah and Madinah).

```json
POST /api/v1/package-templates/
{
  "name": "Economy Hajj",
  "notes": "",
  "lines": [
    {"kind": "HOTEL", "city": "Makkah", "room_type": "Quad", "meal_plan": "BREAKFAST", "nights": 5},
    {"kind": "FLIGHT", "cabin_class": "ECONOMY", "route": "LHE-JED"},
    {"kind": "TRANSPORT", "vehicle_type": "Coaster"}
  ]
}
```

Sending `lines` on update replaces the spec lines. Omitting `lines` on a PATCH
leaves them. A line that fills another kind's fields is a `400`, and the
template is not created.

A booked bundle points at a template with `template` on `POST /api/v1/packages/`.
That id must belong to your company. Deleting a template does not delete bundles
that referenced it.

**Search:** `name`. **Ordering:** `name`, `created_at`, `updated_at`.

### 7.10 Consultancy — tag `Consultancy`

Two case-workflow resources. The difference from bookings: a case tracks
`case_open_date` → `decision_date` and a long status chain (consultation →
documents → submission → biometrics → decision) instead of a date range.

| Resource | Path |
|---|---|
| Visa Consultancy | `/api/v1/visa-consultancy/` |
| Study Visa | `/api/v1/study-visa/` |

Both support full CRUD plus `GET`/`POST {id}/attachments/`, and list rows carry the
nested `customer` and `assigned_counselor`.

#### Fields shared by both cases

`id`, `customer`, `destination_country`, `case_open_date`, `decision_date`,
`service_value`, `currency` (default `PKR`), `assigned_counselor`, `notes`,
`created_at`, `updated_at`.

#### Visa Consultancy — `/api/v1/visa-consultancy/`

**Required:** `customer`, `destination_country`, `visa_category`

```
visa_category, purpose_of_travel, intended_travel_date, status, embassy_vac,
application_tracking_reference, application_submission_date, appointment_date,
biometrics_status, document_checklist_status, visa_decision, visa_valid_from,
visa_valid_until, passport_collection_status
```

`visa_category` → `VisaCategoryChoices`, `status` → `VisaCaseStatusChoices`
(default `CONSULTATION`), `biometrics_status` → `BiometricsStatusChoices`,
`document_checklist_status` → `DocumentChecklistStatusChoices`,
`visa_decision` → `VisaDecisionChoices`, `passport_collection_status` →
`PassportCollectionStatusChoices`.

**Filters:** `status`, `customer`, `visa_category`, `visa_decision`
**Search:** `destination_country`, `application_tracking_reference`, `embassy_vac`, `customer__full_name`, `customer__phone`
**Ordering:** `visa_category`, `status`, `case_open_date`, `decision_date`, `created_at`, `updated_at`

#### Study Visa — `/api/v1/study-visa/`

**Required:** `customer`, `destination_country`, `study_level`, `field_of_study`,
`preferred_intake`, `institution`

```
study_level, field_of_study, preferred_intake, institution,
institution_application_status, institution_reference, offer_acceptance_status,
course_start_date, tuition_fee, tuition_deposit_paid, highest_qualification,
english_test_type, english_test_score, academic_documents_status, sop_status,
financial_evidence_status, enrolment_reference_type, enrolment_reference,
status, visa_tracking_reference, visa_application_date, biometrics_status,
medical_tb_status, visa_decision
```

`status` → `StudyVisaApplicationStatusChoices` (default `NOT_READY`).
`institution_application_status` → `InstitutionApplicationStatusChoices`.
`offer_acceptance_status` → `OfferAcceptanceStatusChoices`.
`enrolment_reference_type` → `EnrolmentReferenceTypeChoices`
(`CAS`, `CoE`, `I-20`, `LOA`).

> `english_test_score` is a **string** on purpose (`"7.5"`, `"100"`) — IELTS band
> scores and TOEFL integer scores do not share a numeric type.

**Filters:** `status`, `customer`, `study_level`, `visa_decision`
**Search:** `institution`, `field_of_study`, `destination_country`, `visa_tracking_reference`, `customer__full_name`, `customer__phone`
**Ordering:** `study_level`, `status`, `case_open_date`, `decision_date`, `created_at`, `updated_at`

### 7.11 Attachments — tag `Attachments`

One document model serves every record in the system. There are two ways in, and
the nested way is the one to use.

#### Nested (preferred) — on every attachable resource

```
GET  /api/v1/customers/{id}/attachments/
POST /api/v1/customers/{id}/attachments/
```

The same two routes exist on **all ten** attachable resources:

`customers`, `hajj`, `umrah`, `tours`, `ticketing`, `hotels`, `transport`,
`packages`, `visa-consultancy`, `study-visa`.

**List** — returns a plain array in `data` (not paginated):

```json
{
  "success": true, "message": "Success",
  "data": [
    {
      "id": 30,
      "content_type": "customers.customer",
      "object_id": 12,
      "target_label": "Ahmed Khan",
      "doc_type": "CNIC copy",
      "file": "http://localhost:8000/media/attachments/2026/09/cnic_a1b2c3.png",
      "file_name": "cnic_a1b2c3.png",
      "file_size": 204821,
      "uploaded_by": { "id": 22, "username": "admin", "full_name": "Admin User", "email": "..." },
      "created_at": "2026-09-21T19:40:00Z"
    }
  ],
  "errors": null
}
```

**Upload** — `multipart/form-data`, two fields:

| Field | Required | Notes |
|---|---|---|
| `file` | ✅ | Any file type. Stored under `attachments/YYYY/MM/` |
| `doc_type` | ❌ | Free text label — `"CNIC copy"`, `"Voucher"`, `"Passport scan"` |

```ts
const form = new FormData();
form.append('file', fileInput.files[0]);
form.append('doc_type', 'CNIC copy');
await api(`/api/v1/customers/${customerId}/attachments/`, { method: 'POST', body: form });
```

**Do not send `content_type` or `object_id` on the nested route** — they come from
the URL, which is exactly why this route cannot be pointed at another record.

#### Flat — `/api/v1/attachments/`

For a company-wide document library or scripted uploads.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/attachments/?content_type=customers.customer&object_id=12` | Filtered list (paginated) |
| `POST` | `/api/v1/attachments/` | Needs `content_type` + `object_id` in the payload |
| `GET` | `/api/v1/attachments/{id}/` | One attachment |
| `PATCH` | `/api/v1/attachments/{id}/` | Relabel (`doc_type`) — **the only edit** |
| `DELETE` | `/api/v1/attachments/{id}/` | Removes the row. No `PUT` |

`content_type` uses the string form `"app_label.model"`. The full set of valid
values:

| Value | Attach to |
|---|---|
| `customers.customer` | Customer |
| `bookings.hajjbooking` | Hajj booking |
| `bookings.umrahbooking` | Umrah booking |
| `bookings.tourbooking` | Tour booking |
| `bookings.ticketingbooking` | Ticketing record |
| `bookings.hotelbooking` | Hotel booking |
| `bookings.transportbooking` | Transport record |
| `bookings.package` | Package |
| `consultancy.visaconsultancycase` | Visa consultancy case |
| `consultancy.studyvisacase` | Study visa case |

Anything else is a `400` — including models that exist but did not opt into
attachments (`400` `"users.user" does not support attachments.`).

**Filters:** `content_type`, `object_id`, `object_ids` (comma-separated),
`doc_type`, `has_doc_type`, `uploaded_by` + the standard timestamp ranges.
**Search:** `doc_type`, `content_type__model`, `created_by__username`.
**Ordering:** `created_at` (default `-created_at`), `updated_at`, `doc_type`.

Reset before shipping UI:

- **Attachments cannot be moved** between records. `PATCH` with
  `content_type`/`object_id` returns `200` and **silently keeps the original
  target**. To move a document, delete it and upload it again.
- **Deletion is hard.** A deleted attachment's file URL stops being listed. There
  is no soft-delete and no trash.
- **Deleting a host record does not delete its attachments.** The generic link is
  a plain integer, so no cascade fires — orphan rows are cleaned by a future
  service, not by the API. Do not rely on "delete the booking, the documents go
  too".
- **No file-size limit or allowed-extension list is configured yet.** The browser
  can upload anything. If you need a client-side cap for UX, agree on a number
  with the backend so it can be enforced server-side too.
- **No thumbnails and no virus scanning.** Files are served as uploaded.

---

## 8. Enums — drop-in for select boxes

All values are strings. Send the **value**; display the **label**.

### Customer

`stage`: `NEW` New · `OLD` Old
`record_status`: `ACTIVE` Active · `INACTIVE` Inactive · `ARCHIVED` Archived

### Staff role
`admin` Admin · `manager` Manager · `agent` Agent

### Booking stage (Hajj, Umrah, Tour)
`INQUIRY` Inquiry · `BOOKED` Booked · `CONFIRMED` Confirmed · `COMPLETED` Completed · `CANCELLED` Cancelled

### Visa status (Hajj, Umrah)
`NOT_APPLIED` Not Applied · `IN_PROCESS` In Process · `ISSUED` Issued · `PROBLEM` Rejected / Problem

### Qurbani arrangement
`INCLUDED` Included · `ARRANGED` Arranged · `NOT_APPLICABLE` Not Applicable

### Tour type
`DOMESTIC` Domestic · `INTERNATIONAL` International

### Ticket status
`RESERVED` Reserved · `ISSUED` Issued · `REISSUED` Reissued · `CANCELLED` Cancelled · `REFUNDED` Refunded

### Trip type (Ticketing, Transport)
`ONE_WAY` One-way · `ROUND_TRIP` Round-trip · `MULTI` Multi-city / Multi-leg

### Cabin class
`ECONOMY` Economy · `PREMIUM_ECONOMY` Premium Economy · `BUSINESS` Business · `FIRST` First

### Passenger type
`ADULT` Adult · `CHILD` Child · `INFANT` Infant

### Refund status
`NOT_REQUESTED` Not Requested · `REQUESTED` Requested · `PROCESSED` Processed · `REJECTED` Rejected · `PARTIAL` Partial

### Hotel status
`INQUIRY` Inquiry · `PENDING` Pending · `CONFIRMED` Confirmed · `COMPLETED` Completed · `CANCELLED` Cancelled

### Occupancy type
`SINGLE` Single · `DOUBLE` Double · `TRIPLE` Triple · `QUAD` Quad · `SHARING` Sharing

### Meal plan
`ROOM_ONLY` Room Only · `BREAKFAST` Breakfast · `HALF_BOARD` Half Board · `FULL_BOARD` Full Board

### Transport service type
`AIRPORT_TRANSFER` Airport Transfer · `HOTEL_TRANSFER` Hotel Transfer · `INTERCITY` Intercity · `LOCAL_TRANSFER` Local Transfer · `ZIYARAT` Ziyarat · `SHUTTLE` Shuttle · `PRIVATE_VEHICLE` Private Vehicle

### Transport status
`INQUIRY` Inquiry · `PENDING` Pending · `CONFIRMED` Confirmed · `DRIVER_ASSIGNED` Driver Assigned · `COMPLETED` Completed · `CANCELLED` Cancelled · `NO_SHOW` No-show

### Visa category
`VISIT_TOURIST` Visit / Tourist · `BUSINESS` Business · `FAMILY` Family · `TRANSIT` Transit · `WORK` Work · `OTHER` Other

### Visa case status
`CONSULTATION` Consultation · `DOCUMENTS_PENDING` Documents Pending · `READY_TO_APPLY` Ready to Apply · `SUBMITTED` Submitted · `IN_PROCESS` In Process · `APPROVED` Approved · `REFUSED` Refused · `CLOSED` Closed

### Biometrics status (both case types)
`NOT_REQUIRED` Not Required · `PENDING` Pending · `BOOKED` Appointment Booked · `COMPLETED` Completed

### Document checklist status
`NOT_STARTED` Not Started · `INCOMPLETE` Incomplete · `COMPLETE` Complete · `SUBMITTED` Submitted

### Visa decision (shared by both case types)
`APPROVED` Approved · `REFUSED` Refused · `WITHDRAWN` Withdrawn · `DEFERRED` Deferred · `OTHER` Other

### Passport collection status
`PENDING` Pending · `READY` Ready for Collection · `COLLECTED` Collected · `COURIERED` Couriered

### Study level
`DIPLOMA` Diploma · `FOUNDATION` Foundation · `BACHELORS` Bachelor's · `MASTERS` Master's · `PHD` PhD · `SCHOOL_COLLEGE` School / College · `OTHER` Other

### Institution application status
`NOT_APPLIED` Not Applied · `APPLIED` Applied · `CONDITIONAL_OFFER` Conditional Offer · `UNCONDITIONAL_OFFER` Unconditional Offer · `ACCEPTED` Accepted · `REJECTED` Rejected · `DEFERRED` Deferred

### Offer acceptance status
`PENDING` Pending · `CONDITIONAL` Conditional · `UNCONDITIONAL` Unconditional · `ACCEPTED` Accepted · `NOT_APPLICABLE` Not Applicable

### English test type
`IELTS` IELTS · `PTE` PTE · `TOEFL` TOEFL · `OTHER` Other

### Academic documents status
`INCOMPLETE` Incomplete · `COMPLETE` Complete · `VERIFIED` Verified · `SUBMITTED` Submitted

### SOP status
`NOT_STARTED` Not Started · `DRAFT` Draft · `FINAL` Final · `SUBMITTED` Submitted

### Financial evidence status
`NOT_STARTED` Not Started · `INCOMPLETE` Incomplete · `COMPLETE` Complete · `SUBMITTED` Submitted · `NOT_REQUIRED` Not Required

### Enrolment reference type
`CAS` CAS (UK) · `COE` CoE (Australia) · `I20` I-20 (USA) · `LOA` LOA (Canada) · `OTHER` Other

### Study visa application status
`NOT_READY` Not Ready · `READY_TO_APPLY` Ready to Apply · `SUBMITTED` Submitted · `BIOMETRICS` Biometrics · `IN_PROCESS` In Process · `APPROVED` Approved · `REFUSED` Refused · `CLOSED` Closed

### Medical / TB status
`NOT_REQUIRED` Not Required · `PENDING` Pending · `COMPLETED` Completed

---

## 9. Errors

| Status | When | What the client should do |
|---|---|---|
| `400` | Validation failed, bad filter value, duplicate tag name, CSV problems | Render `errors` per field, or the `detail` message |
| `401` | Missing/expired access token | Refresh once, retry, then send the user to login |
| `403` | Valid token but missing/mismatched `X-Company-ID` | **Not a login problem.** Check the header before logging anyone out |
| `404` | Record does not exist *in your company* | Show "not found" |
| `405` | Method not allowed (e.g. `PUT` on attachment, `POST` on a read-only viewset) | Fix the call |
| `409` | Protected delete — the record still has dependent rows | Read `errors.blocking_records` and tell the user what must be cleared first. There is no client-side way to force it |
| `500` | Unexpected server error | Show a generic error; the response is still JSON |

Two rules that make error handling much simpler:

- **`404` and `403` are the tenant boundary, not bugs.** Another company's record
  is indistinguishable from a non-existent one, on purpose.
- **The body is always JSON**, including `500`s — a `response.json()` will not
  throw on a server error.

---

## 10. Endpoints not in this release

Planned, and deliberately absent from Module 01 — do not build UI that depends on
them yet:

- **Granular roles and permissions.** `role` exists on the user and in the token,
  but nothing enforces it server-side yet. Every logged-in staff member of a
  company can currently read and write that company's data. Permission screens and
  per-field masking arrive in Module 02.
- **Creating/editing staff accounts** (users is read-only).
- **Creating/editing companies** (tenant is read-only).
- **Package pricing and quotations** — the catalog stores specs only, with no price.
- **Payments, invoices and ledgers.**
- **WhatsApp / email campaign records** (Module 05+).
- **Cross-record links** — the generic `ServiceLink` table exists in the schema
  ("Link a ticketing record to this Hajj booking") but has no API yet.
- **File deletion from storage, thumbnails, virus scanning, size limits.**

---

## 11. Suggested TypeScript types

```ts
export type ApiResponse<T> = {
  success: boolean;
  message: string;
  data: T | null;
  errors: Record<string, string[]> | { detail: string } | null;
};

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type StaffRole = 'admin' | 'manager' | 'agent';

export type UserMini = {
  id: number;
  username: string;
  full_name: string;
  email: string;
};

export type CustomerMini = {
  id: number;
  avatar: string | null;
  full_name: string;
  phone: string;
  city: string;
  stage: 'NEW' | 'OLD';
};

export type Tag = { id: number; name: string; color: string };

export type ServiceSummary = {
  hajj: number; umrah: number; tour: number; ticketing: number;
  hotel: number; transport: number; visa_consultancy: number; study_visa: number;
};

export type Attachment = {
  id: number;
  content_type: string;   // "customers.customer"
  object_id: number;
  target_label: string;
  doc_type: string;
  file: string;           // absolute URL
  file_name: string;
  file_size: number | null;
  uploaded_by: UserMini | null;
  created_at: string;
};

// Money is a string on the wire — keep it that way.
export type Money = string;

export type BookingStage =
  | 'INQUIRY' | 'BOOKED' | 'CONFIRMED' | 'COMPLETED' | 'CANCELLED';
```

---

## 12. Keeping this document honest

The schema is generated from the code, so it cannot drift. Regenerate it after any
backend change and diff the files:

```bash
python manage.py spectacular --file docs/openapi-schema.yml --validate
python manage.py spectacular --format openapi-json --file docs/openapi-schema.json --validate
```

`--validate` failing is a backend bug, not a documentation problem.

For typed clients:

```bash
npx openapi-typescript docs/openapi-schema.json -o src/api/types.ts
```

Or import `docs/openapi-schema.json` into Postman (File → Import) to get a
ready-made collection for every endpoint.

---

## 13. Quick integration checklist

- [ ] Login at `/api/v1/token/`, store `access`, `refresh`, and `company_id`
      (read the claim out of the access token).
- [ ] Attach `Authorization` **and** `X-Company-ID` on every request.
- [ ] Unwrap `data` on every response; check `success` first.
- [ ] Read list rows from `data.results`; drive paging from `count` / `next` /
      `previous`.
- [ ] Refresh the token once on `401`, then log out. **Never log out on `403`** —
      that is a header problem.
- [ ] Send only `full_name` + `phone` to create a customer; everything else is
      optional.
- [ ] Never send `booking_reference` for a booking unless you have a real one.
- [ ] Upload documents to `/<resource>/{id}/attachments/` as `FormData`
      (`file`, optional `doc_type`) — and remember not to set `Content-Type`
      yourself.
- [ ] Send `avatar` for a customer as a real image file (validated server-side).
- [ ] Build select boxes from §8, not from a hardcoded list in the frontend.
