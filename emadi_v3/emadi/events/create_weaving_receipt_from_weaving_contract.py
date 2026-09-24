import frappe
from frappe import _

# "Weaving Receipt" button on Weaving Contract (shown only when Type =
# Outsourced). Builds an unsaved Weaving Receipt with one Items row
# prefilled from this contract - reuses the exact same row shape as
# mjfsd_v3's own get_weaving_contract_items() (the "Get Items From > Weaving
# Contract" popup already on Weaving Receipt itself), so both paths stay
# consistent. Returns the unsaved doc for the browser to route to
# (frappe.model.sync + frappe.set_route) - does NOT insert or submit
# anything, matching this project's "prefill, open the form, let the user
# review and save" pattern for buttons that create a new document.


@frappe.whitelist()
def create_weaving_receipt_from_weaving_contract(weaving_contract):
	from mjfsd_v3.loom_production.events.create_weaving_receipt import get_weaving_contract_items

	wc = frappe.get_doc("Weaving Contract", weaving_contract)
	if wc.docstatus != 1:
		frappe.throw(_("Weaving Contract must be submitted first."))

	rows = get_weaving_contract_items([wc.name])
	if not rows:
		frappe.throw(_("Could not build a Weaving Receipt row from {0}.").format(wc.name))

	wr = frappe.new_doc("Weaving Receipt")
	for row in rows:
		wr.append("items", row)

	return wr
