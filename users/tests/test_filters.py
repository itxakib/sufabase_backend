"""Filter and search tests for the staff directory endpoint.

Note on scope: ``company`` is passed explicitly in most of these because the
directory's default tenant behaviour is still a Module 01 open question (see
``UserViewSet``) - the filters must be tested against a known set rather than
against whatever that decision turns out to be.
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from common.tests.factories import make_company, make_user
from common.tests.mixins import CompanyHeaderMixin
from users.models import User

USERS_URL = '/api/v1/users/'


class UserFilterApiTests(CompanyHeaderMixin, APITestCase):
    def setUp(self):
        self.company = make_company(name='Alpha Travel', slug='alpha-travel')
        self.other_company = make_company(name='Beta Tours', slug='beta-tours')

        self.admin = make_user(
            company=self.company,
            username='admin-1',
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
            email='admin@alpha.test',
            phone='+966500000001',
        )
        self.manager = make_user(
            company=self.company,
            username='manager-1',
            role=User.Role.MANAGER,
            first_name='Mona',
            last_name='Iqbal',
            email='mona@alpha.test',
            phone='+966500000002',
        )
        self.agent = make_user(
            company=self.company,
            username='agent-1',
            role=User.Role.AGENT,
            is_active=False,
        )
        self.newcomer = make_user(
            company=self.company,
            username='newcomer',
            role=User.Role.AGENT,
            first_name='Nadia',
            last_name='Khan',
        )
        self.foreign = make_user(company=self.other_company, username='foreign-1')

        # Everyone but the manager is still on their first login.
        User.objects.filter(pk=self.manager.pk).update(last_login=timezone.now())

        self.client.force_authenticate(self.manager)
        self.client.credentials(HTTP_X_COMPANY_ID=str(self.company.pk))

    def get(self, **params):
        params.setdefault('company', self.company.pk)
        return self.client.get(USERS_URL, params)

    def usernames(self, response):
        return {row['username'] for row in response.data['results']}

    # ── Role ─────────────────────────────────────────────────────────────────
    def test_filters_by_role(self):
        self.assertEqual(self.usernames(self.get(role=User.Role.MANAGER)), {'manager-1'})

    def test_filters_by_a_list_of_roles(self):
        self.assertEqual(
            self.usernames(self.get(role_in='admin,manager')),
            {'admin-1', 'manager-1'},
        )

    def test_excludes_a_list_of_roles(self):
        self.assertEqual(
            self.usernames(self.get(role_not='agent')),
            {'admin-1', 'manager-1'},
        )

    def test_an_invalid_role_is_a_400(self):
        self.assertEqual(self.get(role='superuser').status_code, 400)

    # ── Account state ────────────────────────────────────────────────────────
    def test_filters_by_is_active(self):
        self.assertEqual(self.usernames(self.get(is_active='false')), {'agent-1'})

    def test_filters_by_is_staff(self):
        self.assertEqual(self.usernames(self.get(is_staff='true')), {'admin-1'})

    def test_filters_by_is_superuser(self):
        self.assertEqual(self.usernames(self.get(is_superuser='true')), {'admin-1'})

    def test_filters_staff_who_have_never_logged_in(self):
        """A standing onboarding task, not an implementation detail."""
        self.assertEqual(
            self.usernames(self.get(never_logged_in='true')),
            {'admin-1', 'agent-1', 'newcomer'},
        )

    def test_filters_staff_who_have_logged_in(self):
        self.assertEqual(self.usernames(self.get(never_logged_in='false')), {'manager-1'})

    def test_an_invalid_boolean_is_a_400(self):
        self.assertEqual(self.get(never_logged_in='perhaps').status_code, 400)

    # ── Text ─────────────────────────────────────────────────────────────────
    def test_username_substring_matches(self):
        self.assertEqual(self.usernames(self.get(username='manager')), {'manager-1'})

    def test_username_exact_requires_the_whole_value(self):
        self.assertEqual(self.usernames(self.get(username_exact='manager-1')), {'manager-1'})
        self.assertEqual(self.usernames(self.get(username_exact='manager')), set())

    def test_email_exact_and_substring(self):
        self.assertEqual(self.usernames(self.get(email='alpha.test')), {'admin-1', 'manager-1'})
        self.assertEqual(self.usernames(self.get(email_exact='mona@alpha.test')), {'manager-1'})

    def test_phone_exact_and_substring(self):
        self.assertEqual(self.usernames(self.get(phone_exact='+966500000002')), {'manager-1'})
        self.assertEqual(self.usernames(self.get(phone='0000002')), {'manager-1'})

    def test_full_name_matches_across_both_name_columns(self):
        """Typing a whole person's name must find them, not just half of it."""
        self.assertEqual(self.usernames(self.get(full_name='Iqbal')), {'manager-1'})
        self.assertEqual(self.usernames(self.get(full_name='nadia')), {'newcomer'})
        self.assertEqual(self.usernames(self.get(full_name='Khan')), {'newcomer'})

    def test_search_covers_name_and_email(self):
        self.assertEqual(self.usernames(self.get(search='Iqbal')), {'manager-1'})
        self.assertEqual(self.usernames(self.get(search='mona@alpha.test')), {'manager-1'})

    def test_search_can_match_the_company_name(self):
        """A foreign key in ``search_fields``, so it cannot duplicate rows.

        Deliberately unscoped: a many-to-many or reverse path here is what makes
        search results double up and pagination counts lie.
        """
        response = self.client.get(USERS_URL, {'search': 'Beta'})
        self.assertEqual({row['username'] for row in response.data['results']}, {'foreign-1'})

    # ── Timestamps and ordering ──────────────────────────────────────────────
    def test_last_login_after_excludes_never_logged_in_staff(self):
        cutoff = (timezone.now() - timedelta(minutes=5)).isoformat()
        self.assertEqual(self.usernames(self.get(last_login_after=cutoff)), {'manager-1'})

    def test_created_after_excludes_backdated_staff(self):
        User.objects.filter(pk=self.agent.pk).update(
            created_at=timezone.now() - timedelta(days=30),
        )
        cutoff = (timezone.now() - timedelta(days=1)).isoformat()

        self.assertEqual(
            self.usernames(self.get(created_after=cutoff)),
            {'admin-1', 'manager-1', 'newcomer'},
        )

    def test_created_before_keeps_only_backdated_staff(self):
        User.objects.filter(pk=self.agent.pk).update(
            created_at=timezone.now() - timedelta(days=30),
        )
        cutoff = (timezone.now() - timedelta(days=1)).isoformat()

        self.assertEqual(self.usernames(self.get(created_before=cutoff)), {'agent-1'})

    def test_ordering_by_username_descending(self):
        usernames = [row['username'] for row in self.get(ordering='-username').data['results']]
        self.assertEqual(usernames, ['newcomer', 'manager-1', 'agent-1', 'admin-1'])

    def test_ordering_by_a_related_company_field(self):
        response = self.get(ordering='company__name,username')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 4)

    def test_an_unknown_ordering_field_falls_back_rather_than_500ing(self):
        """DRF drops unknown ordering fields; it must not raise."""
        response = self.get(ordering='password,username')
        self.assertEqual(response.status_code, 200)

    # ── Combinations ─────────────────────────────────────────────────────────
    def test_filters_combine_with_and(self):
        self.assertEqual(
            self.usernames(self.get(role=User.Role.AGENT, is_active='false')),
            {'agent-1'},
        )

    def test_company_scoping_still_holds_with_filters_applied(self):
        self.assertEqual(self.usernames(self.get(role_in='agent,manager,admin')), {
            'admin-1',
            'manager-1',
            'agent-1',
            'newcomer',
        })
