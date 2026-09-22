"""URL routing for the consultancy app — visa and study-visa endpoints."""

from consultancy.api.views import StudyVisaCaseViewSet, VisaConsultancyCaseViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("visa-consultancy", VisaConsultancyCaseViewSet, basename="visa-consultancy")
router.register("study-visa", StudyVisaCaseViewSet, basename="study-visa")

urlpatterns = router.urls
