"""Minimal test factories shared by every app's test suite.

This project does not depend on ``factory_boy``, so these are plain functions.
They live in ``common`` because more than one module app needs to build a
company/user fixture (cursor Rule 10: shared code goes in common, never copied
per app).

``make_attachment`` writes a real file, so any test that uploads should also
point MEDIA_ROOT at a throwaway directory - use ``common.tests.mixins.
MediaRootMixin``. Without it, uploads land in the project's ``media/``.
"""

from itertools import count

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from common.models import Attachment, ServiceLink
from tenant.models import Company

User = get_user_model()

DEFAULT_PASSWORD = 'test-pass-12345'

_company_counter = count(1)
_user_counter = count(1)


def make_company(**overrides):
    """Create a Company with unique name/slug unless overridden."""
    index = next(_company_counter)
    defaults = {
        'name': f'Test Company {index}',
        'slug': f'test-company-{index}',
    }
    defaults.update(overrides)
    return Company.objects.create(**defaults)


def make_user(*, company, password=DEFAULT_PASSWORD, **overrides):
    """Create a staff user through the custom manager (so it is exercised too).

    ``company`` is required, mirroring the model: every staff account belongs to
    exactly one tenant.
    """
    index = next(_user_counter)
    username = overrides.pop('username', f'staff{index}')
    email = overrides.pop('email', f'staff{index}@example.com')
    return User.objects.create_user(
        username=username,
        email=email,
        password=password,
        company=company,
        **overrides,
    )


def make_attachment(
    *,
    company,
    target,
    name='document.pdf',
    doc_type='Test document',
    **overrides,
):
    """Attach a file to any saved model instance via the contenttypes framework.

    ``company`` is passed in rather than read off ``target`` on purpose: nothing
    in the schema ties the two together, and inferring it here would paper over
    exactly the gap the writing service has to close.
    """
    defaults = {
        'company': company,
        'content_object': target,
        'file': SimpleUploadedFile(name, b'sufabase-test-file'),
        'doc_type': doc_type,
    }
    defaults.update(overrides)
    return Attachment.objects.create(**defaults)


def make_service_link(*, company, from_object, to_object, notes='', **overrides):
    """Link two records of any type, in either direction across modules."""
    defaults = {
        'company': company,
        'from_object': from_object,
        'to_object': to_object,
        'notes': notes,
    }
    defaults.update(overrides)
    return ServiceLink.objects.create(**defaults)
