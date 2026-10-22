"""Kontur wielokąta z wymiarów; współrzędne kliknięć nie są wymiarami."""
from dataclasses import dataclass
from math import isfinite
from collections import deque
from shapely.geometry import Polygon
from shapely import affinity


@dataclass(frozen=True)
class DimensionedShape:
    polygon: object
    dimensions: dict
    vertices: list


def number(value, label):
    if value is None or str(value).strip() == '':
        return None
    try:
        result = float(str(value).strip().replace(',', '.'))
    except ValueError:
        raise ValueError(f'{label}: wpisz liczbę w mm.') from None
    if not isfinite(result):
        raise ValueError(f'{label}: wpisz skończoną liczbę.')
    return result


def build_contour(edges, dimensions=()):
    """Każdy bok: {dx, dy}, puste oznacza nieznane; ostatni wraca do P1.

    Dodatkowe wymiary: {start, end, axis, value}; indeksy punktów od zera,
    wartość podpisana w osi X (prawo +) lub Y (dół +).
    Rozwiązujemy grafy różnic, bez skalowania obrazu i uśredniania konfliktów.
    """
    n = len(edges)
    if n < 3 or n > 500:
        raise ValueError('Kontur wymaga od 3 do 500 narożników.')
    graphs = {'x': [[] for _ in edges], 'y': [[] for _ in edges]}
    def relation(start, end, axis, value):
        if type(start) is not int or type(end) is not int or not (0 <= start < n and 0 <= end < n) or axis not in graphs:
            raise ValueError('Nieprawidłowe punkty lub oś wymiaru.')
        if value is None:
            raise ValueError('Uzupełnij wartość dodatkowego wymiaru.')
        graphs[axis][start].append((end, value))
        graphs[axis][end].append((start, -value))
    for i, edge in enumerate(edges):
        for axis in ('x', 'y'):
            value = number(edge.get('d' + axis), f'Bok P{i+1} → P{(i+1)%n+1}, Δ{axis.upper()}')
            if value is not None:
                relation(i, (i + 1) % n, axis, value)
    for item in dimensions:
        relation(item.get('start'), item.get('end'), item.get('axis'), number(item.get('value'), 'Wymiar dodatkowy'))
    coords = {}
    missing = []
    for axis, graph in graphs.items():
        values = {0: 0.0}
        queue = deque([0])
        while queue:
            start = queue.popleft()
            for end, delta in graph[start]:
                proposal = values[start] + delta
                if not isfinite(proposal):
                    raise ValueError('Wymiary są zbyt duże.')
                if end in values:
                    if abs(values[end] - proposal) > 0.001:
                        raise ValueError(f'Sprzeczne wymiary w osi {axis.upper()} przy P{end+1}; różnica {abs(values[end]-proposal):g} mm. Sprawdź także znaki i zamknięcie konturu.')
                else:
                    values[end] = proposal
                    queue.append(end)
        missing.extend(f'P{i+1}: {axis.upper()}' for i in range(n) if i not in values)
        coords[axis] = values
    if missing:
        raise ValueError('Brakuje wymiarów określających: ' + ', '.join(missing[:20]) + (', …' if len(missing)>20 else '') + '. Uzupełnij boki lub dodaj wymiar między punktami. Program nie mierzy szkicu.')
    vertices = [(coords['x'][i], coords['y'][i]) for i in range(n)]
    if len(set(vertices)) != n:
        raise ValueError('Co najmniej dwa narożniki mają te same współrzędne. Popraw wymiary.')
    poly = Polygon(vertices)
    if not poly.is_valid or poly.area <= 0:
        raise ValueError('Kontur przecina sam siebie albo ma zerowe pole. Sprawdź kolejność narożników i wymiary.')
    x, y, right, bottom = poly.bounds
    normalized = affinity.translate(poly, -x, -y)
    return DimensionedShape(normalized, {'width': right-x, 'height': bottom-y}, [(px-x, py-y) for px, py in vertices])


def preview_png(path, rotation=0):
    """Wyłącznie podgląd; wymiary renderu nie wpływają na geometrię."""
    import pymupdf as fitz
    with fitz.open(path) as doc:
        if not len(doc):
            raise ValueError('Plik nie zawiera stron.')
        page = doc[0]
        scale = min(1.5, 1400 / max(page.rect.width, page.rect.height))
        return page.get_pixmap(matrix=fitz.Matrix(scale, scale).prerotate(rotation), alpha=False).tobytes('png')
