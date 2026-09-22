"""Shared django-filter building blocks.

Every app's filterset is built from these pieces, for the same reason
``common.models`` exists: four apps inventing four spellings of the same query
parameter is how an API ends up with ``?is_active=true`` on one endpoint,
``?active=1`` on another and nothing at all on a third.

What lives here is only what django-filter does not already give you:

* comma-separated ``__in`` filters (``?role=admin,manager``) that behave the same
  everywhere, and
* the ``created_after``/``created_before`` pair that is valid on *every* model in
  this project, because every model inherits ``BaseModel``.

Two conventions the base classes cannot enforce but every filterset in this repo
follows, so the parameter vocabulary stays predictable:

===========================  ==================================================
``?name=ali``                substring match (``icontains``) - the default
``?name_exact=ali``          whole-value match, for identifiers people paste in
``?role=admin,manager``      one of several values
``?role_not=agent``          *not* one of several values
``?created_after=...``       range pair: ``created_after`` / ``created_before``
``?ordering=-created_at``    DRF's OrderingFilter, declared per view
``?is_active=maybe``         a 400, via :class:`StrictBooleanFilter`
===========================  ==================================================

``TenantAwareFilterSet`` is the one piece here with judgement in it - see its
docstring for why the company comes off the request rather than the query string.
"""

from django import forms
from django_filters import (
    BaseInFilter,
    BooleanFilter,
    CharFilter,
    DateTimeFilter,
    FilterSet,
    NumberFilter,
)


class StrictBooleanField(forms.Field):
    """A boolean query parameter that refuses anything it does not understand.

    Both of Django's built-in boolean fields are wrong for an HTTP filter, and
    both are wrong *silently*:

    * ``NullBooleanField`` - what django-filter's ``BooleanFilter`` uses - maps any
      unrecognised value to ``None``, which django-filter then reads as "parameter
      absent". ``?is_active=maybe`` therefore returns the **unfiltered** list with a
      200: a client that mistypes a flag is shown every row and told it succeeded.
    * ``BooleanField`` maps anything non-empty to ``True``, so ``?is_active=maybe``
      means "active only" - also silently wrong, in the opposite direction.

    A filter is a promise about which rows come back. Returning rows that do not
    match, under a success status, breaks that promise in the one way a client
    cannot detect. So this accepts exactly the spellings API clients actually send
    and rejects everything else with a 400.

    An empty value stays ``None`` - i.e. "parameter absent" - to match every other
    filter in this project, where ``?field=`` is ignored rather than an error.
    """

    TRUE_VALUES = frozenset({'true', '1'})
    FALSE_VALUES = frozenset({'false', '0'})

    def to_python(self, value):
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip().lower()
            if not stripped:
                return None
            if stripped in self.TRUE_VALUES:
                return True
            if stripped in self.FALSE_VALUES:
                return False
        raise forms.ValidationError(
            'Enter a valid boolean: true or false.',
            code='invalid',
        )


class StrictBooleanFilter(BooleanFilter):
    """``BooleanFilter`` that 400s on a bad value instead of ignoring it.

    Use this instead of ``BooleanFilter`` everywhere in this project - the plain
    one turns a typo into a silently unfiltered response.
    """

    field_class = StrictBooleanField


class InNumberFilter(BaseInFilter, NumberFilter):
    """``?field=1,2,3`` -> ``field__in=[1, 2, 3]`` for integer primary keys.

    Used for foreign keys (``?assigned_agent=4,7``) and for any numeric column.
    ``BaseInFilter`` supplies the ``in`` lookup and the comma splitting; this
    subclass exists so intent is readable at the declaration site.
    """


class InCharFilter(BaseInFilter, CharFilter):
    """``?field=a,b,c`` -> ``field__in=['a', 'b', 'c']`` for text and choices.

    The natural partner to :class:`InNumberFilter`: ``?stage=BOOKED,CONFIRMED``
    reads better than four repeated parameters, and it is the only way to express
    a multi-value choice filter on a ``TextChoices`` column.
    """


class AuditRangeFilterSet(FilterSet):
    """``created_after`` / ``created_before`` / ``updated_after`` / ``updated_before``.

    Valid on any filterset in this project, because every model inherits
    ``BaseModel`` and therefore always has both timestamps. Declaring these once
    here is why no app has to remember to add them.

    Named ``created_after`` rather than django-filter's default
    ``created_at_after``: these parameters are read by humans in Swagger UI and
    typed by humans debugging a frontend, and four extra characters on every one
    of them buys nothing.

    This is a ``FilterSet`` subclass and not a bare mixin on purpose.
    django-filter collects declared filters only from bases that are themselves
    ``FilterSet``s (it reads each base's ``declared_filters``), so the same four
    declarations on a plain mixin are **silently discarded** - no error, no
    warning, just four filters that exist in the source and not at runtime.
    ``common.tests.test_filters`` pins that they reach the queryset.
    """

    created_after = DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = DateTimeFilter(field_name='created_at', lookup_expr='lte')
    updated_after = DateTimeFilter(field_name='updated_at', lookup_expr='gte')
    updated_before = DateTimeFilter(field_name='updated_at', lookup_expr='lte')


class TenantAwareFilterSet(AuditRangeFilterSet):
    """A filterset that can read the caller's company without being told twice.

    DRF's ``DjangoFilterBackend`` passes the request into the filterset, so a
    filter method can reach ``self.company`` - the *requesting user's* tenant.

    That matters for any filter crossing a relation. A related id arriving in the
    query string must be validated against the caller's own tenant, otherwise the
    filter becomes an oracle: ``?assigned_agent=999`` returning a row tells the
    caller that user 999 exists, in whatever company they belong to. Reading the
    company from ``request.user.company`` keeps that check server-side and
    authoritative - the client never supplies a scope in this codebase, it only
    narrows within the scope it already has.

    It is ``None`` when there is no request (a filterset instantiated directly in
    a test) or the caller is anonymous. Filters that need it must treat ``None``
    as "no tenant known" rather than assuming a value.

    Inherits :class:`AuditRangeFilterSet`, so every filterset built on this also
    gets the four timestamp range parameters.
    """

    @property
    def company(self):
        user = getattr(getattr(self, 'request', None), 'user', None)
        return getattr(user, 'company', None)
