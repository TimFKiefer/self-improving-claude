def summary(items, tax):
    subtotal = sum(i.price for i in items)
    grand_total = subtotal + tax
    return {"subtotal": subtotal, "grand_total": grand_total}
