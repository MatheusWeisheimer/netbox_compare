import logging

from django.middleware.csrf import get_token
from django.urls import reverse
from netbox.plugins import PluginTemplateExtension

from netbox_compare.credentials import resolve_credentials
from netbox_compare.models import ComparisonPolicy
from netbox_compare.modules import connection_for_platform

logger = logging.getLogger(__name__)


class DeviceCompareButton(PluginTemplateExtension):
    models = ["dcim.device"]

    def buttons(self):
        device = self.context["object"]
        request = self.context["request"]
        if not request.user.has_perm("netbox_compare.add_comparison"):
            return ""
        try:
            credentials = resolve_credentials(device)
        except Exception:
            # A broken credentials backend must never break the device page.
            logger.exception("Credential resolution crashed for device %s", device.pk)
            return ""
        if credentials is None:
            return ""
        platform = device.platform.slug if device.platform else None
        policies = list(ComparisonPolicy.objects.restrict(request.user, "view"))
        return self.render(
            "netbox_compare/inc/compare_button.html",
            {
                "supported": connection_for_platform(platform) is not None,
                "platform": platform,
                "policies": policies,
                "default_policy": next((p for p in policies if p.is_default), None),
                "compare_url": reverse("plugins:netbox_compare:device_compare", args=[device.pk]),
                "csrf_token": get_token(request),
            },
        )


template_extensions = [DeviceCompareButton]
