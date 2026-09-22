from django.urls import include, path
from rest_framework.routers import DefaultRouter

from customers.api.views import CustomerViewSet, TagViewSet

router = DefaultRouter()
router.register('customers', CustomerViewSet, basename='customer')
router.register('tags', TagViewSet, basename='tag')

urlpatterns = [
    path('', include(router.urls)),
]
