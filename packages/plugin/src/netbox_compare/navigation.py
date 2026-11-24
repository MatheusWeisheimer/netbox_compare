from django.utils.translation import gettext_lazy as _
from netbox.plugins import PluginMenuItem

menu_items = (
    PluginMenuItem(
        link="plugins:netbox_compare:comparison_list",
        link_text=_("Comparisons"),
        permissions=["netbox_compare.view_comparison"],
    ),
)
