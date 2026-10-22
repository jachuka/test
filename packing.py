"""Rozmieszczanie jednakowych prostokątów, wszystkie wymiary w mm."""
from dataclasses import dataclass
from math import floor, isfinite


@dataclass(frozen=True)
class Layout:
    rectangles: list[tuple[float, float, float, float]]
    description: str


def calculate(width, height, part_width, part_height, gap, margin, rotate=True):
    values = (width, height, part_width, part_height, gap, margin)
    if not all(isfinite(v) for v in values):
        raise ValueError("Wprowadź skończone liczby.")
    if min(values[:4]) <= 0 or min(gap, margin) < 0:
        raise ValueError("Wymiary muszą być dodatnie, a odstęp i margines nieujemne.")
    usable_w, usable_h = width - 2 * margin, height - 2 * margin
    if usable_w <= 0 or usable_h <= 0:
        return Layout([], "Margines zajmuje cały arkusz")

    def count(length, size):
        return max(0, floor((length + gap) / (size + gap) + 1e-10))

    # Porównujemy pasy poziome i pionowe, z dwiema orientacjami.
    best = (0, None)
    for transpose in (False, True):
        w, h = (usable_h, usable_w) if transpose else (usable_w, usable_h)
        a, b = (part_height, part_width) if transpose else (part_width, part_height)
        n1, n2 = count(w, a), count(w, b)
        max_rows = count(h, b)
        if max_rows > 200000:
            raise ValueError("Zbyt duża liczba rzędów. Zwiększ rozmiar formatki.")
        for rows1 in range(max_rows + 1):
            used = rows1 * (b + gap)
            rows2 = count(h - used, a) if rotate else 0
            total = rows1 * n1 + rows2 * n2
            if total > best[0]:
                best = total, (transpose, a, b, n1, n2, rows1, rows2)
    if best[1] is None:
        return Layout([], "Formatka nie mieści się na arkuszu")
    if best[0] > 50000:
        raise ValueError("Wynik przekracza limit podglądu 50 000 formatek.")
    transpose, a, b, n1, n2, rows1, rows2 = best[1]
    rectangles = []
    y = 0
    for rows, cols, pw, ph in ((rows1, n1, a, b), (rows2, n2, b, a)):
        for _ in range(rows):
            for col in range(cols):
                x = col * (pw + gap)
                rect = (y, x, ph, pw) if transpose else (x, y, pw, ph)
                rectangles.append((rect[0] + margin, rect[1] + margin, rect[2], rect[3]))
            y += ph + gap
    return Layout(rectangles, "Najlepszy znaleziony układ pasowy")
