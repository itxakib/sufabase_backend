"""Serializers for the bookings app — one file per model.

Every write serializer uses ``TenantScopedSerializerMixin`` to restrict FK
fields (``customer``, ``sales_agent``) to the requesting company's rows.
``company`` / ``created_by`` / ``updated_by`` are never exposed as writable.
"""

from bookings.serializers.hajj import HajjBookingListSerializer, HajjBookingSerializer
from bookings.serializers.hotel import HotelBookingListSerializer, HotelBookingSerializer
from bookings.serializers.package import (
    PackageComponentSerializer,
    PackageMiniSerializer,
    PackageSerializer,
)
from bookings.serializers.ticketing import TicketingBookingListSerializer, TicketingBookingSerializer
from bookings.serializers.tour import TourBookingListSerializer, TourBookingSerializer
from bookings.serializers.transport import TransportBookingListSerializer, TransportBookingSerializer
from bookings.serializers.umrah import UmrahBookingListSerializer, UmrahBookingSerializer

__all__ = [
    "HajjBookingListSerializer",
    "HajjBookingSerializer",
    "HotelBookingListSerializer",
    "HotelBookingSerializer",
    "PackageComponentSerializer",
    "PackageMiniSerializer",
    "PackageSerializer",
    "TicketingBookingListSerializer",
    "TicketingBookingSerializer",
    "TourBookingListSerializer",
    "TourBookingSerializer",
    "TransportBookingListSerializer",
    "TransportBookingSerializer",
    "UmrahBookingListSerializer",
    "UmrahBookingSerializer",
]
