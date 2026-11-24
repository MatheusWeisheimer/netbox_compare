from django.utils.translation import gettext_lazy as _
from netbox.plugins import PluginMenuButton, PluginMenuItem

menu_items = (
    PluginMenuItem(
        link="plugins:netbox_compare:comparison_list",
        link_text=_("Comparisons"),
        permissions=["netbox_compare.view_comparison"],
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
