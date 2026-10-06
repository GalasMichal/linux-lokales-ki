class Catalog:
    def __init__(self, prices: dict[str, int]) -> None:
        self._prices = dict(prices)

    def price(self, sku: str) -> int:
        if sku not in self._prices:
            raise ValueError(f"unknown sku {sku}")
        return self._prices[sku]

    def skus(self) -> list[str]:
        return list(self._prices)
