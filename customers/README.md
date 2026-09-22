# customers — Customer CRM

The customers app owns the canonical "who is this person" record for every
client in every SUFABASE service line (Hajj, Umrah, Tour, Ticketing, Hotel,
Visa Consultancy, Study Visa, Transport). Service-specific data (booking
references, payment records, ticket numbers) lives in the module that owns the
service; `Customer` holds the identity and contact information that every module
needs but none of them should duplicate.

## Models

### `Customer(TenantScopedModel)`

A single customer identity, company-scoped via the inherited `company` FK.

**Key design decisions:**

| Decision | Why |
|---|---|
| `phone` is required and indexed; `email` is optional | In Pakistan's travel market, phone is the primary identifier — many clients don't have email. |
| `stage` is a `TextChoices` field (`NEW`/`OLD`), not a tag | Stage is a binary pipeline state: is this a prospect or a repeat customer? Tags are free-form labels. |
| `record_status` is a `TextChoices` field (`ACTIVE`/`INACTIVE`/`ARCHIVED`), not a soft-delete flag | Lifecycle status has three meaningful states, not two. ARCHIVED is stronger than INACTIVE and surfaces in different contexts. |
| No `customer_since` field | `created_at` (inherited from `BaseModel`) already answers "when did this relationship start". A manually-editable date would only be useful for historical backfill — that's a business decision, not a schema one. |
| `assigned_agent` is nullable | Not every customer has a dedicated agent. When null, the customer is unassigned. |
| `tags` is M2M, not FK | Customers can have multiple tags, and tags are shared across customers. |
| `attachments = GenericRelation('common.Attachment')` | Documents (CNIC copies, offer letters, vouchers) attach to Customer without a dedicated attachment table. Uploaded and listed through `/api/v1/customers/{id}/attachments/`. |
| `avatar` is a nullable `ImageField`, not `FileField` | Nullable because staff create a customer in seconds (often mid-call) and must never be blocked on a photo. `ImageField` rather than `FileField` so Django validates the bytes really are an image instead of accepting a renamed executable. |
| Composite index on `(company, phone)` | The most common query path: "find this customer in this tenant". |

**Field groups:**

- **Identity** — `avatar`, `full_name`, `father_husband_name`, `gender`, `date_of_birth`, CNIC fields, passport fields, `nationality`, `marital_status`
- **Contact** — `phone`, `whatsapp_number`, `alt_phone`, `email`
- **Location** — `country`, `city`, `location_area`, `sub_location`, `complete_address`
- **Professional** — `profession`, `business_type`, `company_name`, `designation`, `business_address`, `business_contact_number`
- **CRM meta** — `customer_source`, `referred_by`, `preferred_contact_method`, `preferred_language`, `assigned_agent` (FK → `users.User`), `notes`
- **Status** — `stage`, `record_status`
- **Marketing** — `marketing_contact_permission`
- **Emergency** — `emergency_contact_name`, `emergency_contact_relationship`, `emergency_contact_number`
- **Relations** — `family_group_reference`, `tags` (M2M → `Tag`), `attachments` (GenericRelation → `common.Attachment`)

### `Tag(TenantScopedModel)`

A free-form label that can be attached to customers for filtering and
segmentation (e.g. "VIP", "Hajj-2026", "Referral-Partner").

Tags are company-scoped: each tenant maintains its own vocabulary. The
`unique_together` constraint on `(company, name)` prevents duplicate tags within
a company.

### `choices.py`

Choice enumerations live in their own module rather than being inlined as tuples
on model fields. This keeps model files readable and lets views, serializers,
tests and management commands import the full set of valid options without
importing the models themselves.

## Selectors

`CustomerSelector` (`customers/selectors/customer_selectors.py`) owns every query
against `Customer`; `TagSelector` owns the tag vocabulary. Both take `company` as
an explicit parameter and never a `request` object.

| Method | Purpose |
|---|---|
| `for_company(company, search=, stage=, tag=, record_status=)` | Base queryset, optionally narrowed. Always `.distinct()` — the `tag` filter joins through the M2M. |
| `get_by_id(company, customer_id)` | One customer or `None`. Returns `None` for another tenant's id, so a view can answer 404. |
| `get_by_phone(company, phone)` | **Exact** phone match within a tenant, or `None`. Fuzzy matching is the API's `?phone=` filter. |
| `active(company)` | Only `RECORD_STATUS = ACTIVE`. |
| `service_summary(customer)` | `{service_key: count}` across all 8 service types, for one customer. |
| `service_summary_for_customers(customers)` | The same for many customers. **Use this in list views.** |

### The N+1 rules this layer exists to enforce

**Eager loading is declared here, not remembered at each call site.**
`for_company` selects the tenant and assigned agent and prefetches tags, because
that is exactly what the serializer and admin list touch. `select_related` omitted
here would mean three queries per row on every list endpoint.

**`service_summary` costs 8 queries — once, not once per customer.**
`service_summary_for_customers` answers for N customers in the same 8 queries that
`service_summary` uses for one. Calling the singular form in a loop is 8 queries
*per row*: a 25-row page becomes 200 round trips. It hides well because each
individual call looks cheap, so
`test_query_count_does_not_grow_with_the_number_of_customers` asserts the count is
identical for one customer and for many.

