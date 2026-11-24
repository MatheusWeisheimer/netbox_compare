from netbox.api.routers import NetBoxRouter

from netbox_compare.api.views import (
    ComparisonPolicyViewSet,
    ComparisonRunViewSet,
    ComparisonScheduleViewSet,
    ComparisonViewSet,
)

router = NetBoxRouter()
router.register("policies", ComparisonPolicyViewSet)
router.register("schedules", ComparisonScheduleViewSet)
router.register("runs", ComparisonRunViewSet)
router.register("comparisons", ComparisonViewSet)
urlpatterns = router.urls
