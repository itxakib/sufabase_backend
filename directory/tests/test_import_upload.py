"""Regression tests for the synchronous directory workbook upload."""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from common.tests.factories import make_company, make_user
from common.tests.mixins import CompanyHeaderMixin
from directory.models import ImportBatch


UPLOAD_URL = '/api/v1/import-batches/upload/'


class DirectoryImportUploadTests(CompanyHeaderMixin, APITestCase):
    """The custom action must use the mixin resolver, not raw request.company."""

    def setUp(self):
        self.company = make_company(name='Alpha Travel', slug='alpha-travel')
        self.user = make_user(company=self.company, username='directory-importer')
        self.client.force_authenticate(self.user)
        super().setUp()

    @patch('directory.api.views.DirectoryImportService.import_workbook')
    @patch('directory.api.views.DirectoryImportService.validate_workbook')
    def test_upload_stamps_the_authenticated_users_company_when_middleware_has_no_company(
        self, validate_workbook, import_workbook
    ):
        """DRF force_authenticate runs after middleware, matching JWT timing."""
        validate_workbook.return_value = (True, None)
        workbook = SimpleUploadedFile(
            'chamber.xls', b'not-read: the parser is mocked for this request test',
            content_type='application/vnd.ms-excel',
        )

        response = self.client.post(UPLOAD_URL, {'file': workbook}, format='multipart')

        self.assertEqual(response.status_code, 201, response.data)
        batch = ImportBatch.objects.get()
        self.assertEqual(batch.company_id, self.company.id)
        self.assertEqual(batch.status, 'COMPLETED')
        import_workbook.assert_called_once_with(
            batch=batch,
            file_path=import_workbook.call_args.kwargs['file_path'],
            company=self.company,
        )
