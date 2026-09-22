"""Small test helpers shared by every app's test suite."""

import shutil
import tempfile

from django.test import override_settings


class CompanyHeaderMixin:
    """Sets the ``X-Company-ID`` header so ``HasCompanyContext`` doesn't block.

    Mix this into any ``APITestCase`` that calls ``force_authenticate``.
    ``self.company`` must be set in ``setUp`` before the super call, or the
    mixin falls back to ``self.user.company``.
    """

    def setUp(self):
        super().setUp()
        company = getattr(self, 'company', None)
        if company is None:
            user = getattr(self, 'user', None)
            if user is not None:
                company = getattr(user, 'company', None)
        if company is not None:
            self.client.credentials(HTTP_X_COMPANY_ID=str(company.pk))


class MediaRootMixin:
    """Point MEDIA_ROOT at a throwaway directory for the duration of a test.

    Uploads in tests must never write into the project's ``media/`` directory.
    It is git-ignored, so the junk is invisible in review but very much present:
    it leaks state between runs and it is the one place a failed test can leave
    files behind that a later test quietly depends on.
    """

    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix='sufabase-test-media-')
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        try:
            super().tearDownClass()
        finally:
            cls._media_override.disable()
            shutil.rmtree(cls._media_root, ignore_errors=True)
