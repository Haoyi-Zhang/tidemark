def coefficient(x1: int, x2: int, x3: int, x4: int, y1: int, y2: int, y3: int, y4: int, which: int) -> int:
    dx = x1
    cx = (x2 - dx) * 3
    bx = (x3 - x2) * 3 - cx
    ax = x4 - dx - cx - bx
    dy = y1
    cy = (y2 - dy) * 3
    by = (y3 - y2) * 3 - cy
    ay = y4 - dy - cy - by
    value = ax if which < 1 else bx if which < 2 else cx if which < 3 else dx if which < 4 else ay if which < 5 else by if which < 6 else cy if which < 7 else dy
    return value
