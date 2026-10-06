from catalog import Catalog


class Cart:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self._lines: list[tuple[str, int]] = []

    def add(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        self.catalog.price(sku)
        self._lines.append((sku, qty))

    def lines(self) -> list[tuple[str, int]]:
        return list(self._lines)

    def subtotal(self) -> int:
        # BUG: drops one unit per line
        return sum(self.catalog.price(sku) * (qty - 1) for sku, qty in self._lines)
