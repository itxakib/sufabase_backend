from django.test import TestCase

from common.tests.factories import make_company, make_user
from users.models import User
from users.selectors.user_selectors import UserSelector


class UserSelectorTests(TestCase):
    def setUp(self):
        self.company_a = make_company(name='Alpha Travel', slug='alpha-travel')
        self.company_b = make_company(name='Beta Tours', slug='beta-tours')

        self.agent_a = make_user(
            company=self.company_a,
            username='agent-a',
            role=User.Role.AGENT,
            phone='+966500000001',
        )
        self.manager_a = make_user(
            company=self.company_a,
            username='manager-a',
            role=User.Role.MANAGER,
            is_active=False,
        )
        self.agent_b = make_user(company=self.company_b, username='agent-b')

    # --- tenant isolation ---------------------------------------------------

    def test_scoping_to_a_company_excludes_every_other_tenant(self):
        self.assertEqual(
            set(UserSelector.list_users(company=self.company_a)),
            {self.agent_a, self.manager_a},
        )
        self.assertNotIn(self.agent_b, UserSelector.list_users(company=self.company_a))

    def test_scoping_also_applies_to_search(self):
        self.assertEqual(
            list(UserSelector.list_users(company=self.company_a, search='agent-b')),
            [],
        )

    def test_get_by_id_outside_the_company_raises(self):
        with self.assertRaises(User.DoesNotExist):
            UserSelector.get_by_id(self.agent_b.pk, company=self.company_a)

    def test_get_by_username_outside_the_company_raises(self):
        with self.assertRaises(User.DoesNotExist):
            UserSelector.get_by_username('agent-b', company=self.company_a)

    def test_omitting_company_is_an_explicit_cross_tenant_lookup(self):
        """No company means "no tenant filter" - deliberately visible, not implicit."""
        self.assertEqual(UserSelector.list_users().count(), 3)

    def test_company_argument_accepts_a_primary_key(self):
        self.assertEqual(
            list(UserSelector.list_users(company=self.company_a.pk)),
            [self.agent_a, self.manager_a],
        )

    # --- filtering ----------------------------------------------------------

    def test_filters_by_role_and_is_active(self):
        self.assertEqual(
            list(UserSelector.list_users(company=self.company_a, role=User.Role.MANAGER)),
            [self.manager_a],
        )
        self.assertEqual(
            list(UserSelector.list_users(company=self.company_a, is_active=True)),
            [self.agent_a],
        )
        self.assertEqual(
            list(UserSelector.list_users(company=self.company_a, is_active=False)),
            [self.manager_a],
        )

    def test_search_matches_username_email_and_phone(self):
        self.assertEqual(list(UserSelector.list_users(search='agent-a')), [self.agent_a])
        self.assertEqual(list(UserSelector.list_users(search='+966500000001')), [self.agent_a])
        self.assertEqual(list(UserSelector.list_users(search=self.manager_a.email)), [self.manager_a])

    # --- lookups ------------------------------------------------------------

    def test_get_by_id_and_username_within_the_company(self):
        self.assertEqual(UserSelector.get_by_id(self.agent_a.pk, company=self.company_a), self.agent_a)
        self.assertEqual(
            UserSelector.get_by_username('agent-a', company=self.company_a),
            self.agent_a,
        )

    def test_get_me_returns_a_fresh_instance_of_the_same_user(self):
        user = UserSelector.get_me(self.agent_a)
        self.assertEqual(user.pk, self.agent_a.pk)
        self.assertIsInstance(user, User)

    def test_results_are_ordered_by_username(self):
        usernames = [u.username for u in UserSelector.list_users()]
        self.assertEqual(usernames, sorted(usernames))

    def test_company_relation_is_eager_loaded(self):
        """One query for the list, none per row for company.name."""
        with self.assertNumQueries(1):
            [user.company.name for user in UserSelector.list_users(company=self.company_a)]
