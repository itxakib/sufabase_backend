from django.urls import include, path
from rest_framework.routers import DefaultRouter

from tenant.api.views import CompanyViewSet, SettingsCompanyView

router = DefaultRouter()
router.register('companies', CompanyViewSet, basename='company')

urlpatterns = [
    path('settings/company/', SettingsCompanyView.as_view(), name='settings-company'),
    path('', include(router.urls)),
]
