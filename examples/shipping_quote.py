def shipping_quote(units: int, weight: int, priority: bool) -> int:
    merchandise = units * 120
    shipping = weight * 15
    handling = units + 2
    packed = shipping + handling
    insured = merchandise + 30
    standard = merchandise + packed
    express = insured + packed
    fee = 25 if priority else 5
    quoted = express if priority else standard
    total = quoted + fee
    return total
