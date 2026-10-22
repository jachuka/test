"""Budowanie konturów wyłącznie z jawnie podanych wymiarów, bez skali skanu."""
from dataclasses import dataclass
from math import isfinite
from shapely.geometry import Polygon, box


@dataclass(frozen=True)
class DimensionedShape:
    polygon: object
    kind: str
    dimensions: dict


def number(value, label):
    if value is None or str(value).strip() == '':
        return None
    try:
        result = float(str(value).strip().replace(',', '.'))
    except ValueError:
        raise ValueError(f'{label}: wpisz liczbę w mm.') from None
    if not isfinite(result) or result <= 0:
        raise ValueError(f'{label}: wymiar musi być dodatnią, skończoną liczbą.')
    return result


LABELS = {'width': 'Szerokość zewnętrzna', 'height': 'Wysokość zewnętrzna',
          'top': 'Grubość poprzeczki', 'left': 'Szerokość lewego ramienia',
          'right': 'Szerokość prawego ramienia', 'inner_width': 'Szerokość wycięcia',
          'inner_height': 'Głębokość wycięcia'}


def build_shape(kind, inputs):
    if kind not in ('U', 'L', 'Prostokąt'):
        raise ValueError('Wybierz obsługiwany typ konturu: U, L lub Prostokąt.')
    keys = ['width', 'height']
    if kind in ('U', 'L'):
        keys += ['top', 'left', 'inner_width', 'inner_height']
    if kind == 'U':
        keys += ['right']
    dims = {key: number(inputs.get(key), LABELS[key]) for key in keys}
    # Relacje wymiarowe pozwalają obliczyć brakujący wymiar, ale nigdy
    # nie uzupełniają go na podstawie proporcji odręcznego obrazka.
    equations = []
    if kind in ('U', 'L'):
        equations = [dict(width=1, left=-1, inner_width=-1),
                     dict(height=1, top=-1, inner_height=-1)]
        if kind == 'U':
            equations[0]['right'] = -1
    changed = True
    while changed:
        changed = False
        for equation in equations:
            missing = [key for key in equation if dims[key] is None]
            if len(missing) == 1:
                key = missing[0]
                value = -sum(dims[k] * coefficient for k, coefficient in equation.items() if k != key) / equation[key]
                if value <= 0:
                    raise ValueError(f'Sprzeczne wymiary: {LABELS[key]} wynika jako {value:g} mm.')
                dims[key] = value
                changed = True
            elif not missing:
                total = sum(dims[k] * coefficient for k, coefficient in equation.items())
                if abs(total) > 0.001:
                    names = ', '.join(LABELS[k].lower() for k in equation)
                    raise ValueError(f'Sprzeczne wymiary: {names}. Różnica wynosi {abs(total):g} mm.')
    missing = [LABELS[key] for key in keys if dims[key] is None]
    if missing:
        raise ValueError('Brak wystarczających wymiarów: ' + ', '.join(missing) + '. Uzupełnij dane; program nie odczytuje proporcji ze szkicu.')
    w, h = dims['width'], dims['height']
    if kind == 'Prostokąt':
        poly = box(0, 0, w, h)
    else:
        t, l = dims['top'], dims['left']
        if kind == 'U':
            r = dims['right']
            poly = Polygon([(0, 0), (w, 0), (w, h), (w-r, h), (w-r, t), (l, t), (l, h), (0, h)])
        else:
            poly = Polygon([(0, 0), (w, 0), (w, t), (l, t), (l, h), (0, h)])
    if not poly.is_valid or poly.area <= 0:
        raise ValueError('Wymiary nie tworzą poprawnego, zamkniętego konturu.')
    return DimensionedShape(poly, kind, dims)


def preview_png(path, rotation=0):
    """Wyłącznie podgląd; wymiary renderu nie wpływają na geometrię."""
    import pymupdf as fitz
    with fitz.open(path) as doc:
        if not len(doc):
            raise ValueError('Plik nie zawiera stron.')
        page = doc[0]
        scale = min(1.5, 1400 / max(page.rect.width, page.rect.height))
        return page.get_pixmap(matrix=fitz.Matrix(scale, scale).prerotate(rotation), alpha=False).tobytes('png')
