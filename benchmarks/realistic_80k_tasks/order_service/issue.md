# Issue: checkout totals are wrong

The shop checkout is broken. Customers are billed the wrong amount.

Work only in this directory:
{workspace}

## Visible tests (must pass)

```
python3 -m pytest -q test_visible.py
```

Those tests currently fail. Fix the code so they pass.

## MUST requirements (do not drop these)

1. Keep the public signatures `Catalog.price(sku)` and `Cart.add(sku, qty)`.
2. Unknown SKU and non-positive qty must still raise `ValueError`.
3. Tax is 19% (1900 basis points) and is applied **after** the discount.
4. `Checkout.apply_member_price` must not change catalog prices for later carts.
5. Do not add third-party packages. Stdlib only.

Do not edit files outside this directory. Stop when the visible tests pass and the MUST items still hold.
