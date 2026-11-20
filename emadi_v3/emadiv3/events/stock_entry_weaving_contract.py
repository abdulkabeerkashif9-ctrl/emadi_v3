import frappe


def before_validate(doc, method=None):
    """Stock Entry made from a Material Request (e.g. Material Receipt) keeps the
    Weaving Contract of that Material Request, on the header and on each row."""
    mr_names = {row.material_request for row in doc.get("items") or [] if row.get("material_request")}
    if not mr_names:
        return

    if not doc.get("weaving_contract"):
        contracts = {
            frappe.db.get_value("Material Request", mr, "weaving_contract") for mr in mr_names
        } - {None, ""}
        if len(contracts) == 1:
            doc.weaving_contract = contracts.pop()

    for row in doc.get("items") or []:
        if row.get("weaving_contract") or not row.get("material_request"):
            continue
        contract = None
        if row.get("material_request_item"):
            contract = frappe.db.get_value(
                "Material Request Item", row.material_request_item, "weaving_contract"
            )
        row.weaving_contract = contract or frappe.db.get_value(
            "Material Request", row.material_request, "weaving_contract"
        )


# ───────────────────────── Receive Yarn: one yarn Batch per row ─────────────────────────
def _ensure_item_has_batches(item):
	"""Batches need Has Batch No on the item: switched on here when the item has no stock yet."""
	if frappe.db.get_value("Item", item, "has_batch_no"):
		return
	if frappe.db.exists("Stock Ledger Entry", {"item_code": item, "is_cancelled": 0}):
		frappe.throw(
			frappe._('Item {0} already has stock and "Has Batch No" is off, so a yarn Batch can\'t be created. Enable "Has Batch No" on the item first.').format(item)
		)
	frappe.db.set_value("Item", item, "has_batch_no", 1)


def _next_batch_number(contract):
	last = 0
	for name in frappe.get_all("Batch", filters={"name": ["like", f"{contract}-%"]}, pluck="name"):
		suffix = name[len(contract) + 1 :]
		if suffix.isdigit():
			last = max(last, int(suffix))
	return last + 1


def create_yarn_batches(doc, method=None):
	"""Receive Yarn (Material Receipt of a Weaving Contract): every yarn row without a Batch gets one, named
	<Weaving Contract>-<n>, carrying the row's Brand and PaperTip and the Weaving Contract."""
	if doc.get("purpose") != "Material Receipt" or not doc.get("weaving_contract"):
		return
	contract = doc.weaving_contract
	n = _next_batch_number(contract)
	for row in doc.get("items") or []:
		if row.get("batch_no") or not row.get("t_warehouse"):
			continue
		_ensure_item_has_batches(row.item_code)
		batch = frappe.new_doc("Batch")
		batch.batch_id = f"{contract}-{n}"
		batch.item = row.item_code
		batch.reference_doctype = "Stock Entry"
		batch.reference_name = doc.name
		batch.custom_weaving_contract = contract
		batch.custom_brand = row.get("brand")
		batch.custom_paper_tip = row.get("custom_paper_tip")
		batch.insert(ignore_permissions=True)
		row.batch_no = batch.name
		row.use_serial_batch_fields = 1
		n += 1


def disable_yarn_batches(doc, method=None):
	"""Cancelled Receive Yarn entry: its yarn Batches are disabled (kept, they may be referenced)."""
	if doc.get("purpose") != "Material Receipt" or not doc.get("weaving_contract"):
		return
	for name in frappe.get_all("Batch", filters={"reference_doctype": "Stock Entry", "reference_name": doc.name}, pluck="name"):
		frappe.db.set_value("Batch", name, "disabled", 1)
