# Server Script (optional, automatic run)
#   Script Type : Scheduler Event
#   Event Frequency : Daily   (or use Cron: 0 2 * * *)

if frappe.db.get_single_value("Google Drive", "enable"):
    frappe.call("frappe.integrations.doctype.google_drive.google_drive.take_backup")
