import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def create_sizing_program_from_weaving_contract(weaving_contract, item=None, beam_for=None, items=None):
	"""Called by the "Sizing Program" button on a submitted, Open Weaving
	Contract. The popup lists every Pile/Ground yarn still pending; `items`
	is a JSON list of the ones ticked ([{"for": "Pile", "yarn_count": ...}]) -
	ONE Sizing Program is made with a Yarn Details row for each (Pile and
	Ground together). `item`/`beam_for` (single yarn) still work for old
	callers.

	Returns a brand-new, unsaved Sizing Program for the user to review.
	"""
	import json

	wc = frappe.get_doc("Weaving Contract", weaving_contract)

	picks = []
	if items:
		picks = json.loads(items) if isinstance(items, str) else items
	else:
		row = _pick_bom_row(wc, item, beam_for)
		if row:
			picks = [{"for": row.get("for"), "yarn_count": row.get("yarn_count")}]
	if not picks:
		frappe.throw(
			_("No Pile/Ground item with a Yarn Count found in this Weaving Contract's BOM Items.")
		)

	sizing_program = frappe.new_doc("Sizing Program")
	sizing_program.weaving_contract = wc.name
	sizing_program.sales_order = wc.get("sales_order")
	sizing_program.weaver = _get_weaver(wc)
	sizing_program.fabric_construction = wc.get("construction")
	# Quality on Sizing Program is a Cotton/Viscose Select - left for the user
	# (setting it to the finish item made saving fail).

	total_pending = 0.0
	for pick in picks:
		beam_for_ = pick.get("for")
		yarn = (pick.get("yarn_count") or "").strip()
		pending = _get_pending(wc, beam_for_, yarn)
		if pending["pending"] <= 0.001:
			frappe.throw(
				_("A Sizing Program has already been created for the full LBS of {0} ({1}).").format(
					yarn, beam_for_
				)
			)
		bom_row = next(
			(
				r
				for r in wc.bom_items or []
				if r.get("for") == beam_for_ and (r.get("yarn_count") or "").strip() == yarn
			),
			None,
		)
		beam_item_code = _beam_item_code(beam_for_, yarn)
		sizing_program.append(
			"yarn_items",
			{
				"weaving_contract": wc.name,
				"finish_item": wc.get("construction"),
				"yarn_item": yarn,
				"beam_item": beam_item_code if frappe.db.exists("Item", beam_item_code) else None,
				"lbs_per_bag": (flt(bom_row.get("lbs_per_bag")) if bom_row else 0) or 100,
				"lbs_issue": pending["pending"],
			},
		)
		total_pending += pending["pending"]

	first = picks[0]
	sizing_program.item = (first.get("yarn_count") or "").strip()
	sizing_program.lbs_issue = total_pending
	first_beam = _beam_item_code(first.get("for"), (first.get("yarn_count") or "").strip())
	if frappe.db.exists("Item", first_beam):
		sizing_program.item_returnable = first_beam

	return sizing_program


def _beam_item_code(beam_for, yarn_count):
	return f"BEAM-{beam_for}-{yarn_count}"


def _get_pending(wc, beam_for, yarn_count):
	"""Total LBS of this (Pile/Ground, yarn) across the contract's BOM Items,
	how much existing Sizing Programs already issued, and what is left."""
	total = sum(
		flt(r.get("yarn_qty"))
		for r in wc.bom_items or []
		if r.get("for") == beam_for and (r.get("yarn_count") or "").strip() == (yarn_count or "").strip()
	)
	# Old-style programs (single yarn in the header) ...
	issued = frappe.db.sql(
		"""
		select coalesce(sum(lbs_issue), 0)
		from `tabSizing Program` sp
		where weaving_contract = %s and item = %s and item_returnable = %s and docstatus != 2
		and not exists (select 1 from `tabSizing Program Yarn` y where y.parent = sp.name)
		""",
		(wc.name, yarn_count, _beam_item_code(beam_for, yarn_count)),
	)[0][0]
	# ... plus programs using the Yarn Details table (row's own contract).
	issued += frappe.db.sql(
		"""
		select coalesce(sum(y.lbs_issue), 0)
		from `tabSizing Program Yarn` y
		inner join `tabSizing Program` sp on sp.name = y.parent and y.parenttype = 'Sizing Program'
		where y.weaving_contract = %s and y.yarn_item = %s
		and coalesce(nullif(y.beam_item, ''), sp.item_returnable) = %s and sp.docstatus != 2
		""",
		(wc.name, yarn_count, _beam_item_code(beam_for, yarn_count)),
	)[0][0]
	return {"total": total, "issued": flt(issued), "pending": max(0.0, total - flt(issued))}


