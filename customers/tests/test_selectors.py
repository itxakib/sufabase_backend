"""Selector tests for the customers app.

This file was an empty stub, which is how ``CustomerSelector.active()`` shipped
raising ``AttributeError`` on every call - it read a choice constant off the model
that does not exist there. Every public method now has at least one test that
actually calls it.

The query-count tests are not decoration. Each one pins a property that a later
"simplification" would silently break: that ``for_company`` keeps its eager
loading, and that ``service_summary_for_customers`` answers for N customers in the
same number of queries as for one.
"""

from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection

from bookings.models import (
    HajjBooking,
    HotelBooking,
    TicketingBooking,
    TourBooking,
    TransportBooking,
    UmrahBooking,
)
from common.tests.factories import make_company, make_user
from consultancy.models import StudyVisaCase, VisaConsultancyCase
from customers.choices import RecordStatusChoices, StageChoices
from customers.models import Customer, Tag
from customers.selectors.customer_selectors import SERVICE_KEYS, CustomerSelector


class CustomerSelectorForCompanyTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.other_company = make_company()
        self.agent = make_user(company=self.company)

        self.vip = Tag.objects.create(company=self.company, name='VIP')
        self.corporate = Tag.objects.create(company=self.company, name='Corporate')

        self.ali = Customer.objects.create(
            company=self.company,
            full_name='Ali Khan',
            phone='03001112223',
            city='Karachi',
            profession='Engineer',
            stage=StageChoices.NEW,
            record_status=RecordStatusChoices.ACTIVE,
            assigned_agent=self.agent,
        )
        self.ali.tags.set([self.vip, self.corporate])

        self.sara = Customer.objects.create(
            company=self.company,
            full_name='Sara Ahmed',
            phone='03219998887',
            city='Lahore',
            profession='Doctor',
            stage=StageChoices.OLD,
            record_status=RecordStatusChoices.ARCHIVED,
        )
        self.sara.tags.set([self.vip])

        self.foreign = Customer.objects.create(
            company=self.other_company,
            full_name='Foreign Customer',
            phone='03000000000',
        )

    def names(self, queryset):
        return {customer.full_name for customer in queryset}

    def test_scopes_to_the_tenant(self):
        self.assertEqual(self.names(CustomerSelector.for_company(self.company)), {'Ali Khan', 'Sara Ahmed'})

    def test_search_matches_name_phone_city_and_profession(self):
        for term, expected in (
            ('ali', {'Ali Khan'}),
            ('0300', {'Ali Khan'}),
            ('lahore', {'Sara Ahmed'}),
            ('doctor', {'Sara Ahmed'}),
        ):
            with self.subTest(term=term):
                self.assertEqual(
                    self.names(CustomerSelector.for_company(self.company, search=term)),
                    expected,
                )

    def test_filters_by_stage(self):
        self.assertEqual(
            self.names(CustomerSelector.for_company(self.company, stage=StageChoices.OLD)),
            {'Sara Ahmed'},
        )

    def test_filters_by_record_status(self):
        self.assertEqual(
            self.names(
                CustomerSelector.for_company(
                    self.company,
                    record_status=RecordStatusChoices.ARCHIVED,
                ),
            ),
            {'Sara Ahmed'},
        )

    def test_filters_by_tag_name(self):
        self.assertEqual(
            self.names(CustomerSelector.for_company(self.company, tag='Corporate')),
            {'Ali Khan'},
        )

    def test_tag_filter_does_not_duplicate_a_customer_with_several_matching_tags(self):
        """Ali carries both tags; he must still be one row.

        Without the ``.distinct()`` in ``for_company`` this returns him twice - and
        the pagination count would then disagree with the rows a client can
        iterate, which is worse than an obviously wrong answer.
        """
        queryset = CustomerSelector.for_company(self.company, tag='VIP')
        self.assertEqual(queryset.count(), 2)
        self.assertEqual(len({c.pk for c in queryset}), 2)

    def test_a_foreign_tenants_customer_is_never_returned(self):
        for kwargs in ({}, {'search': 'Foreign'}, {'tag': 'VIP'}):
            with self.subTest(**kwargs):
                self.assertNotIn(
                    'Foreign Customer',
                    self.names(CustomerSelector.for_company(self.company, **kwargs)),
                )

    def test_eager_loading_survives_into_the_rendered_row(self):
        """Pins the ``select_related``/``prefetch_related`` on ``for_company``.

        Touching the tenant, the agent and the tags of every row must cost zero
        further queries. Dropping either clause re-introduces an N+1 that no
        functional test would notice, because the output stays correct.
        """
        customers = list(CustomerSelector.for_company(self.company))

        with self.assertNumQueries(0):
            for customer in customers:
                customer.company.name
                if customer.assigned_agent_id:
                    customer.assigned_agent.username
                list(customer.tags.all())


class CustomerSelectorLookupTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.other_company = make_company()
        self.active_customer = Customer.objects.create(
            company=self.company,
            full_name='Active Person',
            phone='03001112223',
            record_status=RecordStatusChoices.ACTIVE,
        )
        self.archived_customer = Customer.objects.create(
            company=self.company,
            full_name='Archived Person',
            phone='03219998887',
            record_status=RecordStatusChoices.ARCHIVED,
        )
        self.foreign_customer = Customer.objects.create(
            company=self.other_company,
            full_name='Foreign Person',
            phone='03000000000',
        )

    def test_active_returns_only_active_customers(self):
        """Regression: this method used to raise ``AttributeError`` on every call.

        It read ``Customer.RecordStatusChoices``, which does not exist - the enum
        lives in ``customers.choices``. Nothing caught it because this test file
        was an empty stub.
        """
        result = CustomerSelector.active(self.company)
        self.assertEqual([c.full_name for c in result], ['Active Person'])

    def test_get_by_id_returns_the_customer(self):
        found = CustomerSelector.get_by_id(self.company, self.active_customer.pk)
        self.assertEqual(found.pk, self.active_customer.pk)

    def test_get_by_id_returns_none_for_another_tenants_customer(self):
        """A 404, not a leak: the id exists but not in this tenant."""
        self.assertIsNone(CustomerSelector.get_by_id(self.company, self.foreign_customer.pk))

    def test_get_by_id_returns_none_when_missing(self):
        self.assertIsNone(CustomerSelector.get_by_id(self.company, 10_000_000))

    def test_get_by_phone_is_exact_not_substring(self):
        self.assertEqual(
            CustomerSelector.get_by_phone(self.company, '03001112223').pk,
            self.active_customer.pk,
        )
        self.assertIsNone(CustomerSelector.get_by_phone(self.company, '0300111222'))

    def test_get_by_phone_returns_none_for_another_tenants_customer(self):
        self.assertIsNone(CustomerSelector.get_by_phone(self.company, '03000000000'))


