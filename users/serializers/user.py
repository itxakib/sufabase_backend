from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from users.models import User


class UserMiniSerializer(serializers.ModelSerializer):
    """Minimal user representation — used nested inside other serializers
    so the frontend sees a name instead of a bare integer ID.
    Five fields only, zero extra queries.  Read-only."""

    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "full_name", "email"]
        read_only_fields = fields

    def get_full_name(self, obj) -> str:
        return obj.get_full_name() or obj.username


class UserSerializer(serializers.ModelSerializer):
    """Read serializer for a staff account.

    ``company`` is read-only in every serializer: the tenant is never accepted
    from the client payload. Module 02 will set it from the validated
    ``X-Company-ID`` request context; in Module 01 it is set server-side by
    whoever creates the record.

    ``created_by``/``updated_by`` are excluded, and no field masking is applied
    - masking is Module 02's concern.
    """

    company_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'phone',
            'role',
            'is_active',
            'is_staff',
            'company',
            'company_name',
            'date_joined',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'company',
            'company_name',
            'date_joined',
            'created_at',
            'updated_at',
        )

    def get_company_name(self, obj) -> str | None:
        """The tenant's display name.

        Type-annotated because drf-spectacular cannot infer a ``SerializerMethodField``'s
        type from its body - without the annotation it falls back to ``string`` and
        logs a warning on every schema generation.
        """
        return obj.company.name if obj.company_id else None


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Staff login: adds tenant/role claims to the access token.

    Claim contract - types are pinned by tests so the frontend can rely on them:

    * ``user_id``    str, supplied by SimpleJWT
    * ``username``   str, supplied by SimpleJWT
    * ``company_id`` str, always present (company is required on User)
    * ``role``       str
    * ``is_staff``   bool

    Identifiers are strings because SimpleJWT stringifies its own ``user_id``
    claim; mixing a numeric ``company_id`` with a string ``user_id`` is how
    ``company_id === '3'`` comparison bugs get written.

    Module 02 note: these claims are a convenience for the frontend only.
    Authorization must never trust them - Module 02 enforces permissions
    server-side against the database.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['company_id'] = str(user.company_id)
        token['role'] = user.role
        token['is_staff'] = user.is_staff
        return token
