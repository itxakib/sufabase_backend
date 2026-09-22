"""Dashboard summary view — aggregates data across all service models."""

from datetime import date

from django.db.models import Sum
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import HasCompanyContext
from dashboard.serializers import DashboardSummarySerializer


@extend_schema(responses=DashboardSummarySerializer, tags=['Dashboard'])
class DashboardSummaryView(APIView):
    """GET /dashboard/summary/

    Returns aggregated stats for the authenticated user's company:
    - total_customers, new_customers_this_month
    - total_revenue, currency (PKR)
    - service_totals: per-service count + amount
    - upcoming_departures: next 10 bookings by start_date
    - recent_activity: last 10 records created across all services
    """

    permission_classes = [IsAuthenticated, HasCompanyContext]

    def get(self, request):
        company = getattr(request, 'company', None)
        if company is None:
            company = getattr(request.user, 'company', None)
        if company is None:
            return Response({'detail': 'Company context required.'}, status=400)

        # ── Lazy imports to avoid circular dependencies ────────────────────
        from customers.models import Customer
        from bookings.models import (
            HajjBooking, UmrahBooking, TourBooking,
            TicketingBooking, HotelBooking, TransportBooking,
        )
        from consultancy.models import VisaConsultancyCase, StudyVisaCase

        today = date.today()
        month_start = today.replace(day=1)

        # ── Customer counts ────────────────────────────────────────────────
        customer_qs = Customer.objects.filter(company=company)
        total_customers = customer_qs.count()
        new_customers_this_month = customer_qs.filter(
            created_at__date__gte=month_start,
        ).count()

        # ── Service totals (count + amount per service type) ───────────────
        service_configs = [
            ('hajj', HajjBooking),
            ('umrah', UmrahBooking),
            ('tour', TourBooking),
            ('ticketing', TicketingBooking),
            ('hotel', HotelBooking),
            ('transport', TransportBooking),
            ('visa_consultancy', VisaConsultancyCase),
            ('study_visa', StudyVisaCase),
        ]

        service_totals = []
        total_revenue = 0

        for service_type, model_cls in service_configs:
            qs = model_cls.objects.filter(company=company)
            count = qs.count()
            # Both ServiceRecordBase and CaseRecordBase have 'amount'/'service_value'
            amount_field = 'amount' if hasattr(model_cls, 'amount') else 'service_value'
            amount = qs.aggregate(total=Sum(amount_field))['total'] or 0
            total_revenue += amount
            service_totals.append({
                'service_type': service_type,
                'count': count,                    'amount': str(amount),
            })

        # ── Upcoming departures (next 10 by start_date) ───────────────────
        upcoming_qs = []
        for model_cls, service_type, dest_field in [
            (TourBooking, 'tour', 'destination_country'),
            (TicketingBooking, 'ticketing', 'destination'),
            (HotelBooking, 'hotel', 'city'),
            (TransportBooking, 'transport', 'dropoff_location'),
        ]:
            records = model_cls.objects.filter(
                company=company,
                start_date__gte=today,
            ).select_related('customer').order_by('start_date')[:10]

            for r in records:
                upcoming_qs.append({
                    'id': r.id,
                    'service_type': service_type,
                    'customer_name': r.customer.full_name if r.customer else '',
                    'destination': getattr(r, dest_field, ''),
                    'start_date': r.start_date.isoformat() if r.start_date else None,
                    'booking_reference': r.booking_reference or '',
                    'status': r.status,
                    'amount': r.amount,
                })

        # Sort by start_date and take top 10
        upcoming_departures = sorted(upcoming_qs, key=lambda x: x['start_date'])[:10]

        # ── Recent activity (last 10 created across all services) ──────────
        recent_qs = []

        # Customers first — they don't have a customer FK
        for r in Customer.objects.filter(company=company).order_by('-created_at')[:5]:
            recent_qs.append({
                'id': r.id,
                'service_type': 'customer',
                'customer_name': r.full_name,
                'action': 'created',
                'description': 'Customer record created',
                'timestamp': r.created_at.isoformat() if r.created_at else None,
            })

        # Service records — all have a customer FK
        for model_cls, service_type in [
            (HajjBooking, 'hajj'),
            (UmrahBooking, 'umrah'),
            (TourBooking, 'tour'),
            (TicketingBooking, 'ticketing'),
            (HotelBooking, 'hotel'),
            (TransportBooking, 'transport'),
            (VisaConsultancyCase, 'visa_consultancy'),
            (StudyVisaCase, 'study_visa'),
        ]:
            for r in model_cls.objects.filter(
                company=company,
            ).select_related('customer').order_by('-created_at')[:5]:
                recent_qs.append({
                    'id': r.id,
                    'service_type': service_type,
                    'customer_name': r.customer.full_name if r.customer else '',
                    'action': 'created',
                    'description': f'{service_type.replace("_", " ").title()} record created',
                    'timestamp': r.created_at.isoformat() if r.created_at else None,
                })

        # Sort by timestamp descending and take top 10
        recent_activity = sorted(recent_qs, key=lambda x: x['timestamp'], reverse=True)[:10]

        return Response({
            'total_customers': total_customers,
            'new_customers_this_month': new_customers_this_month,
            'total_revenue': str(total_revenue),
            'currency': 'PKR',
            'service_totals': service_totals,
            'upcoming_departures': upcoming_departures,
            'recent_activity': recent_activity,
        })
