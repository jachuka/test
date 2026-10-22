"""Lokalne wykrywanie zamkniętych obrysów i opcjonalny OCR Tesseract."""
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import csv
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import numpy as np
import pymupdf as fitz
from shapely.ops import unary_union
from shapely.geometry import Polygon
from irregular import trace_silhouettes


@dataclass
class Detection:
    contours: list
    mask: object
    png: bytes


def monochrome(png):
    pix = fitz.Pixmap(png)
    if pix.colorspace != fitz.csRGB:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
    # Odrzuć jasną niebieską kratkę oraz kolorowe pieczątki; zachowaj ciemny tusz.
    return (rgb.max(axis=2) < 205) & (np.ptp(rgb, axis=2) < 75)


def close_gaps(mask):
    h,w=mask.shape
    padded=np.pad(mask,1)
    dilated=np.logical_or.reduce([padded[y:y+h,x:x+w] for y in range(3) for x in range(3)])
    padded=np.pad(dilated,1,constant_values=True)
    return np.logical_and.reduce([padded[y:y+h,x:x+w] for y in range(3) for x in range(3)])


def enclosed_regions(dark):
    """Białe pola zamknięte tuszem, etykietowane przebiegami wierszy."""
    parents=[]
    segments=[]
    previous=[]
    def find(i):
        while parents[i]!=i:
            parents[i]=parents[parents[i]]
            i=parents[i]
        return i
    def union(i,j):
        i,j=find(i),find(j)
        if i!=j:
            parents[j]=i
    for y,row in enumerate(~dark):
        changes=np.flatnonzero(np.diff(np.r_[False,row,False].astype(np.int8)))
        current=[]
        j=0
        for left,right in zip(changes[::2].tolist(),changes[1::2].tolist()):
            k=len(parents)
            parents.append(k)
            current.append((left,right,k))
            segments.append((y,left,right,k))
            while j<len(previous) and previous[j][1]<=left:
                j+=1
            m=j
            while m<len(previous) and previous[m][0]<right:
                union(k,previous[m][2]);m+=1
        previous=current
    groups=defaultdict(list)
    areas=defaultdict(int)
    outside=set()
    for y,left,right,k in segments:
        root=find(k)
        groups[root].append((y,left,right))
        areas[root]+=right-left
        if y in (0,dark.shape[0]-1) or left==0 or right==dark.shape[1]:
            outside.add(root)
    minimum=max(300,dark.size*.001)
    roots=sorted((root for root in groups if root not in outside and areas[root]>=minimum),key=lambda root:-areas[root])[:16]
    result=[]
    for root in roots:
        image=np.full(dark.shape,255,np.uint8)
        for y,left,right in groups[root]:
            image[y,left:right]=0
        result.extend(trace_silhouettes(image,normalize_result=False))
    return result


def detect_contours(png):
    mask=monochrome(png)
    regions=enclosed_regions(close_gaps(mask))
    if not regions:
        raise ValueError('Nie wykryto zamkniętego obrysu. Wykadruj szkic, popraw przerwy w obrysie albo zaznacz narożniki ręcznie.')
    # Linia wymiarowa może rozdzielić wnętrze formatki. Scal sąsiednie pola
    # oddzielone tylko cienką kreską; wynik zawsze wymaga obejrzenia.
    parent=list(range(len(regions)))
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    for i,a in enumerate(regions):
        for j,b in enumerate(regions[:i]):
            if a.distance(b)<=5:
                parent[find(i)]=find(j)
    grouped=defaultdict(list)
    for i,poly in enumerate(regions):
        grouped[find(i)].append(poly)
    contours=[]
    for pieces in grouped.values():
        if len(pieces)>1:
            merged=unary_union([p.buffer(3,join_style='mitre') for p in pieces]).buffer(-3,join_style='mitre')
        else:
            merged=pieces[0]
        polys=list(merged.geoms) if merged.geom_type=='MultiPolygon' else [merged]
        for p in polys:
            if p.geom_type!='Polygon':
                continue
            p=p.simplify(4,preserve_topology=True)
            # Wyprostowanie odręcznych prawie poziomych i pionowych boków.
            # Są to relacje topologiczne, nie rzeczywiste wymiary w mm.
            points=list(p.exterior.coords)[:-1]
            for axis in (0,1):
                coordinates=sorted(set(point[axis] for point in points))
                clusters=[]
                for value in coordinates:
                    if clusters and value-clusters[-1][0]<=6:
                        clusters[-1].append(value)
                    else:
                        clusters.append([value])
                mapping={v:sum(cluster)/len(cluster) for cluster in clusters for v in cluster}
                points=[tuple(mapping[v] if index==axis else v for index,v in enumerate(point)) for point in points]
            changed=True
            while changed and len(points)>3:
                changed=False
                for i,b in enumerate(points):
                    a,c=points[i-1],points[(i+1)%len(points)]
                    cross=(b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])
                    if abs(cross)<.01:
                        points.pop(i);changed=True;break
            outline=Polygon(points)
            if outline.is_valid and outline.area>0 and 3<=len(points)<=500:
                contours.append(points)
    if not contours:
        raise ValueError('Nie udało się uzyskać poprawnego konturu. Wybierz narożniki ręcznie.')
    contours.sort(key=lambda points:-Polygon(points).area)
    return Detection(contours,mask,png)


