from netbox.plugins import PluginConfig

__version__ = "0.1.0"


class NetBoxCompareConfig(PluginConfig):
    name = "netbox_compare"
    verbose_name = "NetBox Compare"
    description = "Detect drift between documented (NetBox) and observed (device) state"
    version = __version__
    base_url = "compare"
    min_version = "4.5.0"
    default_settings = {
        # Ordered list of {"module": "<entry point name>", "config": {...}}.
        # The first module that resolves a device wins.
        "credentials": [],
        # Ordered list of {"module": "<entry point name>", "config": {...}}.
        # A device uses the first module that declares its platform slug.
        "connections": [],
        # {canonical field path: severity}; None means netbox_compare.policy.DEFAULT_POLICY.
        "policy": None,
        # Name of a Device custom field documenting the OS version (NetBox has none).
        "os_version_custom_field": None,
    }

    def ready(self):
        super().ready()
        from netbox_compare import modules

        modules.discover()


config = NetBoxCompareConfig
