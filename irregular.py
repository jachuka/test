"""Import obrysów i heurystyczne układanie wielokątów w milimetrach."""
from dataclasses import dataclass
from math import isfinite
from time import monotonic
import pymupdf as fitz
from shapely import affinity
from shapely.geometry import Polygon, box
from shapely.strtree import STRtree

MM = 25.4 / 72
TOLERANCE = 0.05  # maksymalne odchylenie aproksymacji krzywych w mm


def normalize(poly):
    x, y, _, _ = poly.bounds
    return affinity.translate(poly, -x, -y)


def bezier(points, tolerance=TOLERANCE / MM, depth=0):
    """Adaptacyjne spłaszczanie krzywej Béziera, z kontrolą odległości od cięciwy."""
    a, b, c, d = points
    from shapely.geometry import LineString, Point
    line = LineString([a, d])
    if depth >= 18 or max(line.distance(Point(b)), line.distance(Point(c))) <= tolerance:
        return [a, d]
    def mid(p, q):
        return ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    ab, bc, cd = mid(a, b), mid(b, c), mid(c, d)
    abc, bcd = mid(ab, bc), mid(bc, cd)
    m = mid(abc, bcd)
    return bezier([a, ab, abc, m], tolerance, depth + 1)[:-1] + bezier([m, bcd, cd, d], tolerance, depth + 1)


def read_vector_pdf(path):
    """Zwraca niezależne zamknięte obrysy pierwszej strony. Otwory są pomijane."""
    result = []
    with fitz.open(path) as doc:
        if not len(doc):
            raise ValueError('PDF nie zawiera stron.')
        page = doc[0]
        # Rysunki PDF są w układzie strony sprzed obrotu. Obiekty poza
        # CropBox mogą istnieć w pliku, mimo że czytnik ich nie wyświetla.
        visible = page.rect * page.derotation_matrix
        visible_area = box(visible.x0 * MM, visible.y0 * MM, visible.x1 * MM, visible.y1 * MM).buffer(0.001)
        if page.get_images() and not page.get_drawings():
            raise ValueError('PDF zawiera obraz. Wybierz import ze skanu.')
        drawings = page.get_drawings()
        if len(drawings) > 10000:
            raise ValueError('PDF zawiera zbyt wiele ścieżek. Wyeksportuj sam obrys formatki.')
        for drawing in drawings:
            chains = []
            chain = []
            def flush():
                nonlocal chain
                if len(chain) >= 3 and (chain[0] == chain[-1] or drawing.get('closePath')):
                    chains.append(chain)
                chain = []
            for item in drawing['items']:
                kind = item[0]
                if kind == 're':
                    flush()
                    r = item[1]
                    chains.append([(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)])
                elif kind == 'qu':
                    flush()
                    q = item[1]
                    chains.append([tuple(q.ul), tuple(q.ur), tuple(q.lr), tuple(q.ll)])
                elif kind in ('l', 'c'):
                    points = [tuple(p) for p in item[1:]]
                    segment = points if kind == 'l' else bezier(points)
                    if chain and chain[-1] != segment[0]:
                        flush()
                    chain.extend(segment if not chain else segment[1:])
                    if len(chain) >= 4 and chain[0] == chain[-1]:
                        chains.append(chain)
                        chain = []
                else:
                    flush()
            flush()
            for points in chains:
                poly = Polygon([(x * MM, y * MM) for x, y in points])
                if poly.is_valid and poly.area > 0.01:
                    if not visible_area.covers(poly):
                        continue
                    poly = normalize(poly)
                    if not any(poly.equals(old) for old in result):
                        result.append(poly)
    if not result:
        raise ValueError('Brak poprawnych, zamkniętych obrysów na pierwszej stronie PDF. Eksportuj zamkniętą krzywą bez tekstu lub wybierz skan.')
    return sorted(result, key=lambda p: -p.area)


