# Server Script
#   Script Type : API
#   API Method  : backup_to_gdrive
#   Allow Guest : No
# Call: /api/method/backup_to_gdrive

if "System Manager" not in frappe.get_roles():
    frappe.throw("Only System Manager can trigger a backup", frappe.PermissionError)

if not frappe.db.get_single_value("Google Drive", "enable"):
    frappe.throw("Google Drive integration is not enabled. Open 'Google Drive' settings, "
                 "authorize access and tick Enable.")

# Frappe's whitelisted method: queues a DB (+ optional files) backup on the
# long queue and uploads it to the folder set in Google Drive settings.
frappe.call("frappe.integrations.doctype.google_drive.google_drive.take_backup")

frappe.response["message"] = "Backup queued. It will be uploaded to Google Drive shortly."
