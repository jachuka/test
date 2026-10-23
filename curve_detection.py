"""Ostrożne propozycje łuków z pikselowego obrysu, bez pomiarów w mm.

Dopasowanie okręgu służy tylko do rozpoznania przebiegu kreski. Promień
rzeczywisty musi zostać podany/potwierdzony osobno z wymiarów rysunku.
"""
from math import atan2, degrees, hypot
import numpy as np


def _sample(path, step=2):
    """Próbkuj równomiernie, aby gęstość wierzchołków nie ważyła dopasowania."""
    result=[]
    for a,b in zip(path,path[1:]):
        length=hypot(b[0]-a[0],b[1]-a[1])
        count=max(1,int(length/step))
        result.extend((a[0]+(b[0]-a[0])*i/count,a[1]+(b[1]-a[1])*i/count) for i in range(count))
    result.append(path[-1])
    return np.asarray(result,dtype=float)


def _arc_candidate(path, diagonal):
    # Zwykły narożnik lub faza z trzech punktów nie jest dowodem łuku.
    if len(path)<6:
        return None
    sample=_sample(path)
    origin=sample.mean(axis=0)
    local=sample-origin
    matrix=np.column_stack((2*local[:,0],2*local[:,1],np.ones(len(local))))
    solution,_,rank,_=np.linalg.lstsq(matrix,np.sum(local*local,axis=1),rcond=None)
    if rank<3:
        return None
    center=solution[:2]+origin
    squared=solution[2]+np.sum(solution[:2]**2)
    if squared<=0:
        return None
    radius=float(np.sqrt(squared))
    if radius<5 or radius>diagonal*.22:
        return None
    residual=np.abs(np.linalg.norm(sample-center,axis=1)-radius)
    tolerance=2.5
    if residual.max()>tolerance:
        return None
    angles=np.unwrap(np.arctan2(sample[:,1]-center[1],sample[:,0]-center[0]))
    sweep=degrees(float(angles[-1]-angles[0]))
    target=min((90,180),key=lambda value:abs(abs(sweep)-value))
    if abs(abs(sweep)-target)>(28 if target==180 else 18):
        return None
    variation=degrees(float(np.abs(np.diff(angles)).sum()))
    if variation>abs(sweep)*1.25+10:
        return None
    # Wymagaj rzeczywistego rozłożonego zakrzywienia, nie pojedynczego zgięcia.
    turns=[]
    for a,b,c in zip(path,path[1:],path[2:]):
        u=np.asarray(b)-a;v=np.asarray(c)-b
        if min(np.linalg.norm(u),np.linalg.norm(v))<1:
            continue
        turns.append(abs(degrees(atan2(float(u[0]*v[1]-u[1]*v[0]),float(np.dot(u,v))))))
    if sum(t>8 for t in turns)<3:
        return None
    dx,dy=path[-1][0]-path[0][0],path[-1][1]-path[0][1]
    if target==180 and min(abs(dx),abs(dy))>max(abs(dx),abs(dy))*.2:
        return None
    if target==90 and min(abs(dx),abs(dy))<max(abs(dx),abs(dy))*.35:
        return None
    # Zapis sweep używa osi obrazka (Y w dół): dodatni = zgodnie z zegarem.
    return dict(sweep=target if sweep>0 else -target,score=abs(sweep)/(1+float(residual.mean())))


def suggest_arcs(points):
    """Zwróć (punkty końcowe, propozycje_boków) w układzie obrazu.

    Każda propozycja ma radius=None, signed sweep 90/180 i source_path.
    To propozycje do sprawdzenia, nie potwierdzone cechy geometrii.
    Niejednoznaczne kreski i krótkie fazy pozostają odcinkami. Funkcja
    nie obiecuje wykrycia wszystkich łuków i nigdy nie podaje promienia mm.
    """
    points=[tuple(map(float,p)) for p in points]
    if len(points)>1 and points[0]==points[-1]:
        points.pop()
    n=len(points)
    if n<6:
        return points,{}
    if not np.isfinite(np.asarray(points)).all():
        raise ValueError('Współrzędne obrysu muszą być skończone.')
    xs,ys=zip(*points)
    diagonal=hypot(max(xs)-min(xs),max(ys)-min(ys))
    candidates=[]
    for start in range(n):
        # Ograniczenie pracy oraz wykluczenie całego zamkniętego obrysu.
        for count in range(6,min(n-1,24)+1):
            indices=[(start+i)%n for i in range(count)]
            path=[points[i] for i in indices]
            candidate=_arc_candidate(path,diagonal)
            if candidate:
                candidates.append((candidate['score'],start,indices,path,candidate['sweep']))
    chosen=[];used=set()
    for _,start,indices,path,sweep in sorted(candidates,reverse=True,key=lambda item:item[0]):
        # Wspólne końce łuków są dozwolone, wspólne boki nie.
        edges=set(indices[:-1])
        if edges&used:
            continue
        chosen.append((start,indices,path,sweep));used.update(edges)
    if not chosen:
        return points,{}
    by_start={start:(indices,path,sweep) for start,indices,path,sweep in chosen}
    # Początek wybranego łuku zapewnia, że żaden łuk nie przechodzi przez szew.
    origin=chosen[0][0]
    result=[];specs={};current=origin;traversed=0
    while traversed<n:
        if current in by_start:
            result.append(points[current])
            indices,path,sweep=by_start[current]
            specs[len(result)-1]=dict(radius=None,sweep=sweep,source_path=list(path))
            advance=len(indices)-1
        else:
            # Uprość tylko otwarty przebieg między łukami. Ich końce pozostają
            # chronione i nie wolno zgubić przypisania promienia do boku.
            from shapely.geometry import LineString
            advance=1
            while advance<n-traversed and (current+advance)%n not in by_start:
                advance+=1
            path=[points[(current+i)%n] for i in range(advance+1)]
            reduced=list(LineString(path).simplify(4,preserve_topology=False).coords)
            result.extend(tuple(p) for p in reduced[:-1])
        current=(current+advance)%n;traversed+=advance
    # Wyprostuj tylko długie, niemal osiowe odcinki; krótkie fazy pozostają.
    # To relacje kierunków, a nie pomiar rzeczywistych odległości.
    result=[list(p) for p in result]
    for i,a in enumerate(result):
        if i in specs:
            continue
        b=result[(i+1)%len(result)]
        dx,dy=abs(b[0]-a[0]),abs(b[1]-a[1])
        if dx<=3 and dy>=20:
            a[0]=b[0]=(a[0]+b[0])/2
        if dy<=3 and dx>=20:
            a[1]=b[1]=(a[1]+b[1])/2
    return [tuple(p) for p in result],specs
