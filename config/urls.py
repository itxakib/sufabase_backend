from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),

    # OpenAPI schema + interactive docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # Staff auth (token/, token/refresh/, token/logout/) lives in the users app,
    # because it is Module 01's "secure staff login" surface.
    path('api/v1/', include('users.api.urls')),
    # Generic document uploads — attachments hang off records in every module,
    # so the route cannot belong to any one of them.
    path('api/v1/', include('common.urls')),
    path('api/v1/', include('tenant.api.urls')),
    path('api/v1/', include('customers.api.urls')),
    path('api/v1/', include('catalog.api.urls')),
    path('api/v1/', include('bookings.api.urls')),
    path('api/v1/', include('consultancy.api.urls')),
    path('api/v1/', include('dashboard.urls')),
    path('api/v1/', include('directory.api.urls')),
]

# Django serves uploaded files itself in development only. In production a web
# server or object storage serves MEDIA_URL, and this block does nothing.
#
# Without it, every avatar and every uploaded document returns a 404 locally —
# the API hands the frontend a URL that nothing is listening on.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
