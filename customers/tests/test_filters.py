"""Filter and search tests for the customer and tag endpoints.

Exercised through the API rather than the filtersets directly, on purpose: that
covers the filterset, the backend, the view's company-scoped queryset and the
serializer in one assertion, and a wiring mistake only ever shows up at that
boundary. The filterset unit tests live in ``common.tests.test_filters``.
"""

from datetime import date, timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from common.tests.factories import make_attachment, make_company, make_user
from common.tests.mixins import CompanyHeaderMixin, MediaRootMixin
from customers.choices import RecordStatusChoices, StageChoices
from customers.models import Customer, Tag

CUSTOMERS_URL = '/api/v1/customers/'
TAGS_URL = '/api/v1/tags/'


class CustomerFilterApiTests(CompanyHeaderMixin, MediaRootMixin, APITestCase):
    """The customer filterset, end to end."""

    def setUp(self):
        self.company = make_company(name='Alpha Travel', slug='alpha-travel')
        self.other_company = make_company(name='Beta Tours', slug='beta-tours')
        self.agent = make_user(company=self.company, username='agent-1')
        self.client.force_authenticate(self.agent)
        self.client.credentials(HTTP_X_COMPANY_ID=str(self.company.pk))

        self.vip = Tag.objects.create(company=self.company, name='VIP', color='#ff0000')
        self.umrah = Tag.objects.create(company=self.company, name='Umrah-2026')
        self.other_tenant_tag = Tag.objects.create(company=self.other_company, name='VIP')

        # Ali carries two tags on purpose: he is the row that duplicates if a
        # many-to-many filter forgets to de-duplicate.
        self.ali = self._customer(
            full_name='Ali Khan',
            phone='03001112223',
            whatsapp_number='+923001112223',
            email='ali@example.com',
            cnic_number='4210112345671',
            passport_number='AB1234567',
            passport_expiry_date=date(2027, 6, 1),
            city='Karachi',
            country='PK',
            profession='Engineer',
            customer_source='WhatsApp',
            stage=StageChoices.NEW,
            record_status=RecordStatusChoices.ACTIVE,
            assigned_agent=self.agent,
        )
        self.ali.tags.set([self.vip, self.umrah])
        make_attachment(company=self.company, target=self.ali)

        self.sara = self._customer(
            full_name='Sara Ahmed',
            phone='03219998887',
            email='',
            passport_number='CD7654321',
            passport_expiry_date=date(2026, 11, 1),
            city='Lahore',
            country='PK',
            stage=StageChoices.OLD,
            record_status=RecordStatusChoices.ARCHIVED,
        )
        self.sara.tags.set([self.vip])

        self.bilal = self._customer(
            full_name='Bilal Qureshi',
            phone='03334445556',
            city='Islamabad',
            stage=StageChoices.NEW,
            record_status=RecordStatusChoices.INACTIVE,
        )

        self.other_tenant = Customer.objects.create(
            company=self.other_company,
            full_name='Other Tenant Customer',
            phone='03000000000',
        )

    def _customer(self, **overrides):
        defaults = {'company': self.company}
        defaults.update(overrides)
        return Customer.objects.create(**defaults)

    # ── Helpers ──────────────────────────────────────────────────────────────
    def get(self, **params):
        return self.client.get(CUSTOMERS_URL, params)

    def names(self, response):
        return {row['full_name'] for row in response.data['results']}

    # ── Status filters ───────────────────────────────────────────────────────
    def test_filters_by_stage(self):
        self.assertEqual(self.names(self.get(stage=StageChoices.NEW)), {'Ali Khan', 'Bilal Qureshi'})
        self.assertEqual(self.names(self.get(stage=StageChoices.OLD)), {'Sara Ahmed'})

    def test_filters_by_a_list_of_stages(self):
        self.assertEqual(
            self.names(self.get(stage_in='NEW,OLD')),
            {'Ali Khan', 'Bilal Qureshi', 'Sara Ahmed'},
        )

    def test_excludes_a_list_of_stages(self):
        self.assertEqual(self.names(self.get(stage_not='NEW')), {'Sara Ahmed'})

    def test_filters_by_record_status(self):
        self.assertEqual(self.names(self.get(record_status=RecordStatusChoices.ARCHIVED)), {'Sara Ahmed'})

    def test_excludes_a_list_of_record_statuses(self):
        """The common real question: everything except the archived ones."""
        self.assertEqual(
            self.names(self.get(record_status_not=RecordStatusChoices.ARCHIVED)),
            {'Ali Khan', 'Bilal Qureshi'},
        )

    # ── Assignment ───────────────────────────────────────────────────────────
    def test_filters_by_assigned_agent(self):
        self.assertEqual(self.names(self.get(assigned_agent=self.agent.pk)), {'Ali Khan'})

    def test_filters_by_a_list_of_agents(self):
        self.assertEqual(self.names(self.get(assigned_agent_in=str(self.agent.pk))), {'Ali Khan'})

    def test_filters_unassigned(self):
        self.assertEqual(self.names(self.get(unassigned='true')), {'Sara Ahmed', 'Bilal Qureshi'})

    def test_filters_assigned(self):
        self.assertEqual(self.names(self.get(unassigned='false')), {'Ali Khan'})

    # ── Tags, including the de-duplication contract ──────────────────────────
    def test_filters_by_tag_and_does_not_duplicate_rows(self):
        """Ali has both tags; he must still appear exactly once.

        This is the whole reason the tag filters carry ``distinct=True``: without
        it the page would hold Ali twice and the pagination ``count`` would
        disagree with the rows a client can actually iterate.
        """
        response = self.get(tags=f'{self.vip.pk},{self.umrah.pk}')

        self.assertEqual(response.data['count'], 2)
        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual(self.names(response), {'Ali Khan', 'Sara Ahmed'})

    def test_filters_by_tag_name_substring(self):
        self.assertEqual(self.names(self.get(tag_name='umrah')), {'Ali Khan'})

    def test_all_tags_requires_every_tag_not_any(self):
        """``?all_tags=`` is AND; ``?tags=`` is OR. They answer different questions."""
        self.assertEqual(
            self.names(self.get(all_tags=f'{self.vip.pk},{self.umrah.pk}')),
            {'Ali Khan'},
        )

    def test_filters_customers_without_tags(self):
        self.assertEqual(self.names(self.get(has_tags='false')), {'Bilal Qureshi'})

    def test_a_foreign_tenant_tag_id_matches_nothing(self):
        """A tag id from another company must not be a way to find anything.

        The queryset is company-scoped before the filter runs, so the id simply
        has no reachable rows - it is not an existence oracle either.
        """
        response = self.get(tags=str(self.other_tenant_tag.pk))
        self.assertEqual(response.data['count'], 0)

    # ── Documents and expiry ─────────────────────────────────────────────────
    def test_partial_document_number_matches(self):
        self.assertEqual(self.names(self.get(cnic_number='1234567')), {'Ali Khan'})

    def test_exact_document_number_is_a_whole_value_match(self):
        """A 13-digit CNIC typed from a document must not match mid-number."""
        self.assertEqual(self.names(self.get(cnic_number_exact='4210112345671')), {'Ali Khan'})
        self.assertEqual(self.names(self.get(cnic_number_exact='1234567')), set())

    def test_passport_expiring_before_a_date(self):
        """The "who needs renewing before the season" list."""
        cutoff = date(2027, 1, 1).isoformat()
        self.assertEqual(self.names(self.get(passport_expiry_before=cutoff)), {'Sara Ahmed'})

    def test_passport_expiring_after_a_date(self):
        cutoff = date(2027, 1, 1).isoformat()
        self.assertEqual(self.names(self.get(passport_expiry_after=cutoff)), {'Ali Khan'})

    def test_filters_customers_with_attachments(self):
        self.assertEqual(self.names(self.get(has_attachments='true')), {'Ali Khan'})
        self.assertEqual(
            self.names(self.get(has_attachments='false')),
            {'Sara Ahmed', 'Bilal Qureshi'},
        )

    # ── Contact and presence flags ───────────────────────────────────────────
    def test_filters_customers_without_an_email(self):
        self.assertEqual(self.names(self.get(has_email='false')), {'Sara Ahmed', 'Bilal Qureshi'})

    def test_filters_customers_with_whatsapp(self):
        self.assertEqual(self.names(self.get(has_whatsapp='true')), {'Ali Khan'})

    def test_exact_phone_matches_whole_value_only(self):
        self.assertEqual(self.names(self.get(phone_exact='03001112223')), {'Ali Khan'})
        self.assertEqual(self.names(self.get(phone_exact='0300111222')), set())

    # ── Timestamps ───────────────────────────────────────────────────────────
    def test_created_after_excludes_backdated_rows(self):
        Customer.objects.filter(pk=self.sara.pk).update(
            created_at=timezone.now() - timedelta(days=30),
        )
        cutoff = (timezone.now() - timedelta(days=1)).isoformat()

        self.assertEqual(self.names(self.get(created_after=cutoff)), {'Ali Khan', 'Bilal Qureshi'})

    def test_created_before_keeps_only_backdated_rows(self):
        Customer.objects.filter(pk=self.sara.pk).update(
            created_at=timezone.now() - timedelta(days=30),
        )
        cutoff = (timezone.now() - timedelta(days=1)).isoformat()

        self.assertEqual(self.names(self.get(created_before=cutoff)), {'Sara Ahmed'})

    # ── Combinations, search, ordering ───────────────────────────────────────
    def test_filters_combine_with_and(self):
        self.assertEqual(
            self.names(self.get(stage=StageChoices.NEW, record_status=RecordStatusChoices.INACTIVE)),
            {'Bilal Qureshi'},
        )

    def test_search_spans_the_scalar_columns(self):
        for term, expected in (
            ('Karachi', {'Ali Khan'}),
            ('ali@example.com', {'Ali Khan'}),
            ('AB1234567', {'Ali Khan'}),
            ('WhatsApp', {'Ali Khan'}),
            ('engin', {'Ali Khan'}),
            ('Khan', {'Ali Khan'}),
        ):
            with self.subTest(term=term):
                self.assertEqual(self.names(self.get(search=term)), expected)

    def test_ordering_ascending_and_descending(self):
        ascending = [row['full_name'] for row in self.get(ordering='full_name').data['results']]
        descending = [row['full_name'] for row in self.get(ordering='-full_name').data['results']]

        self.assertEqual(ascending, ['Ali Khan', 'Bilal Qureshi', 'Sara Ahmed'])
        self.assertEqual(descending, ['Sara Ahmed', 'Bilal Qureshi', 'Ali Khan'])

    def test_ordering_by_several_fields(self):
        response = self.get(ordering='record_status,full_name')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 3)

    # ── Tenant isolation and validation ──────────────────────────────────────
    def test_filters_cannot_reach_another_tenant(self):
        self.assertEqual(self.names(self.get(full_name='Other Tenant')), set())
        self.assertEqual(self.names(self.get(search='Other Tenant')), set())

    def test_an_invalid_choice_value_is_a_400(self):
        self.assertEqual(self.get(stage='NOT_A_STAGE').status_code, 400)

    def test_an_invalid_boolean_is_a_400(self):
        """Silently ignoring an unparseable flag would show the user the wrong list.

        This used to return 200 with *every* customer, because django-filter's
        own ``BooleanFilter`` maps an unknown value to ``None`` and then treats it
        as "parameter absent". ``StrictBooleanFilter`` is what makes it a 400.
        """
        self.assertEqual(self.get(unassigned='maybe').status_code, 400)

    def test_an_empty_boolean_is_ignored_like_every_other_empty_filter(self):
        response = self.get(has_email='')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 3)

    def test_an_invalid_date_is_a_400(self):
        self.assertEqual(self.get(passport_expiry_before='not-a-date').status_code, 400)

    def test_an_invalid_tag_id_is_a_400(self):
        self.assertEqual(self.get(tags='abc').status_code, 400)

    def test_unknown_parameters_are_ignored(self):
        """Unknown params must not 400 - frontends pass stale keys during deploys."""
        response = self.get(nonexistent_filter='x')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 3)


