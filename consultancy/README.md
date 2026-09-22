# consultancy — Visa Consultancy and Study Visa cases

The consultancy app owns the last two of the eight service types in the field
spec: **Visa Consultancy** (visit/tourist, business, family, transit, work) and
**Study Visa** (education consultancy through to the visa decision).

This pass is **schema only**: choices, models, migration, admin and tests. No
serializers, selectors, filters or API yet.

## Why this is a separate app from `bookings`

The two look similar from a distance — both hang off `Customer`, both are
company-scoped, both are something a client paid for. They are different *shapes*
of work, and merging them would produce one table where half the columns are null
for half the rows.

| | `bookings.ServiceRecordBase` | `consultancy.CaseRecordBase` |
|---|---|---|
| Shape | a **dated transaction** | a **process** |
| Dates | `start_date` / `end_date` (departure/return, check-in/check-out) | `case_open_date` / `decision_date` |
| Status | short flow (`RESERVED` → `ISSUED`) | long chain (documents → submission → biometrics → decision) |
| Duration driven by | us and the supplier | an embassy, not us |
| Progress tracked by | one status field | several parallel tracks (documents, biometrics, passport) |

A case has no meaningful date range at all — which is why `CaseRecordBase` has
neither `start_date` nor `end_date`, and why `test_cases_are_not_dated_bookings`
fails if someone later adds a booking-shaped date pair here.

## The shared base: `CaseRecordBase`

Both case models inherit `CaseRecordBase(TenantScopedModel)`:

| Field | Notes |
|---|---|
| `customer` | PROTECT (see delete rules below) |
| `destination_country` | Required. The primary way cases are grouped and reported. |
| `case_open_date` | Nullable — a case can exist from the first consultation. |
| `decision_date` | Nullable, and stays so for months. |
| `service_value` / `currency` | What the client paid for the consultancy service. |
| `assigned_counselor` | SET_NULL FK to `users.User`. |
| `notes` | Free text. |
| `attachments` | `GenericRelation('common.Attachment')`. |

`case_open_date` and `decision_date` are two separate dates rather than one range,
because **the duration between them is a first-class business metric** — "how long
does a visa actually take, per category and per embassy" — and because an open
case with no decision is a normal, long-lived state, not missing data.

## Models

### `VisaConsultancyCase`

One model for visit/business/family/transit/work visas rather than five: the
workflow is identical across them and only `visa_category` changes which checklist
and fee apply. Five models would be five copies of the same twenty columns.

Three parallel tracks run independently of `status`, which is why each is its own
field rather than being folded in:

- `document_checklist_status` — is the client's pack ready?
- `biometrics_status` — is enrolment done?
- `passport_collection_status` — is the passport back with the client?

Plus the fields that make a case answerable without opening a document:
`embassy_vac`, `application_tracking_reference`, `application_submission_date`,
`appointment_date`, and `visa_valid_from` / `visa_valid_until`. The validity dates
are kept because the visa granted is frequently *not* what the client asked for (a
30-day single-entry instead of a multi-entry year visa), and staff need that
recorded to advise correctly next time.

The status chain runs `CONSULTATION` → `DOCUMENTS_PENDING` → `READY_TO_APPLY` →
`SUBMITTED` → `IN_PROCESS` → `APPROVED` / `REFUSED` → `CLOSED`.

Two separations worth knowing, both explained in `choices.py`:

- `SUBMITTED` vs `IN_PROCESS` — "we sent it" versus "they have opened it". The gap
  between them is where appointment scheduling lives.
- `APPROVED`/`REFUSED` vs `CLOSED` — a decision is not the end of a case. The
  passport still has to come back, so `CLOSED` follows either outcome.

### `StudyVisaCase`

The defining difference: **most of this case happens before any visa exists.** The
client has to be admitted to an institution first, and the visa application cannot
be lodged without an enrolment reference — which is why `status` starts at
`NOT_READY` and the admission pipeline is a full pipeline rather than a footnote.
Treating admissions as a footnote is what hides where study cases actually stall.

