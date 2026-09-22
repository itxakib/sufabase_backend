"""Import service for Chamber of Commerce style directory workbooks.

The core entry point is ``DirectoryImportService.import_workbook`` — called by
both the management command and the API upload endpoint. It is synchronous
because the project has no Celery configuration; making it async is flagged
as a follow-up.

**File format assumptions** (validated against the real LCCI 2025-26 export):

* 5 sheets: Manufacturers, Exporters, Importers, Traders, Services
* Row 0: title row (sheet category name in column C)
* Row 1: header row — Sr No, Company, Name, Sub Sector, Address, Product Line,
  EMail, Url, Ph. No, M.Ship #, M.type
* Row 2+: data rows, interspersed with **sector marker rows** identified by
  ``col[1] == 'Business Sector:'``. The sector name sits in ``col[2]`` and
  applies to every subsequent data row until the next marker.
* Dedup key: ``M.Ship #`` (membership number, col 9). Same company legitimately
  appears in multiple sheets — the service creates one ``DirectoryCompany`` per
  unique membership number and one ``DirectoryBusinessActivity`` per
  (company, sheet) combination.
* Null-like values: xlrd returns empty strings for blank cells. The service
  treats ``''`` and whitespace-only strings as absent.
* Phone numbers may carry a leading space (e.g. ``' +92-42-35321461'``) —
  stripped on import.
* URLs may omit the protocol (e.g. ``www.example.com``) — ``http://`` is
  prepended when missing so ``URLField`` validation passes.

**If a future export arrives as .xlsx**, the ``_iter_source_rows`` generator
needs an ``openpyxl`` branch — xlrd 2.x cannot read .xlsx files. That is a
deliberate decision: ``xlrd`` is pinned to ``>=1.2`` to preserve .xls support,
and the note here is the only reminder the team needs when the format changes.
"""

import logging
import os
import re

import xlrd
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from directory.choices import ImportStatusChoices
from directory.models import (
    DirectoryBusinessActivity,
    DirectoryCompany,
    ImportBatch,
    ImportRowIssue,
)

logger = logging.getLogger(__name__)

# Columns by index — matching the real LCCI header row.
COL_SR_NO = 0
COL_COMPANY = 1
COL_NAME = 2
COL_SUB_SECTOR = 3
COL_ADDRESS = 4
COL_PRODUCT_LINE = 5
COL_EMAIL = 6
COL_URL = 7
COL_PHONE = 8
COL_MEMBERSHIP_NO = 9
COL_MEMBERSHIP_TYPE = 10

# xlrd returns empty strings for blank cells — treat these as absent.
_NULL_LIKE = ('', None)


def _clean(value):
    """Strip a cell value; return '' for null-like values."""
    if value in _NULL_LIKE:
        return ''
    return str(value).strip()


def _normalise_url(raw):
    """Prepend ``http://`` if the URL has no protocol, so ``URLField`` accepts it."""
    if not raw:
        return ''
    if not re.match(r'https?://', raw, re.IGNORECASE):
        return f'http://{raw}'
    return raw


def _iter_sheet_rows(ws):
    """Yield ``(row_idx, vals, current_sector)`` for data rows on one sheet.

    Sector marker rows (``Business Sector:`` in the company column) are not
    yielded. The sector title on those rows sits in the Name column — the Sub
    Sector column is blank there — and it applies to every following data row
    until the next marker.
    """
    current_sector = ''
    width = ws.ncols
    for row_idx in range(2, ws.nrows):  # skip title (0) + header (1)
        vals = [_clean(ws.cell(row_idx, c).value) for c in range(width)]
        if vals[COL_COMPANY] == 'Business Sector:':
            current_sector = vals[COL_NAME]
            continue
        yield row_idx, vals, current_sector


