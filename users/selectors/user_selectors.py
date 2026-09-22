"""All User query logic.

Every method takes ``company`` explicitly - there is no thread-local, global,
or middleware-provided tenant context anywhere in this codebase. Callers that
need cross-tenant results must pass ``company=None`` on purpose, which makes
that intent visible in the call site instead of implicit.
"""

from django.db.models import Q, QuerySet

from users.models import User


class UserSelector:
    """Staticmethods only: no instance state, no ambient company."""

    @staticmethod
    def list_users(
        *,
        company=None,
        role: str | None = None,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> QuerySet[User]:
        """Base queryset for staff lookups.

        ``company`` accepts a ``Company`` instance or a primary key. ``None``
        deliberately means "no tenant filter" (platform-level callers).
        """
        queryset = User.objects.select_related('company')
        if company is not None:
            queryset = queryset.filter(company=company)
        if role:
            queryset = queryset.filter(role=role)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        return queryset.order_by('username')

    @staticmethod
    def get_by_id(user_id, *, company=None) -> User:
        """Raises User.DoesNotExist when the user is missing or out of tenant."""
        return UserSelector.list_users(company=company).get(pk=user_id)

    @staticmethod
    def get_by_username(username: str, *, company=None) -> User:
        """Raises User.DoesNotExist when the user is missing or out of tenant."""
        return UserSelector.list_users(company=company).get(username=username)

    @staticmethod
    def get_me(user) -> User:
        """Fresh copy of the authenticated user, company eagerly loaded."""
        return UserSelector.list_users().get(pk=user.pk)
