"""Models for the B2B company directory.

Two layers, deliberately:

* ``DirectoryCompany`` — one row per unique membership number, tenant-scoped.
  This is the "who is this business" record, deduped across sheets. It is
  deliberately separate from ``customers.Customer``: a directory row is an
  unvetted lead, and only becomes a Customer when staff explicitly convert it.
  The ``converted_customer`` FK is the hook for that follow-up — it is not
  wired into any view yet.

* ``DirectoryBusinessActivity`` — one row per (company, sheet-category)
  combination. A company appearing in Manufacturers, Importers and Traders
  produces three activity rows. The sheet name and the sequence number within
  that sheet are the only data that lives here: everything else is on the
  company.

* ``ImportBatch`` — one row per import run, tracking file, counts and status.

* ``ImportRowIssue`` — one row per problem found during import, linked to a
  batch. This is the table the frontend shows so staff can spot-check what the
  import skipped or flagged.

``DirectoryCompany`` and ``DirectoryBusinessActivity`` inherit
``TenantScopedModel``: each tenant gets its own copy of the directory.
The LCCI file is public data, but the import path, the conversion status and
any future annotations (notes, tags, assignment) are per-tenant.
"""

from django.conf import settings
from django.db import models

from common.models import TenantScopedModel
from directory.choices import ImportStatusChoices


class DirectoryCompany(TenantScopedModel):
    """One unique business entry from a Chamber of Commerce directory.

    Deduped by ``membership_number`` within a tenant — the LCCI source file
    legitimately lists the same company under multiple category sheets
    (Manufacturers, Exporters, etc.), and the membership number is the only
    field the source system validated as unique. ``company_name`` and ``email``
    were both checked and are not safe dedup keys (708 emails are shared
    across more than one company; company names were never validated by the
    source system).

    ``converted_customer`` is the FK to ``customers.Customer`` that makes this
    entry actionable: a directory company becomes a Customer when staff
    explicitly convert it. The conversion endpoint is a follow-up — this FK
    exists now so the migration is in place, but no view writes to it yet.
    """

    # ── Identity ────────────────────────────────────────────────────────────
    membership_number = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text='LCCI membership number — the dedup key across sheets.',
    )
    membership_type = models.CharField(
        max_length=5,
        blank=True,
        help_text='Membership type from the source file (e.g. A = Annual, C = Corporate).',
    )
    company_name = models.CharField(max_length=500)
    contact_person = models.CharField(
        max_length=500,
        blank=True,
        help_text='Contact name and designation as listed (e.g. "MR. ALI RAZA - Partner").',
    )

    # ── Classification ──────────────────────────────────────────────────────
    business_sector = models.CharField(
        max_length=255,
        blank=True,
        help_text='Top-level sector from the section header (e.g. "AGRICULTURE & HORTICULTURE").',
    )
    sub_sector = models.CharField(
        max_length=255,
        blank=True,
        help_text='Sub-sector from the data row (e.g. "AGRICULTURAL CROPS & SEEDS").',
    )
    product_line = models.CharField(max_length=500, blank=True)

    # ── Contact / address ───────────────────────────────────────────────────
    address = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(max_length=500, blank=True)
    phone = models.CharField(max_length=100, blank=True)

    # ── Conversion hook (Module 02+ follow-up) ──────────────────────────────
    converted_customer = models.ForeignKey(
        'customers.Customer',
        null=True,
        blank=True,
        related_name='directory_entries',
        on_delete=models.SET_NULL,
        help_text='Set when staff convert this directory entry into a Customer.',
    )
    converted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the conversion happened.',
    )

    class Meta:
        ordering = ['company_name']
        indexes = [
            models.Index(fields=['company_name']),
            models.Index(fields=['business_sector']),
            models.Index(fields=['sub_sector']),
        ]

    def __str__(self):
        return self.company_name


class DirectoryBusinessActivity(TenantScopedModel):
    """One row per (company, sheet-category) combination.

    A company that appears in three LCCI sheets (e.g. Manufacturers, Traders,
    Services) produces three activity rows. The company record is shared —
    ``DirectoryCompany`` holds all the contact and classification data — and
    the activity only records *which* sheets it appeared in, plus the sequence
    number within each sheet.

    This design keeps the company data in one place (no duplication across
    sheets) while preserving the full import trail.
    """

    directory_company = models.ForeignKey(
        DirectoryCompany,
        related_name='activities',
        on_delete=models.CASCADE,
    )
    sheet_name = models.CharField(
        max_length=50,
        help_text='Source sheet name (e.g. "Manufacturers", "Exporters").',
    )
    sr_no = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Sequence number within the source sheet.',
    )

    class Meta:
        ordering = ['sheet_name']
        unique_together = [('directory_company', 'sheet_name')]

    def __str__(self):
        return f'{self.directory_company} — {self.sheet_name}'


class ImportBatch(TenantScopedModel):
    """Tracks one import run: the uploaded file, the counts, and the outcome.

    Both the management command and the API upload endpoint create one of
    these. The ``file`` field stores the uploaded XLS under ``media/`` so
    staff can re-download the original if they need to audit what was
    imported.
    """

    filename = models.CharField(max_length=255)
    file = models.FileField(upload_to='directory-imports/%Y/%m/', blank=True)
    status = models.CharField(
        max_length=20,
        choices=ImportStatusChoices.choices,
        default=ImportStatusChoices.PENDING,
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name='directory_imports',
        on_delete=models.SET_NULL,
    )

    # ── Counts ──────────────────────────────────────────────────────────────
    total_rows = models.PositiveIntegerField(default=0)
    companies_created = models.PositiveIntegerField(default=0)
    companies_updated = models.PositiveIntegerField(default=0)
    activities_created = models.PositiveIntegerField(default=0)
    issues_count = models.PositiveIntegerField(default=0)

    # ── Timing ──────────────────────────────────────────────────────────────
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Import #{self.pk} — {self.filename}'


class ImportRowIssue(TenantScopedModel):
    """One problem found during import, linked to a batch.

    These are the rows the import *skipped* or *flagged* — the file is
    imported as far as it can go, and the issues are reported back so staff
    can decide whether to fix and re-import. The ``field_name`` and
    ``issue_type`` pair is what the frontend uses to build a filterable
    issues table.
    """

    batch = models.ForeignKey(
        ImportBatch,
        related_name='issues',
        on_delete=models.CASCADE,
    )
    sheet_name = models.CharField(max_length=50)
    row_number = models.PositiveIntegerField()
    membership_number = models.CharField(max_length=50, blank=True)
    field_name = models.CharField(
        max_length=100,
        blank=True,
        help_text='Which field the issue relates to, if applicable.',
    )
    issue_type = models.CharField(
        max_length=50,
        help_text='Machine-readable category (e.g. "missing_membership", "invalid_email").',
    )
    raw_value = models.TextField(
        blank=True,
        help_text='The original value from the file, for audit.',
    )
    message = models.TextField()

    class Meta:
        ordering = ['batch', 'row_number']
        indexes = [
            models.Index(fields=['batch', 'issue_type']),
        ]

    def __str__(self):
        return f'Row {self.row_number} ({self.sheet_name}): {self.issue_type}'
