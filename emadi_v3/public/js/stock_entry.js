frappe.ui.form.on('Stock Entry', {
    refresh: function(frm) {
        // calculate_total_qty(frm)
    }
});


function calculate_total_qty(frm) {
    let total_qty = 0;
    
    $.each(frm.doc.items || [], function(_, row) {
        total_qty += row.qty || 0;
    });

    frm.set_value('total_qty', total_qty);
}

// Bags <-> Qty on every item row: 1 bag = 100.
//   typing Bags  ->  Qty  = Bags * 100
//   typing Qty   ->  Bags = Qty / 100
// A flag on the row stops the two handlers from re-triggering each other.
// The field is Stock Entry Detail > custom_bags (the old name `bags` is no longer used anywhere).
const BAG_SIZE = 100;

function sync_bags_qty(frm, cdt, cdn, from_field) {
    const row = locals[cdt][cdn];
    if (!row || row.__bags_sync) {
        return;
    }
    row.__bags_sync = true;
    const done = () => { row.__bags_sync = false; };
    let p;
    if (from_field === "custom_bags") {
        p = frappe.model.set_value(cdt, cdn, "qty", flt(flt(row.custom_bags) * BAG_SIZE, precision("qty", row)));
    } else {
        p = frappe.model.set_value(cdt, cdn, "custom_bags", flt(flt(row.qty) / BAG_SIZE, precision("custom_bags", row) || 6));
    }
    Promise.resolve(p).then(done, done);
}

frappe.ui.form.on('Stock Entry Detail', {
    custom_bags: function(frm, cdt, cdn) {
        sync_bags_qty(frm, cdt, cdn, "custom_bags");
    },
    qty: function(frm, cdt, cdn) {
        if (frappe.meta.has_field("Stock Entry Detail", "custom_bags")) {
            sync_bags_qty(frm, cdt, cdn, "qty");
        }
    }
});
