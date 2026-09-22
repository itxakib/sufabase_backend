from django.db import models


class TemplateLineKind(models.TextChoices):
    """Which spec a catalog line describes.

    A line is a requirement for a sellable package — a room in a city, a cabin
    on a route, a vehicle — not a reservation. Guest names, ticket numbers and
    passenger counts belong on the booking that later fulfills the spec.
    """

    HOTEL = 'HOTEL', 'Hotel'
    FLIGHT = 'FLIGHT', 'Flight'
    TRANSPORT = 'TRANSPORT', 'Transport'
