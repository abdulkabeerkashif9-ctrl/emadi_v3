import frappe
from frappe.model.document import Document

from emadi_v3.emadiv3 import emadi_defaults


class EmadiSettings(Document):
    def validate(self):
        emadi_defaults.validate_mapping(self)

    def on_update(self):
        emadi_defaults.clear_cache()
