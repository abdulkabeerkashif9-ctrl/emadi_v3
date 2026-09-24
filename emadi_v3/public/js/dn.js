frappe.ui.form.on('Delivery Note', {
    fabric_qty: function(frm) {
        if (frm.doc.custom_non_conversion==0) {
            if (frm.doc.fabric_qty) {
            $.each(frm.doc.items || [], function(index, row) {
                frappe.model.set_value(row.doctype, row.name, "qty", frm.doc.fabric_qty);
            });
            frm.refresh_field("items");

            $.each(frm.doc.bom_items_dn|| [], function(index, row) {
                frappe.model.set_value(row.doctype, row.name, "yarn_qty", frm.doc.fabric_qty * row.consumption);
            });
            frm.refresh_field("bom_items_dn");
        }
        }
        
    },
    // fabric_item: function(frm) {
    //     // When the fabric_item is changed, fetch the item doc
    //     if (frm.doc.fabric_item) {
    //         frappe.db.get_doc("Item", frm.doc.fabric_item)
    //             .then(item_doc => {
    //                 // Check the custom field and set custom_non_conversion accordingly
    //                 if (item_doc.custom_conversion === 1) {
    //                     frm.set_value("custom_non_conversion", 1);
    //                 } else {
    //                     frm.set_value("custom_non_conversion", 0);
    //                 }
    //             });
    //     } else {
    //         // No item selected, default
    //         frm.set_value("custom_non_conversion", 0);
    //     }
    // }
});


                