from netbox.api.routers import NetBoxRouter

from netbox_compare.api.views import ComparisonViewSet

router = NetBoxRouter()
router.register("comparisons", ComparisonViewSet)
urlpatterns = router.urls