**The tenant filter lives in one place.** All eight service models are queried
through `common.selectors.TenantScopedSelector`, so a forgotten `company=` is a
single code change to reason about rather than eight.

**`for_customer` reads `customer.company_id`, not `customer.company`.** The first
is an already-loaded column; the second is a related-object dereference that
silently issues a second SELECT the first time it is touched — an N+1 hidden
inside a parameter. A test pins the query count at 1.

### A note on the trust boundary

`TenantScopedSelector.for_customer(model, customer)` scopes to **that customer's
own tenant**, read off the instance. It is not the guard against cross-tenant
reads — it answers "this person's records" for whoever it is handed.

The guard is the tenant-scoped lookup that produces the customer:
`CustomerSelector.get_by_id(company, pk)` returns `None` for an id outside the
caller's tenant, so a foreign customer can never be passed in. Both halves are
tested together in `bookings/tests/test_selectors.py`, because neither is safe to
change alone.

## API

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/customers/` | GET, POST | List (company-scoped) and create |
| `/api/v1/customers/{id}/` | GET, PUT, PATCH, DELETE | Retrieve, update, delete |
| `/api/v1/tags/` | GET, POST | List (company-scoped) and create |
| `/api/v1/tags/{id}/` | GET, PUT, PATCH, DELETE | Retrieve, update, delete |
| `/api/v1/customers/{id}/attachments/` | GET, POST | List / upload documents for one customer (`multipart`: `file`, optional `doc_type`) |
| `/api/v1/customers/template/` | GET | Download the CSV import template (raw `text/csv`, **not** JSON-wrapped) |
| `/api/v1/customers/bulk-upload/` | POST | Import customers from a CSV (`multipart`: `file`) |

> **Writes are live, not withheld.** Both viewsets are `ModelViewSet`s, so any
authenticated staff member can currently create, edit and delete customer records.
That contradicts the original Module 01 "read-only" intent and is an open decision,
not an oversight — Module 02 is where permission classes are supposed to gate it.

> **Deleting a customer that still has bookings is a `409`, not a delete.** The
> `PROTECT` foreign key from `bookings.ServiceRecordBase` raises a
> `ProtectedError`, and `common/exception_handler.py` maps it to
> `409 {"detail": ..., "blocking_records": {"HajjBooking": 1}}` so the caller is
> told what stood in the way. It used to surface as a generic `500`; the mapping
> is pinned by `common/tests/test_exception_handler.py`. The intended path for a
> customer you are done with is `record_status = ARCHIVED`.

### Filtering and search

Every filter is declared in `customers/filters/customer.py` and
`customers/filters/tag.py`; the parameter vocabulary is shared across the project
(see `ARCHITECTURE.md` → Filtering and search). `GET /api/v1/customers/`
documents 68 query parameters:

| Group | Parameters |
|---|---|
| **Status** | `stage`, `stage_in`, `stage_not`, `record_status`, `record_status_in`, `record_status_not` |
| **Assignment** | `assigned_agent`, `assigned_agent_in`, `unassigned` |
| **Tags** | `tags` (any of), `all_tags` (all of), `tag_name` (substring), `has_tags` |
| **Identity** | `full_name`, `full_name_exact`, `father_husband_name`, `gender`, `nationality`, `marital_status`, `date_of_birth_after` / `_before` |
| **Documents** | `cnic_number`, `cnic_number_exact`, `passport_number`, `passport_number_exact`, `cnic_expiry_after` / `_before`, `passport_expiry_after` / `_before`, `passport_issued_after` / `_before`, `has_attachments` |
| **Contact** | `phone`, `phone_exact`, `whatsapp_number`, `alt_phone`, `email`, `email_exact`, `has_email`, `has_whatsapp`, `has_avatar` |
| **Location** | `country`, `city`, `location_area`, `sub_location`, `address` |
| **Professional** | `profession`, `business_type`, `company_name`, `designation`, `business_address`, `business_contact_number` |
| **CRM meta** | `customer_source`, `referred_by`, `preferred_contact_method`, `preferred_language`, `has_notes` |
| **Emergency** | `emergency_contact_name`, `emergency_contact_relationship`, `emergency_contact_number` |
| **Family** | `family_group_reference` |
| **Audit** | `created_after`, `created_before`, `updated_after`, `updated_before` |
| **Other** | `search` (scalar columns only), `ordering`, `page` |

The two filters worth knowing about:

- `?passport_expiry_before=2027-01-01` answers "whose passport expires before the
  season" — the renewal list, and the reason the expiry dates are filterable at
  all rather than just readable.
- `?all_tags=3,5` is AND (must carry every tag); `?tags=3,5` is OR (any of them).
  Both exist because they answer genuinely different segmentation questions.

`GET /api/v1/tags/` documents 12: `name`, `name_exact`, `color`, `has_color`,
`used`, the four audit ranges, plus `search`/`ordering`/`page`.

An invalid value for any choice, date, number or boolean is a **400**, not a
silently unfiltered list.

## Admin

Both `Customer` and `Tag` are registered in Django admin with sensible
list displays, filters and search. `CustomerAdmin` optimises queries with
`select_related('company', 'assigned_agent')` and `prefetch_related('tags')`.