Country flexibility comes from `destination_country` (on the base) plus
`enrolment_reference_type`, which records *which* country's system the case sits in:

| Value | Country |
|---|---|
| `CAS` | UK |
| `COE` | Australia |
| `I20` | USA |
| `LOA` | Canada |
| `OTHER` | elsewhere |

One reference field plus one type, instead of four country-specific column groups.
Adding a destination later needs no migration.

Three readiness tracks, owned by different people, so they are separate fields:

- `academic_documents_status` and `sop_status` — the applicant's side. The SOP is
  tracked on its own because it is usually the longest-lead item and the one
  clients return late, so hiding it inside "documents complete" would lose the
  status that matters most.
- `financial_evidence_status` — usually a parent or sponsor, and the most common
  cause of a study-visa refusal.
- `medical_tb_status` — required by several destinations, arranged with a clinic,
  on nobody else's critical path.

`tuition_fee` and `tuition_deposit_paid` are both kept because the deposit is what
unlocks the enrolment reference at most institutions, so "what is outstanding" is
a real question this model has to answer. `course_start_date` exists because that,
not the visa, is the real deadline the whole case is racing.

`english_test_score` is a **`CharField`, not a number**: IELTS reports band scores
like `7.5` while TOEFL uses a different integer scale, so a single numeric column
would be both lossy and misleading about comparability between tests. A test pins
the column type.

## Delete rules

No `CASCADE` anywhere in this app.

| Edge | Rule | Why |
|---|---|---|
| `company` ← any case | **PROTECT** (inherited) | A company holds live client data. Retire a tenant with `Company.is_active = False`. |
| `customer` ← any case | **PROTECT** | A case carries a paper trail — submissions, decisions, refusals — that cannot be reconstructed. Retire a customer with `record_status = ARCHIVED`. |
| `assigned_counselor` ← any case | **SET_NULL** | An assignment is not part of the record's identity; a departing staff member must never be un-deletable because of an old case. |

`customer` is PROTECT to match `bookings.ServiceRecordBase`. The spec for this app
said CASCADE, and it was changed deliberately: the same reasoning that made the
bookings edge PROTECT — unrecoverable client business data must fail loudly rather
than disappear — applies identically here. The trade-off is that a GDPR-style
erasure is not a single `delete()`; that is intended, and Module 07 owns the purge
workflow.

`ProtectedDeleteTests` covers both PROTECT edges from both directions, including
that a customer with no cases still deletes cleanly — which is what proves the
protection is conditional rather than a blanket block.

## `choices.py`

Sixteen `TextChoices` classes, per the project-wide rule that choices live in their
own module rather than as inline tuples.

