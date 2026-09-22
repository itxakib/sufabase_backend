"""Selectors for the customers app.

Selectors are pure query functions or static methods that take ``company`` as an
explicit parameter. They never rely on thread-local/global context for scoping,
and they never take a ``request`` - extracting the tenant out of the request is
the API layer's job, and keeping it there is what makes these callable from admin
actions, management commands and Celery tasks unchanged.
"""

from django.db.models import Q

from common.selectors import TenantScopedSelector
from customers.choices import RecordStatusChoices
from customers.models import Customer

#: ``service_summary`` keys, in the order the customer detail view renders them.
#: Public so a serializer or template can iterate the contract without hardcoding
#: the same eight strings a second time.
SERVICE_KEYS = (
    'hajj',
    'umrah',
    'tour',
    'ticketing',
    'hotel',
    'transport',
    'visa_consultancy',
    'study_visa',
)


class CustomerSelector:
    """Lookup and query logic for Customer records."""

    @staticmethod
    def for_company(company, *, search=None, stage=None, tag=None, record_status=None):
        """Base queryset for a tenant, optionally narrowed.

        Always returns ``.distinct()``: the ``tag`` filter joins through the tag
        many-to-many, so a customer carrying two matching tags would otherwise
        occupy two rows on a page and make the pagination count disagree with the
        rows a client can actually iterate.

        ``select_related``/``prefetch_related`` cover exactly what the serializer
        and the admin list touch (tenant, assigned agent, tags). Adding a field to
        ``CustomerSerializer`` that dereferences a *new* relation means adding it
        here too, or the list endpoint starts issuing one query per row.
        """
        queryset = (
            Customer.objects
            .filter(company=company)
            .select_related('company', 'assigned_agent')
            .prefetch_related('tags')
        )
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(city__icontains=search)
                | Q(profession__icontains=search)
            )
        if stage:
            queryset = queryset.filter(stage=stage)
        if record_status:
            queryset = queryset.filter(record_status=record_status)
        if tag:
            queryset = queryset.filter(tags__name=tag)
        return queryset.distinct()

    @staticmethod
    def active(company):
        """Return only ACTIVE customers.

        The choice constant comes from ``customers.choices``, not off the model.
        The first version of this method read ``Customer.RecordStatusChoices``,
        which does not exist - ``Customer`` has no nested choices class - so every
        call raised ``AttributeError``. It went unnoticed because
        ``customers/tests/test_selectors.py`` was an empty stub, which is why that
        file is no longer empty.
        """
        return CustomerSelector.for_company(
            company,
            record_status=RecordStatusChoices.ACTIVE,
        )

    @staticmethod
    def get_by_id(company, customer_id):
        """A single customer by primary key, or ``None``.

        Returns ``None`` rather than raising so a view can answer 404; a
        ``DoesNotExist`` from a selector forces every caller to write the same
        try/except.
        """
        return CustomerSelector.for_company(company).filter(pk=customer_id).first()

    @staticmethod
    def get_by_phone(company, phone):
        """Exact-phone lookup within a tenant, or ``None``.

        Exact, not substring: phone is the primary identifier in this market, and
        a partial match here returns the wrong client. Fuzzy phone matching is the
        API's ``?phone=`` filter, which is explicit about being fuzzy.
        """
        return CustomerSelector.for_company(company).filter(phone=phone).first()

    @staticmethod
    def _service_models():
        """``{service_key: model}`` for every service-record model.

        Imported lazily, not at module level. ``customers`` is the *lower* layer
        here - ``bookings`` and ``consultancy`` point at it, never the reverse (see
        ARCHITECTURE.md's dependency graph) - so a module-level import of those
        apps would invert the dependency direction. ``common`` is safe to import at
        module scope because it is the bottom of the graph; these two are not.
        """
        from bookings.models import (
            HajjBooking,
            HotelBooking,
            TicketingBooking,
            TourBooking,
            TransportBooking,
            UmrahBooking,
        )
        from consultancy.models import StudyVisaCase, VisaConsultancyCase

        return {
            'hajj': HajjBooking,
            'umrah': UmrahBooking,
            'tour': TourBooking,
            'ticketing': TicketingBooking,
            'hotel': HotelBooking,
            'transport': TransportBooking,
            'visa_consultancy': VisaConsultancyCase,
            'study_visa': StudyVisaCase,
        }

    @staticmethod
    def service_summary(customer):
        """How many of each service this customer has.

        These are precisely the derived values deliberately *not* stored as columns
        on ``Customer`` (see ``customers/README.md``): a stored counter is a second
        source of truth that drifts the moment a booking is deleted.

        Costs a fixed 8 queries (one per service model) - fine for a single
        customer detail view, and **not** fine inside a loop. For a list of
        customers use :meth:`service_summary_for_customers`, which answers the same
        question for every row in the same 8 queries.
        """
        return CustomerSelector.service_summary_for_customers([customer])[customer.pk]

    @staticmethod
    def service_summary_for_customers(customers, company=None):
        """``{customer_id: {service_key: count}}`` for many customers at once.

        Implemented as 8 aggregate queries regardless of how many customers are
        passed, rather than 8 *per customer*. That is the whole point: the naive
        version is the N+1 this project forbids, and it hides well because each
        individual call looks cheap - ``service_summary`` once per row on a 25-row
        page is 200 round trips.

        ``company`` is inferred from the first customer when not given. That is
        safe because callers hold already tenant-scoped rows, and it is read as
        ``company_id`` so it costs no query either way.

        Every input customer gets a full key set with zeros, so a caller can index
        ``summary[pk]['hotel']`` without a ``.get(..., 0)`` at every use site.
        """
        customers = list(customers)
        if not customers:
            return {}
        if company is None:
            company = customers[0].company_id

        summary = {
            customer.pk: dict.fromkeys(SERVICE_KEYS, 0)
            for customer in customers
        }
        for key, model in CustomerSelector._service_models().items():
            counts = TenantScopedSelector.counts_by_customer(model, summary.keys(), company)
            for customer_id, total in counts.items():
                summary[customer_id][key] = total
        return summary
