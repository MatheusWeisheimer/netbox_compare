"""Lets the plugin's pure modules (no Django use) be tested without a NetBox install.

Importing any ``netbox_compare.*`` module runs the package ``__init__``, which needs
``netbox.plugins.PluginConfig``; a stub stands in when NetBox is not importable.
"""

import sys
import types

try:
    import netbox.plugins  # noqa: F401
except ImportError:
    netbox = types.ModuleType("netbox")
    plugins = types.ModuleType("netbox.plugins")
    plugins.PluginConfig = type("PluginConfig", (), {})
    netbox.plugins = plugins
    sys.modules.setdefault("netbox", netbox)
    sys.modules.setdefault("netbox.plugins", plugins)
