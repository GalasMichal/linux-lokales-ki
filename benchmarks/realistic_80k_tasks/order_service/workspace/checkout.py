class Checkout:
    TAX_BP = 1900

    def __init__(self, cart) -> None:
        self.cart = cart
        self._member: dict[str, int] = {}

    def total(self, discount_bp: int = 0) -> int:
        # BUG: tax before discount
        sub = self.cart.subtotal()
        taxed = sub + (sub * self.TAX_BP) // 10000
        return taxed - (sub * discount_bp) // 10000

    def apply_member_price(self, sku: str, member_price: int) -> None:
        # BUG: mutates shared catalog
        self.cart.catalog._prices[sku] = member_price
