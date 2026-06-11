"""Compatibility facade for property view modules."""

from .view_modules.dashboard import dashboard
from .view_modules.inventory import (
    colony_plot_detail,
    colony_plot_create,
    colony_plot_edit,
    developer_create,
    plot_booking_create,
    plot_quotation_create,
    property_bulk_action,
    property_create,
    property_detail,
    property_edit,
    property_list,
    property_share_email,
)
from .view_modules.visits import (
    property_visit_create,
    property_visit_delete,
    property_visit_detail,
    property_visit_edit,
    property_visit_list,
)

__all__ = [
    "dashboard",
    "property_list",
    "property_bulk_action",
    "property_create",
    "property_detail",
    "property_edit",
    "property_share_email",
    "developer_create",
    "colony_plot_detail",
    "colony_plot_create",
    "colony_plot_edit",
    "plot_quotation_create",
    "plot_booking_create",
    "property_visit_list",
    "property_visit_create",
    "property_visit_detail",
    "property_visit_edit",
    "property_visit_delete",
]
