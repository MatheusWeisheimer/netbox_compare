from django import template
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext as _

from netbox_compare_core import FIELDS

register = template.Library()


def _speed(kbps: int) -> str:
    for unit, factor in (("Tbps", 10**9), ("Gbps", 10**6), ("Mbps", 10**3)):
        if kbps >= factor:
            return f"{kbps / factor:g} {unit}"
    return f"{kbps} Kbps"


@register.simple_tag
def canonical_value(value, field_path):
    """Render one canonical value; blank values are shown explicitly, never as nothing."""
    if value is None:
        return format_html('<span class="text-muted fst-italic">{}</span>', _("blank"))
    if value == "":
        return format_html('<span class="text-muted fst-italic">{}</span>', _("empty"))
    if isinstance(value, bool):
        icon, color = ("check-bold", "success") if value else ("close-thick", "danger")
        return format_html(
            '<i class="mdi mdi-{} text-{}"></i> {}', icon, color, _("Yes") if value else _("No")
        )
    if field_path == "interface.speed" and isinstance(value, int):
        return _speed(value)
    if isinstance(value, dict):
        # A whole object (presence divergence). jsonb does not keep key order: use the
        # catalogue's, and skip the key field, which the report already shows.
        object_type = field_path.split(".", 1)[0]
        rows = [
            (spec.label, canonical_value(value[spec.name], path))
            for path, spec in FIELDS.items()
            if spec.object_type == object_type and not spec.key and spec.name in value
        ]
        return format_html(
            '<dl class="row mb-0 small">{}</dl>',
            format_html_join(
                "",
                '<dt class="col-5 fw-normal text-muted">{}</dt><dd class="col-7 mb-0">{}</dd>',
                rows,
            ),
        )
    return format_html("<code>{}</code>", value)


@register.filter
def field_label(path):
    spec = FIELDS.get(path)
    return spec.label if spec else path
