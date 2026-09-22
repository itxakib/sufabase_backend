"""Contract tests for the shared abstractions in ``common.models``."""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import models
from django.test import TestCase

from common.models import (
    Attachment,
    AuditModel,
    BaseModel,
    ServiceLink,
    TenantScopedModel,
    TimeStampedModel,
)
from tenant.models import Company

User = get_user_model()

ABSTRACT_MODELS = (TimeStampedModel, AuditModel, BaseModel, TenantScopedModel)

# The two concrete models common owns: generic, so no single module can own them.
GENERIC_MODELS = (Attachment, ServiceLink)

# Every concrete model built on the shared bases, across all apps.
CONCRETE_MODELS = (Company, User, Attachment, ServiceLink)


class SharedBaseModelTests(TestCase):
    def test_every_common_model_is_abstract(self):
        for model in ABSTRACT_MODELS:
            with self.subTest(model=model.__name__):
                self.assertTrue(
                    model._meta.abstract,
                    f'{model.__name__} must stay abstract - concrete bases would '
                    'create tables and migrations in common.',
                )

    def test_common_owns_only_the_shared_generic_models(self):
        """common is shared infrastructure, not a home for domain models.

        ``Attachment`` and ``ServiceLink`` belong here because their whole point
        is to attach to models in *any* module, so no single module owns them -
        unlike, say, a booking, which belongs to the module that defines it. Any
        other name appearing in this set is a module model in the wrong app.
        """
        self.assertEqual(
            {model.__name__ for model in apps.get_app_config('common').get_models()},
            {'Attachment', 'ServiceLink'},
        )

    def test_every_concrete_common_model_is_tenant_scoped(self):
        """Nothing in common may be tenant-less: these are tenant-owned rows."""
        for model in apps.get_app_config('common').get_models():
            with self.subTest(model=model.__name__):
                self.assertTrue(issubclass(model, TenantScopedModel))
                self.assertTrue(issubclass(model, BaseModel))

    def test_each_base_lives_in_its_own_module(self):
        """One model per file - the layout requested for ``common/models/``."""
        self.assertEqual(
            {model.__module__ for model in ABSTRACT_MODELS},
            {
                'common.models.time_stamped',
                'common.models.audit',
                'common.models.base',
                'common.models.tenant_scoped',
            },
        )

    def test_each_generic_model_lives_in_its_own_module(self):
        """One model per file holds for the concrete models too."""
        self.assertEqual(
            {model.__module__ for model in GENERIC_MODELS},
            {
                'common.models.attachment',
                'common.models.service_link',
            },
        )

    def test_package_reexports_are_the_public_import_path(self):
        import common.models as common_models

        self.assertEqual(
            sorted(common_models.__all__),
            [
                'Attachment',
                'AuditModel',
                'BaseModel',
                'ServiceLink',
                'TenantScopedModel',
                'TimeStampedModel',
            ],
        )

    def test_layering_is_base_over_timestamps_and_audit(self):
        self.assertTrue(issubclass(BaseModel, TimeStampedModel))
        self.assertTrue(issubclass(BaseModel, AuditModel))
        self.assertTrue(issubclass(TenantScopedModel, BaseModel))

    def test_company_inherits_base_model_only(self):
        """A company is the tenant: it cannot belong to a company."""
        self.assertTrue(issubclass(Company, BaseModel))
        self.assertFalse(issubclass(Company, TenantScopedModel))

    def test_user_is_tenant_scoped(self):
        self.assertTrue(issubclass(User, TenantScopedModel))
        self.assertTrue(issubclass(User, BaseModel))

    def test_audit_fields_are_nullable_and_set_null(self):
        """The first row ever created has no creator, and deleting a staff
        account must never delete the records they touched."""
        for model in CONCRETE_MODELS:
            for field_name in ('created_by', 'updated_by'):
                with self.subTest(model=model.__name__, field=field_name):
                    field = model._meta.get_field(field_name)
                    self.assertTrue(field.null)
                    self.assertIs(field.remote_field.on_delete, models.SET_NULL)

    def test_audit_fields_are_not_editable(self):
        """editable=False is what keeps them out of forms and serializers."""
        for model in CONCRETE_MODELS:
            for field_name in ('created_by', 'updated_by'):
                with self.subTest(model=model.__name__, field=field_name):
                    self.assertFalse(model._meta.get_field(field_name).editable)

    def test_tenant_scoped_company_field_is_required_and_protected(self):
        """PROTECT, never CASCADE: one careless delete must not wipe a tenant."""
        field = TenantScopedModel._meta.get_field('company')
        self.assertIs(field.remote_field.on_delete, models.PROTECT)
        self.assertFalse(field.null)
        # On an abstract base the target is still the unresolved label; concrete
        # subclasses resolve it to Company (see the users model tests).
        self.assertEqual(field.remote_field.model, 'tenant.Company')

    def test_tenant_scoped_reverse_accessor_is_unique_per_model(self):
        field = TenantScopedModel._meta.get_field('company')
        self.assertIn('%(app_label)s', field.remote_field.related_name)
        self.assertIn('%(class)s', field.remote_field.related_name)
