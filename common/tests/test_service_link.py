"""Schema-level tests for the generic ``common.ServiceLink`` model.

Like attachments, links have no views or serializers yet - the "Linked X
Record" field is optional and hidden by default, so this pass is schema only.
"""

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, models, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from common.models import ServiceLink
from common.tests.factories import make_company, make_service_link, make_user
from tenant.models import Company


class ServiceLinkSchemaTests(TestCase):
    def test_links_any_pair_of_records(self):
        """Cross-module is the point: neither end has to know about the other."""
        company = make_company()
        booker = make_user(company=company, username='booker')
        traveller = make_user(company=company, username='traveller')

        same_type = make_service_link(
            company=company, from_object=booker, to_object=traveller
        )
        cross_type = make_service_link(
            company=company, from_object=booker, to_object=company
        )

        self.assertEqual(same_type.from_object, booker)
        self.assertEqual(same_type.to_object, traveller)
        self.assertEqual(cross_type.to_object, company)
        self.assertEqual(same_type.from_content_type, same_type.to_content_type)
        self.assertNotEqual(cross_type.from_content_type, cross_type.to_content_type)

    def test_direction_is_preserved_and_not_mirrored(self):
        company = make_company()
        first = make_user(company=company, username='first')
        second = make_user(company=company, username='second')

        link = make_service_link(
            company=company, from_object=first, to_object=second
        )

        self.assertEqual(link.from_object, first)
        self.assertEqual(link.to_object, second)
        self.assertFalse(
            ServiceLink.objects.filter(
                from_object_id=second.pk, to_object_id=first.pk
            ).exists(),
            'a link is directional; nothing should create a reverse row',
        )

    def test_links_can_be_found_from_either_end(self):
        """Both ends are queried in practice, which is why both are indexed."""
        company = make_company()
        first = make_user(company=company, username='first')
        second = make_user(company=company, username='second')
        link = make_service_link(
            company=company, from_object=first, to_object=second
        )

        outgoing = ServiceLink.objects.filter(
            from_content_type=ContentType.objects.get_for_model(first),
            from_object_id=first.pk,
        )
        incoming = ServiceLink.objects.filter(
            to_content_type=ContentType.objects.get_for_model(second),
            to_object_id=second.pk,
        )

        self.assertEqual(list(outgoing), [link])
        self.assertEqual(list(incoming), [link])

    def test_indexes_cover_both_directions(self):
        indexed = [tuple(index.fields) for index in ServiceLink._meta.indexes]
        self.assertIn(('from_content_type', 'from_object_id'), indexed)
        self.assertIn(('to_content_type', 'to_object_id'), indexed)

    def test_notes_is_optional_but_never_null(self):
        field = ServiceLink._meta.get_field('notes')
        self.assertTrue(field.blank)
        self.assertFalse(field.null)

    def test_company_is_required(self):
        company = make_company()

        with self.assertRaises(IntegrityError), transaction.atomic():
            ServiceLink.objects.create(from_object=company, to_object=company)

    def test_company_fk_is_protected_and_accessor_follows_the_shared_pattern(self):
        field = ServiceLink._meta.get_field('company')
        self.assertIs(field.remote_field.on_delete, models.PROTECT)
        # Interpolated per concrete model; see the attachment test for why.
        self.assertEqual(field.remote_field.related_name, 'common_servicelink_set')
        self.assertEqual(Company.common_servicelink_set.field, field)

    def test_deleting_a_company_with_links_is_protected(self):
        company = make_company()
        make_service_link(company=company, from_object=company, to_object=company)

        with self.assertRaises(ProtectedError):
            company.delete()

        self.assertTrue(Company.objects.filter(pk=company.pk).exists())

    def test_company_is_never_implied_by_the_generic_lookup(self):
        """Same rule as attachments: the selector owns tenant filtering."""
        company_a = make_company()
        company_b = make_company()
        user_a = make_user(company=company_a, username='a')
        user_b = make_user(company=company_b, username='b')
        link_a = make_service_link(
            company=company_a, from_object=user_a, to_object=user_a
        )
        make_service_link(company=company_b, from_object=user_b, to_object=user_b)

        self.assertEqual(
            ServiceLink.objects.filter(
                from_object_id__in=[user_a.pk, user_b.pk]
            ).count(),
            2,
            'the generic lookup is not tenant-aware, so scoping is the selector\'s job',
        )
        self.assertEqual(list(ServiceLink.objects.filter(company=company_a)), [link_a])

    def test_both_ends_sharing_a_company_is_not_enforced_at_the_schema_level(self):
        """A generic FK cannot carry that constraint, so the service layer owns it.

        This test pins the current behaviour so the gap stays visible. If links
        ever start rejecting mixed-tenant pairs, that should be a deliberate
        change - not something discovered by accident.
        """
        company_a = make_company()
        company_b = make_company()
        user_a = make_user(company=company_a, username='a')
        user_b = make_user(company=company_b, username='b')

        link = make_service_link(
            company=company_a, from_object=user_a, to_object=user_b
        )
        link.full_clean()

        self.assertEqual(link.to_object.company, company_b)
        self.assertNotEqual(link.to_object.company, link.company)
