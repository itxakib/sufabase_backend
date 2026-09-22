"""Query-string filters for the customer record.

This is the widest filterset in the project, on purpose: ``Customer`` is the
table every other module joins to, and "find the customers that match X" is the
question the CRM exists to answer. Everything a sales or operations user would
reasonably narrow by is a parameter here.
"""

from django.db.models import Q
from django_filters import (
    CharFilter,
    ChoiceFilter,
    DateFilter,
    NumberFilter,
)

from common.filters import (
    InCharFilter,
    InNumberFilter,
    StrictBooleanFilter,
    TenantAwareFilterSet,
)
from customers.choices import RecordStatusChoices, StageChoices
from customers.models import Customer


class CustomerFilter(TenantAwareFilterSet):
    """Filters for ``GET /api/v1/customers/``.

    Two things worth knowing before reading the field list:

    **Why ``_exact`` variants exist on the document fields.** ``cnic_number`` and
    ``passport_number`` are typed from a scanned document or a phone call, and a
    substring match on a 13-digit CNIC happily returns the wrong person when a
    search term lands mid-number. The substring filter is the convenient default;
    ``*_exact`` is the one to use when the answer must be right.

    **Why the tag filters carry ``distinct=True``.** They cross a many-to-many
    join, so a customer with two matching tags would otherwise appear twice in the
    page - and, worse, a ``count`` in the pagination envelope would disagree with
    the number of rows a client can actually see. ``distinct`` applies only when
    that specific filter is used, so the cost is not paid on every list request.

    The ``*_not`` filters exist because the common real-world question is
    exclusion: "everyone except the archived ones". Expressing that as a client
    loop over a positive filter is how stale UI lists get written.
    """

    # ── Identity ─────────────────────────────────────────────────────────────
    full_name = CharFilter(field_name='full_name', lookup_expr='icontains')
    full_name_exact = CharFilter(field_name='full_name', lookup_expr='iexact')
    father_husband_name = CharFilter(field_name='father_husband_name', lookup_expr='icontains')
    gender = CharFilter(field_name='gender', lookup_expr='iexact')
    nationality = CharFilter(field_name='nationality', lookup_expr='iexact')
    marital_status = CharFilter(field_name='marital_status', lookup_expr='iexact')
    date_of_birth_after = DateFilter(field_name='date_of_birth', lookup_expr='gte')
    date_of_birth_before = DateFilter(field_name='date_of_birth', lookup_expr='lte')

    # ── Document numbers and expiry ──────────────────────────────────────────
    cnic_number = CharFilter(field_name='cnic_number', lookup_expr='icontains')
    cnic_number_exact = CharFilter(field_name='cnic_number', lookup_expr='iexact')
    passport_number = CharFilter(field_name='passport_number', lookup_expr='icontains')
    passport_number_exact = CharFilter(field_name='passport_number', lookup_expr='iexact')
    cnic_expiry_after = DateFilter(field_name='cnic_expiry_date', lookup_expr='gte')
    cnic_expiry_before = DateFilter(field_name='cnic_expiry_date', lookup_expr='lte')
    passport_expiry_after = DateFilter(field_name='passport_expiry_date', lookup_expr='gte')
    passport_expiry_before = DateFilter(field_name='passport_expiry_date', lookup_expr='lte')
    passport_issued_after = DateFilter(field_name='passport_issue_date', lookup_expr='gte')
    passport_issued_before = DateFilter(field_name='passport_issue_date', lookup_expr='lte')

    # ── Contact ──────────────────────────────────────────────────────────────
    phone = CharFilter(field_name='phone', lookup_expr='icontains')
    phone_exact = CharFilter(field_name='phone', lookup_expr='iexact')
    whatsapp_number = CharFilter(field_name='whatsapp_number', lookup_expr='icontains')
    alt_phone = CharFilter(field_name='alt_phone', lookup_expr='icontains')
    email = CharFilter(field_name='email', lookup_expr='icontains')
    email_exact = CharFilter(field_name='email', lookup_expr='iexact')
    has_email = StrictBooleanFilter(method='filter_has_email')
    has_whatsapp = StrictBooleanFilter(method='filter_has_whatsapp')
    has_avatar = StrictBooleanFilter(method='filter_has_avatar')

    # ── Location ─────────────────────────────────────────────────────────────
    country = CharFilter(field_name='country', lookup_expr='iexact')
    city = CharFilter(field_name='city', lookup_expr='icontains')
    location_area = CharFilter(field_name='location_area', lookup_expr='icontains')
    sub_location = CharFilter(field_name='sub_location', lookup_expr='icontains')
    address = CharFilter(field_name='complete_address', lookup_expr='icontains')

    # ── Professional ─────────────────────────────────────────────────────────
    profession = CharFilter(field_name='profession', lookup_expr='icontains')
    business_type = CharFilter(field_name='business_type', lookup_expr='icontains')
    # ``company_name`` on Customer is the customer's *employer*, not the tenant.
    # Named to match the payload field so the two stay in step; the tenant is
    # ``?company=`` on the staff directory and is never a filter here.
    company_name = CharFilter(field_name='company_name', lookup_expr='icontains')
    designation = CharFilter(field_name='designation', lookup_expr='icontains')
    business_address = CharFilter(field_name='business_address', lookup_expr='icontains')
    business_contact_number = CharFilter(
        field_name='business_contact_number', lookup_expr='icontains',
    )

    # ── CRM meta ─────────────────────────────────────────────────────────────
    customer_source = CharFilter(field_name='customer_source', lookup_expr='icontains')
    referred_by = CharFilter(field_name='referred_by', lookup_expr='icontains')
    preferred_contact_method = CharFilter(field_name='preferred_contact_method', lookup_expr='iexact')
    preferred_language = CharFilter(field_name='preferred_language', lookup_expr='iexact')
    assigned_agent = NumberFilter(field_name='assigned_agent_id')
    assigned_agent_in = InNumberFilter(field_name='assigned_agent')
    unassigned = StrictBooleanFilter(method='filter_unassigned')
    has_notes = StrictBooleanFilter(method='filter_has_notes')

    # ── Status ───────────────────────────────────────────────────────────────
    stage = ChoiceFilter(field_name='stage', choices=StageChoices.choices)
    stage_in = InCharFilter(field_name='stage')
    stage_not = InCharFilter(field_name='stage', exclude=True)
    record_status = ChoiceFilter(field_name='record_status', choices=RecordStatusChoices.choices)
    record_status_in = InCharFilter(field_name='record_status')
    record_status_not = InCharFilter(field_name='record_status', exclude=True)

    # ── Marketing and emergency ──────────────────────────────────────────────
    marketing_contact_permission = CharFilter(
        field_name='marketing_contact_permission', lookup_expr='iexact',
    )
    emergency_contact_name = CharFilter(field_name='emergency_contact_name', lookup_expr='icontains')
    emergency_contact_relationship = CharFilter(
        field_name='emergency_contact_relationship', lookup_expr='iexact',
    )
    emergency_contact_number = CharFilter(
        field_name='emergency_contact_number', lookup_expr='icontains',
    )

    # ── Family and documents ─────────────────────────────────────────────────
    family_group_reference = CharFilter(field_name='family_group_reference', lookup_expr='icontains')
    has_attachments = StrictBooleanFilter(method='filter_has_attachments')

    # ── Tags (many-to-many: distinct or the page duplicates rows) ────────────
    tags = InNumberFilter(field_name='tags', distinct=True)
    all_tags = InNumberFilter(field_name='tags', method='filter_all_tags', distinct=True)
    tag_name = CharFilter(field_name='tags__name', lookup_expr='icontains', distinct=True)
    has_tags = StrictBooleanFilter(method='filter_has_tags')

    class Meta:
        model = Customer
        fields = []

    # ── Custom filters ───────────────────────────────────────────────────────
    #
    # django-filter never calls a filter method for an empty value, so ``value``
    # here is always True or False - an unparseable value is rejected as a 400
    # before reaching any of this.

    def filter_has_email(self, queryset, name, value):
        """``?has_email=false`` - reachable by phone only, the common case."""
        return self._presence(queryset, 'email', value)

    def filter_has_whatsapp(self, queryset, name, value):
        return self._presence(queryset, 'whatsapp_number', value)

    def filter_has_notes(self, queryset, name, value):
        return self._presence(queryset, 'notes', value)

    def filter_has_avatar(self, queryset, name, value):
        """``?has_avatar=false`` - the profiles still missing a photo.

        Checks both NULL and '' rather than reusing ``_presence``: ``avatar`` is
        a nullable ``ImageField``, and a row can end up with either spelling of
        "no file" depending on how it was written (admin, serializer, bulk
        import). Testing only one of the two would quietly return the wrong
        half of the data under a filter that promised the whole set.
        """
        if value:
            return queryset.exclude(Q(avatar__isnull=True) | Q(avatar=''))
        return queryset.filter(Q(avatar__isnull=True) | Q(avatar=''))

    def filter_unassigned(self, queryset, name, value):
        """``?unassigned=true`` - nobody owns this customer yet.

        The workload-and-handover list. Nullable FK, so this is an ``isnull``
        check rather than a comparison against an empty value.
        """
        return queryset.filter(assigned_agent__isnull=value)

    def filter_has_tags(self, queryset, name, value):
        """``?has_tags=true`` - segmented, as opposed to untouched raw records."""
        return queryset.filter(tags__isnull=not value).distinct()

    def filter_has_attachments(self, queryset, name, value):
        """``?has_attachments=false`` - chasing the missing passport/CNIC scan.

        Crosses the reverse generic relation, so it joins and must de-duplicate:
        a customer with three uploaded files would otherwise occupy three rows.
        """
        return queryset.filter(attachments__isnull=not value).distinct()

    def filter_all_tags(self, queryset, name, values):
        """``?all_tags=3,5`` - must carry *every* tag, not just one of them.

        Chained ``filter()`` calls are what give AND semantics; a single
        ``tags__in`` (which is what ``?tags=`` does) means OR. Both are useful and
        they answer genuinely different questions, so both exist.
        """
        for tag_id in dict.fromkeys(values):
            queryset = queryset.filter(tags__pk=tag_id)
        return queryset.distinct()

    @staticmethod
    def _presence(queryset, field_name, value):
        """Filter a CharField/TextField on "has any content" vs "is empty".

        These columns are ``blank=True``, not ``null=True``, so "not filled in"
        is the empty string. Comparing ``__isnull`` here would match nothing and
        silently return an empty page.
        """
        if value:
            return queryset.exclude(**{field_name: ''})
        return queryset.filter(**{field_name: ''})