class DirectoryImportService:
    """Stateless import logic — every method takes explicit parameters.

    The class exists only to namespace the methods; there is no instance state.
    """

    @staticmethod
    @transaction.atomic
    def import_workbook(batch, file_path, company):
        """Import an LCCI-style XLS workbook into the directory.

        ``batch`` is an ``ImportBatch`` instance (already saved, status
        ``PROCESSING``). ``file_path`` is the absolute path to the .xls file.
        ``company`` is the tenant.

        Creates or updates ``DirectoryCompany`` and
        ``DirectoryBusinessActivity`` rows.  Issues are written to
        ``ImportRowIssue`` linked to the batch.  Batch counts are updated at
        the end so the caller can read them back.

        The ``transaction.atomic`` ensures either everything commits or nothing
        does — a partial import is worse than a failed one, because the counts
        would be wrong and the staff member would have no idea which rows
        landed.
        """
        wb = xlrd.open_workbook(file_path)
        stats = {
            'total_rows': 0,
            'companies_created': 0,
            'companies_updated': 0,
            'activities_created': 0,
            'issues': [],
        }

        for sheet_name in wb.sheet_names():
            ws = wb.sheet_by_name(sheet_name)
            DirectoryImportService._import_sheet(
                ws, sheet_name, company, batch, stats,
            )

        # Bulk-create issues — one query per batch, not per row.
        if stats['issues']:
            ImportRowIssue.objects.bulk_create([
                ImportRowIssue(
                    company=company,
                    batch=batch,
                    sheet_name=issue['sheet_name'],
                    row_number=issue['row_number'],
                    membership_number=issue.get('membership_number', ''),
                    field_name=issue.get('field_name', ''),
                    issue_type=issue['issue_type'],
                    raw_value=issue.get('raw_value', ''),
                    message=issue['message'],
                )
                for issue in stats['issues']
            ])

        # Update batch counts.
        batch.total_rows = stats['total_rows']
        batch.companies_created = stats['companies_created']
        batch.companies_updated = stats['companies_updated']
        batch.activities_created = stats['activities_created']
        batch.issues_count = len(stats['issues'])
        batch.completed_at = timezone.now()
        batch.save(update_fields=[
            'total_rows', 'companies_created', 'companies_updated',
            'activities_created', 'issues_count', 'completed_at',
        ])

        logger.info(
            'Import batch %d complete: %d rows, %d created, %d updated, '
            '%d activities, %d issues',
            batch.pk,
            stats['total_rows'],
            stats['companies_created'],
            stats['companies_updated'],
            stats['activities_created'],
            stats['issues'],
        )

    @staticmethod
    def _import_sheet(ws, sheet_name, company, batch, stats):
        """Import one sheet, tracking sector markers and deduping by membership number."""
        for row_idx, vals, current_sector in _iter_sheet_rows(ws):
            # ── Skip truly empty rows ───────────────────────────────────────
            if all(v in _NULL_LIKE for v in vals):
                continue

            stats['total_rows'] += 1
            row_number = row_idx + 1  # 1-indexed for human display

            membership_number = vals[COL_MEMBERSHIP_NO]

            # ── Issue: missing membership number ────────────────────────────
            if not membership_number:
                stats['issues'].append({
                    'sheet_name': sheet_name,
                    'row_number': row_number,
                    'issue_type': 'missing_membership',
                    'raw_value': vals[COL_COMPANY],
                    'message': f'Row has no membership number — cannot deduplicate.',
                })
                continue

            # ── Normalise phone and URL ─────────────────────────────────────
            phone = vals[COL_PHONE]
            website = _normalise_url(vals[COL_URL])

            # ── Validate email ──────────────────────────────────────────────
            email = vals[COL_EMAIL]
            if email:
                try:
                    validate_email(email)
                except ValidationError:
                    stats['issues'].append({
                        'sheet_name': sheet_name,
                        'row_number': row_number,
                        'membership_number': membership_number,
                        'field_name': 'email',
                        'issue_type': 'invalid_email',
                        'raw_value': email,
                        'message': f'"{email}" is not a valid email address.',
                    })
                    email = ''

            # ── Get or create the company ───────────────────────────────────
            company_data = {
                'company_name': vals[COL_COMPANY],
                'contact_person': vals[COL_NAME],
                'business_sector': current_sector,
                'sub_sector': vals[COL_SUB_SECTOR],
                'address': vals[COL_ADDRESS],
                'product_line': vals[COL_PRODUCT_LINE],
                'email': email,
                'website': website,
                'phone': phone,
                'membership_type': vals[COL_MEMBERSHIP_TYPE],
            }

            dir_company, created = DirectoryCompany.objects.get_or_create(
                company=company,
                membership_number=membership_number,
                defaults=company_data,
            )

            if created:
                stats['companies_created'] += 1
            else:
                # Fill in blanks — never overwrite existing non-empty values
                # with values from a different sheet, since the same company
                # may have slightly different data across sheets.
                updated_fields = []
                for field, value in company_data.items():
                    if value and not getattr(dir_company, field):
                        setattr(dir_company, field, value)
                        updated_fields.append(field)
                if updated_fields:
                    updated_fields.append('updated_at')
                    dir_company.save(update_fields=updated_fields)
                    stats['companies_updated'] += 1

            # ── Activity row (one per sheet) ────────────────────────────────
            activity, activity_created = DirectoryBusinessActivity.objects.get_or_create(
                directory_company=dir_company,
                sheet_name=sheet_name,
                defaults={
                    'company': company,
                    'sr_no': int(vals[COL_SR_NO]) if vals[COL_SR_NO].isdigit() else None,
                },
            )
            if activity_created:
                stats['activities_created'] += 1

    @staticmethod
    def validate_workbook(file_path):
        """Quick structural check before committing to a full import.

        Returns ``(ok: bool, error: str | None)``.  Does not create any
        database rows — purely a pre-flight for the management command and
        the API endpoint.
        """
        if not os.path.exists(file_path):
            return False, f'File not found: {file_path}'

        try:
            wb = xlrd.open_workbook(file_path)
        except xlrd.XLRDError as exc:
            return False, f'Cannot open workbook: {exc}'

        expected_headers = [
            'Sr No', 'Company', 'Name', 'Sub Sector', 'Address',
            'Product Line', 'EMail', 'Url', 'Ph. No', 'M.Ship #', 'M.type',
        ]

        for name in wb.sheet_names():
            ws = wb.sheet_by_name(name)
            if ws.nrows < 2:
                return False, f'Sheet "{name}" has fewer than 2 rows.'
            headers = [_clean(ws.cell(1, c).value) for c in range(ws.ncols)]
            if headers != expected_headers:
                return (
                    False,
                    f'Sheet "{name}" header row does not match expected columns. '
                    f'Got {headers}',
                )

        return True, None

    @staticmethod
    def repair_business_sectors(company, file_path):
        """Fill blank ``business_sector`` values from an LCCI workbook.

        A previous import read the sector title from the Sub Sector column,
        which is empty on marker rows, so every company was stored with a
        blank sector and the list filters had nothing to offer. Re-reading
        the Name column and writing it onto rows that are still blank repairs
        that without touching a sector that was set on purpose.

        The first sheet that names a membership number wins, matching import
        order (Manufacturers, then Exporters, Importers, Traders, Services).

        Returns the number of companies updated.
        """
        wb = xlrd.open_workbook(file_path)
        sector_by_membership = {}
        for sheet_name in wb.sheet_names():
            ws = wb.sheet_by_name(sheet_name)
            for _row_idx, vals, current_sector in _iter_sheet_rows(ws):
                membership_number = vals[COL_MEMBERSHIP_NO] if len(vals) > COL_MEMBERSHIP_NO else ''
                if membership_number and current_sector and membership_number not in sector_by_membership:
                    sector_by_membership[membership_number] = current_sector

        if not sector_by_membership:
            return 0

        pending = []
        now = timezone.now()
        queryset = DirectoryCompany.objects.filter(
            company=company,
            business_sector='',
            membership_number__in=sector_by_membership,
        )
        for row in queryset.iterator():
            sector = sector_by_membership.get(row.membership_number)
            if not sector:
                continue
            row.business_sector = sector
            row.updated_at = now
            pending.append(row)

        if pending:
            DirectoryCompany.objects.bulk_update(
                pending, ['business_sector', 'updated_at'], batch_size=1000,
            )
        return len(pending)
