from catalog import Catalog
from cart import Cart


def test_unknown_sku_raises() -> None:
    cat = Catalog({"a": 1})
    cart = Cart(cat)
    raised = False
    try:
        cart.add("missing", 1)
    except ValueError:
        raised = True
    assert raised


def test_qty_must_be_positive() -> None:
    cat = Catalog({"a": 1})
    cart = Cart(cat)
    raised = False
    try:
        cart.add("a", 0)
    except ValueError:
        raised = True
    assert raised


def test_price_lookup_still_works() -> None:
    cat = Catalog({"x": 5})
    assert cat.price("x") == 5
