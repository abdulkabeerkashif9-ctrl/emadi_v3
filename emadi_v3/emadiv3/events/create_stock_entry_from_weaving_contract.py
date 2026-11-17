import frappe
from frappe.model.document import Document

from emadi_v3.emadiv3.emadi_defaults import get_default_warehouse

@frappe.whitelist()
def create_stock_entry_from_weaving_contract(weaving_contract):
    # Fetch the Weaving Contract document
    contract = frappe.get_doc("Weaving Contract", weaving_contract)
    if frappe.db.exists("Stock Entry", {"weaving_contract": weaving_contract, "purpose": "Material Receipt", "docstatus": ["!=", 2]}):
        frappe.throw(f"Stock Entry already created for {weaving_contract} Weaving Contract")
    # Create a new Stock Entry
    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.stock_entry_type = "Material Receipt"  # Change as needed
    stock_entry.purpose = "Material Receipt"
    stock_entry.weaving_contract = weaving_contract  # Link back to Weaving Contract
    stock_entry.weaver = contract.weaver  # Link back to Weaving Contract

    warehouse = get_default_warehouse("cpy_target_warehouse")      # Emadi Settings > Customer Provided Yarn

    # One row per Yarn Item: BOM Items rows that use the same yarn are added together
    totals = {}
    uoms = {}
    for item in contract.bom_items:
        if not item.yarn_count:
            continue
        totals[item.yarn_count] = totals.get(item.yarn_count, 0) + (item.yarn_qty or 0)
        uoms.setdefault(item.yarn_count, item.uom)
    if not totals:
        frappe.throw("No yarn rows found on Weaving Contract {0}.".format(weaving_contract))

    for yarn, qty in totals.items():
        uom = frappe.db.get_value("Item", yarn, "stock_uom") or uoms.get(yarn)
        stock_entry.append("items", {
            "item_code": yarn,
            "qty": qty,
            "uom": uom,
            "stock_uom": uom,
            "conversion_factor": 1,
            "allow_zero_valuation_rate": 1,
            "t_warehouse": warehouse
        })

    # Return the Stock Entry name to open in the form view
    return stock_entry

