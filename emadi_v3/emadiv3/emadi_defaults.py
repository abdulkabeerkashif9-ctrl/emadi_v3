"""Warehouse defaults kept in one place: the single doctype "Emadi Settings".

Python:   get_default_warehouse("sizing_receipt_source_warehouse")
Browser:  emadi_defaults.get("sizing_receipt_source_warehouse").then(wh => ...)

Documents whose code lives in another app (Sizing Program, Daily Loom Production, ...) need no code change:
list their warehouse fields in Emadi Settings > "Apply Warehouse Defaults To Other Documents" and every empty one is
filled from the setting - on the form (new documents) and again on save.
"""
import frappe
from frappe import _

SETTINGS_DOCTYPE = "Emadi Settings"
CACHE_KEY = "emadi_warehouse_default_map"


def _warehouse_keys():
	meta = frappe.get_meta(SETTINGS_DOCTYPE)
	return [f.fieldname for f in meta.fields if f.fieldtype == "Link" and f.options == "Warehouse"]


def get_default_warehouse(key, required=True):
	"""Warehouse configured under `key` in Emadi Settings. With required=True a missing/removed warehouse stops the
	user with a message saying exactly which setting to fill in."""
	if key not in _warehouse_keys():
		frappe.throw(_("Unknown Emadi Settings warehouse: {0}").format(key))
	wh = frappe.db.get_single_value(SETTINGS_DOCTYPE, key)
	label = frappe.get_meta(SETTINGS_DOCTYPE).get_label(key)
	if not wh:
		if required:
			frappe.throw(
				_("Please set <b>{0}</b> in <a href='/app/emadi-settings'>Emadi Settings</a> first.").format(label),
				title=_("Default warehouse missing"),
			)
		return None
	if not frappe.db.exists("Warehouse", wh):
		frappe.throw(_("Warehouse {0} (Emadi Settings > {1}) does not exist any more.").format(wh, label))
	return wh


def _mapping():
	"""{doctype: [row dicts]} for rows whose setting currently has a value (cached until Emadi Settings changes)."""
	cached = frappe.cache().get_value(CACHE_KEY)
	if cached is not None:
		return cached
	out = {}
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return out
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	for r in settings.get("warehouse_defaults") or []:
		wh = settings.get(r.setting)
		if not (r.document_type and r.fieldname and wh):
			continue
		out.setdefault(r.document_type, []).append({
			"table_field": r.table_field or "", "fieldname": r.fieldname,
			"condition_field": r.condition_field or "", "condition_value": r.condition_value or "", "warehouse": wh,
		})
	frappe.cache().set_value(CACHE_KEY, out)
	return out


def clear_cache():
	frappe.cache().delete_value(CACHE_KEY)


@frappe.whitelist()
def get_defaults():
	"""All configured warehouses plus the field mapping, for the browser."""
	return {
		"warehouses": {k: frappe.db.get_single_value(SETTINGS_DOCTYPE, k) for k in _warehouse_keys()},
		"mapping": _mapping(),
	}


def _fill(row, rule):
	if row.get(rule["fieldname"]):
		return False
	if rule["condition_field"] and str(row.get(rule["condition_field"]) or "") != rule["condition_value"]:
		return False
	row.set(rule["fieldname"], rule["warehouse"])
	return True


def apply_defaults(doc, method=None):
	"""doc_events['*'].before_validate: fill empty mapped warehouse fields on drafts."""
	if doc.docstatus != 0 or doc.doctype == SETTINGS_DOCTYPE:
		return
	rules = _mapping().get(doc.doctype)
	if not rules:
		return
	for rule in rules:
		rows = doc.get(rule["table_field"]) if rule["table_field"] else [doc]
		for row in rows or []:
			_fill(row, rule)


def validate_mapping(settings):
	"""Called from Emadi Settings.validate: reject rows pointing at fields that don't exist, with the row number."""
	for r in settings.get("warehouse_defaults") or []:
		try:
			parent = frappe.get_meta(r.document_type)
		except Exception:
			frappe.throw(_("Row #{0}: document type {1} not found").format(r.idx, r.document_type))
		target = parent
		if r.table_field:
			tf = parent.get_field(r.table_field)
			if not tf or tf.fieldtype not in ("Table", "Table MultiSelect"):
				frappe.throw(_("Row #{0}: {1} has no table field '{2}'").format(r.idx, r.document_type, r.table_field))
			target = frappe.get_meta(tf.options)
		for fn, what in ((r.fieldname, _("warehouse field")), (r.condition_field, _("condition field"))):
			if fn and not target.has_field(fn):
				frappe.throw(_("Row #{0}: {1} '{2}' does not exist on {3}").format(r.idx, what, fn, target.name))
		if bool(r.condition_field) != bool(r.condition_value):
			frappe.throw(_("Row #{0}: fill both 'Only When Field' and 'Equals', or neither").format(r.idx))
