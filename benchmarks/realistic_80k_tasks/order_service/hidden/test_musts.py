import ast
import inspect
from pathlib import Path

from catalog import Catalog
from cart import Cart
from checkout import Checkout


FORBIDDEN = {"requests", "httpx", "numpy", "pandas", "docker"}


def test_signatures_kept() -> None:
    assert list(inspect.signature(Catalog.price).parameters) == ["self", "sku"]
    assert list(inspect.signature(Cart.add).parameters) == ["self", "sku", "qty"]


def test_no_third_party_imports() -> None:
    root = Path(__file__).resolve().parents[1] / "workspace"
    if not (root / "catalog.py").is_file():
        root = Path.cwd()
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                assert name not in FORBIDDEN, f"{path.name} imports {name}"


def test_member_price_this_cart_only() -> None:
    cat = Catalog({"a": 100})
    cart = Cart(cat)
    cart.add("a", 1)
    checkout = Checkout(cart)
    checkout.apply_member_price("a", 50)
    assert checkout.total() == 59
    later = Cart(cat)
    later.add("a", 1)
    assert later.subtotal() == 100
