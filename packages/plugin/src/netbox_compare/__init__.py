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
        # Ordered list of {"module": "<entry point name>", "config": {...}}. Scheduled jobs
        # pick which of these receive their results.
        "notifications": [],
    }

    def ready(self):
        super().ready()
        from netbox_compare import modules

        modules.discover()


config = NetBoxCompareConfig
