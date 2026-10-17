# RetroTransfer 98 — Changelog

## English-only edition — October 17, 2026

### Language and consistency

- Converted all graphical interface labels, hints, menus, file-picker dialogs, confirmations, warnings, error messages, and status updates to English.
- Converted all backend exceptions, authentication messages, server logs, CLI prompts, and Linux launcher messages to English.
- Rewrote the README and changelog entirely in English, including Windows/Linux setup, transfer steps, troubleshooting, and security limitations.
- Standardized the file browser terminology to **Local** and **Remote**, so the same interface makes sense on Linux or Windows in either role.
- Updated the existing integration tests to assert the English diagnostic messages.
- Preserved the transfer protocol and existing server/client behavior. Both machines should still run the same release.

### Validation

- All 12 backend integration tests passed after the language changes.
- Python syntax compilation passed.
- The graphical interface has not been runtime-tested in this environment because PySide6 is unavailable here.

## Version 2 fixes — October 17, 2026

- Added a local file explorer to the Client tab with a **Drives** button for Windows drive letters and external drives.
- Placed Local and Remote explorers side by side.
- Single-click selects an upload source; double-click navigates into folders.
- Labeled **Parent** buttons as directory navigation, not upload actions.
- Automatically refreshed the correct remote directory after successful uploads into subfolders.
- Added an explicit message when the remote shared directory is empty.
- Selected the download destination using OS-aware paths with a home-directory fallback.
- Locked server share-key and connection settings while the server is running.
- Added validation to reject absolute paths in the remote upload destination field.
