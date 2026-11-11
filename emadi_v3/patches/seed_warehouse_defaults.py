import frappe

# The warehouses that used to be hardcoded in the code: keep today's behaviour by copying them into Emadi Settings
# (only when they exist on this site and the setting is still empty). Everything is editable afterwards.
OLD = {
	"yarn_issue_source_warehouse": "Source - PT",
	"yarn_issue_target_warehouse": "Supplier - PT",
	"weaving_receipt_source_warehouse": "Supplier - PT",
	"weaving_receipt_target_warehouse": "Finished Goods - PT",
	"cpy_target_warehouse": "Customer Warehouse - ET",
}


def execute():
	frappe.reload_doc("emadiv3", "doctype", "emadi_warehouse_default")
	frappe.reload_doc("emadiv3", "doctype", "emadi_settings")
	s = frappe.get_single("Emadi Settings")
	for key, wh in OLD.items():
		if not s.get(key) and frappe.db.exists("Warehouse", wh):
			s.set(key, wh)
	if not any(r.document_type == "Sales Order" and r.fieldname == "set_warehouse" and not r.table_field for r in s.warehouse_defaults):
		s.append("warehouse_defaults", {"document_type": "Sales Order", "fieldname": "set_warehouse", "setting": "so_default_warehouse"})
	s.flags.ignore_permissions = True
	s.save()
