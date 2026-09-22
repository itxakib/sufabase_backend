"""Bookings models, one per file, exported in dependency order.

The import order mirrors how the models reference each other: the abstract
``ServiceRecordBase`` first, then the three component records it feeds, then
``Package`` and ``PackageComponent`` (which link those components), then the
three trip records that point at ``Package``. The string model references
(``'bookings.Package'``) would
resolve lazily either way, but importing in dependency order keeps the graph
readable and makes an import cycle obvious the moment one appears.
"""

from bookings.models.base import ServiceRecordBase
from bookings.models.ticketing import TicketingBooking
from bookings.models.hotel import HotelBooking
from bookings.models.transport import TransportBooking
from bookings.models.package import Package, PackageComponent
from bookings.models.hajj import HajjBooking
from bookings.models.umrah import UmrahBooking
from bookings.models.tour import TourBooking

__all__ = [
    'ServiceRecordBase',
    'TicketingBooking',
    'HotelBooking',
    'TransportBooking',
    'Package',
    'PackageComponent',
    'HajjBooking',
    'UmrahBooking',
    'TourBooking',
]
