"""Convert Python comments/docstrings to Traditional Chinese without changing code."""

from __future__ import annotations

import ast
import ctypes
import io
import json
import tokenize
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("core", "platform_api", "mcp_server", "examples", "tests", "scripts")
WORDING = {
    "爲": "為",
    "啓": "啟",
    "裏": "裡",
    "纔": "才",
    "僞": "偽",
    "注釋": "註解",
    "默認": "預設",
    "異步": "非同步",
    "創建": "建立",
    "調用": "呼叫",
    "接口": "介面",
    "數據": "資料",
    "信息": "資訊",
    "字符": "字元",
    "文本": "文字",
    "網絡": "網路",
    "模塊": "模組",
    "返回": "回傳",
    "運行": "執行",
    "擴展": "擴充",
    "用戶": "使用者",
    "存儲": "儲存",
    "全局": "全域",
    "消息": "訊息",
}


def convert(text: str) -> str:
    mapping = ctypes.windll.kernel32.LCMapStringW
    mapping.argtypes = [
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.c_wchar_p,
        ctypes.c_int,
    ]
    output = ctypes.create_unicode_buffer(len(text) + 1)
    if text and not mapping(1028, 0x04000000, text, len(text), output, len(output)):
        raise ctypes.WinError()
    result = output.value
    for source, target in WORDING.items():
        result = result.replace(source, target)
    # These are existing filesystem names, not prose: retain exact spelling.
    for translated, actual in {
        "CASE-工具鏈組合": "CASE-工具鏈組合",
        "CASE-搭建故障診斷Agent": "CASE-搭建故障診斷Agent",
    }.items():
        result = result.replace(translated, actual)
    return result


def docstring_positions(tree: ast.AST) -> set[tuple[int, int]]:
    positions = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                value = node.body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    positions.add((value.lineno, value.col_offset))
    return positions


def executable_tree(source: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                value = node.body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    node.body.pop(0)
    return ast.dump(tree, include_attributes=False)


def localize(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    positions = docstring_positions(ast.parse(source))
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    edits = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT or (
            token.type == tokenize.STRING and token.start in positions
        ):
            converted = convert(token.string)
            if converted != token.string:
                start = offsets[token.start[0] - 1] + token.start[1]
                end = offsets[token.end[0] - 1] + token.end[1]
                edits.append((start, end, converted))
    revised = source
    for start, end, text in reversed(edits):
        revised = revised[:start] + text + revised[end:]
    if executable_tree(revised) != executable_tree(source):
        raise ValueError(f"Executable code changed unexpectedly: {path}")
    if edits:
        path.write_text(revised, encoding="utf-8")
    return {
        "file": path.relative_to(ROOT).as_posix(),
        "annotation_edits": len(edits),
        "executable_ast_unchanged": True,
    }


def main() -> None:
    # Exclude this converter: changing its wording map would invalidate the audit.
    files = [
        path
        for name in SOURCE_DIRS
        for path in sorted((ROOT / name).rglob("*.py"))
        if path != Path(__file__).resolve()
    ]
    results = [localize(path) for path in files]
    report = {
        "scope": "Python comments and docstrings only",
        "files_scanned": len(files),
        "files_changed": sum(r["annotation_edits"] > 0 for r in results),
        "annotation_edits": sum(r["annotation_edits"] for r in results),
        "executable_ast_unchanged": True,
        "files": results,
    }
    (ROOT / "reports" / "annotation-localization.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in report.items() if key != "files"}))


if __name__ == "__main__":
    main()
