"""URL routing for the catalog app."""

from catalog.api.views import PackageTemplateViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register('package-templates', PackageTemplateViewSet, basename='package-template')

urlpatterns = router.urls
