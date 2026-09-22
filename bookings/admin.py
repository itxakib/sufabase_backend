"""Django admin registration for the bookings app.

Django admin is currently the only write path in SUFABASE (Module 01 ships
read-only APIs), so every booking model is registered here. The six
``ServiceRecordBase`` subclasses share one admin base class so their common
presentation is defined once and a new service record only adds its own columns.
"""

from django.contrib import admin

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


class ServiceRecordAdmin(admin.ModelAdmin):
    """Shared admin config for the six ``ServiceRecordBase`` subclasses.

    Never registered itself - it has no model. Concrete admins inherit it and
    append their own columns.

    ``customer`` and ``sales_agent`` are autocomplete rather than plain selects,
    because both tables grow without bound in a live CRM and rendering every
    customer into a dropdown is the classic way an admin page stops loading.
    ``customer__*`` in ``search_fields`` is the staff workflow that matters:
    "find this person's bookings".
    """

    list_display = (
        'booking_reference',
        'customer',
        'company',
        'start_date',
        'end_date',
        'amount',
        'currency',
        'status',
        'sales_agent',
    )
    list_filter = ('company', 'status')
    search_fields = ('booking_reference', 'customer__full_name', 'customer__phone')
    autocomplete_fields = ('customer', 'sales_agent')
    list_select_related = ('company', 'customer', 'sales_agent')
    readonly_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')
    date_hierarchy = 'start_date'


@admin.register(TicketingBooking)
class TicketingBookingAdmin(ServiceRecordAdmin):
    list_display = ServiceRecordAdmin.list_display + ('pnr', 'airline', 'passenger_name')
    search_fields = ServiceRecordAdmin.search_fields + (
        'pnr',
        'e_ticket_number',
        'airline',
        'passenger_name',
    )
    list_filter = ('company', 'status', 'refund_status', 'trip_type', 'cabin_class')


@admin.register(HotelBooking)
class HotelBookingAdmin(ServiceRecordAdmin):
    list_display = ServiceRecordAdmin.list_display + (
        'hotel_name',
        'city',
        'confirmation_number',
    )
    search_fields = ServiceRecordAdmin.search_fields + (
        'hotel_name',
        'confirmation_number',
        'lead_guest_name',
    )
    list_filter = ('company', 'status', 'city', 'meal_plan')


@admin.register(TransportBooking)
class TransportBookingAdmin(ServiceRecordAdmin):
    list_display = ServiceRecordAdmin.list_display + (
        'service_type',
        'pickup_location',
        'dropoff_location',
        'vehicle_type',
    )
    search_fields = ServiceRecordAdmin.search_fields + (
        'pickup_location',
        'dropoff_location',
        'supplier_vendor',
        'lead_passenger_name',
    )
    list_filter = ('company', 'status', 'service_type', 'trip_type')


class PackageComponentInline(admin.TabularInline):
    """Pick an existing hotel, ticket, or transport row. Does not create one."""

    model = PackageComponent
    extra = 0
    autocomplete_fields = ('hotel_booking', 'ticketing_booking', 'transport_booking')
    exclude = ('company', 'created_by', 'updated_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    """Admin for the trip bundle.

    Components are an inline of links. Autocomplete looks up rows that already
    exist; the inline has no hotel, ticket, or transport fieldset of its own.
    """

    list_display = ('name', 'company', 'created_at')
    list_filter = ('company',)
    search_fields = ('name',)
    autocomplete_fields = ('template',)
    readonly_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')
    inlines = [PackageComponentInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('company', 'template')

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for obj in instances:
            if isinstance(obj, PackageComponent):
                obj.company = form.instance.company
            obj.save()
        formset.save_m2m()


@admin.register(PackageComponent)
class PackageComponentAdmin(admin.ModelAdmin):
    """Correct a single link without opening the whole bundle."""

    list_display = (
        'package',
        'company',
        'hotel_booking',
        'ticketing_booking',
        'transport_booking',
    )
    list_filter = ('company',)
    search_fields = ('package__name',)
    autocomplete_fields = (
        'package',
        'company',
        'hotel_booking',
        'ticketing_booking',
        'transport_booking',
    )
    readonly_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')


@admin.register(HajjBooking)
class HajjBookingAdmin(ServiceRecordAdmin):
    list_display = ServiceRecordAdmin.list_display + ('hajj_year', 'application_number', 'package_name', 'group_name')
    search_fields = ServiceRecordAdmin.search_fields + (
        'hajj_year',
        'application_number',
        'package_name',
        'group_name',
    )
    list_filter = ('company', 'status', 'visa_status', 'qurbani_arrangement')


@admin.register(UmrahBooking)
class UmrahBookingAdmin(ServiceRecordAdmin):
    list_display = ServiceRecordAdmin.list_display + ('umrah_year_season', 'package_name')
    search_fields = ServiceRecordAdmin.search_fields + (
        'umrah_year_season',
        'package_name',
        'package_category',
    )
    list_filter = ('company', 'status', 'visa_status')


@admin.register(TourBooking)
class TourBookingAdmin(ServiceRecordAdmin):
    list_display = ServiceRecordAdmin.list_display + (
        'tour_name',
        'destination_country',
        'tour_type',
    )
    search_fields = ServiceRecordAdmin.search_fields + (
        'tour_name',
        'destination_country',
        'destination_city',
        'package_name',
    )
    list_filter = ('company', 'status', 'tour_type', 'destination_country')
