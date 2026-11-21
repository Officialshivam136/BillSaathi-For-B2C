"""Parse multipart/form-data (file uploads) with the standard library's email parser."""
from email.parser import BytesParser
from email.policy import HTTP


def parse_multipart(content_type, body):
    """Return (fields, files). fields: {name: str}; files: {name: (filename, content_type, bytes)}."""
    if not content_type or not content_type.lower().startswith("multipart/form-data"):
        raise ValueError("Expected a file upload form")
    msg = BytesParser(policy=HTTP).parsebytes(b"Content-Type: " + content_type.encode("latin-1") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
    if not msg.is_multipart():
        raise ValueError("The upload could not be read")
    fields, files = {}, {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        data = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename is not None:
            files[name] = (filename, part.get_content_type(), data)
        else:
            fields[name] = data.decode("utf-8", "replace")
    return fields, files