def topology(points):
    """Zera osi boków i wyrównanie współrzędnych; żadnych długości ze skali zdjęcia."""
    edges=[]
    extra=[]
    for i,(x,y) in enumerate(points):
        xx,yy=points[(i+1)%len(points)]
        edges.append(dict(dx=0 if abs(x-xx)<.01 else '',dy=0 if abs(y-yy)<.01 else ''))
    for axis,name in enumerate(('x','y')):
        first={}
        for i,p in enumerate(points):
            key=round(p[axis],3)
            if key in first:
                extra.append(dict(start=first[key],end=i,axis=name,value=0))
            else:
                first[key]=i
    return edges,extra


def find_tesseract():
    candidates=[]
    if getattr(sys,'frozen',False):
        candidates.append(Path(sys._MEIPASS)/'tesseract'/'tesseract.exe')
    existing=shutil.which('tesseract')
    if existing:
        candidates.append(Path(existing))
    for key in ('ProgramFiles','ProgramFiles(x86)','LOCALAPPDATA'):
        base=os.environ.get(key)
        if base:
            candidates.append(Path(base)/'Tesseract-OCR'/'tesseract.exe')
            candidates.append(Path(base)/'Programs'/'Tesseract-OCR'/'tesseract.exe')
    return next((p for p in candidates if p.is_file()),None)


@dataclass
class OCRWord:
    value: float
    confidence: float
    bounds: tuple