def trace_silhouettes(image, threshold=180, normalize_result=True):
    """Śledzenie krawędzi ciemnych pikseli bez OpenCV i dodatkowych DLL."""
    import numpy as np
    if not 1 <= threshold <= 254:
        raise ValueError('Próg musi być z zakresu 1–254.')
    dark = image <= threshold
    padded = np.pad(dark, 1)
    sides = [dark & ~padded[:-2, 1:-1], dark & ~padded[1:-1, 2:],
             dark & ~padded[2:, 1:-1], dark & ~padded[1:-1, :-2]]
    if sum(int(side.sum()) for side in sides) > 200000:
        raise ValueError('Skan zawiera zbyt wiele krawędzi. Usuń szum lub wykadruj formatkę.')
    edges = {}
    for side, mask in enumerate(sides):
        ys, xs = np.nonzero(mask)
        for x, y in zip(xs.tolist(), ys.tolist()):
            start, end = (((x, y), (x + 1, y)), ((x + 1, y), (x + 1, y + 1)),
                          ((x + 1, y + 1), (x, y + 1)), ((x, y + 1), (x, y)))[side]
            edges.setdefault(start, set()).add(end)
    result = []
    directions = {(1, 0): 0, (0, 1): 1, (-1, 0): 2, (0, -1): 3}
    while edges:
        start = next(iter(edges))
        current = start
        ring = [start]
        previous_direction = None
        while True:
            choices = edges.get(current)
            if not choices:
                break
            def priority(point):
                direction = directions[(point[0] - current[0], point[1] - current[1])]
                if previous_direction is None:
                    return direction
                turn = (direction - previous_direction) % 4
                return {1: 0, 0: 1, 3: 2, 2: 3}[turn]
            end = min(choices, key=priority)
            choices.remove(end)
            if not choices:
                del edges[current]
            previous_direction = directions[(end[0] - current[0], end[1] - current[1])]
            ring.append(end)
            current = end
            if current == start:
                break
        if len(ring) < 4 or ring[-1] != start:
            continue
        # Współrzędna Y rośnie w dół: dodatnie pole to zewnętrzny obrys.
        signed_area = sum(x * yy - xx * y for (x, y), (xx, yy) in zip(ring, ring[1:])) / 2
        if signed_area < 25:
            continue
        poly = Polygon(ring)
        if poly.is_valid:
            poly = poly.simplify(0.5, preserve_topology=True)
            result.append(normalize(poly) if normalize_result else poly)
    return sorted(result, key=lambda p: -p.area)[:100]


def read_scan(path, threshold=180):
    """PyMuPDF odczytuje PDF oraz obrazy; skala wymaga kalibracji."""
    import numpy as np
    if str(path).lower().endswith('.pdf'):
        with fitz.open(path) as doc:
            if not len(doc):
                raise ValueError('Plik nie zawiera stron.')
            page = doc[0]
            factor = min(2, 3000 / max(page.rect.width, page.rect.height))
            pix = page.get_pixmap(matrix=fitz.Matrix(factor, factor), colorspace=fitz.csGRAY, alpha=False)
    else:
        pix = fitz.Pixmap(str(path))
        while max(pix.width, pix.height) > 3000:
            pix.shrink(1)
        if pix.alpha:
            # Przezroczyste tło obrazu zastępujemy białym, nie czarnym.
            rgba = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            colors = rgba[:, :, :-1].astype(np.uint16)
            alpha = rgba[:, :, -1:].astype(np.uint16)
            colors = (colors + 255 - alpha).clip(0, 255).astype(np.uint8)
            pix = fitz.Pixmap(pix.colorspace, pix.width, pix.height, colors.tobytes(), False)
        if pix.colorspace != fitz.csGRAY:
            pix = fitz.Pixmap(fitz.csGRAY, pix)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    result = trace_silhouettes(image, threshold)
    if not result:
        raise ValueError('Nie znaleziono obrysu. Użyj ciemnej sylwetki lub wyraźnego zamkniętego obrysu na białym tle.')
    return result


@dataclass
class NestResult:
    shapes: list
    width: float
    height: float
    gap: float
    margin: float
    limited: bool = False


