# Backup ERPNext site to Google Drive

1. Enable Server Scripts: `bench set-config -g server_script_enabled 1`
2. Google Cloud Console: create OAuth client (Web), enable Drive API, add redirect URI
   `https://<site>/api/method/frappe.integrations.google_oauth.callback`.
3. In ERPNext, open **Google Settings**, enter Client ID/Secret, enable.
4. Open **Google Drive** (single doctype): set Backup Folder Name, tick Enable, click **Authorize Google Drive Access**.
5. Create the Server Script(s) and the Client Script using the files here.
6. Open Google Drive settings → Actions → **Backup to Google Drive**.

Notes:
- Server Scripts run in a sandbox (no `import`, no direct Google API calls), so the upload
  is delegated to Frappe's own whitelisted `google_drive.take_backup`, which handles
  OAuth token refresh, folder creation and upload.
- Built-in alternative: set *Frequency* (Daily/Weekly) in Google Drive settings.
- Method/field names (`take_backup`, `enable`) come from Frappe v13+; verify on your version.
