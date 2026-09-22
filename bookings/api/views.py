"""ViewSets for the bookings app — one per service record type.

All views use ``TenantScopedViewSetMixin`` for company scoping and audit
field stamping.  Filter and search fields are kept lean: only fields that
answer real operational questions are included, not every column.
"""

import csv
import io

from django.http import HttpResponse
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from common.attachment_views import AttachmentActionsMixin
from common.viewsets import TenantScopedViewSetMixin
from django_filters.rest_framework import DjangoFilterBackend

from bookings.models import (
    HajjBooking,
    HotelBooking,
    Package,
    PackageComponent,
    TicketingBooking,
    TourBooking,
    TransportBooking,
    UmrahBooking,
)
from bookings.serializers import (
    HajjBookingListSerializer,
    HajjBookingSerializer,
    HotelBookingListSerializer,
    HotelBookingSerializer,
    PackageComponentSerializer,
    PackageSerializer,
    TicketingBookingListSerializer,
    TicketingBookingSerializer,
    TourBookingListSerializer,
    TourBookingSerializer,
    TransportBookingListSerializer,
    TransportBookingSerializer,
    UmrahBookingListSerializer,
    UmrahBookingSerializer,
)
from bookings.hajj_import import default_hajj_year, import_hajj_applications
from bookings.utils import generate_booking_reference


class BookingReferenceMixin:
    """Auto-generates ``booking_reference`` on create if not provided.

    Uses ``generate_booking_reference()`` which produces ``PREFIX-YEAR-SEQ``
    format (e.g. ``HJ-2026-000001``).  The user can still override it by
    sending their own value in the request body.
    """

    def perform_create(self, serializer):
        ref = serializer.validated_data.get('booking_reference', '')
        if not ref:
            ref = generate_booking_reference(
                serializer.Meta.model,
                self._resolve_company(),
            )
        super().perform_create(serializer)
        if not serializer.instance.booking_reference:
            serializer.instance.booking_reference = ref
            serializer.instance.save(update_fields=['booking_reference'])


class HajjBookingViewSet(AttachmentActionsMixin, BookingReferenceMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Hajj service records — one row per customer's Hajj trip."""

    queryset = HajjBooking.objects.select_related('customer', 'sales_agent').all()

    def get_serializer_class(self):
        if self.action == 'list':
            return HajjBookingListSerializer
        return HajjBookingSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "customer", "hajj_year", "application_number"]
    search_fields = [
        "booking_reference",
        "application_number",
        "hajj_year",
        "group_name",
        "package_name",
        "departure_city",
        "customer__full_name",
        "customer__phone",
    ]
    ordering_fields = ["hajj_year", "status", "created_at", "updated_at"]
    ordering = ["-created_at"]

    @action(detail=False, methods=['get'], url_path='import-template', pagination_class=None, filter_backends=[])
    def import_template(self, request):
        """Blank CSV: application id and passport number, plus one example row."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['application_number', 'passport_number'])
        writer.writerow(['HAJJ-2026-00123', 'AB1234567'])
        response = HttpResponse(buf.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="hajj_application_import.csv"'
        return response

    @action(
        detail=False,
        methods=['post'],
        url_path='import',
        parser_classes=[MultiPartParser, FormParser],
        pagination_class=None,
        filter_backends=[],
    )
    def import_applications(self, request):
        """Create a Hajj booking per CSV row whose passport matches a customer.

        The file has two columns, ``application_number`` and ``passport_number``.
        ``hajj_year`` is one value for the whole file (form field), because a
        Hajj record is for a season and the spreadsheet does not repeat it.
        Rows with no matching customer are reported and not created.
        """
        company = self._resolve_company()
        if company is None:
            return Response(
                {'detail': 'A valid company context is required.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        uploaded = request.FILES.get('file')
        if not uploaded:
            return Response(
                {'detail': 'No file provided. Send a CSV file as the "file" field.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        hajj_year = (request.data.get('hajj_year') or default_hajj_year()).strip()
        if not hajj_year or len(hajj_year) > 9:
            return Response(
                {'detail': 'hajj_year must be 1–9 characters (for example 2026).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            decoded = uploaded.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            return Response(
                {'detail': 'File must be UTF-8 encoded.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        report, error = import_hajj_applications(
            company=company,
            user=request.user,
            decoded_csv=decoded,
            hajj_year=hajj_year,
        )
        if error:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)
        return Response(report)


class UmrahBookingViewSet(AttachmentActionsMixin, BookingReferenceMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Umrah service records — one row per customer's Umrah trip."""

    queryset = UmrahBooking.objects.select_related('customer', 'sales_agent').all()

    def get_serializer_class(self):
        if self.action == 'list':
            return UmrahBookingListSerializer
        return UmrahBookingSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "customer", "umrah_year_season"]
    search_fields = [
        "booking_reference",
        "umrah_year_season",
        "package_name",
        "customer__full_name",
        "customer__phone",
    ]
    ordering_fields = ["umrah_year_season", "status", "created_at", "updated_at"]
    ordering = ["-created_at"]


