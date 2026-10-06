from catalog import Catalog
from cart import Cart
from checkout import Checkout


def test_subtotal_uses_full_qty() -> None:
    cat = Catalog({"bread": 100})
    cart = Cart(cat)
    cart.add("bread", 2)
    assert cart.subtotal() == 200


def test_total_applies_discount_before_tax() -> None:
    cat = Catalog({"bread": 10000})
    cart = Cart(cat)
    cart.add("bread", 1)
    checkout = Checkout(cart)
    assert checkout.total(discount_bp=1000) == 10710
