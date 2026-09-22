"""Thin viewsets for the users app: parse request -> selector -> serialize."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework_simplejwt.views import TokenObtainPairView

from users.filters.user import UserFilter
from users.selectors.user_selectors import UserSelector
from users.serializers.user import CustomTokenObtainPairSerializer, UserSerializer


class CustomTokenObtainPairView(TokenObtainPairView):
    """Staff login.

    Returns access/refresh tokens that also carry the caller's company and role
    (see ``CustomTokenObtainPairSerializer``). Must stay ``AllowAny`` - it is
    the endpoint that hands out the credentials in the first place - and
    SimpleJWT already rejects inactive accounts.
    """

    serializer_class = CustomTokenObtainPairSerializer


class UserViewSet(ReadOnlyModelViewSet):
    """Staff directory, scoped to a company.

    Read-only for Module 01 on purpose. Writes would be unguarded: any
    authenticated staff member could mint accounts, and Module 02 owns real
    permission enforcement (no inline role checks here). Staff are created via
    ``createsuperuser`` or Django admin until then.

    Query-param filtering is owned by ``UserFilter``, so the filter contract is
    declarative and reviewable in one place; ``UserSelector`` owns the same query
    logic for non-HTTP callers. ``company`` is applied by the selector first and
    is idempotent when the filterset applies it again.
    """

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = UserFilter
    search_fields = [
        'username',
        'email',
        'first_name',
        'last_name',
        'phone',
        # A foreign key, so searching it cannot duplicate rows the way a
        # many-to-many path would.
        'company__name',
    ]
    ordering_fields = [
        'username',
        'email',
        'first_name',
        'last_name',
        'role',
        'is_active',
        'date_joined',
        'last_login',
        'created_at',
        'updated_at',
        'company__name',
    ]
    ordering = ['username']

    def get_queryset(self):
        return UserSelector.list_users(company=self._requested_company())

    def _requested_company(self):
        """Return ``?company=`` as an int pk, or None.

        Unparseable values are ignored here rather than raised: DjangoFilterBackend
        validates the same parameter and answers 400, so this must not 500 first.
        """
        raw = self.request.query_params.get('company')
        try:
            return int(raw) if raw else None
        except (TypeError, ValueError):
            return None

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        """The authenticated staff member's own profile."""
        user = UserSelector.get_me(request.user)
        serializer = self.get_serializer(user)
        return Response(serializer.data)