class TourBookingViewSet(AttachmentActionsMixin, BookingReferenceMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Tour package bookings — domestic and international."""

    queryset = TourBooking.objects.select_related('customer', 'sales_agent').all()

    def get_serializer_class(self):
        if self.action == 'list':
            return TourBookingListSerializer
        return TourBookingSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "customer", "tour_type", "destination_country"]
    search_fields = [
        "booking_reference",
        "tour_name",
        "destination_country",
        "destination_city",
        "package_name",
        "customer__full_name",
        "customer__phone",
    ]
    ordering_fields = ["start_date", "destination_country", "status", "created_at", "updated_at"]
    ordering = ["-created_at"]


class TicketingBookingViewSet(AttachmentActionsMixin, BookingReferenceMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Airline ticket records."""

    queryset = TicketingBooking.objects.select_related('customer', 'sales_agent').all()

    def get_serializer_class(self):
        if self.action == 'list':
            return TicketingBookingListSerializer
        return TicketingBookingSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "customer", "airline"]
    search_fields = [
        "booking_reference",
        "pnr",
        "passenger_name",
        "airline",
        "origin",
        "destination",
        "customer__full_name",
        "customer__phone",
    ]
    ordering_fields = ["ticket_issue_date", "status", "created_at", "updated_at"]
    ordering = ["-created_at"]


class HotelBookingViewSet(AttachmentActionsMixin, BookingReferenceMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Hotel stay records."""

    queryset = HotelBooking.objects.select_related('customer', 'sales_agent').all()

    def get_serializer_class(self):
        if self.action == 'list':
            return HotelBookingListSerializer
        return HotelBookingSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "customer", "city"]
    search_fields = [
        "booking_reference",
        "hotel_name",
        "lead_guest_name",
        "city",
        "country",
        "confirmation_number",
        "customer__full_name",
        "customer__phone",
    ]
    ordering_fields = ["start_date", "city", "status", "created_at", "updated_at"]
    ordering = ["-created_at"]


class TransportBookingViewSet(AttachmentActionsMixin, BookingReferenceMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Ground transport service records."""

    queryset = TransportBooking.objects.select_related('customer', 'sales_agent').all()

    def get_serializer_class(self):
        if self.action == 'list':
            return TransportBookingListSerializer
        return TransportBookingSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "customer", "service_type"]
    search_fields = [
        "booking_reference",
        "pickup_location",
        "dropoff_location",
        "vehicle_type",
        "supplier_vendor",
        "customer__full_name",
        "customer__phone",
    ]
    ordering_fields = ["service_type", "status", "created_at", "updated_at"]
    ordering = ["-created_at"]


class PackageViewSet(AttachmentActionsMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Trip bundles. Components are linked separately and returned read-only."""

    queryset = Package.objects.select_related('template').prefetch_related(
        'components__hotel_booking',
        'components__ticketing_booking',
        'components__transport_booking',
    ).all()
    serializer_class = PackageSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at", "updated_at"]
    ordering = ["-created_at"]


class PackageComponentViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Links an existing hotel, ticket, or transport row into a package.

    Delete removes the link only. The booking row stays.
    """

    queryset = PackageComponent.objects.select_related(
        'package',
        'hotel_booking',
        'ticketing_booking',
        'transport_booking',
    ).all()
    serializer_class = PackageComponentSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['package']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['created_at']
