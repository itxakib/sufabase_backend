from rest_framework.routers import DefaultRouter
from directory.api.views import DirectoryCompanyViewSet, ImportBatchViewSet

router = DefaultRouter()
router.register('directory-companies', DirectoryCompanyViewSet, basename='directory-company')
router.register('import-batches', ImportBatchViewSet, basename='import-batch')

urlpatterns = router.urls
