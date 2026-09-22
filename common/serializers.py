"""Shared serializer infrastructure for SUFABASE.

``TenantScopedSerializerMixin`` is mixed into every write serializer that has a
FK pointing at a tenant-owned model (Customer, User, Tag). It restricts the
field's queryset at init time so a crafted payload can never link a record to
another company's row — that check happens in the serializer, not the view,
because DRF does not guarantee every write path goes through a viewset.

``StatusRequiredFieldsMixin`` is the other half of "validate what the client
sent": it makes a field required from a particular status onwards, so a record
can be created at sale time without the values that provably do not exist yet.
"""

from django.db import models
from rest_framework import serializers


class TenantScopedSerializerMixin:
    """Restricts FK/M2M fields to the requesting company's own records.

    Set ``tenant_scoped_fields = {field_name: ModelClass}`` on the concrete
    serializer.  Both FK and M2M ``PrimaryKeyRelatedField`` instances are
    handled — both expose a ``queryset`` attribute that can be narrowed.

    Requires DRF to pass ``request`` in serializer context (the default).

    The mixin reads ``request.user.company``, not ``request.company`` — DRF
    does not copy user attributes onto the request object.  If the user has no
    company (platform superuser) or the request is missing, the fields are left
    unscoped and rely on the view's queryset restriction instead.

    Scoping a FK is not optional just because the field looks harmless. Every
    field on ``tenant_scoped_fields`` is written from a client-supplied id, and
    an unscoped id is how a record ends up pointing at another company's row —
    the ``package`` FK on the trip serializers was missing from this dict for
    exactly that reason and was a real cross-tenant write leak.
    """

    tenant_scoped_fields: dict[str, type] = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        company = self._get_company()
        if company is None:
            return
        for field_name, model_cls in self.tenant_scoped_fields.items():
            field = self.fields.get(field_name)
            if field is None:
                continue
            scoped_qs = model_cls.objects.filter(company=company)
            # ManyRelatedField wraps a child PrimaryKeyRelatedField —
            # validation reads from child_relation.queryset, not from
            # the outer wrapper's queryset.  Scope whichever exists.
            child = getattr(field, "child_relation", None)
            target = child if child is not None else field
            if hasattr(target, "queryset") and target.queryset is not None:
                target.queryset = scoped_qs

    def _get_company(self):
        """Extract the tenant from the DRF request, safely.

        Prefers ``request.company`` (set by ``CompanyContextMiddleware``),
        falls back to ``request.user.company`` for test clients and any
        request that bypassed the middleware.
        """
        request = self.context.get("request")
        if request is None:
            return None
        # Primary: middleware-set company
        company = getattr(request, "company", None)
        if company is not None:
            return company
        # Fallback: user's own company
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        return getattr(user, "company", None)


class StatusRequiredFieldsMixin:
    """Requires a field only once a record reaches the status that needs it.

    Declare ``status_required_fields = {status_value: (field_names,)}`` on the
    concrete serializer. The table itself belongs to the app
    (``bookings/status_rules.py``) and is assigned straight onto the serializer
    class, so the model, the admin, the API and the database constraint all read
    one source rather than four copies that drift.

    Exists because some fields provably cannot be known when a record is
    *created* — a PNR does not exist until the ticket is issued, and a hotel
    guest name may not exist until the rooming list arrives. Demanding them up
    front pushes staff into typing placeholders, and a placeholder in a real
    column is indistinguishable from real data forever. See
    ``bookings/status_rules.py`` for the full reasoning.

    Runs on create **and** update. For a partial update the effective value of a
    field is whatever the request sent, falling back to the stored value — which
    is what makes ``PATCH {"status": "ISSUED"}`` fail on a ticket with no PNR
    while ``PATCH {"pnr": "ABC123"}`` on a ``RESERVED`` one passes.
    """

    status_field = 'status'
    status_required_fields: dict = {}

    def validate(self, attrs):
        attrs = super().validate(attrs)
        self._check_status_requirements(attrs)
        return attrs

    def _effective_status(self, attrs):
        """What ``status`` will be after this save.

        Three sources in falling order of authority: the payload (only present
        when the client sent it), the stored row on an update, and finally the
        model field's own default — which is what a create that never mentions
        ``status`` will end up with. Reading the default off ``_meta`` rather
        than hardcoding it means changing the model default cannot silently
        disable the check.
        """
        if self.status_field in attrs:
            return attrs[self.status_field]
        if self.instance is not None:
            return getattr(self.instance, self.status_field, None)
        model_field = self.Meta.model._meta.get_field(self.status_field)
        default = model_field.get_default()
        return None if default is models.NOT_PROVIDED else default

    def _check_status_requirements(self, attrs):
        if not self.status_required_fields:
            return
        status = self._effective_status(attrs)
        errors = {}
        for field in self.status_required_fields.get(status, ()):
            if field in attrs:
                value = attrs[field]
            elif self.instance is not None:
                value = getattr(self.instance, field, None)
            else:
                value = None
            if value is None or value == '':
                errors[field] = (
                    f'This field is required once status is "{status}".'
                )
        if errors:
            raise serializers.ValidationError(errors)
