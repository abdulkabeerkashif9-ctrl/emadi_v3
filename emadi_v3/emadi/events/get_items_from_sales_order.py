import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_sales_order_items(sales_order):
	"""Items on a Sales Order that still have a weaving balance
	(qty - custom_weave_qty > 0), for the Weaving Contract "Get Items From"
	item-picker dialog.

	2026-09-14 update: grouped by item_code, summing balance across every
	row of that item. Previously this listed one entry per Sales Order
	Item row - fine when each Item appeared once per Sales Order, but the
	Dyeing feature now splits an Item across multiple rows (one per
	Color), so the same Item started showing up twice with two separate
	balances. Weaving happens before dyeing (Greige stage) and doesn't
	care about Color, so one Item = one combined balance here.
	"""
	so_items = frappe.get_all(
		"Sales Order Item",
		filters={"parent": sales_order},
		fields=["name", "item_code", "item_name", "qty", "custom_weave_qty"],
		order_by="idx asc",
	)

	balances = {}
	for d in so_items:
		group = balances.setdefault(
			d.item_code, {"item_code": d.item_code, "item_name": d.item_name, "balance_qty": 0.0}
		)
		group["balance_qty"] += flt(d.qty) - flt(d.custom_weave_qty)

	return [g for g in balances.values() if g["balance_qty"] > 0]


@frappe.whitelist()
def get_weaving_items_from_sales_order(sales_order, item_code):
	"""Build the Finish Item + BOM Items payload for a Weaving Contract from
	every Sales Order Item row on this Sales Order with this item_code -
	order qty = combined balance across all of them (qty - already-weaved
	qty, summed). Raw materials/wastage/weights are still per-Item (not
	per-row), pulled from the Towel Costing Sheet referenced on a
	representative row.

	2026-09-14 update: takes item_code instead of a single sales_order_item
	row name - see get_sales_order_items' own note above. The actual
	balance draw-down across rows happens at Weaving Contract submit time
	(server-side, re-queried fresh from the DB - see weaving_contract.py's
	allocate_sales_order_balance) - this method only computes what to
	show/prefill, so it can't itself over- or under-reserve anything.

	2026-09-16: the actual field-gathering was pulled out into
	`_get_weaving_data_from_sales_order` so `create_weaving_contract_from_sales_order`
	(below) can reuse the exact same logic instead of duplicating it.
	"""
	return _get_weaving_data_from_sales_order(sales_order, item_code)


@frappe.whitelist()
def create_weaving_contract_from_sales_order(sales_order, item_code):
	"""New 2026-09-16 - "the weaving contract button in sales order doesn't
	fetch any data ... it should ask for finish item first and then take
	the user to weaving contract form and all the data that is fetched
	either from sales order or towel costing sheet when we use get items
	from sales order" (your words). Sales Order's own "Weaving Contract"
	button used to just do `frappe.new_doc("Weaving Contract", {sales_order:
	...})` client-side - a blank draft with nothing but the Sales Order
	link set, leaving the user to run Weaving Contract's own "Get Items
	From > Sales Order" picker themselves.

	This builds an unsaved Weaving Contract the same way that picker does -
	reusing `_get_weaving_data_from_sales_order`, the exact same
	field-gathering `get_weaving_items_from_sales_order` already uses - so
	both paths always agree, then returns the draft doc directly (same
	"build unsaved doc server-side, sync + route client-side" pattern as
	`create_dyeing_contract_from_sales_order`), which the browser routes to.
	"""
	data = _get_weaving_data_from_sales_order(sales_order, item_code)

	wc = frappe.new_doc("Weaving Contract")
	wc.sales_order = sales_order
	wc.sales_order_item = data["sales_order_item"]
	wc.construction = data["item_code"]
	wc.fabric_qty = data["order_qty"]
	wc.finish_weight = data["finish_weight"]
	wc.gross_weight = data["gross_weight"]

	for row in data["bom_items"]:
		wc.append("bom_items", row)

	return wc


def _get_weaving_data_from_sales_order(sales_order, item_code):
	"""Shared by `get_weaving_items_from_sales_order` (Weaving Contract's own
	on-form "Get Items From > Sales Order" picker) and
	`create_weaving_contract_from_sales_order` (the new Sales Order ->
	Weaving Contract button) - see both callers' docstrings. Not
	whitelisted itself; call one of the two above."""
	so_items = frappe.get_all(
		"Sales Order Item",
		filters={"parent": sales_order, "item_code": item_code},
		fields=["name", "qty", "custom_weave_qty", "custom_towel_costing_sheet"],
		order_by="idx asc",
	)
	if not so_items:
		frappe.throw(_("Item {0} not found on Sales Order {1}").format(item_code, sales_order))

	balance_qty = sum(flt(d.qty) - flt(d.custom_weave_qty) for d in so_items)

	# Representative row - used only so downstream docs that read Weaving
	# Contract.sales_order_item (e.g. Weaving Receipt's TCS Reference
	# derivation) keep working unchanged. Every row of the same Item is
	# expected to carry the same Towel Costing Sheet regardless of Color,
	# so any one of them works; if they genuinely don't match, the first
	# row that HAS a Towel Costing Sheet set wins - flagged, not a
	# blocking error, since this only affects which TCS gets shown/used
	# here, not the balance math above.
	representative = next((d for d in so_items if d.custom_towel_costing_sheet), so_items[0])
	towel_costing_sheet = representative.custom_towel_costing_sheet

	bom_items = []
	weaving_wastage = 0
	finish_weight = 0
	gross_weight = 0
	if towel_costing_sheet:
		tcs = frappe.get_doc("Towel Costing Sheet", towel_costing_sheet)

		for finish_row in tcs.finish_item_towel_costing or []:
			if finish_row.article == item_code:
				weaving_wastage = flt(finish_row.weaving_wastage_percet)
				finish_weight = flt(finish_row.finish_weight)
				gross_weight = flt(finish_row.greige_weight)
				break

		for row in tcs.materials or []:
			if row.item != item_code:
				continue
			bom_items.append(
				{
					"for": row.get("for"),
					"yarn_count": row.raw_material,
					"ratio": flt(row.ratio),
					"weaving_wastage": weaving_wastage,
					"yarn_qty": flt(balance_qty) * flt(row.yarn_required_in_lbs),
					# Required Bags is a Float field - no rounding, keep the
					# exact calculated value.
					"required_bags": flt(balance_qty) * flt(row.bags_reqd),
				}
			)

	return {
		"item_code": item_code,
		"order_qty": balance_qty,
		"sales_order_item": representative.name,
		"towel_costing_sheet": towel_costing_sheet,
		"finish_weight": finish_weight,
		"gross_weight": gross_weight,
		"bom_items": bom_items,
	}