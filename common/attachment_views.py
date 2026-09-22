"""Attachment endpoints: one generic ViewSet, plus a nested action for hosts.

Two surfaces, deliberately:

* ``/api/v1/attachments/`` - the generic collection. Filter by ``content_type``
  and ``object_id`` to answer "documents for this record", or leave both off to
  answer "everything uploaded in this company".
* ``/<resource>/{id}/attachments/`` - added to every host ViewSet by
  :class:`AttachmentActionsMixin`. This is the path the frontend is expected to
  use, because the tenant scoping is already applied by the ViewSet's queryset
  and the client never has to construct a ``content_type`` string correctly.

Both are tenant-scoped and both stamp ``company`` / ``created_by`` through
``TenantScopedViewSetMixin`` - the one place that logic lives.
"""

from django.contrib.contenttypes.models import ContentType
from django_filters import CharFilter, NumberFilter
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from common.attachment_selectors import AttachmentSelector
from common.attachment_serializers import AttachmentSerializer
from common.filters import InNumberFilter, StrictBooleanFilter, TenantAwareFilterSet
from common.models import Attachment
from common.viewsets import TenantScopedViewSetMixin


class AttachmentFilter(TenantAwareFilterSet):
    """Filters for ``GET /api/v1/attachments/``.

    Inherits the standard ``created_after``/``created_before`` range pair from
    ``AuditRangeFilterSet``, so "what was uploaded in the last week" needs no new
    parameter.
    """

    content_type = CharFilter(method='filter_content_type')
    object_id = NumberFilter(field_name='object_id')
    object_ids = InNumberFilter(field_name='object_id')
    doc_type = CharFilter(field_name='doc_type', lookup_expr='icontains')
    uploaded_by = NumberFilter(field_name='created_by_id')
    has_doc_type = StrictBooleanFilter(method='filter_has_doc_type')

    class Meta:
        model = Attachment
        fields = []

    def filter_content_type(self, queryset, name, value):
        """``?content_type=customers.customer``.

        Takes the same ``app_label.model`` spelling the serializer reads and
        writes, so a client can round-trip the value it was given. An unknown
        value is a 400 rather than an empty page - silently returning nothing
        for a typo is how a frontend ships a filter that "sometimes shows no
        results" and nobody can explain why.
        """
        if '.' not in value:
            raise ValidationError({
                'content_type': 'Expected "app_label.model", e.g. "customers.customer".',
            })
        app_label, _, model = value.partition('.')
        try:
            content_type = ContentType.objects.get_by_natural_key(
                app_label.strip().lower(), model.strip().lower(),
            )
        except ContentType.DoesNotExist:
            raise ValidationError({'content_type': f'Unknown content type "{value}".'})
        return queryset.filter(content_type=content_type)

    def filter_has_doc_type(self, queryset, name, value):
        """``?has_doc_type=true|false`` - uploaded but never labelled, which is
        the worklist for tidying a document library."""
        if value:
            return queryset.exclude(doc_type='')
        return queryset.filter(doc_type='')


class AttachmentViewSet(
    TenantScopedViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """The generic document collection, scoped to the caller's company.

    Deliberately has no ``PUT``-only semantics quirk: ``PATCH`` is the expected
    way to relabel a document (``doc_type``), and re-uploading the bytes is just
    another ``PATCH`` of ``file``. Deletion is hard, not soft - an attachment is
    a file reference, and a "deleted" row would still leak the URL.
    """

    queryset = Attachment.objects.all()
    serializer_class = AttachmentSerializer
    # No PUT. A full-replace of a document is not a meaningful operation (the
    # bytes and the target cannot both be "replaced"), and exposing it invites a
    # client to send a field-less PUT that silently blanks ``doc_type``.
    # PATCH is the edit that exists, so PATCH is the only one offered.
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = AttachmentFilter
    # Multipart for uploads, JSON so relabelling a document (``PATCH`` with just
    # a new ``doc_type``) does not force the client to build a multipart body for
    # a one-word change - which is what a multipart-only parser list would do.
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    search_fields = ['doc_type', 'content_type__model', 'created_by__username']
    ordering_fields = ['created_at', 'updated_at', 'doc_type']
    ordering = ['-created_at']

    def get_queryset(self):
        return super().get_queryset().select_related('content_type', 'created_by')


class AttachmentActionsMixin:
    """Adds ``GET``/``POST`` ``/<resource>/{id}/attachments/`` to a ViewSet.

    Mix in **before** the ViewSet base class, alongside
    ``TenantScopedViewSetMixin`` - it relies on that mixin for
    ``_resolve_company()`` and for ``get_object()`` scoped to the caller's
    tenant, which is what makes the nested route safe without repeating a single
    company check here.

    The host model must declare ``attachments = GenericRelation(...)``; without
    it the route still works (the generic FK does not need the relation) but the
    point of mixing this in is that the model opted into attachments.
    """

    @extend_schema(
        methods=['GET'],
        responses={200: AttachmentSerializer(many=True)},
        description='List every document attached to this record.',
    )
    @extend_schema(
        methods=['POST'],
        request=AttachmentSerializer,
        responses={201: AttachmentSerializer},
        description=(
            'Upload a document and attach it to this record. '
            'Send `multipart/form-data` with `file` (required) and '
            '`doc_type` (optional, e.g. "CNIC copy", "Voucher"). '
            'The host record comes from the URL — do not send '
            '`content_type` or `object_id`.'
        ),
    )
    @action(
        detail=True,
        methods=['get', 'post'],
        url_path='attachments',
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def attachments(self, request, pk=None):
        target = self.get_object()
        company = self._resolve_company()

        if request.method == 'GET':
            queryset = AttachmentSelector.for_object(target, company)
            serializer = AttachmentSerializer(
                queryset, many=True, context=self.get_serializer_context(),
            )
            return Response(serializer.data)

        serializer = AttachmentSerializer(
            data=request.data,
            context={**self.get_serializer_context(), 'target': target},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(company=company, created_by=request.user)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )
