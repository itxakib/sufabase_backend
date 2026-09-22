from django.test import TestCase

from common.tests.factories import make_company
from users.models import User


class CustomUserManagerTests(TestCase):
    def setUp(self):
        self.company = make_company()

    def test_create_user_hashes_the_password(self):
        user = User.objects.create_user(
            username='sam',
            email='sam@example.com',
            password='secret-pass',
            company=self.company,
        )
        self.assertNotEqual(user.password, 'secret-pass')
        self.assertTrue(user.check_password('secret-pass'))

    def test_create_user_defaults_flags_and_role(self):
        user = User.objects.create_user(username='sam', password='secret-pass', company=self.company)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.role, User.Role.AGENT)

    def test_create_user_normalizes_the_email_domain(self):
        user = User.objects.create_user(
            username='sam',
            email='sam@EXAMPLE.com',
            password='x',
            company=self.company,
        )
        self.assertEqual(user.email, 'sam@example.com')

    def test_create_user_attaches_the_company(self):
        user = User.objects.create_user(username='sam', password='x', company=self.company)
        self.assertEqual(user.company, self.company)

    def test_create_user_requires_a_username(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(username='', password='x', company=self.company)

    def test_create_user_requires_a_company(self):
        """A staff account can never be tenant-less - fail clearly, not with
        an IntegrityError from the database."""
        with self.assertRaises(ValueError):
            User.objects.create_user(username='sam', password='x')
        self.assertEqual(User.objects.count(), 0)

    def test_create_superuser_sets_flags_role_and_company(self):
        user = User.objects.create_superuser(
            username='root',
            email='root@example.com',
            password='x',
            company=self.company,
        )
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertEqual(user.company, self.company)

    def test_create_superuser_requires_a_company(self):
        """Superusers are not exempt from tenant scoping."""
        with self.assertRaises(ValueError):
            User.objects.create_superuser(username='root', password='x')
        self.assertEqual(User.objects.count(), 0)

    def test_create_superuser_rejects_explicit_false_flags(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                username='root',
                password='x',
                company=self.company,
                is_staff=False,
            )
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                username='root',
                password='x',
                company=self.company,
                is_superuser=False,
            )
