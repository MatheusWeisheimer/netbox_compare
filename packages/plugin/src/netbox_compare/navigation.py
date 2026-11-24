from django.utils.translation import gettext_lazy as _
from netbox.plugins import PluginMenuButton, PluginMenuItem

menu_items = (
    PluginMenuItem(
        link="plugins:netbox_compare:comparison_list",
        link_text=_("Device comparison results"),
        permissions=["netbox_compare.view_comparison"],
    ),
    PluginMenuItem(
        link="plugins:netbox_compare:comparisonrun_list",
        link_text=_("Scheduled jobs results"),
        permissions=["netbox_compare.view_comparisonrun"],
    ),
    PluginMenuItem(
        link="plugins:netbox_compare:comparisonschedule_list",
        link_text=_("Scheduled jobs"),
        permissions=["netbox_compare.view_comparisonschedule"],
        buttons=(
            PluginMenuButton(
                link="plugins:netbox_compare:comparisonschedule_add",
                title=_("Add"),
                icon_class="mdi mdi-plus-thick",
                permissions=["netbox_compare.add_comparisonschedule"],
            ),
        ),
    ),
    PluginMenuItem(
        link="plugins:netbox_compare:comparisonpolicy_list",
        link_text=_("Comparison policies"),
        permissions=["netbox_compare.view_comparisonpolicy"],
        buttons=(
            PluginMenuButton(
                link="plugins:netbox_compare:comparisonpolicy_add",
                title=_("Add"),
                icon_class="mdi mdi-plus-thick",
                permissions=["netbox_compare.add_comparisonpolicy"],
            ),
        ),
    ),
)
