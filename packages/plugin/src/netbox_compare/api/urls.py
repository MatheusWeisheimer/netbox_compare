from netbox.api.routers import NetBoxRouter

from netbox_compare.api.views import ComparisonPolicyViewSet, ComparisonViewSet

router = NetBoxRouter()
router.register("policies", ComparisonPolicyViewSet)
router.register("comparisons", ComparisonViewSet)
urlpatterns = router.urls
