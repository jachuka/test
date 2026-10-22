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
                    poly = normalize(poly)
                    if not any(poly.equals(old) for old in result):
                        result.append(poly)
    if not result:
        raise ValueError('Brak poprawnych, zamkniętych obrysów na pierwszej stronie PDF. Eksportuj zamkniętą krzywą bez tekstu lub wybierz skan.')
    return sorted(result, key=lambda p: -p.area)


def read_scan(path, threshold=180):
    """Zewnętrzne ciemne sylwetki na jasnym tle; skala wymaga kalibracji."""
    import cv2
    import numpy as np
    if str(path).lower().endswith('.pdf'):
        with fitz.open(path) as doc:
            if not len(doc):
                raise ValueError('PDF nie zawiera stron.')
            page = doc[0]
            factor = min(2, 4000 / max(page.rect.width, page.rect.height))
            pix = page.get_pixmap(matrix=fitz.Matrix(factor, factor), colorspace=fitz.csGRAY, alpha=False)
            image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    else:
        image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError('Nie można odczytać obrazu.')
        if max(image.shape) > 4000:
            image = cv2.resize(image, None, fx=4000 / max(image.shape), fy=4000 / max(image.shape))
    _, binary = cv2.threshold(image, threshold, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    result = []
    for contour in contours:
        if cv2.contourArea(contour) < 25:
            continue
        contour = cv2.approxPolyDP(contour, 0.5, True)
        points = contour.reshape(-1, 2)
        if len(points) >= 3:
            poly = Polygon(points)
            if poly.is_valid and poly.area > 0:
                result.append(normalize(poly))
    if not result:
        raise ValueError('Nie znaleziono obrysu. Użyj ciemnej sylwetki lub wyraźnego zamkniętego obrysu na białym tle.')
    return sorted(result, key=lambda p: -p.area)[:100]


@dataclass
class NestResult:
    shapes: list
    width: float
    height: float
    gap: float
    margin: float
    limited: bool = False


def nest(poly, width, height, gap, margin, rotate=True, seconds=15, cancel=None, limit=1000):
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
                        if margin - 1e-7 <= tx <= width - margin - vw + 1e-7 and margin - 1e-7 <= ty <= height - margin - vh + 1e-7:
                            candidates.add((round(max(margin, tx), 6), round(max(margin, ty), 6)))
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
                if any(candidate.intersection(result.shapes[i]).area > 1e-9 or candidate.distance(result.shapes[i]) < clearance - 1e-7 for i in indices):
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
