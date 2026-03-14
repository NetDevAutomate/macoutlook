# Contributors

- **Jon Hammant** -- Discovered the .olk15MsgSource extraction approach that enables full email content recovery (858x improvement over database preview). The original implementation in `outlook-connector-package/getEmails_FULL_ENHANCED.py` demonstrated that macOS Outlook stores complete RFC 2822 MIME email content in `.olk15MsgSource` files alongside the SQLite database, and that these files can be read to extract full email bodies, bypassing the 256-character preview limitation.
