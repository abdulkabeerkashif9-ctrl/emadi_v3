import frappe

OLD = "Stock Entry Detail-bags"
NEW = "Stock Entry Detail-custom_bags"


def execute():
	"""The Bags field of Stock Entry Detail is now `custom_bags` (the apps' custom field files say so). If the site already renamed the
	field in Customize Form, its Custom Field record is still *named* "Stock Entry Detail-bags"; syncing the files would then add a second
	"custom_bags" field. Give the record the new name first so the sync updates it instead.
	"""
	if not frappe.db.exists("Custom Field", OLD) or frappe.db.exists("Custom Field", NEW):
		return
	fieldname = frappe.db.get_value("Custom Field", OLD, "fieldname")
	if fieldname != "custom_bags":
		# still called `bags` on this site: rename the field itself (column, saved views, reports) first
		from frappe.model.utils.rename_field import rename_field

		frappe.db.set_value("Custom Field", OLD, "fieldname", "custom_bags", update_modified=False)
		if frappe.db.has_column("Stock Entry Detail", "bags") and not frappe.db.has_column("Stock Entry Detail", "custom_bags"):
			frappe.reload_doctype("Stock Entry Detail", force=True)
			rename_field("Stock Entry Detail", "bags", "custom_bags")
	frappe.db.sql("update `tabCustom Field` set name=%s where name=%s", (NEW, OLD))
	frappe.clear_cache(doctype="Stock Entry Detail")
