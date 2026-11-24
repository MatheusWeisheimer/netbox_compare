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
        # Name of a Device custom field documenting the OS version (NetBox has none).
        "os_version_custom_field": None,
        # Ordered list of {"module": "<entry point name>", "config": {...}}. Scheduled jobs
        # pick which of these receive their results.
        "notifications": [],
        # Minutes after a scheduled run starts at which it is finalized (and notified) even if
        # some device comparisons have not finished; those are marked failed.
        "notification_deadline": 60,
        # NetBox's external URL (e.g. "https://netbox.example.com"), used for links in
        # notifications. Background jobs have no request to derive it from.
        "base_url": None,
    }

    def ready(self):
        super().ready()
        from netbox_compare import modules

        modules.discover()


config = NetBoxCompareConfig
