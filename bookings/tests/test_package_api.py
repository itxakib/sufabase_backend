"""HTTP tests for how a Package bundle is linked, and how a template is not.

Composition is loose: a bundle may hold transport and no hotel, or two hotels.
Linking only ever sends an id of a booking that already exists. The tenant wall
holds on the package, on each booking id, and on the optional catalog template.
"""

from rest_framework.test import APITestCase

from bookings.models import HajjBooking, HotelBooking, Package, PackageComponent, TourBooking
from common.tests.factories import make_company, make_user
from common.tests.mixins import CompanyHeaderMixin
from customers.models import Customer


class PackageApiTestCase(CompanyHeaderMixin, APITestCase):
    """One tenant, one staff user, one customer to hang records off."""

    def setUp(self):
        self.company = make_company()
        self.user = make_user(company=self.company)
        self.customer = Customer.objects.create(
            company=self.company, full_name='Ahmed Khan', phone='03001234567',
        )
        self.client.force_authenticate(user=self.user)
        super().setUp()

    def act_as(self, user):
        """Authenticate as another staff member and send their company header."""
        self.client.force_authenticate(user=user)
        self.client.credentials(HTTP_X_COMPANY_ID=str(user.company_id))

    def foreign_user(self):
        return make_user(company=make_company())

    def make_transport(self, customer_id):
        return self.client.post('/api/v1/transport/', {
            'customer': customer_id,
            'service_type': 'ZIYARAT',
            'pickup_location': 'Makkah',
            'dropoff_location': 'Madinah',
            'pickup_time': '06:30:00',
            'number_of_passengers': 4,
            'vehicle_type': 'Hiace',
        }, format='json').json()['data']

    def make_hotel(self, customer_id):
        return self.client.post('/api/v1/hotels/', {
            'customer': customer_id,
            'lead_guest_name': 'Ahmed Khan',
            'hotel_name': 'Hilton Makkah',
            'city': 'Makkah',
            'room_type': 'Double',
        }, format='json').json()['data']

    def make_package(self, **payload):
        body = {'name': 'Bundle'}
        body.update(payload)
        return self.client.post('/api/v1/packages/', body, format='json').json()['data']

    def link(self, package_id, **booking):
        body = {'package': package_id, **booking}
        return self.client.post('/api/v1/package-components/', body, format='json')

    def make_hajj(self, **payload):
        body = {
            'customer': self.customer.pk,
            'hajj_year': '2026',
            'package_name': 'Economy Hajj',
        }
        body.update(payload)
        return self.client.post('/api/v1/hajj/', body, format='json')

    def component_ids(self, package, field):
        return [row[field] for row in package['components'] if row[field] is not None]


