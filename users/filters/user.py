"""Query-string filters for the staff directory."""

from django.db.models import Q
from django_filters import CharFilter, ChoiceFilter, DateTimeFilter, NumberFilter

from common.filters import InCharFilter, StrictBooleanFilter, TenantAwareFilterSet
from users.models import User


class UserFilter(TenantAwareFilterSet):
    """Filters for ``GET /api/v1/users/``.

    Text filters are substrings; ``*_exact`` variants exist for the fields people
    copy out of an email and expect to match as a whole (username, email, phone).
    Time filters are always pairs, so "staff created since the migration" never
    needs a second endpoint or a client-side filter.

    ``company`` is a plain exact filter here, deliberately not a
    ``company__in`` list: the directory's tenant behaviour is a Module 01 open
    question (see ``UserViewSet``), and widening it to a list before that is
    settled would quietly make the question harder to answer.
    """

    # ── Identity ─────────────────────────────────────────────────────────────
    username = CharFilter(field_name='username', lookup_expr='icontains')
    username_exact = CharFilter(field_name='username', lookup_expr='iexact')
    email = CharFilter(field_name='email', lookup_expr='icontains')
    email_exact = CharFilter(field_name='email', lookup_expr='iexact')
    first_name = CharFilter(field_name='first_name', lookup_expr='icontains')
    last_name = CharFilter(field_name='last_name', lookup_expr='icontains')
    full_name = CharFilter(method='filter_full_name')
    phone = CharFilter(field_name='phone', lookup_expr='icontains')
    phone_exact = CharFilter(field_name='phone', lookup_expr='iexact')

    # ── Tenancy and role ─────────────────────────────────────────────────────
    company = NumberFilter(field_name='company_id')
    role = ChoiceFilter(field_name='role', choices=User.Role.choices)
    role_in = InCharFilter(field_name='role')
    role_not = InCharFilter(field_name='role', exclude=True)

    # ── Account state ────────────────────────────────────────────────────────
    is_active = StrictBooleanFilter(field_name='is_active')
    is_staff = StrictBooleanFilter(field_name='is_staff')
    is_superuser = StrictBooleanFilter(field_name='is_superuser')
    never_logged_in = StrictBooleanFilter(method='filter_never_logged_in')

    # ── Timestamps ───────────────────────────────────────────────────────────
    date_joined_after = DateTimeFilter(field_name='date_joined', lookup_expr='gte')
    date_joined_before = DateTimeFilter(field_name='date_joined', lookup_expr='lte')
    last_login_after = DateTimeFilter(field_name='last_login', lookup_expr='gte')
    last_login_before = DateTimeFilter(field_name='last_login', lookup_expr='lte')

    class Meta:
        model = User
        # No auto-generated filters: every parameter below is declared explicitly,
        # so the API surface is reviewable in one place instead of being implied
        # by the model's field list.
        fields = []

    def filter_full_name(self, queryset, name, value):
        """``?full_name=ali khan`` - matches across the two name columns.

        A single search box that only looked at ``first_name`` would miss half of
        "Ali Khan" typed as one string, which is how people actually type it.
        """
        return queryset.filter(
            Q(first_name__icontains=value) | Q(last_name__icontains=value),
        )

    def filter_never_logged_in(self, queryset, name, value):
        """``?never_logged_in=true`` - invited but never signed in.

        Worth its own parameter because it is a standing onboarding task and
        nobody remembers that ``last_login__isnull`` is how you ask for it.
        """
        if value:
            return queryset.filter(last_login__isnull=True)
        return queryset.filter(last_login__isnull=False)