def inspect_tesseract(executable):
    report=dict(available=bool(executable),executable=str(executable) if executable else '',version='',languages=[],errors=[],attempts=0,successful=0,words=0,status='not_installed')
    if not executable:
        return report
    environment=os.environ.copy()
    tessdata=Path(executable).parent/'tessdata'
    if tessdata.is_dir():
        environment['TESSDATA_PREFIX']=str(tessdata)
    for option in ('--version','--list-langs'):
        try:
            process=subprocess.run([str(executable),option],capture_output=True,timeout=10,env=environment,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except (OSError,subprocess.TimeoutExpired) as exc:
            report['status']='launch_failure'
            report['errors'].append(str(exc)[:1500])
            return report
        stdout=process.stdout.decode('utf-8',errors='replace')
        stderr=process.stderr.decode('utf-8',errors='replace')
        if process.returncode!=0:
            report['status']='launch_failure'
            report['errors'].append(f'{option}: kod {process.returncode}. '+(stderr or stdout)[:1500])
            return report
        if option=='--version':
            report['version']=(stdout or stderr).splitlines()[0] if (stdout or stderr).splitlines() else 'brak informacji'
        else:
            report['languages']=[line.strip() for line in stdout.splitlines() if line.strip() and not line.startswith('List of available languages')]
    if 'eng' not in report['languages']:
        report['status']='missing_eng'
        report['errors'].append('Brak danych języka angielskiego eng.traineddata. Doinstaluj język eng w Tesseract.')
    else:
        report['status']='ready'
    return report


def format_ocr_report(report):
    states={'not_installed':'Nie znaleziono Tesseract. Wykrywanie obrysu działa, ale OCR cyfr nie został uruchomiony.',
            'launch_failure':'Nie udało się uruchomić Tesseract. Sprawdź błąd poniżej.',
            'missing_eng':'Tesseract jest dostępny, ale brakuje modelu języka eng.',
            'ready':'Tesseract jest gotowy do odczytu.',
            'run_failure':'Próby odczytu zakończyły się błędem.',
            'no_digits':'OCR wykonał odczyt, ale nie rozpoznał cyfr z wymaganą oceną.',
            'read':'OCR rozpoznał cyfry. Ich dopasowanie do wymiarów to oddzielny etap.',
            'partial':'Część prób OCR zakończyła się błędem.'}
    lines=[states.get(report.get('status'),'Nie wykonano jeszcze odczytu OCR.'),
           'Silnik: '+(report.get('executable') or 'brak'),
           'Wersja: '+(report.get('version') or 'nieustalona'),
           'Języki: '+(', '.join(report.get('languages',[])) or 'nieustalone'),
           f"Próby: {report.get('attempts',0)}; udane: {report.get('successful',0)}; liczby: {report.get('words',0)}"]
    lines.extend(report.get('errors',[]))
    if report.get('numbers'):
        lines.append('Odczytane liczby (ocena OCR, nie prawdopodobieństwo poprawności):')
        lines.extend(f"{value:g} — {confidence:.1f}" for value,confidence in report['numbers'])
    if 'matched' in report:
        lines.append(f"Dopasowane wymiary: {report['matched']}; niepewne dopasowania: {report['uncertain']}")
    return '\n'.join(lines)


def ocr_numbers(mask, executable, diagnostics=None):
    if diagnostics is not None:
        diagnostics.clear()
        diagnostics.update(inspect_tesseract(executable))
        if diagnostics['status']!='ready':
            return []
    elif executable is None:
        return []
    words=[]
    h,w=mask.shape
    with tempfile.TemporaryDirectory(prefix='formatki-ocr-') as folder:
        for rotation in range(4):
            image=np.rot90((~mask).astype(np.uint8)*255,rotation).copy()
            path=Path(folder)/'page.png'
            fitz.Pixmap(fitz.csGRAY,image.shape[1],image.shape[0],image.tobytes(),False).save(path)
            environment=os.environ.copy()
            tessdata=Path(executable).parent/'tessdata'
            if tessdata.is_dir():
                environment['TESSDATA_PREFIX']=str(tessdata)
            if diagnostics is not None:
                diagnostics['attempts']+=1
            try:
                process=subprocess.run([str(executable),str(path),'stdout','--psm','11','-l','eng','tsv'],capture_output=True,timeout=20,env=environment,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except (OSError,subprocess.TimeoutExpired) as exc:
                if diagnostics is not None:
                    diagnostics['errors'].append(f'Obrót {rotation*90}°: '+str(exc)[:1500])
                continue
            if process.returncode!=0:
                if diagnostics is not None:
                    diagnostics['errors'].append(f'Obrót {rotation*90}°: kod {process.returncode}. '+process.stderr.decode('utf-8',errors='replace')[:1500])
                continue
            if diagnostics is not None:
                diagnostics['successful']+=1
            for row in csv.DictReader(io.StringIO(process.stdout.decode('utf-8',errors='replace')),delimiter='\t'):
                text=row.get('text','').strip()
                if not re.fullmatch(r'\d{1,5}(?:[.,]\d{1,3})?',text):
                    continue
                try:
                    confidence=float(row['conf'])
                    value=float(text.replace(',','.'))
                    x,y,bw,bh=(int(row[k]) for k in ('left','top','width','height'))
                except (ValueError,KeyError):
                    continue
                if value<=0 or confidence<40:
                    continue
                corners=[(x,y),(x+bw,y+bh)]
                def original(px,py):
                    if rotation==0:return px,py
                    if rotation==1:return w-py,px
                    if rotation==2:return w-px,h-py
                    return py,h-px
                corners=[original(*p) for p in corners]
                bounds=(min(p[0] for p in corners),min(p[1] for p in corners),max(p[0] for p in corners),max(p[1] for p in corners))
                words.append(OCRWord(value,confidence,bounds))
    if diagnostics is not None:
        diagnostics['words']=len(words)
        diagnostics['numbers']=[(word.value,word.confidence) for word in words]
        diagnostics['status']='partial' if diagnostics['errors'] else ('read' if words else 'no_digits')
        if diagnostics['successful']==0:
            diagnostics['status']='run_failure'
    return words


def straight_lines(mask):
    result=[]
    for axis in ('x','y'):
        rows=mask if axis=='x' else mask.T
        for pos,row in enumerate(rows):
            indices=np.flatnonzero(row)
            if len(indices)<30:
                continue
            groups=np.split(indices,np.flatnonzero(np.diff(indices)>4)+1)
            for group in groups:
                if group[-1]-group[0]>=35:
                    result.append((axis,float(pos),float(group[0]),float(group[-1])))
    return result


def match_dimensions(points,mask,words):
    """Wiąż cyfry tylko z linią o końcach odpowiadających poziomom narożników."""
    lines=straight_lines(mask)
    proposals=defaultdict(list)
    for word in words:
        bx0,by0,bx1,by1=word.bounds
        cx,cy=(bx0+bx1)/2,(by0+by1)/2
        candidates=[]
        for axis,pos,start,end in lines:
            along,across=(cx,cy) if axis=='x' else (cy,cx)
            size=(by1-by0) if axis=='x' else (bx1-bx0)
            span=end-start
            if abs(across-pos)>max(35,2*size) or abs(along-(start+end)/2)>max(15,span*.12):
                continue
            index=0 if axis=='x' else 1
            ends=[]
            for target in (start,end):
                close=[(i,p) for i,p in enumerate(points) if abs(p[index]-target)<=10]
                if not close:
                    break
                i,p=min(close,key=lambda item:abs(item[1][1-index]-pos))
                ends.append(i)
            if len(ends)!=2 or ends[0]==ends[1]:
                continue
            # Dwie interpretacje tej samej projekcji są równoważne, gdy
            # końce leżą na tych samych poziomach współrzędnych konturu.
            key=(axis,round(points[ends[0]][index],2),round(points[ends[1]][index],2))
            score=abs(across-pos)+abs(along-(start+end)/2)
            candidates.append((score,key,ends))
        if not candidates:
            continue
        candidates.sort(key=lambda item:item[0])
        best=candidates[0]
        competing=next((item for item in candidates if item[1]!=best[1]),None)
        certain=word.confidence>=85 and (competing is None or competing[0]-best[0]>15)
        proposals[best[1]].append((word,best[2],certain))
    accepted=[]
    questions=[]
    for key,items in proposals.items():
        values={item[0].value for item in items}
        best=max(items,key=lambda item:item[0].confidence)
        word,ends,certain=best
        item=dict(start=ends[0],end=ends[1],axis=key[0],value=word.value)
        if certain and len(values)==1:
            accepted.append(item)
        else:
            questions.append(dict(**item,candidates=sorted(values),confidence=word.confidence))
    return accepted,questions


def missing_dimension(points,edges,extra):
    """Proponuj tylko relację łączącą nierozwiązane grupy współrzędnych."""
    from sketch import number
    candidates=[]
    for axis,index in (('x',0),('y',1)):
        parent=list(range(len(points)))
        def find(i):
            while parent[i]!=i:
                parent[i]=parent[parent[i]];i=parent[i]
            return i
        def join(i,j):
            parent[find(i)]=find(j)
        for i,edge in enumerate(edges):
            if number(edge.get('d'+axis),'Wymiar') is not None:
                join(i,(i+1)%len(points))
        for item in extra:
            if item['axis']==axis:
                join(item['start'],item['end'])
        for i,a in enumerate(points):
            for j,b in enumerate(points[:i]):
                if find(i)!=find(j):
                    start,end=(j,i) if a[index]>=b[index] else (i,j)
                    candidates.append((abs(a[index]-b[index]),dict(start=start,end=end,axis=axis)))
    return max(candidates,key=lambda item:item[0])[1] if candidates else None


def known_dimension(edges,extra,item):
    """Zwróć już określoną różnicę, aby nie pytać o wymiar wynikający z innych."""
    from sketch import number
    axis=item['axis']
    graph=[[] for _ in edges]
    def add(a,b,value):
        graph[a].append((b,value));graph[b].append((a,-value))
    for i,edge in enumerate(edges):
        value=number(edge.get('d'+axis),'Wymiar')
        if value is not None:
            add(i,(i+1)%len(edges),value)
    for relation in extra:
        if relation['axis']==axis:
            add(relation['start'],relation['end'],relation['value'])
    stack=[item['start']]
    values={item['start']:0}
    while stack:
        start=stack.pop()
        for end,delta in graph[start]:
            if end not in values:
                values[end]=values[start]+delta;stack.append(end)
    return values.get(item['end'])
