"""Evidence-backed system cartography."""

__version__ = "0.4.2"

from .composition_rules import (
    evaluate_cardinality,
    load_pinned_composition_rules,
    validate_composition_rules,
)
from .probe_receipts import import_probe_receipt, validate_probe_receipt
from .stack_schema import validate_stack_schema_pin, verify_pinned_stack_schema
from .host_bridge import (
    create_readonly_panel,
    mount_unified_gui_panel,
    panel_contract,
    probe_unified_gui_host,
)

__all__ = [
    "evaluate_cardinality",
    "create_readonly_panel",
    "import_probe_receipt",
    "load_pinned_composition_rules",
    "mount_unified_gui_panel",
    "panel_contract",
    "probe_unified_gui_host",
    "validate_composition_rules",
    "validate_probe_receipt",
    "validate_stack_schema_pin",
    "verify_pinned_stack_schema",
]
