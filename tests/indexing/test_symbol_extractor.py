"""Unit tests for AST and regex code symbol extraction."""

from pathlib import Path
import pytest

from codeagent.indexing.symbol_extractor import CodeSymbol, SymbolExtractor


def test_python_ast_extraction() -> None:
    """Verify AST extraction of classes, methods, functions, docstrings, and signatures."""
    code = '''"""Sample module docstring."""

class UserService:
    """Service handling user accounts."""

    def __init__(self, db_conn):
        self.db = db_conn

    def get_user_by_id(self, user_id: int) -> dict:
        """Fetch user by primary key."""
        return {"id": user_id}


def calculate_tax(amount: float, rate: float = 0.05) -> float:
    """Compute tax on given amount."""
    return amount * rate
'''
    extractor = SymbolExtractor()
    symbols = extractor.extract_from_code(code=code, file_path="services/user.py", language="python")

    assert len(symbols) >= 4

    names = {s.name: s for s in symbols}
    assert "UserService" in names
    assert names["UserService"].symbol_type == "class"
    assert "Service handling user accounts." in names["UserService"].docstring

    assert "get_user_by_id" in names
    assert names["get_user_by_id"].symbol_type == "method"
    assert names["get_user_by_id"].parent_symbol == "UserService"
    assert "user_id: int" in names["get_user_by_id"].signature

    assert "calculate_tax" in names
    assert names["calculate_tax"].symbol_type == "function"
    assert names["calculate_tax"].parent_symbol is None


def test_syntax_error_fallback() -> None:
    """Verify malformed Python code falls back to regex parser gracefully."""
    malformed_code = """
def broken_syntax(
    print("missing closing paren"
"""
    extractor = SymbolExtractor()
    symbols = extractor.extract_from_code(code=malformed_code, file_path="broken.py", language="python")
    # Regex fallback should detect broken_syntax function definition
    assert any(s.name == "broken_syntax" for s in symbols)


def test_javascript_symbol_extraction() -> None:
    """Verify JS/TS regex symbol extraction."""
    js_code = """
export class AuthManager {
    constructor() {}
    async login(username, password) {
        return true;
    }
}

export function validateToken(token) {
    return token.length > 0;
}

const formatUser = (user) => {
    return user.name;
};
"""
    extractor = SymbolExtractor()
    symbols = extractor.extract_from_code(code=js_code, file_path="src/auth.js", language="javascript")

    names = {s.name for s in symbols}
    assert "AuthManager" in names
    assert "login" in names
    assert "validateToken" in names