@frappe.whitelist()
def get_sizing_program_items(weaving_contract):
	"""Pile/Ground yarns that still need a Sizing Program, for the popup. The
	same yarn on several BOM rows is listed once with the rows' LBS added
	together; a yarn drops out once its full LBS has a Sizing Program."""
	wc = frappe.get_doc("Weaving Contract", weaving_contract)
	seen = []
	out = []
	for r in wc.bom_items or []:
		key = (r.get("for"), (r.get("yarn_count") or "").strip())
		if r.get("for") not in ("Pile", "Ground") or not key[1] or key in seen:
			continue
		seen.append(key)
		data = _get_pending(wc, *key)
		if data["pending"] > 0.001:
			out.append({"for": key[0], "yarn_count": key[1], **data})
	return out


def _pick_bom_row(wc, item, beam_for):
	rows = [r for r in (wc.bom_items or []) if r.get("for") in ("Pile", "Ground") and r.get("yarn_count")]

	if item:
		for r in rows:
			if r.get("yarn_count") == item and (not beam_for or r.get("for") == beam_for):
				return r

	return rows[0] if rows else None


def _get_weaver(wc):
	"""Weaving Contract doesn't carry an explicit "weaver"/"customer" field
	in the schema seen so far, so this falls back to the Customer on the
	linked Sales Order. Flagged - if Weaving Contract does have its own
	weaver/customer field under a different name, say so and this can read
	straight from that instead.
	"""
	# Weaving Contract's Weaver is a Supplier now, but Sizing Program.weaver
	# links to Customer - only use it when a Customer of that name exists
	# (otherwise saving fails with "Could not find Weaver").
	weaver = wc.get("weaver") or wc.get("customer")
	if weaver and frappe.db.exists("Customer", weaver):
		return weaver
	if wc.get("sales_order"):
		return frappe.db.get_value("Sales Order", wc.sales_order, "customer")
	return None


@frappe.whitelist()
def get_yarn_rows_for_contracts(weaving_contracts):
	"""For the "Get Items From Weaving Contract" button on Sizing Program:
	a Yarn Details row for every Pile/Ground yarn that still needs a Sizing
	Program, across all the given (submitted) Weaving Contracts."""
	import json

	if isinstance(weaving_contracts, str):
		weaving_contracts = json.loads(weaving_contracts)

	out = []
	for name in weaving_contracts or []:
		wc = frappe.get_doc("Weaving Contract", name)
		if wc.docstatus != 1:
			frappe.throw(_("Weaving Contract {0} is not submitted.").format(name))
		for data in get_sizing_program_items(name):
			yarn = data["yarn_count"]
			beam_item = _beam_item_code(data["for"], yarn)
			bom_row = next(
				(
					r
					for r in wc.bom_items or []
					if r.get("for") == data["for"] and (r.get("yarn_count") or "").strip() == yarn
				),
				None,
			)
			out.append(
				{
					"weaving_contract": wc.name,
					"finish_item": wc.get("construction"),
					"yarn_item": yarn,
					"beam_item": beam_item if frappe.db.exists("Item", beam_item) else None,
					"lbs_per_bag": (flt(bom_row.get("lbs_per_bag")) if bom_row else 0) or 100,
					"lbs_issue": data["pending"],
					"beam_for": data["for"],
				}
			)
	if not out:
		frappe.msgprint(_("No Pile/Ground yarn is left to create a Sizing Program for in the selected contracts."))
	return out
