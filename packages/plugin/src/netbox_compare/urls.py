from django.urls import include, path
from utilities.urls import get_model_urls

from netbox_compare import views

urlpatterns = [
    path(
        "policies/",
        include(get_model_urls("netbox_compare", "comparisonpolicy", detail=False)),
    ),
    path(
        "policies/<int:pk>/",
        include(get_model_urls("netbox_compare", "comparisonpolicy")),
    ),
    path(
        "schedules/",
        include(get_model_urls("netbox_compare", "comparisonschedule", detail=False)),
    ),
    path(
        "schedules/<int:pk>/",
        include(get_model_urls("netbox_compare", "comparisonschedule")),
    ),
    path(
        "schedules/<int:pk>/run/",
        views.ComparisonScheduleRunView.as_view(),
        name="comparisonschedule_run",
    ),
    path(
        "runs/",
        include(get_model_urls("netbox_compare", "comparisonrun", detail=False)),
    ),
    path(
        "runs/<int:pk>/",
        include(get_model_urls("netbox_compare", "comparisonrun")),
    ),
    path(
        "runs/<int:pk>/notify/",
        views.ComparisonRunNotifyView.as_view(),
        name="comparisonrun_notify",
    ),
    path(
        "comparisons/",
        include(get_model_urls("netbox_compare", "comparison", detail=False)),
    ),
    path(
        "comparisons/<int:pk>/",
        include(get_model_urls("netbox_compare", "comparison")),
    ),
    path(
        "comparisons/<int:pk>/resolve/",
        views.ComparisonResolveView.as_view(),
        name="comparison_resolve",
    ),
    path("devices/<int:pk>/compare/", views.DeviceCompareView.as_view(), name="device_compare"),
]
