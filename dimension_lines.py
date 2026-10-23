"""Podział łańcuchów wymiarowych na odcinki w układzie pikseli szkicu.

Współrzędne służą do skojarzenia linii z punktami. Nie określają długości
ani skali w mm. Odcinek dzielimy tylko przy widocznej kresce pomocniczej
lub znaczniku, a nie w każdym miejscu odpowiadającym poziomowi narożnika.
"""
from math import isfinite
import numpy as np


def _levels(points,index):
    clusters=[]
    for value in sorted({float(p[index]) for p in points if isfinite(p[index])}):
        if clusters and value-clusters[-1][0]<=4:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [sum(group)/len(group) for group in clusters]


def _tick(view,position,target):
    """Kreska poprzeczna połączona z linią, dłuższa niż jej grubość."""
    position,target=round(position),round(target)
    if not (0<=position<view.shape[0] and 0<=target<view.shape[1]):
        return False
    left,right=max(0,target-1),min(view.shape[1],target+2)
    for sign in (-1,1):
        ink=[]
        for distance in range(1,24):
            row=position+sign*distance
            ink.append(bool(view[row,left:right].any()) if 0<=row<view.shape[0] else False)
        # Wymagaj połączenia z linią, aby nie brać osobnego napisu obok niej.
        connected=all(any(ink[i:i+2]) for i in range(11))
        if connected and sum(ink[:4])>=3 and sum(ink[4:])>=12:
            return True
    return False


def dimension_spans(mask,points,lines):
    """Zwróć (axis,pos,start,end), rozcinając widoczne łańcuchy wymiarowe.

    Oś x oznacza poziomą linię w wierszu pos, y pionową w kolumnie pos.
    Cięcia wymagają poziomu punktu konturu (tolerancja 10 px) oraz śladu
    poprzecznej kreski. Pełny nierozdzielony wymiar na osobnej linii zostaje.
    """
    if np.ndim(mask)!=2:
        raise ValueError('Maska szkicu musi być dwuwymiarowa.')
    lines=list(lines)
    levels={'x':_levels(points,0),'y':_levels(points,1)}
    result=[]
    for axis,pos,start,end in lines:
        if axis not in levels or not all(isfinite(v) for v in (pos,start,end)) or end<=start:
            continue
        eligible=[level for level in levels[axis] if start+14<level<end-14]
        if not eligible:
            result.append((axis,pos,start,end));continue
        candidates=[]
        # Długie linie pomocnicze mogą kończyć się tuż obok linii wymiarowej.
        for other_axis,along,left,right in lines:
            if other_axis==axis or not (start+14<along<end-14):
                continue
            if not any(abs(along-level)<=10 for level in eligible):
                continue
            if left-3<=pos<=right+3 and max(pos-left,right-pos)>=16:
                candidates.append(float(along))
        # Krótkie kreski / znaczniki często nie trafiają do listy długich linii.
        view=mask if axis=='x' else mask.T
        for level in eligible:
            for target in range(max(round(start+15),round(level)-8),min(round(end-14),round(level)+9)):
                if _tick(view,pos,target):
                    candidates.append(float(target))
        grouped=[]
        for value in sorted(set(candidates)):
            if grouped and value-grouped[-1][-1]<=3:
                grouped[-1].append(value)
            else:
                grouped.append([value])
        cuts=[float(np.median(group)) for group in grouped]
        # Nie wytwarzaj bardzo krótkich odcinków z grubości kreski/grotu.
        boundaries=[float(start)]
        for cut in cuts:
            if cut-boundaries[-1]>=14 and end-cut>=14:
                boundaries.append(cut)
        boundaries.append(float(end))
        result.extend((axis,pos,a,b) for a,b in zip(boundaries,boundaries[1:]))
    return list(dict.fromkeys(result))
