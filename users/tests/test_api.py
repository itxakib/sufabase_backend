from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from common.tests.factories import DEFAULT_PASSWORD, make_company, make_user
from common.tests.mixins import CompanyHeaderMixin
from users.models import User
from users.serializers.user import UserSerializer

TOKEN_URL = '/api/v1/token/'
REFRESH_URL = '/api/v1/token/refresh/'
LOGOUT_URL = '/api/v1/token/logout/'
USERS_URL = '/api/v1/users/'


class StaffLoginTests(APITestCase):
    def setUp(self):
        self.company = make_company(name='Alpha Travel', slug='alpha-travel')
        self.user = make_user(
            company=self.company,
            username='manager-1',
            role=User.Role.MANAGER,
        )

    def login(self, username='manager-1', password=DEFAULT_PASSWORD):
        return self.client.post(
            TOKEN_URL,
            {'username': username, 'password': password},
            format='json',
        )

    def test_login_returns_access_and_refresh_tokens(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_access_token_carries_user_company_and_role_claims(self):
        token = AccessToken(self.login().data['access'])
        self.assertEqual(token['user_id'], str(self.user.id))
        self.assertEqual(token['company_id'], str(self.company.id))
        self.assertEqual(token['role'], User.Role.MANAGER)
        self.assertFalse(token['is_staff'])

    def test_claim_types_are_pinned_for_the_frontend(self):
        token = AccessToken(self.login().data['access'])
        self.assertIsInstance(token['user_id'], str)
        self.assertIsInstance(token['company_id'], str)
        self.assertIsInstance(token['role'], str)
        self.assertIsInstance(token['is_staff'], bool)

    def test_superuser_claim_reflects_its_company(self):
        """A superuser is tenant-scoped too, so it still carries a company."""
        User.objects.create_superuser(
            username='platform-admin',
            email='admin@example.com',
            password=DEFAULT_PASSWORD,
            company=self.company,
        )
        token = AccessToken(self.login(username='platform-admin').data['access'])
        self.assertEqual(token['company_id'], str(self.company.id))
        self.assertEqual(token['role'], User.Role.ADMIN)
        self.assertTrue(token['is_staff'])

    def test_login_rejects_a_wrong_password(self):
        self.assertEqual(self.login(password='not-the-password').status_code, 401)

    def test_login_rejects_an_unknown_username(self):
        self.assertEqual(self.login(username='nobody').status_code, 401)

    def test_login_rejects_inactive_staff(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.assertEqual(self.login().status_code, 401)

    def test_logout_blacklists_the_refresh_token(self):
        refresh = self.login().data['refresh']

        response = self.client.post(LOGOUT_URL, {'refresh': refresh}, format='json')
        self.assertEqual(response.status_code, 200)

        replay = self.client.post(REFRESH_URL, {'refresh': refresh}, format='json')
        self.assertEqual(replay.status_code, 401)

    def test_refresh_rotates_the_token_and_kills_the_old_one(self):
        refresh = self.login().data['refresh']

        rotated = self.client.post(REFRESH_URL, {'refresh': refresh}, format='json')
        self.assertEqual(rotated.status_code, 200)
        self.assertNotEqual(rotated.data['refresh'], refresh)

        replay = self.client.post(REFRESH_URL, {'refresh': refresh}, format='json')
        self.assertEqual(replay.status_code, 401)


class UserDirectoryApiTests(CompanyHeaderMixin, APITestCase):
    def setUp(self):
        self.company_a = make_company(name='Alpha Travel', slug='alpha-travel')
        self.company_b = make_company(name='Beta Tours', slug='beta-tours')

        self.staff_a = make_user(
            company=self.company_a,
            username='staff-a',
            role=User.Role.AGENT,
            phone='+966500000001',
        )
        self.manager_a = make_user(
            company=self.company_a,
            username='manager-a',
            role=User.Role.MANAGER,
            is_active=False,
        )
        self.staff_b = make_user(company=self.company_b, username='staff-b')

        self.client.force_authenticate(self.staff_a)
        self.client.credentials(HTTP_X_COMPANY_ID=str(self.company_a.pk))

    def usernames(self, response):
        return {row['username'] for row in response.data['results']}

    def test_directory_requires_authentication(self):
        self.assertEqual(APIClient().get(USERS_URL).status_code, 401)

    def test_me_returns_the_authenticated_profile(self):
        response = self.client.get(f'{USERS_URL}me/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['username'], 'staff-a')
        self.assertEqual(response.data['company'], self.company_a.id)
        self.assertEqual(response.data['company_name'], 'Alpha Travel')
        self.assertEqual(response.data['role'], User.Role.AGENT)

    def test_list_is_scoped_by_the_company_parameter(self):
        response = self.client.get(USERS_URL, {'company': self.company_a.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.usernames(response), {'staff-a', 'manager-a'})
        self.assertNotIn('staff-b', self.usernames(response))

    def test_unscoped_list_spans_tenants(self):
        """Documented Module 01 behaviour until Module 02 adds enforcement."""
        self.assertEqual(self.usernames(self.client.get(USERS_URL)), {'staff-a', 'manager-a', 'staff-b'})

    def test_filters_by_role(self):
        response = self.client.get(USERS_URL, {'company': self.company_a.id, 'role': User.Role.MANAGER})
        self.assertEqual(self.usernames(response), {'manager-a'})

    def test_filters_by_is_active(self):
        response = self.client.get(USERS_URL, {'company': self.company_a.id, 'is_active': 'false'})
        self.assertEqual(self.usernames(response), {'manager-a'})

        response = self.client.get(USERS_URL, {'company': self.company_a.id, 'is_active': 'true'})
        self.assertEqual(self.usernames(response), {'staff-a'})

    def test_searches_by_username_email_and_phone(self):
        for term, expected in (
            ('staff-b', {'staff-b'}),
            ('+966500000001', {'staff-a'}),
            (self.staff_a.email, {'staff-a'}),
        ):
            with self.subTest(term=term):
                response = self.client.get(USERS_URL, {'search': term})
                self.assertEqual(self.usernames(response), expected)

    def test_unparseable_company_parameter_is_a_400_not_a_500(self):
        response = self.client.get(USERS_URL, {'company': 'not-a-number'})
        self.assertEqual(response.status_code, 400)

    def test_directory_is_read_only(self):
        """Writes are withheld until Module 02 can gate them with permissions."""
        payload = {'username': 'newcomer', 'password': 'x'}
        self.assertEqual(self.client.post(USERS_URL, payload, format='json').status_code, 405)
        self.assertEqual(
            self.client.patch(f'{USERS_URL}{self.staff_a.pk}/', payload, format='json').status_code,
            405,
        )
        self.assertEqual(self.client.delete(f'{USERS_URL}{self.staff_a.pk}/').status_code, 405)
        self.assertEqual(User.objects.count(), 3)

    def test_audit_and_password_fields_are_not_exposed(self):
        response = self.client.get(f'{USERS_URL}me/')
        for field in ('created_by', 'updated_by', 'password'):
            self.assertNotIn(field, response.data)

    def test_company_is_never_client_writable(self):
        self.assertTrue(UserSerializer().fields['company'].read_only)