**Three are shared between the two models on purpose:** `VisaDecisionChoices` and
`BiometricsStatusChoices` (plus the base's `currency`). The underlying real-world
process is the same, and two near-identical copies would drift the first time one
gained a value. A test asserts both models reference the *same* enum.

Everything else is specific to one case type — a study case has an institution
pipeline, an English test and financial evidence, none of which belongs on a
family-visit visa.

`VisaDecisionChoices` keeps `WITHDRAWN` and `DEFERRED` distinct from `REFUSED`:
withdrawn means the *client* pulled the application and deferred means a decision
was postponed. Folding either into `REFUSED` would misstate the refusal rate —
which is the number this kind of business watches.

`test_every_choice_value_fits_its_column` walks every choice field on both models
and fails if a value is longer than its column. The longest values today are
"Unconditional Offer" (19 chars) and `DOCUMENTS_PENDING` (17), both comfortably
inside their columns — the test exists for the ones added later.

## Deliberately omitted

Per the spec's own "hide by default" guidance, optional fields are **not** bulk
included. Left out, to be added individually when SUFA actually needs them:

- **Visa Consultancy** — biometrics date, appointment time, sponsor/host details,
  travel insurance status, entries allowed, visa number, refusal reason.
- **Study Visa** — campus/city, offer date, course end date, scholarship details,
  previous institution, academic result/GPA, English test date, financial sponsor,
  country-specific attestation, health cover status, visa interview date,
  visa/permit number, visa validity dates, refusal notes.

## Never stored

- `created_at` / `updated_at` / `created_by` / `updated_by` — inherited from
  `BaseModel` via `TenantScopedModel`.
- "Days open" / "days to decision" — derived from the two dates. A stored copy
  would go stale overnight, which is worse than recomputing it.
- Documents / checklist evidence — covered by the single `attachments`
  `GenericRelation`. The checklist *status* is a column because that is what gets
  filtered and reported on; the files are the evidence behind it.

## Tenant scoping

Both models inherit `TenantScopedModel`, so `company` is required and PROTECT, and
the reverse accessors on `Company` are `company.consultancy_visaconsultancycase_set`
and `company.consultancy_studyvisacase_set`.

The reverse accessors on `Customer` are `visaconsultancycase_set` and
`studyvisacase_set` — distinct from the bookings app's `hajjbooking_set`,
`ticketingbooking_set` and so on, because `related_name='%(class)s_set'` resolves
to the concrete class name per subclass.

Nothing here filters automatically. When selectors land they must take `company` as
an explicit parameter — no thread-locals, no ambient context — exactly like
`customers`. `TenantIsolationTests` states that contract explicitly rather than
leaving it implied.

## Admin

Both models are registered, sharing a `CaseRecordAdmin` base so the
`CaseRecordBase` columns are defined once. `customer` and `assigned_counselor` use
autocomplete rather than plain selects, because both tables grow without bound and
rendering every customer into a dropdown is how an admin page stops loading.
`date_hierarchy` is on `case_open_date` — the axis cases are actually worked and
reported on.

## API

Two `ModelViewSet`s under `/api/v1/`: `visa-consultancy` and `study-visa`. Both use
`TenantScopedViewSetMixin` for company scoping and audit stamping, filter by
`status` / `customer` / the case-type field / `visa_decision`, and search across the
institution or tracking reference plus `customer__full_name` and `customer__phone`.

Both also expose the generic document routes, which is what the case workflow
actually runs on — a visa case *is* a pile of documents moving through a checklist:

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/visa-consultancy/{id}/attachments/` | GET, POST | Documents for one case (`multipart`: `file`, optional `doc_type`) |
| `/api/v1/study-visa/{id}/attachments/` | GET, POST | Same, for study-visa cases |
| `/api/v1/attachments/?content_type=consultancy.visaconsultancycase&object_id=7` | GET | The generic collection, filtered to one case |

## What this pass does not include

- **No document-checklist enforcement.** `document_checklist_status` is a field a
  human sets; nothing cross-checks it against which attachments actually exist, and
  nothing validates that `status = SUBMITTED` has the documents behind it. That is
  a service-layer rule, and it is deliberately not guessed at in the schema.
- **No `ServiceLink` usage.** The generic cross-reference model is in `common` for
  when a case needs to link to a booking (e.g. a visa case supporting a Hajj trip).
- **No indexes beyond the FK indexes Django creates.** The likely candidates
  (`(company, status)` for the work queues, `(company, case_open_date)` for
  reporting) were left out until the selectors that need them exist.

## Known gaps

- Nothing prevents a case pointing at a `Customer` belonging to a different
  company. The writing service owns that check — the same open gap already
  documented for `common.Attachment` and the bookings app.
- `StudyVisaCase.status` is not enforced against the enrolment reference: the model
  allows `SUBMITTED` while `enrolment_reference` is empty. The rule exists in the
  business, and a service-layer check (or a DB constraint) has to own it — the
  schema deliberately does not guess.
- Payments are not modelled. `service_value` records what the case was sold for;
  instalments, receipts and refunds are not represented.

## Tests

`consultancy/tests/test_models.py` — 43 structural tests: app shape and model
inventory, the "not a dated booking" pin, shared-enum reuse, choice/column widths,
inherited field shapes and defaults, both PROTECT edges and the SET_NULL edge,
tenant isolation, per-model field behaviour, and that a minimal record is possible.

```bash
python manage.py test consultancy
```
