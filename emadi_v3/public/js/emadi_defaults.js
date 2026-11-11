// Warehouse defaults from Emadi Settings, available on every form.
//   emadi_defaults.get("sizing_receipt_source_warehouse").then(wh => ...)
// New documents also get their mapped warehouse fields filled automatically (Emadi Settings > "Apply Warehouse
// Defaults To Other Documents"), so forms of other apps need no code change.
(function () {
	const state = { data: null, loading: null };

	function load() {
		if (state.data) return Promise.resolve(state.data);
		if (!state.loading) {
			state.loading = frappe.xcall("emadi_v3.emadiv3.emadi_defaults.get_defaults")
				.then(d => (state.data = d))
				.catch(() => (state.data = { warehouses: {}, mapping: {} }));
		}
		return state.loading;
	}

	window.emadi_defaults = {
		get: key => load().then(d => (d.warehouses || {})[key] || null),
		reload: () => { state.data = state.loading = null; return load(); },
	};

	function fillNew(frm) {
		if (!frm || !frm.doc || !frm.is_new() || frm.doc.docstatus !== 0) return;
		load().then(d => {
			const rules = (d.mapping || {})[frm.doctype];
			if (!rules) return;
			rules.forEach(r => {
				const match = row => !(r.condition_field && String(row[r.condition_field] || "") !== r.condition_value);
				if (!r.table_field) {
					if (!frm.doc[r.fieldname] && match(frm.doc)) frm.set_value(r.fieldname, r.warehouse);
					return;
				}
				(frm.doc[r.table_field] || []).forEach(row => {
					if (!row[r.fieldname] && match(row)) frappe.model.set_value(row.doctype, row.name, r.fieldname, r.warehouse);
				});
			});
		});
	}

	// every form refresh (covers new documents and rows added before saving)
	$(document).on("app_ready", function () {
		const proto = frappe.ui.form && frappe.ui.form.Form && frappe.ui.form.Form.prototype;
		if (!proto || proto.__emadi_wrapped) return;
		const orig = proto.refresh;
		proto.refresh = function () {
			const out = orig.apply(this, arguments);
			try { fillNew(this); } catch (e) { /* never block a form */ }
			return out;
		};
		proto.__emadi_wrapped = true;
	});
})();