class TagFilterApiTests(CompanyHeaderMixin, APITestCase):
    """The tag filterset, including the usage check."""

    def setUp(self):
        self.company = make_company()
        self.other_company = make_company()
        self.user = make_user(company=self.company)
        self.client.force_authenticate(self.user)
        self.client.credentials(HTTP_X_COMPANY_ID=str(self.company.pk))

        self.used = Tag.objects.create(company=self.company, name='VIP', color='#ff0000')
        self.unused = Tag.objects.create(company=self.company, name='Dormant')
        self.foreign = Tag.objects.create(company=self.other_company, name='Other Tenant Tag')

        customer = Customer.objects.create(
            company=self.company,
            full_name='Tagged Customer',
            phone='03001112223',
        )
        customer.tags.set([self.used])

    def get(self, **params):
        return self.client.get(TAGS_URL, params)

    def names(self, response):
        return {row['name'] for row in response.data['results']}

    def test_lists_only_the_callers_tags(self):
        self.assertEqual(self.names(self.get()), {'VIP', 'Dormant'})

    def test_filters_by_name_substring(self):
        self.assertEqual(self.names(self.get(name='dorm')), {'Dormant'})

    def test_exact_name_is_a_whole_value_match(self):
        self.assertEqual(self.names(self.get(name_exact='VIP')), {'VIP'})
        self.assertEqual(self.names(self.get(name_exact='vip')), {'VIP'})
        self.assertEqual(self.names(self.get(name_exact='V')), set())

    def test_filters_by_color(self):
        self.assertEqual(self.names(self.get(color='#ff0000')), {'VIP'})

    def test_filters_tags_without_a_color(self):
        self.assertEqual(self.names(self.get(has_color='false')), {'Dormant'})

    def test_filters_unused_tags(self):
        """The tag-hygiene list: labels nobody ever applied."""
        self.assertEqual(self.names(self.get(used='false')), {'Dormant'})

    def test_filters_used_tags_without_duplicating_them(self):
        response = self.get(used='true')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(self.names(response), {'VIP'})

    def test_searches_by_name(self):
        self.assertEqual(self.names(self.get(search='vip')), {'VIP'})

    def test_orders_by_name_descending(self):
        names = [row['name'] for row in self.get(ordering='-name').data['results']]
        self.assertEqual(names, ['VIP', 'Dormant'])
