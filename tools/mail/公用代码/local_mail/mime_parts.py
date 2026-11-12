# Derived from Wh1isper/mcp-email-server, BSD-3-Clause.
# Copyright (c) 2025-2026, wh1isper. See licenses/Wh1isper-BSD-3-Clause.txt.
# Source commit: acbe0ec9981876f6cbb4e3a381295ca1b1113c33
# Changes: extract method as a function, remove unused self and logger call.
import mimetypes
from email import encoders
from email.mime.base import MIMEBase
from pathlib import Path

def create_attachment_part(path: Path, file_data: bytes) -> MIMEBase:
    """Create a MIME attachment part from already bounded bytes."""
    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type is None:
        mime_type = 'application/octet-stream'
    main_type, sub_type = mime_type.split('/', 1)
    attachment_part = MIMEBase(main_type, sub_type)
    attachment_part.set_payload(file_data)
    encoders.encode_base64(attachment_part)
    attachment_part.add_header('Content-Disposition', 'attachment', filename=path.name)
    return attachment_part
