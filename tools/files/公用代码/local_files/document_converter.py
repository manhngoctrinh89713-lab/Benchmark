# Adapted from microsoft/markitdown MCP (MIT); see EXTRACTION.json.
from markitdown import MarkItDown


def convert_document(path: str) -> str:
    """Convert a validated local file; no plugins, URI loading, server or network client."""
    converter = MarkItDown(enable_plugins=False)
    return converter.convert_local(path).markdown
