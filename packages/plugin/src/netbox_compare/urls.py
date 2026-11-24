from django.urls import include, path
from utilities.urls import get_model_urls

from netbox_compare import views

urlpatterns = [
    path(
        "comparisons/",
        include(get_model_urls("netbox_compare", "comparison", detail=False)),
    ),
    path(
        "comparisons/<int:pk>/",
        include(get_model_urls("netbox_compare", "comparison")),
    ),
    path("devices/<int:pk>/compare/", views.DeviceCompareView.as_view(), name="device_compare"),
]
