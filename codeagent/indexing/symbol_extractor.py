"""Source-code symbol extractor using AST for Python and regex patterns for other languages."""

import ast
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class ExtractedSymbol(BaseModel):
    """Structured code symbol (function, class, method, or global)."""

    name: str
    symbol_type: str  # "function", "class", "method", "variable", "import"
    file_path: str
    line_start: int
    line_end: int
    signature: Optional[str] = None
    docstring: Optional[str] = None
    parent_symbol: Optional[str] = None


CodeSymbol = ExtractedSymbol


class SymbolExtractor:
    """Extracts code symbols from Python AST and other languages via structural patterns.

    Language Parser Capabilities & Limitations:
    - Python: Full AST semantic extraction (classes, methods, functions, async functions, decorators, docstrings).
    - JavaScript / TypeScript: Regex-based extraction (functions, classes, export const/let, arrow functions).
      Limitation: Does not resolve TypeScript type hierarchies or complex macro evaluations.
    - Java: Regex-based extraction (public/private class, interface, method definitions).
      Limitation: Does not build Java type-binding symbol tables.
    - C / C++: Regex-based extraction (struct, class, functions).
      Limitation: Does not resolve preprocessor directives (#define, #ifdef) or templates.
    """

    def __init__(self) -> None:
        """Initialize SymbolExtractor."""
        pass

    def extract_symbols(self, file_path: str, content: str) -> List[ExtractedSymbol]:
        """Extract symbols from source code based on file extension."""
        ext = Path(file_path).suffix.lower()

        if ext == ".py":
            return self._extract_python_ast(file_path, content)
        elif ext in (".js", ".jsx", ".ts", ".tsx", ".mjs"):
            return self._extract_javascript_symbols(file_path, content)
        elif ext in (".java",):
            return self._extract_java_symbols(file_path, content)
        elif ext in (".c", ".cpp", ".cc", ".h", ".hpp"):
            return self._extract_c_cpp_symbols(file_path, content)
        return []

    def extract_from_code(self, code: str, file_path: str, language: Optional[str] = None) -> List[ExtractedSymbol]:
        """Convenience method extracting symbols from code string."""
        return self.extract_symbols(file_path=file_path, content=code)

    def _extract_python_ast(self, file_path: str, content: str) -> List[ExtractedSymbol]:
        """Parse Python AST to extract classes, methods, functions, and imports."""
        symbols: List[ExtractedSymbol] = []
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError:
            # If code has syntax errors, fall back to line-by-line regex
            return self._extract_python_regex_fallback(file_path, content)

        lines = content.splitlines()

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                cls_doc = ast.get_docstring(node)
                start_l = node.lineno
                end_l = getattr(node, "end_lineno", start_l)
                cls_sig = f"class {node.name}"
                if node.bases:
                    base_names = [ast.unparse(b) for b in node.bases]
                    cls_sig += f"({', '.join(base_names)})"

                symbols.append(
                    ExtractedSymbol(
                        name=node.name,
                        symbol_type="class",
                        file_path=file_path,
                        line_start=start_l,
                        line_end=end_l,
                        signature=cls_sig,
                        docstring=cls_doc,
                        parent_symbol=None,
                    )
                )

                # Extract methods inside class
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_doc = ast.get_docstring(item)
                        m_start = item.lineno
                        m_end = getattr(item, "end_lineno", m_start)
                        args_list = [
                            f"{arg.arg}: {ast.unparse(arg.annotation)}" if arg.annotation else arg.arg
                            for arg in item.args.args
                        ]
                        ret_ann = f" -> {ast.unparse(item.returns)}" if item.returns else ""
                        m_sig = f"def {item.name}({', '.join(args_list)}){ret_ann}"
                        symbols.append(
                            ExtractedSymbol(
                                name=item.name,
                                symbol_type="method",
                                file_path=file_path,
                                line_start=m_start,
                                line_end=m_end,
                                signature=m_sig,
                                docstring=method_doc,
                                parent_symbol=node.name,
                            )
                        )

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_doc = ast.get_docstring(node)
                start_l = node.lineno
                end_l = getattr(node, "end_lineno", start_l)
                args_list = [
                    f"{arg.arg}: {ast.unparse(arg.annotation)}" if arg.annotation else arg.arg
                    for arg in node.args.args
                ]
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                ret_ann = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                fn_sig = f"{prefix} {node.name}({', '.join(args_list)}){ret_ann}"

                symbols.append(
                    ExtractedSymbol(
                        name=node.name,
                        symbol_type="function",
                        file_path=file_path,
                        line_start=start_l,
                        line_end=end_l,
                        signature=fn_sig,
                        docstring=fn_doc,
                        parent_symbol=None,
                    )
                )

        return symbols

    def _extract_python_regex_fallback(self, file_path: str, content: str) -> List[ExtractedSymbol]:
        """Regex fallback for malformed or incomplete Python files."""
        symbols: List[ExtractedSymbol] = []
        for idx, line in enumerate(content.splitlines(), start=1):
            m_cls = re.match(r"^class\s+([A-Za-z0-9_]+)", line.strip())
            if m_cls:
                symbols.append(
                    ExtractedSymbol(
                        name=m_cls.group(1),
                        symbol_type="class",
                        file_path=file_path,
                        line_start=idx,
                        line_end=idx,
                        signature=line.strip(),
                    )
                )
                continue

            m_fn = re.match(r"^(?:async\s+)?def\s+([A-Za-z0-9_]+)", line.strip())
            if m_fn:
                symbols.append(
                    ExtractedSymbol(
                        name=m_fn.group(1),
                        symbol_type="function",
                        file_path=file_path,
                        line_start=idx,
                        line_end=idx,
                        signature=line.strip(),
                    )
                )
        return symbols

    def _extract_javascript_symbols(self, file_path: str, content: str) -> List[ExtractedSymbol]:
        """Extract functions, classes, and exported constants from JS/TS."""
        symbols: List[ExtractedSymbol] = []
        lines = content.splitlines()

        for idx, line in enumerate(lines, start=1):
            clean = line.strip()

            # Class definition: class Person { or export class Person
            m_cls = re.search(r"(?:export\s+)?class\s+([A-Za-z0-9_]+)", clean)
            if m_cls:
                symbols.append(
                    ExtractedSymbol(
                        name=m_cls.group(1),
                        symbol_type="class",
                        file_path=file_path,
                        line_start=idx,
                        line_end=idx,
                        signature=clean,
                    )
                )
                continue

            # Function definition: function doSomething(...) or export function ...
            m_fn = re.search(r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(", clean)
            if m_fn:
                symbols.append(
                    ExtractedSymbol(
                        name=m_fn.group(1),
                        symbol_type="function",
                        file_path=file_path,
                        line_start=idx,
                        line_end=idx,
                        signature=clean,
                    )
                )
                continue

            # Arrow function const: const handleClick = (...) =>
            m_arrow = re.search(r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", clean)
            if m_arrow:
                symbols.append(
                    ExtractedSymbol(
                        name=m_arrow.group(1),
                        symbol_type="function",
                        file_path=file_path,
                        line_start=idx,
                        line_end=idx,
                        signature=clean,
                    )
                )
                continue

            # Class method: async login(...) or login(...)
            m_method = re.search(r"^(?:async\s+)?([A-Za-z0-9_]+)\s*\([^)]*\)\s*\{?", clean)
            if m_method and m_method.group(1) not in ("if", "for", "while", "switch", "catch", "function", "constructor"):
                symbols.append(
                    ExtractedSymbol(
                        name=m_method.group(1),
                        symbol_type="method",
                        file_path=file_path,
                        line_start=idx,
                        line_end=idx,
                        signature=clean,
                    )
                )

        return symbols

    def _extract_java_symbols(self, file_path: str, content: str) -> List[ExtractedSymbol]:
        """Extract Java classes, interfaces, and methods."""
        symbols: List[ExtractedSymbol] = []
        lines = content.splitlines()

        for idx, line in enumerate(lines, start=1):
            clean = line.strip()

            # Class / Interface
            m_cls = re.search(r"(?:public|protected|private)?\s*(?:static\s+)?(?:class|interface|enum)\s+([A-Za-z0-9_]+)", clean)
            if m_cls and not clean.startswith("//"):
                symbols.append(
                    ExtractedSymbol(
                        name=m_cls.group(1),
                        symbol_type="class",
                        file_path=file_path,
                        line_start=idx,
                        line_end=idx,
                        signature=clean,
                    )
                )
                continue

            # Method: public void myMethod(...)
            m_method = re.search(r"(?:public|protected|private|static|\s)+[\w<>\[\]]+\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{?", clean)
            if m_method and not clean.startswith("//") and not clean.startswith("class ") and "if " not in clean:
                symbols.append(
                    ExtractedSymbol(
                        name=m_method.group(1),
                        symbol_type="method",
                        file_path=file_path,
                        line_start=idx,
                        line_end=idx,
                        signature=clean,
                    )
                )

        return symbols

    def _extract_c_cpp_symbols(self, file_path: str, content: str) -> List[ExtractedSymbol]:
        """Extract C/C++ structs, classes, and function declarations."""
        symbols: List[ExtractedSymbol] = []
        lines = content.splitlines()

        for idx, line in enumerate(lines, start=1):
            clean = line.strip()

            m_cls = re.search(r"^(?:struct|class)\s+([A-Za-z0-9_]+)", clean)
            if m_cls and not clean.startswith("//"):
                symbols.append(
                    ExtractedSymbol(
                        name=m_cls.group(1),
                        symbol_type="class",
                        file_path=file_path,
                        line_start=idx,
                        line_end=idx,
                        signature=clean,
                    )
                )
                continue

            # C/C++ function: int calculate(int a, int b) {
            m_fn = re.search(r"^[A-Za-z0-9_&*]+\s+([A-Za-z0-9_]+)\s*\([^;)]*\)\s*\{?", clean)
            if m_fn and not clean.startswith("//") and "if " not in clean and "while " not in clean:
                symbols.append(
                    ExtractedSymbol(
                        name=m_fn.group(1),
                        symbol_type="function",
                        file_path=file_path,
                        line_start=idx,
                        line_end=idx,
                        signature=clean,
                    )
                )

        return symbols
