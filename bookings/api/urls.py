"""URL routing for the bookings app — one endpoint per service record type."""

from bookings.api.views import (
    HajjBookingViewSet,
    HotelBookingViewSet,
    PackageComponentViewSet,
    PackageViewSet,
    TicketingBookingViewSet,
    TourBookingViewSet,
    TransportBookingViewSet,
    UmrahBookingViewSet,
)
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("hajj", HajjBookingViewSet, basename="hajj-booking")
router.register("umrah", UmrahBookingViewSet, basename="umrah-booking")
router.register("tours", TourBookingViewSet, basename="tour-booking")
router.register("ticketing", TicketingBookingViewSet, basename="ticketing-booking")
router.register("hotels", HotelBookingViewSet, basename="hotel-booking")
router.register("transport", TransportBookingViewSet, basename="transport-booking")
router.register("packages", PackageViewSet, basename="package")
router.register("package-components", PackageComponentViewSet, basename="package-component")

urlpatterns = router.urls