class PackageCompositionTests(PackageApiTestCase):
    """Any combination of components is valid — no required component type."""

    def test_a_package_can_hold_transport_and_no_hotel(self):
        package = self.make_package(name='Transport only')
        transport = self.make_transport(self.customer.pk)

        response = self.link(package['id'], transport_booking=transport['id'])

        self.assertEqual(response.status_code, 201, response.json())
        detail = self.client.get(f"/api/v1/packages/{package['id']}/").json()['data']
        self.assertEqual(self.component_ids(detail, 'transport_booking'), [transport['id']])
        self.assertEqual(self.component_ids(detail, 'hotel_booking'), [])
        self.assertEqual(self.component_ids(detail, 'ticketing_booking'), [])

    def test_a_package_can_hold_a_hotel_and_no_transport(self):
        package = self.make_package(name='Hotel only')
        hotel = self.make_hotel(self.customer.pk)

        self.link(package['id'], hotel_booking=hotel['id'])

        detail = self.client.get(f"/api/v1/packages/{package['id']}/").json()['data']
        self.assertEqual(self.component_ids(detail, 'hotel_booking'), [hotel['id']])
        self.assertEqual(self.component_ids(detail, 'transport_booking'), [])

    def test_an_empty_package_is_allowed(self):
        """Components are attached as they are booked, not before."""
        package = self.make_package(name='Not yet filled in')

        self.assertEqual(package['components'], [])

    def test_a_package_requires_a_name(self):
        response = self.client.post('/api/v1/packages/', {'notes': 'no name'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('name', response.json()['errors'])

    def test_components_can_be_added_later(self):
        package = self.make_package(name='Started empty')
        transport = self.make_transport(self.customer.pk)
        hotel = self.make_hotel(self.customer.pk)

        self.link(package['id'], hotel_booking=hotel['id'])
        self.link(package['id'], transport_booking=transport['id'])
        detail = self.client.get(f"/api/v1/packages/{package['id']}/").json()['data']

        self.assertEqual(self.component_ids(detail, 'hotel_booking'), [hotel['id']])
        self.assertEqual(self.component_ids(detail, 'transport_booking'), [transport['id']])

    def test_a_package_can_hold_more_than_one_of_a_component_type(self):
        package = self.make_package(name='Two transfers')
        first = self.make_transport(self.customer.pk)
        second = self.make_transport(self.customer.pk)

        self.link(package['id'], transport_booking=first['id'])
        self.link(package['id'], transport_booking=second['id'])
        detail = self.client.get(f"/api/v1/packages/{package['id']}/").json()['data']

        self.assertEqual(
            sorted(self.component_ids(detail, 'transport_booking')),
            sorted([first['id'], second['id']]),
        )

    def test_linking_does_not_create_a_booking(self):
        """A nested booking object is not a way to create a hotel through the bundle."""
        package = self.make_package(name='No inline create')
        before = HotelBooking.objects.count()

        response = self.link(package['id'], hotel_booking={
            'hotel_name': 'Invented',
            'city': 'Makkah',
            'room_type': 'Double',
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('hotel_booking', response.json()['errors'])
        self.assertEqual(HotelBooking.objects.count(), before)

    def test_a_link_needs_exactly_one_booking(self):
        package = self.make_package(name='Ambiguous')
        hotel = self.make_hotel(self.customer.pk)
        transport = self.make_transport(self.customer.pk)

        response = self.link(
            package['id'],
            hotel_booking=hotel['id'],
            transport_booking=transport['id'],
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(PackageComponent.objects.filter(package_id=package['id']).count(), 0)

    def test_deleting_a_link_keeps_the_booking(self):
        package = self.make_package(name='Detach')
        hotel = self.make_hotel(self.customer.pk)
        created = self.link(package['id'], hotel_booking=hotel['id']).json()['data']

        response = self.client.delete(f"/api/v1/package-components/{created['id']}/")

        self.assertEqual(response.status_code, 204)
        self.assertTrue(HotelBooking.objects.filter(pk=hotel['id']).exists())


class PackageTripLinkTests(PackageApiTestCase):
    """The package is linked from the trip record, not the other way round."""

    def test_a_hajj_record_can_point_at_a_package(self):
        package = self.make_package(name='Hajj bundle')

        response = self.make_hajj(package=package['id'])

        self.assertEqual(response.status_code, 201, response.json())
        self.assertEqual(response.json()['data']['package'], package['id'])

    def test_a_trip_without_a_package_is_still_valid(self):
        response = self.make_hajj()

        self.assertEqual(response.status_code, 201, response.json())
        self.assertIsNone(response.json()['data']['package'])

    def test_the_link_can_be_made_after_the_trip_exists(self):
        created = self.make_hajj().json()['data']
        package = self.make_package(name='Bundle added later')

        updated = self.client.patch(
            f"/api/v1/hajj/{created['id']}/", {'package': package['id']},
            format='json',
        ).json()['data']

        self.assertEqual(updated['package'], package['id'])

    def test_the_link_can_be_cleared_without_deleting_the_package(self):
        package = self.make_package(name='Detachable')
        created = self.make_hajj(package=package['id']).json()['data']

        updated = self.client.patch(
            f"/api/v1/hajj/{created['id']}/", {'package': None}, format='json',
        ).json()['data']

        self.assertIsNone(updated['package'])
        self.assertTrue(Package.objects.filter(pk=package['id']).exists())

    def test_the_same_package_can_back_more_than_one_trip(self):
        package = self.make_package(name='Shared bundle')
        hajj = self.make_hajj(package=package['id']).json()['data']
        tour = self.client.post('/api/v1/tours/', {
            'customer': self.customer.pk,
            'tour_name': 'Same bundle tour',
            'destination_country': 'Saudi Arabia',
            'package': package['id'],
        }, format='json').json()['data']

        self.assertEqual(HajjBooking.objects.filter(package_id=package['id']).count(), 1)
        self.assertEqual(TourBooking.objects.filter(package_id=package['id']).count(), 1)
        self.assertEqual(hajj['package'], tour['package'])
        self.assertEqual(
            list(Package.objects.get(pk=package['id']).hajj_trips.values_list('pk', flat=True)),
            [hajj['id']],
        )

    def test_the_list_row_carries_the_package_name_not_just_an_id(self):
        package = self.make_package(name='Hajj 2026 Ultra')
        self.make_hajj(package=package['id'])

        row = self.client.get('/api/v1/hajj/').json()['data']['results'][0]

        self.assertEqual(row['package']['name'], 'Hajj 2026 Ultra')


class PackageTenantIsolationTests(PackageApiTestCase):
    """Every id that crosses the wire is narrowed to the caller's company."""

    def test_cannot_link_another_tenants_package(self):
        package = self.make_package(name='Our bundle')
        self.act_as(self.foreign_user())

        response = self.make_hajj(package=package['id'])

        self.assertEqual(response.status_code, 400)
        self.assertIn('package', response.json()['errors'])

    def test_cannot_link_another_tenants_umrah_package(self):
        package = self.make_package(name='Our bundle')
        self.act_as(self.foreign_user())

        response = self.client.post('/api/v1/umrah/', {
            'customer': self.customer.pk, 'umrah_year_season': 'Ramadan 2026',
            'package_name': 'Rival', 'package': package['id'],
        }, format='json')

        self.assertEqual(response.status_code, 400)

    def test_cannot_link_another_tenants_package_to_a_tour(self):
        package = self.make_package(name='Our bundle')
        self.act_as(self.foreign_user())

        response = self.client.post('/api/v1/tours/', {
            'customer': self.customer.pk, 'tour_name': 'Rival tour',
            'destination_country': 'Saudi Arabia', 'package': package['id'],
        }, format='json')

        self.assertEqual(response.status_code, 400)

    def test_cannot_link_another_tenants_components_into_a_package(self):
        transport = self.make_transport(self.customer.pk)
        self.act_as(self.foreign_user())
        package = self.make_package(name='Theft')

        response = self.link(package['id'], transport_booking=transport['id'])

        self.assertEqual(response.status_code, 400)
        self.assertIn('transport_booking', response.json()['errors'])

    def test_cannot_point_a_bundle_at_another_tenants_template(self):
        template = self.client.post('/api/v1/package-templates/', {
            'name': 'Economy Hajj',
            'lines': [{
                'kind': 'HOTEL',
                'city': 'Makkah',
                'room_type': 'Quad',
                'meal_plan': 'BREAKFAST',
                'nights': 5,
            }],
        }, format='json').json()['data']
        self.act_as(self.foreign_user())

        response = self.client.post('/api/v1/packages/', {
            'name': 'Stolen',
            'template': template['id'],
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('template', response.json()['errors'])

    def test_another_tenants_package_is_not_readable(self):
        package = self.make_package(name='Our bundle')
        self.act_as(self.foreign_user())

        response = self.client.get(f"/api/v1/packages/{package['id']}/")

        self.assertEqual(response.status_code, 404)

    def test_another_tenants_package_is_not_listed(self):
        self.make_package(name='Our bundle')
        self.act_as(self.foreign_user())

        payload = self.client.get('/api/v1/packages/').json()

        self.assertEqual(payload['data']['count'], 0)
