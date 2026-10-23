"""Kontur wielokąta z wymiarów; współrzędne kliknięć nie są wymiarami."""
from dataclasses import dataclass, field
from math import isfinite, hypot, sqrt, atan2, pi, asin, cos, sin, ceil, radians
from collections import deque
from shapely.geometry import Polygon
from shapely import affinity


@dataclass(frozen=True)
class DimensionedShape:
    polygon: object
    dimensions: dict
    vertices: list
    segments: list = field(default_factory=list)


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


def arc_geometry(start, end, arc, tolerance=0.05):
    """Łuk z jawnego promienia mm i kąta sweep +/-90|180 (Y rośnie w dół).

    Dodatni sweep jest zgodny z ruchem wskazówek zegara. Alternatywnie
    clockwise: bool wraz z opcjonalnym dodatnim sweep określa kierunek.
    Końce są punktami styczności. Piksele nie określają rozmiaru łuku.
    """
    if not isinstance(arc, dict):
        raise ValueError('Nieprawidłowe dane łuku.')
    radius=number(arc.get('radius'),'Promień łuku')
    if radius is None:
        raise ValueError('Uzupełnij promień łuku w mm.')
    if radius<=0:
        raise ValueError('Promień łuku musi być dodatni.')
    declared=number(arc.get('sweep'),'Kąt łuku')
    clockwise=arc.get('clockwise')
    if clockwise is None:
        if declared is None or abs(declared) not in (90,180):
            raise ValueError('Potwierdź kierunek i kąt łuku: +/-90° lub +/-180°.')
        clockwise=declared>0
    elif type(clockwise) is not bool:
        raise ValueError('Potwierdź kierunek łuku (clockwise).')
    elif declared is not None and declared<0 and clockwise:
        raise ValueError('Sprzeczny kierunek i kąt łuku.')
    if not isfinite(tolerance) or tolerance<=0:
        raise ValueError('Tolerancja łuku musi być dodatnia i skończona.')
    x,y=start;xx,yy=end
    chord=hypot(xx-x,yy-y)
    if not isfinite(chord) or chord<=0:
        raise ValueError('Łuk musi mieć różne, skończone punkty końcowe.')
    epsilon=max(1e-9,radius*1e-9)
    if chord>2*radius+epsilon:
        raise ValueError('Promień łuku jest za mały dla odległości między jego końcami.')
    ratio=min(1.0,chord/(2*radius))
    angle=2*asin(ratio)
    if declared is not None:
        if abs(declared) not in (90,180):
            raise ValueError('Obsługiwany kąt łuku to +/-90° albo +/-180°.')
        expected=2*radius*sin(radians(abs(declared))/2)
        if abs(chord-expected)>epsilon:
            raise ValueError('Promień i kąt łuku nie zgadzają się z jego punktami końcowymi.')
    sign=1 if clockwise else -1
    height=radius*sqrt(max(0.0,1-ratio*ratio))
    center=((x+xx)/2-sign*(yy-y)/chord*height,(y+yy)/2+sign*(xx-x)/chord*height)
    theta=atan2(y-center[1],x-center[0])
    max_step=min(pi/2,4*asin(sqrt(min(1.0,tolerance/radius/2))))
    if max_step==0 or angle/max_step>100000:
        raise ValueError('Łuk jest zbyt duży dla wymaganej tolerancji 0,05 mm.')
    steps=max(1,ceil(angle/max_step))
    fractions={i/steps for i in range(steps+1)}
    for cardinal in (0,pi/2,pi,3*pi/2):
        delta=((cardinal-theta)*sign)%(2*pi)
        if 0<delta<angle:
            fractions.add(delta/angle)
    points=[(center[0]+radius*cos(theta+sign*angle*t),center[1]+radius*sin(theta+sign*angle*t)) for t in sorted(fractions)]
    points[0],points[-1]=start,end
    midpoint=(center[0]+radius*cos(theta+sign*angle/2),center[1]+radius*sin(theta+sign*angle/2))
    return dict(kind='arc',start=start,end=end,radius=radius,clockwise=clockwise,
                sweep=sign*angle*180/pi,center=center,midpoint=midpoint,
                length=radius*angle,points=points,path=points)


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
    outline=[]
    segments=[]
    for i,edge in enumerate(edges):
        start,end=vertices[i],vertices[(i+1)%n]
        if edge.get('arc') is not None:
            segment=arc_geometry(start,end,edge['arc'])
        else:
            segment=dict(kind='line',start=start,end=end,
                         midpoint=((start[0]+end[0])/2,(start[1]+end[1])/2),
                         length=hypot(end[0]-start[0],end[1]-start[1]),points=[start,end],path=[start,end])
        segments.append(segment)
        outline.extend(segment['points'][:-1])
    poly = Polygon(outline)
    if not poly.is_valid or poly.area <= 0:
        raise ValueError('Kontur przecina sam siebie albo ma zerowe pole. Sprawdź kolejność narożników i wymiary.')
    x, y, right, bottom = poly.bounds
    normalized = affinity.translate(poly, -x, -y)
    for segment in segments:
        for name in ('start','end','midpoint','center'):
            if name in segment:
                px,py=segment[name]
                segment[name]=(px-x,py-y)
        segment['points']=[(px-x,py-y) for px,py in segment['points']]
        segment['path']=segment['points']
    return DimensionedShape(normalized, {'width': right-x, 'height': bottom-y}, [(px-x, py-y) for px, py in vertices], segments)


def preview_png(path, rotation=0):
    """Wyłącznie podgląd; wymiary renderu nie wpływają na geometrię."""
    import pymupdf as fitz
    with fitz.open(path) as doc:
        if not len(doc):
            raise ValueError('Plik nie zawiera stron.')
        page = doc[0]
        scale = min(1.5, 1400 / max(page.rect.width, page.rect.height))
        return page.get_pixmap(matrix=fitz.Matrix(scale, scale).prerotate(rotation), alpha=False).tobytes('png')
