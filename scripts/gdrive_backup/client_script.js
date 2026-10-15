// Client Script
//   DocType : Google Drive      (the single settings doctype)
//   Apply To: Form
// Adds a "Backup to Google Drive" button.

frappe.ui.form.on("Google Drive", {
    refresh(frm) {
        frm.add_custom_button(__("Backup to Google Drive"), () => {
            frappe.confirm(__("Create a backup now and upload it to Google Drive?"), () => {
                frappe.call({
                    method: "backup_to_gdrive",   // the API Server Script
                    freeze: true,
                    freeze_message: __("Queuing backup..."),
                    callback(r) {
                        if (r.message) {
                            frappe.show_alert({ message: r.message, indicator: "green" }, 7);
                        }
                    },
                });
            });
        }, __("Actions"));
    },
});
