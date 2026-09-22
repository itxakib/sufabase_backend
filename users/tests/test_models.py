from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import ProtectedError
from django.test import TestCase

from common.models import BaseModel, TenantScopedModel
from common.tests.factories import make_company, make_user
from tenant.models import Company
from users.models import User


class UserModelTests(TestCase):
    def setUp(self):
        self.company = make_company()

    def test_custom_user_model_is_the_configured_auth_user_model(self):
        self.assertIs(get_user_model(), User)

    def test_user_is_tenant_scoped(self):
        self.assertTrue(issubclass(User, TenantScopedModel))
        self.assertTrue(issubclass(User, BaseModel))

    def test_company_is_required_and_protected(self):
        field = User._meta.get_field('company')
        self.assertFalse(field.null)
        self.assertFalse(field.blank)
        self.assertIs(field.remote_field.on_delete, models.PROTECT)
        # Resolved to the concrete model on User, even though the base declares
        # it as the string 'tenant.Company'.
        self.assertIs(field.remote_field.model, Company)

    def test_role_defaults_to_agent(self):
        self.assertEqual(make_user(company=self.company).role, User.Role.AGENT)

    def test_company_assignment_and_reverse_accessor(self):
        user = make_user(company=self.company)
        self.assertEqual(user.company, self.company)
        # Inherited from TenantScopedModel, so the accessor uses its pattern.
        self.assertIn(user, self.company.users_user_set.all())

    def test_deleting_a_company_is_blocked_while_staff_belong_to_it(self):
        make_user(company=self.company)

        with self.assertRaises(ProtectedError):
            self.company.delete()

        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())

    def test_audit_columns_exist_and_are_nullable(self):
        user = make_user(company=self.company)
        self.assertIsNone(user.created_by)
        self.assertIsNone(user.updated_by)
        self.assertIsNotNone(user.created_at)
        self.assertIsNotNone(user.updated_at)

    def test_is_active_is_available_and_defaults_to_true(self):
        self.assertTrue(make_user(company=self.company).is_active)

    def test_user_cannot_be_abstract(self):
        """Guards against inheriting AbstractUser.Meta.abstract by accident."""
        self.assertFalse(User._meta.abstract)
        self.assertIsNotNone(User._meta.db_table)

    def test_createsuperuser_will_prompt_for_a_company(self):
        self.assertIn('company', User.REQUIRED_FIELDS)
