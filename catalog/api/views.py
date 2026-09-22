"""ViewSets for the catalog app — sellable package specs."""

from catalog.models import PackageTemplate
from catalog.serializers import PackageTemplateListSerializer, PackageTemplateSerializer
from common.attachment_views import AttachmentActionsMixin
from common.viewsets import TenantScopedViewSetMixin
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets


class PackageTemplateViewSet(
    AttachmentActionsMixin,
    TenantScopedViewSetMixin,
    viewsets.ModelViewSet,
):
    """Sellable packages. Spec lines and optional paperwork — no guest, ticket, or passenger data."""

    queryset = PackageTemplate.objects.prefetch_related('lines').all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'created_at', 'updated_at']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return PackageTemplateListSerializer
        return PackageTemplateSerializer
