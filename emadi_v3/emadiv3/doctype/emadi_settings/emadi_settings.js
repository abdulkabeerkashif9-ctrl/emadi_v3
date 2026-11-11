// Copyright (c) 2025, Safdar Ali and contributors
// For license information, please see license.txt

frappe.ui.form.on('Emadi Settings', {
	setup(frm) {
		// only real (non-group, enabled) warehouses can hold stock
		frm.meta.fields.filter(f => f.fieldtype === 'Link' && f.options === 'Warehouse').forEach(f => {
			frm.set_query(f.fieldname, () => ({ filters: { is_group: 0, disabled: 0 } }));
		});
	},
	after_save() {
		if (window.emadi_defaults) emadi_defaults.reload();
	},
});
