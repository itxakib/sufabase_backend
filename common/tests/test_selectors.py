"""Tests for ``common.selectors.TenantScopedSelector``.

The shared selector is the one place the tenant filter is written for all eight
service models, so these tests are about two things: that it scopes correctly, and
that it does not quietly cost extra queries.
"""

from django.test import TestCase

from bookings.models import HajjBooking, TicketingBooking
from common.selectors import TenantScopedSelector
from common.tests.factories import make_company, make_user
from customers.models import Customer


class TenantScopedSelectorTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.other_company = make_company()
        self.agent = make_user(company=self.company)

        self.customer = Customer.objects.create(
            company=self.company,
            full_name='Ali Khan',
            phone='03001112223',
        )
        self.other_tenant_customer = Customer.objects.create(
            company=self.other_company,
            full_name='Foreign Customer',
            phone='03009998887',
        )

        self.hajj = HajjBooking.objects.create(
            company=self.company,
            customer=self.customer,
            hajj_year='2026',
            package_name='Economy Hajj',
            sales_agent=self.agent,
        )
        TicketingBooking.objects.create(
            company=self.company,
            customer=self.customer,
            passenger_name='Ali Khan',
            pnr='AAA111',
            airline='PIA',
            origin='KHI',
            destination='JED',
        )
        HajjBooking.objects.create(
            company=self.other_company,
            customer=self.other_tenant_customer,
            hajj_year='2026',
            package_name='Other Tenant Hajj',
        )

    # ── for_company ──────────────────────────────────────────────────────────
    def test_for_company_scopes_to_the_tenant(self):
        records = TenantScopedSelector.for_company(HajjBooking, self.company)
        self.assertEqual(list(records), [self.hajj])

    def test_for_company_accepts_a_company_primary_key(self):
        records = TenantScopedSelector.for_company(HajjBooking, self.company.pk)
        self.assertEqual(list(records), [self.hajj])

    def test_for_company_applies_extra_exact_filters(self):
        records = TenantScopedSelector.for_company(
            HajjBooking,
            self.company,
            hajj_year='2025',
        )
        self.assertEqual(records.count(), 0)

    def test_for_company_does_not_reach_another_tenant(self):
        records = TenantScopedSelector.for_company(HajjBooking, self.company)
        self.assertNotIn(
            self.other_tenant_customer,
            [record.customer for record in records],
        )

    # ── for_customer ─────────────────────────────────────────────────────────
    def test_for_customer_scopes_to_the_customer_and_their_tenant(self):
        records = TenantScopedSelector.for_customer(HajjBooking, self.customer)
        self.assertEqual(list(records), [self.hajj])

    def test_for_customer_never_returns_another_model_of_the_same_customer(self):
        """The customer has both a Hajj and a ticket; only one is a Hajj."""
        self.assertEqual(
            TenantScopedSelector.for_customer(HajjBooking, self.customer).count(),
            1,
        )
        self.assertEqual(
            TenantScopedSelector.for_customer(TicketingBooking, self.customer).count(),
            1,
        )

    def test_for_customer_reads_the_tenant_off_the_column_not_the_relation(self):
        """``company_id`` is already loaded; ``company`` would be a second query.

        Re-fetching the customer guarantees the related object is not cached, so
        this measures exactly the difference between the two implementations: 1
        query with ``company_id``, 2 with a ``customer.company`` dereference. One
        hidden query per call is an N+1 when the selector is called in a loop.
        """
        fresh = Customer.objects.get(pk=self.customer.pk)

        with self.assertNumQueries(1):
            TenantScopedSelector.for_customer(HajjBooking, fresh).exists()

    # ── counts_by_customer ───────────────────────────────────────────────────
    def test_counts_by_customer_returns_a_count_per_customer(self):
        counts = TenantScopedSelector.counts_by_customer(
            HajjBooking,
            [self.customer.pk, self.other_tenant_customer.pk],
            self.company,
        )
        self.assertEqual(counts, {self.customer.pk: 1})

    def test_counts_by_customer_omits_a_foreign_tenants_rows(self):
        """The other customer is excluded because the *company* is filtered."""
        counts = TenantScopedSelector.counts_by_customer(
            HajjBooking,
            [self.other_tenant_customer.pk],
            self.company,
        )
        self.assertEqual(counts, {})

    def test_counts_by_customer_is_a_single_query_for_many_customers(self):
        """One aggregate, not one COUNT per id - the whole point of the method."""
        ids = [self.customer.pk, self.other_tenant_customer.pk]

        with self.assertNumQueries(1):
            TenantScopedSelector.counts_by_customer(HajjBooking, ids, self.company)

    def test_counts_by_customer_short_circuits_on_an_empty_id_list(self):
        """No ids means no query at all, not an ``IN ()`` against the table."""
        with self.assertNumQueries(0):
            counts = TenantScopedSelector.counts_by_customer(HajjBooking, [], self.company)

        self.assertEqual(counts, {})