def _greedy_nest(poly, width, height, gap, margin, rotate=True, seconds=15, cancel=None, limit=1000):
    if not all(isfinite(v) for v in (width, height, gap, margin)) or min(width, height) <= 0 or min(gap, margin) < 0:
        raise ValueError('Podaj dodatnie wymiary oraz nieujemny odstęp i margines.')
    if not poly.is_valid or poly.is_empty or poly.area <= 0:
        raise ValueError('Nieprawidłowy obrys.')
    result = NestResult([], width, height, gap, margin)
    if min(width, height) <= 2 * margin:
        return result
    sheet = box(margin, margin, width - margin, height - margin)
    variants = [normalize(affinity.rotate(poly, a, origin=(0, 0))) for a in ((0, 90, 180, 270) if rotate else (0,))]
    variants = [p for p in variants if p.bounds[2] <= width - 2 * margin and p.bounds[3] <= height - 2 * margin]
    end = monotonic() + seconds
    obstacles = []
    # Rzeczywiste krzywe są aproksymowane; niewielki zapas do testów kolizji.
    clearance = gap + 2 * TOLERANCE
    while variants and len(result.shapes) < limit:
        tree = STRtree(result.shapes)
        best = None
        for variant in variants:
            points = list(variant.simplify(0.2, preserve_topology=True).exterior.coords)[:-1]
            points = points[::max(1, (len(points) + 31) // 32)]
            vw, vh = variant.bounds[2:]
            candidates = {(margin, margin)}
            for obstacle in obstacles:
                if monotonic() > end or (cancel and cancel.is_set()):
                    result.limited = True
                    return result
                vertices = list(obstacle.simplify(0.2, preserve_topology=True).exterior.coords)[:-1]
                vertices = vertices[::max(1, (len(vertices) + 47) // 48)]
                for x, y in vertices:
                    for px, py in points:
                        tx, ty = x - px, y - py
                        fits_x = margin - 1e-7 <= tx <= width - margin - vw + 1e-7
                        fits_y = margin - 1e-7 <= ty <= height - margin - vh + 1e-7
                        if fits_x and fits_y:
                            candidates.add((round(max(margin, tx), 6), round(max(margin, ty), 6)))
                        # Dopasowanie wcięcia przy krawędzi arkusza nie wymaga
                        # jednoczesnego wyrównania obu współrzędnych wierzchołków.
                        if fits_x:
                            candidates.add((round(max(margin, tx), 6), margin))
                        if fits_y:
                            candidates.add((margin, round(max(margin, ty), 6)))
                _, _, right, bottom = obstacle.bounds
                candidates.add((right, margin))
                candidates.add((margin, bottom))
            for x, y in sorted(candidates, key=lambda p: (p[1], p[0])):
                if monotonic() > end or (cancel and cancel.is_set()):
                    result.limited = True
                    return result
                candidate = affinity.translate(variant, x, y)
                if not sheet.covers(candidate):
                    continue
                indices = tree.query(candidate.buffer(clearance))
                if any(candidate.intersection(result.shapes[i]).area > 1e-9 or candidate.distance(result.shapes[i]) < clearance - 1e-6 for i in indices):
                    continue
                score = (candidate.bounds[3], candidate.bounds[2], y, x)
                if best is None or score < best[0]:
                    best = score, candidate
                break
        if best is None:
            return result
        result.shapes.append(best[1])
        obstacles.append(best[1].buffer(clearance, join_style='mitre'))
    result.limited = len(result.shapes) >= limit
    return result


def nest(poly, width, height, gap, margin, rotate=True, seconds=15, cancel=None, limit=1000):
    """Najpierw pełny układ bazowy, potem powtarzalne grupy dopasowanych obrysów."""
    from packing import calculate
    if not all(isfinite(v) for v in (width, height, gap, margin, seconds)) or min(width, height) <= 0 or min(gap, margin, seconds) < 0:
        raise ValueError('Podaj dodatnie wymiary oraz nieujemny odstęp, margines i czas.')
    if not poly.is_valid or poly.is_empty or poly.area <= 0:
        raise ValueError('Nieprawidłowy obrys.')
    result = NestResult([], width, height, gap, margin)
    if cancel and cancel.is_set():
        result.limited = True
        return result
    if min(width, height) <= 2 * margin:
        return result
    poly = normalize(poly)
    clearance = gap + 2 * TOLERANCE
    end = monotonic() + seconds

    def repeat_group(group):
        from shapely.ops import unary_union
        bounds = unary_union(group).bounds
        gw, gh = bounds[2] - bounds[0], bounds[3] - bounds[1]
        # Kalkulator prostokątów nie tworzy tu ogromnej listy pojedynczych formatek.
        try:
            layout = calculate(width, height, gw, gh, clearance, margin, rotate)
        except ValueError:
            # Bardzo drobne elementy: wystarczy pierwsze limit pozycji regularnej siatki.
            from math import floor
            from itertools import islice
            cols = max(0, floor((width - 2 * margin + clearance) / (gw + clearance)))
            rows = max(0, floor((height - 2 * margin + clearance) / (gh + clearance)))
            rectangles = list(islice(((margin + col * (gw + clearance), margin + row * (gh + clearance), gw, gh)
                          for row in range(min(rows, limit)) for col in range(min(cols, limit))), limit))
        else:
            rectangles = layout.rectangles
        count = min(limit, len(rectangles) * len(group))
        if count <= len(result.shapes):
            return
        straight = [affinity.translate(p, -bounds[0], -bounds[1]) for p in group]
        turned = [affinity.rotate(p, 90, origin=(0, 0)) for p in straight]
        turned = [affinity.translate(p, gh, 0) for p in turned]
        shapes = []
        for x, y, rw, rh in rectangles:
            oriented = straight if abs(rw - gw) < 1e-6 and abs(rh - gh) < 1e-6 else turned
            for p in oriented:
                shapes.append(affinity.translate(p, x, y))
                if len(shapes) >= limit:
                    break
            if len(shapes) >= limit:
                break
        result.shapes = shapes

    # Pełny wynik powstaje przed kosztowną optymalizacją.
    repeat_group([poly])
    if len(result.shapes) >= limit:
        result.limited = True
        return result
    pw, ph = poly.bounds[2:]
    # Niewielkie grupy znajdują dopasowanie wcięć bez ponawiania kosztownego
    # wyszukiwania osobno dla każdej kopii na całym arkuszu.
    sizes = [(2 * pw + clearance, ph), (pw, 2 * ph + clearance),
             (pw + ph + clearance, max(pw, ph)),
             (2 * pw + clearance, 2 * ph + clearance),
             (3 * pw + 2 * clearance, 2 * ph + clearance),
             (2 * pw + clearance, 3 * ph + 2 * clearance)]
    for index, (tw, th) in enumerate(sizes):
        remaining = end - monotonic()
        if remaining <= 0 or (cancel and cancel.is_set()):
            result.limited = True
            return result
        tw, th = min(tw, width - 2 * margin), min(th, height - 2 * margin)
        local = _greedy_nest(poly, tw, th, gap, 0, rotate,
                             seconds=remaining / (len(sizes) - index), cancel=cancel, limit=12)
        # Każdy prefiks może stanowić bardziej wydajny moduł niż cała grupa.
        for count in range(2, len(local.shapes) + 1):
            if cancel and cancel.is_set():
                result.limited = True
                return result
            repeat_group(local.shapes[:count])
        if local.limited:
            result.limited = True
    if len(result.shapes) >= limit:
        result.limited = True
    return result


def export_pdf(path, result):
    if not result.shapes:
        raise ValueError('Nie ma formatek do eksportu.')
    # PDF do 14 400 punktów na bok jest szeroko obsługiwany przez czytniki.
    if max(result.width, result.height) / MM > 14400:
        raise ValueError('Eksport PDF 1:1 obsługuje arkusze do 5080 mm na bok.')
    import os
    import tempfile
    from pathlib import Path
    target = Path(path)
    fd, temporary = tempfile.mkstemp(suffix='.pdf', dir=target.parent)
    os.close(fd)
    try:
        with fitz.open() as doc:
            page = doc.new_page(width=result.width / MM, height=result.height / MM)
            drawing = page.new_shape()
            for poly in result.shapes:
                drawing.draw_polyline([(x / MM, y / MM) for x, y in poly.exterior.coords])
                drawing.finish(color=(0, 0, 0), width=0.1 / MM, closePath=True)
            drawing.commit()
            doc.set_metadata({'title': 'Rozmieszczenie formatek 1:1', 'subject': f'{len(result.shapes)} formatek; odstep {result.gap:g} mm; margines {result.margin:g} mm'})
            doc.save(temporary, deflate=True)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
