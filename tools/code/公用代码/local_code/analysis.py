"""Tree-sitter structure and diagnostics; no user code execution."""
import ast
import json
from pathlib import Path

from tree_sitter import Query, QueryCursor
from tree_sitter_language_pack import get_language, get_parser

EXTENSIONS = {".py": "python", ".pyi": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".ts": "typescript", ".tsx": "tsx", ".java": "java", ".go": "go", ".rs": "rust", ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp"}
QUERIES = json.loads(Path(__file__).with_name("symbol_queries.json").read_text(encoding="utf-8"))


def language_for(path):
    language = EXTENSIONS.get(Path(path).suffix.lower())
    if language is None:
        raise ValueError("Structure/diagnostics require a supported code extension")
    return language


def parse(path, text):
    language = language_for(path)
    data = text.encode("utf-8")
    return language, data, get_parser(language).parse(data)


def nodes(root):
    stack = [root]; count = 0
    while stack:
        node = stack.pop(); count += 1
        if count > 100000:
            raise ValueError("Syntax tree exceeds 100000 nodes")
        yield node
        stack.extend(reversed(node.children))


def point(data, byte):
    line = data.count(b"\n", 0, byte) + 1
    start = data.rfind(b"\n", 0, byte) + 1
    return {"line": line, "column": len(data[start:byte].decode("utf-8"))}


def diagnostics(path, text):
    language, data, tree = parse(path, text)
    errors = []
    if language == "python":
        try:
            compile(text, str(path), "exec", dont_inherit=True)
        except (SyntaxError, ValueError) as exc:
            errors.append({"message": str(exc), "line": getattr(exc, "lineno", 1), "column": max(0, (getattr(exc, "offset", 1) or 1)-1)})
    else:
        for node in nodes(tree.root_node):
            if node.is_error or node.is_missing:
                errors.append({"message": "Unexpected syntax" if node.is_error else "Missing " + node.type, **point(data, node.start_byte)})
                if len(errors) == 100:
                    break
    return {"language": language, "ok": not errors, "diagnostics": errors, "limit_reached": len(errors) == 100}


def symbols(path, text):
    language, data, tree = parse(path, text)
    if tree.root_node.has_error:
        raise ValueError("Fix syntax errors before structural lookup/editing; use get_diagnostics")
    output, seen = [], set()
    for category, query_text in QUERIES["typescript" if language == "tsx" else language].items():
        query = Query(get_language(language), query_text)
        cursor = QueryCursor(query)
        cursor.match_limit = 10000
        for _, captures in cursor.matches(tree.root_node):
            for capture, definitions in captures.items():
                if not capture.endswith((".def", ".decl")):
                    continue
                prefix = capture.rsplit(".", 1)[0]
                names = captures.get(prefix + ".name", [])
                for original in definitions:
                    node = original
                    if names:
                        name_node = names[0]
                    elif node.type == "arrow_function" and node.parent.type == "variable_declarator":
                        node = node.parent
                        name_node = node.child_by_field_name("name")
                    else:
                        continue
                    if name_node is None:
                        continue
                    # Include the syntax wrappers that must move with a definition.
                    while node.parent and node.parent.type in ("decorated_definition", "export_statement"):
                        node = node.parent
                    key = (node.start_byte, node.end_byte)
                    if key in seen:
                        continue
                    seen.add(key)
                    name = data[name_node.start_byte:name_node.end_byte].decode("utf-8")
                    output.append({"name": name, "kind": prefix, "start_byte": node.start_byte, "end_byte": node.end_byte,
                                   "start": point(data, node.start_byte), "end": point(data, node.end_byte), "name_position": point(data, name_node.start_byte)})
        if cursor.did_exceed_match_limit:
            raise ValueError("Symbol query exceeds match limit")
    output.sort(key=lambda s: (s["start_byte"], -s["end_byte"]))
    if len(output) > 10000:
        raise ValueError("Too many symbols")
    parents = []
    for item in output:
        while parents and item["end_byte"] > parents[-1]["end_byte"]:
            parents.pop()
        item["name_path"] = "/".join([p["name"] for p in parents] + [item["name"]])
        parents.append(item)
    return output


def public_symbol(item, text, include_body=False):
    result = {k: v for k, v in item.items() if k not in ("start_byte", "end_byte")}
    if include_body:
        result["body"] = text.encode("utf-8")[item["start_byte"]:item["end_byte"]].decode("utf-8")
    return result


def select_symbol(path, text, name_path):
    candidates = [s for s in symbols(path, text) if s["name_path"] == name_path]
    if len(candidates) != 1:
        raise ValueError("name_path must identify exactly one symbol; use overview/find_symbol (overloads require text/line edits)")
    return candidates[0]
