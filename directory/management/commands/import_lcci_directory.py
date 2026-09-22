"""Management command to import an LCCI-style directory workbook.

Usage:
    python manage.py import_lcci_directory /path/to/lcci_directory_2025-26.xls --company-id 1

The command validates the workbook structure before touching the database,
then runs the full import inside a single transaction. A summary is printed
to stdout on completion.
"""

import os
import sys
import time

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from directory.choices import ImportStatusChoices
from directory.models import ImportBatch
from directory.services import DirectoryImportService


class Command(BaseCommand):
    help = 'Import a Chamber of Commerce style directory workbook (LCCI format)'

    def add_arguments(self, parser):
        parser.add_argument(
            'file_path',
            type=str,
            help='Path to the .xls or .xlsx workbook',
        )
        parser.add_argument(
            '--company-id',
            type=int,
            required=True,
            help='ID of the company (tenant) to import into',
        )
        parser.add_argument(
            '--batch-name',
            type=str,
            default='',
            help='Optional label for this import batch (defaults to filename)',
        )

    def handle(self, *args, **options):
        from tenant.models import Company

        file_path = options['file_path']
        company_id = options['company_id']
        # ── Validate company exists ─────────────────────────────────────
        try:
            company = Company.objects.get(pk=company_id)
        except Company.DoesNotExist:
            raise CommandError(f'Company with id={company_id} does not exist.')

        # ── Validate file exists ────────────────────────────────────────
        if not os.path.exists(file_path):
            raise CommandError(f'File not found: {file_path}')

        # ── Pre-flight structural check ─────────────────────────────────
        self.stdout.write(f'Validating workbook structure...')
        ok, error = DirectoryImportService.validate_workbook(file_path)
        if not ok:
            raise CommandError(f'Workbook validation failed: {error}')
        self.stdout.write(self.style.SUCCESS('Structure OK'))

        # ── Create batch ────────────────────────────────────────────────
        batch = ImportBatch.objects.create(
            company=company,
            triggered_by=None,  # management command — no user context
            filename=os.path.basename(file_path),
            status=ImportStatusChoices.PROCESSING,
            started_at=timezone.now(),
        )

        self.stdout.write(f'Importing into batch #{batch.pk}...')

        # ── Run import ──────────────────────────────────────────────────
        start = time.time()
        try:
            DirectoryImportService.import_workbook(
                batch=batch,
                file_path=file_path,
                company=company,
            )
        except Exception as exc:
            batch.status = ImportStatusChoices.FAILED
            batch.error_message = str(exc)[:1000]
            batch.completed_at = timezone.now()
            batch.save(update_fields=['status', 'error_message', 'completed_at'])
            raise CommandError(f'Import failed: {exc}')

        elapsed = time.time() - start

        # Refresh from DB — the service updated counts inside its own
        # @transaction.atomic block; the Python object may be stale.
        batch.refresh_from_db()
        batch.status = ImportStatusChoices.COMPLETED
        batch.save(update_fields=['status'])

        # ── Print summary ───────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS(f'  IMPORT COMPLETE -- Batch #{batch.pk}'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'  File:              {batch.filename}')
        self.stdout.write(f'  Company:           {company.name} (#{company.pk})')
        self.stdout.write(f'  Time elapsed:      {elapsed:.1f}s')
        self.stdout.write('')
        self.stdout.write(f'  Total rows:        {batch.total_rows:,}')
        self.stdout.write(f'  Companies created: {batch.companies_created:,}')
        self.stdout.write(f'  Companies updated: {batch.companies_updated:,}')
        self.stdout.write(f'  Activities created:{batch.activities_created:,}')
        self.stdout.write(f'  Issues logged:     {batch.issues_count:,}')
        self.stdout.write(self.style.SUCCESS('=' * 60))

        if batch.issues_count > 0:
            self.stdout.write('')
            self.stdout.write(
                f'  View issues: python manage.py shell -c '
                f'"from directory.models import ImportRowIssue; '
                f'[print(i) for i in ImportRowIssue.objects.filter(batch_id={batch.pk})]"'
            )
