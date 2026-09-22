"""URL routing for ``common`` — the generic document collection.

Only one route lives here. ``common`` is not a module app; it exposes this
because attachments belong to no single module (a customer, a booking and a case
all carry them), so the endpoint cannot sensibly live in any one of them.
"""

from common.attachment_views import AttachmentViewSet
from django.urls import include, path
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register('attachments', AttachmentViewSet, basename='attachment')

urlpatterns = [
    path('', include(router.urls)),
]