class ServiceSummaryTests(TestCase):
    """The derived per-service counts that are deliberately not stored columns."""

    def setUp(self):
        self.company = make_company()
        self.agent = make_user(company=self.company)
        self.customer = Customer.objects.create(
            company=self.company,
            full_name='Ali Khan',
            phone='03001112223',
        )
        self.empty_customer = Customer.objects.create(
            company=self.company,
            full_name='No Services',
            phone='03009990000',
        )

    def _one_of_each_service(self):
        """Create one record of every service type for ``self.customer``."""
        common = {'company': self.company, 'customer': self.customer}
        HajjBooking.objects.create(hajj_year='2026', package_name='Hajj', **common)
        UmrahBooking.objects.create(umrah_year_season='Ramadan 2026', package_name='Umrah', **common)
        TourBooking.objects.create(tour_name='Turkey', destination_country='Turkey', **common)
        TicketingBooking.objects.create(
            passenger_name='Ali Khan', pnr='AAA111', airline='PIA',
            origin='KHI', destination='JED', **common,
        )
        HotelBooking.objects.create(
            lead_guest_name='Ali Khan', hotel_name='Hilton', city='Makkah',
            room_type='Double', **common,
        )
        TransportBooking.objects.create(
            service_type='AIRPORT_TRANSFER', pickup_location='JED',
            dropoff_location='Hilton', pickup_time='02:30', number_of_passengers=2,
            vehicle_type='Hiace', **common,
        )
        VisaConsultancyCase.objects.create(
            destination_country='Schengen', visa_category='VISIT_TOURIST', **common,
        )
        StudyVisaCase.objects.create(
            destination_country='UK', study_level='MASTERS', field_of_study='Data Science',
            preferred_intake='Sept 2026', institution='Manchester', **common,
        )

    def test_summary_counts_every_service_type(self):
        self._one_of_each_service()

        summary = CustomerSelector.service_summary(self.customer)

        self.assertEqual(summary, dict.fromkeys(SERVICE_KEYS, 1))

    def test_summary_returns_zeroes_for_a_customer_with_no_services(self):
        """A full key set, so callers never need ``.get(key, 0)``."""
        summary = CustomerSelector.service_summary(self.empty_customer)

        self.assertEqual(set(summary), set(SERVICE_KEYS))
        self.assertTrue(all(count == 0 for count in summary.values()))

    def test_a_record_belonging_to_another_tenant_is_not_counted(self):
        """The ``company`` clause in the count query is load-bearing.

        Nothing in the schema stops a booking from carrying one company's id while
        pointing at another company's customer (the documented cross-tenant gap).
        Because the count filters on company as well as ``customer_id``, such a row
        does not inflate this customer's totals - it is invisible rather than
        wrong.
        """
        other_company = make_company()
        HajjBooking.objects.create(
            company=other_company,
            customer=self.customer,
            hajj_year='2026',
            package_name='Wrongly scoped',
        )

        summary = CustomerSelector.service_summary(self.customer)

        self.assertEqual(summary['hajj'], 0)

    def test_batch_summary_matches_the_single_customer_summary(self):
        self._one_of_each_service()

        batch = CustomerSelector.service_summary_for_customers([self.customer])

        self.assertEqual(batch[self.customer.pk], CustomerSelector.service_summary(self.customer))

    def test_batch_summary_covers_every_requested_customer(self):
        summary = CustomerSelector.service_summary_for_customers(
            [self.customer, self.empty_customer],
        )

        self.assertEqual(set(summary), {self.customer.pk, self.empty_customer.pk})

    def test_batch_summary_returns_nothing_for_no_customers(self):
        with self.assertNumQueries(0):
            self.assertEqual(CustomerSelector.service_summary_for_customers([]), {})

    def test_query_count_does_not_grow_with_the_number_of_customers(self):
        """The N+1 guard, and the reason the batch method exists.

        Calling ``service_summary`` once per row issues 8 queries *per customer*,
        so a 25-row page is 200 round trips. The batch form must cost the same
        whether it is handed one customer or twenty - and never more than one query
        per service model.
        """
        for index in range(6):
            Customer.objects.create(
                company=self.company,
                full_name=f'Extra {index}',
                phone=f'0300111000{index}',
            )
        everyone = list(CustomerSelector.for_company(self.company))

        with CaptureQueriesContext(connection) as one:
            CustomerSelector.service_summary_for_customers(everyone[:1])
        with CaptureQueriesContext(connection) as all_of_them:
            CustomerSelector.service_summary_for_customers(everyone)

        self.assertEqual(len(one.captured_queries), len(all_of_them.captured_queries))
        self.assertLessEqual(len(all_of_them.captured_queries), len(SERVICE_KEYS))
        self.assertGreater(len(everyone), 1, 'the test needs more than one customer')
