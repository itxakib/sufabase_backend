"""Generic selectors shared by every service-record model.

Eight models across two apps - six in ``bookings``, two in ``consultancy`` - share
exactly two query shapes: "this company's records" and "this customer's records".
Writing that chain eight times would mean eight chances to forget the tenant
filter, and a forgotten tenant filter is the one mistake this codebase treats as a
security bug rather than a bug.

Everything here takes ``company`` (or a ``customer``) as an explicit parameter.
No thread-locals, no ``request`` objects, no ambient context: a selector that needs
the tenant is told the tenant.
"""

from django.db.models import Count


class TenantScopedSelector:
    """Query building for any model with ``company`` + ``customer`` fields.

    Covers every ``ServiceRecordBase`` / ``CaseRecordBase`` subclass. It
    deliberately does **not** cover:

    * ``Customer`` itself - it has no ``customer`` field, so use
      ``customers.selectors.customer_selectors.CustomerSelector``.
    * ``Package`` - it has a ``company`` but no customer link (the customer lives
      on the trip record that composes it), so use
      ``bookings.selectors.booking_selectors.BookingSelector.package_with_components``.

    The ``select_related``/``prefetch_related`` arguments exist because the point
    of centralising these queries is to centralise the *loading strategy* too. A
    list view that forgets them turns one query into one query per row - the N+1
    this project explicitly forbids - and a caller that has to remember which
    relations each model needs will eventually get it wrong. Pass the set the
    model needs; the app-level selectors below declare them per model.
    """

    @staticmethod
    def for_company(
        model_cls,
        company,
        *,
        select_related=(),
        prefetch_related=(),
        **filters,
    ):
        """This tenant's records, optionally narrowed by exact-match ``filters``.

        ``company`` accepts a ``Company`` instance or a primary key. There is no
        ``company=None`` escape hatch - unlike ``UserSelector.list_users``, which
        has a legitimate platform-level cross-tenant caller, nothing here should
        ever query across tenants by accident.
        """
        queryset = model_cls.objects.filter(company=company, **filters)
        if select_related:
            queryset = queryset.select_related(*select_related)
        if prefetch_related:
            queryset = queryset.prefetch_related(*prefetch_related)
        return queryset

    @staticmethod
    def for_customer(
        model_cls,
        customer,
        *,
        select_related=(),
        prefetch_related=(),
        **filters,
    ):
        """One customer's records, still pinned to that customer's tenant.

        Two details that matter more than they look:

        * ``customer.pk`` and ``customer.company_id`` are read rather than
          ``customer`` and ``customer.company``. Both are already loaded columns on
          the instance, so they cost no query - whereas ``customer.company`` is a
          related-object dereference that silently issues a second SELECT the first
          time it is touched. In a selector called once per row, that is an N+1
          hidden inside a parameter.
        * ``company_id`` is kept even though ``customer`` already implies it, as a
          deliberate second condition. Nothing in the schema prevents a record from
          pointing at another company's customer (the documented cross-tenant gap),
          and this clause makes such a row invisible rather than visible. It costs
          nothing - no join, an already-matched column.
        """
        return TenantScopedSelector.for_company(
            model_cls,
            customer.company_id,
            select_related=select_related,
            prefetch_related=prefetch_related,
            customer_id=customer.pk,
            **filters,
        )

    @staticmethod
    def counts_by_customer(model_cls, customer_ids, company):
        """``{customer_id: record_count}`` for many customers in **one** query.

        The batched form of ``for_customer(...).count()``, and the reason it
        exists: calling the singular form once per service per customer is 8
        queries *per row*, so a 25-row list page costs 200 round trips to answer
        "how many services does each of these people have". This returns the same
        numbers in one query, and is what
        ``CustomerSelector.service_summary_for_customers`` is built on.

        Missing customers are simply absent from the result, so callers that need
        a key for every input should default it themselves.
        """
        ids = list(customer_ids)
        if not ids:
            return {}
        rows = (
            model_cls.objects
            .filter(company=company, customer_id__in=ids)
            .values('customer_id')
            .annotate(total=Count('pk'))
        )
        return {row['customer_id']: row['total'] for row in rows}
