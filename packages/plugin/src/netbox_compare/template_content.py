import logging

from netbox.plugins import PluginTemplateExtension

from netbox_compare.credentials import resolve_credentials

logger = logging.getLogger(__name__)


class DeviceCompareButton(PluginTemplateExtension):
    models = ["dcim.device"]

    def buttons(self):
        device = self.context["object"]
        try:
            credentials = resolve_credentials(device)
        except Exception:
            # A broken credentials backend must never break the device page.
            logger.exception("Credential resolution crashed for device %s", device.pk)
            return ""
        if credentials is None:
            return ""
        return self.render("netbox_compare/inc/compare_button.html")


template_extensions = [DeviceCompareButton]
