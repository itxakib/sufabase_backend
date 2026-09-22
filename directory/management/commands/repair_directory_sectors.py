"""Fill blank directory business sectors from an LCCI workbook.

Usage:
    python manage.py repair_directory_sectors "M:/sufa international/data format/lcci_directory_2025-26.xls" --company-id 1

Only rows whose ``business_sector`` is still blank are updated. A sector that
already has a value is left as it is.
"""

import os

from django.core.management.base import BaseCommand, CommandError

from directory.services import DirectoryImportService


class Command(BaseCommand):
    help = 'Fill blank business_sector values from an LCCI-style workbook'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the .xls workbook')
        parser.add_argument(
            '--company-id',
            type=int,
            required=True,
            help='ID of the company (tenant) whose directory should be repaired',
        )

    def handle(self, *args, **options):
        from tenant.models import Company

        file_path = options['file_path']
        company_id = options['company_id']

        try:
            company = Company.objects.get(pk=company_id)
        except Company.DoesNotExist:
            raise CommandError(f'Company with id={company_id} does not exist.')

        if not os.path.exists(file_path):
            raise CommandError(f'File not found: {file_path}')

        ok, error = DirectoryImportService.validate_workbook(file_path)
        if not ok:
            raise CommandError(f'Workbook validation failed: {error}')

        updated = DirectoryImportService.repair_business_sectors(company, file_path)
        self.stdout.write(self.style.SUCCESS(
            f'Updated {updated:,} companies in {company.name} (#{company.pk}).'
        ))
