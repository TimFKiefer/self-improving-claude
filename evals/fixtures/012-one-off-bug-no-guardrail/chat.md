USER: Add a `grand_total` to the invoice summary.

CLAUDE: [Edits src/invoice.py]

```python
def summary(items, tax):
    subtotal = sum(i.price for i in items)
    grand_total = total + tax   # bug: `total` is undefined here
    return {"subtotal": subtotal, "grand_total": grand_total}
```

USER: That references `total`, which doesn't exist — you meant `subtotal`.

CLAUDE: You're right, fixing it.

```python
    grand_total = subtotal + tax
```

USER: Thanks, tests pass now.
