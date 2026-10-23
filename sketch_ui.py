"""Edytor dowolnego konturu wielokątnego ze szkicu, wyłącznie lokalny."""
import queue
import threading
from math import isfinite, hypot
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from sketch import build_contour, preview_png
from curve_detection import suggest_arcs
from zoom_preview import ZoomPreview, OverlayZoomPreview, bounded_scale, photo_from_png
from irregular import NestResult, export_pdf
from preferences import save_tesseract
from auto_sketch import detect_contours, topology, find_tesseract, ocr_numbers, match_dimensions, missing_dimension, known_dimension, format_ocr_report, question_crop, monochrome


class DimensionQuestion(simpledialog.Dialog):
    def __init__(self,parent,title,prompt,png=None,initial=None):
        self.prompt=prompt
        self.png=png
        self.initial=initial
        self.owner=parent.winfo_toplevel()
        super().__init__(self.owner,title)

    def body(self,master):
        master.pack(fill='both',expand=True)
        ttk.Label(master,text=self.prompt,wraplength=450).pack(anchor='w',pady=5)
        if self.png:
            self.preview=ZoomPreview(master,self.png)
            self.preview.pack(fill='both',expand=True,pady=8)
            ttk.Label(master,text='Niebieska linia wskazuje pytany wymiar.',wraplength=450).pack(anchor='w')
        ttk.Label(master,text='Wartość w milimetrach:').pack(anchor='w',pady=(8,2))
        self.entry=ttk.Entry(master)
        if self.initial is not None:
            self.entry.insert(0,f'{self.initial:g}')
        self.entry.pack(fill='x')
        return self.entry

    def wait_visibility(self,window=None):
        super().wait_visibility(window)
        self._bring_to_front()

    def _bring_to_front(self):
        if self.winfo_exists():
            self.lift(self.owner)
            self.focus_force()
            self.entry.focus_set()

    def validate(self):
        from sketch import number
        try:
            value=number(self.entry.get(),'Wymiar')
            if value is None or value<0:
                raise ValueError('Wpisz nieujemny wymiar w mm.')
        except ValueError as exc:
            messagebox.showerror('Wymiar',str(exc),parent=self)
            return False
        self.result=value
        return True


class ArcQuestion(simpledialog.Dialog):
    """Promień pochodzi z odpowiedzi, nigdy ze skali źródłowego obrazka."""
    options=(('Odcinek prosty',None),('Łuk 90° — zgodnie z ruchem wskazówek',90),
             ('Łuk 90° — przeciwnie do wskazówek',-90),
             ('Półokrąg — zgodnie z ruchem wskazówek',180),
             ('Półokrąg — przeciwnie do wskazówek',-180))

    def __init__(self,parent,count,selected=0,spec=None,png=None,on_select=None,locked=False):
        self.count,self.selected,self.spec,self.png=count,selected,spec or {},png
        self.on_select,self.locked=on_select,locked
        super().__init__(parent.winfo_toplevel(),'Sprawdź łuk i podaj promień')

    def body(self,panel):
        panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='Wybierz bok między oznaczonymi punktami szkicu.',wraplength=450).pack(anchor='w')
        self.edge=ttk.Combobox(panel,state='readonly',values=[f'P{i+1} → P{(i+1)%self.count+1}' for i in range(self.count)])
        self.edge.current(self.selected)
        self.edge.pack(fill='x',pady=5)
        if self.locked:
            self.edge.configure(state='disabled')
        self.preview=None
        if self.png:
            self.preview=ZoomPreview(panel,self.png,height=190)
            self.preview.pack(fill='both',expand=True,pady=6)
        ttk.Label(panel,text='Rodzaj boku (patrząc od pierwszego punktu do drugiego):',wraplength=450).pack(anchor='w')
        self.kind=ttk.Combobox(panel,state='readonly',values=[label for label,_ in self.options],width=48)
        self.kind.current(next((i for i,(_,sweep) in enumerate(self.options) if sweep==self.spec.get('sweep')),0))
        self.kind.pack(fill='x',pady=5)
        ttk.Label(panel,text='Promień R [mm] — przepisz ze szkicu:').pack(anchor='w')
        self.radius=ttk.Entry(panel)
        if self.spec.get('radius') is not None:
            self.radius.insert(0,f"{self.spec['radius']:g}")
        self.radius.pack(fill='x',pady=5)
        self.derive=tk.BooleanVar(value=True)
        ttk.Checkbutton(panel,text='Końce ćwiartki/półokręgu zgodne z osiami X/Y',variable=self.derive).pack(anchor='w')
        ttk.Label(panel,text='Ta opcja wyznacza różnice X/Y z podanego promienia. Wyłącz ją, jeśli końce łuku wymagają osobnych wymiarów. Kierunek łuku i promień wymagają sprawdzenia.',wraplength=450).pack(anchor='w')
        self.edge.bind('<<ComboboxSelected>>',self.edge_changed)
        return self.radius

    def edge_changed(self,event=None):
        if self.on_select is None:
            return
        spec,png=self.on_select(self.edge.current())
        self.kind.current(next((i for i,(_,sweep) in enumerate(self.options) if sweep==spec.get('sweep')),0))
        self.radius.delete(0,'end')
        if spec.get('radius') is not None:
            self.radius.insert(0,f"{spec['radius']:g}")
        if png:
            if self.preview is not None:
                self.preview.set_image(png)

    def wait_visibility(self,window=None):
        super().wait_visibility(window)
        self.lift();self.focus_force();self.radius.focus_set()

    def validate(self):
        from sketch import number
        sweep=self.options[self.kind.current()][1]
        try:
            radius=number(self.radius.get(),'Promień') if sweep is not None else None
            if sweep is not None and (radius is None or radius<=0):
                raise ValueError('Wpisz dodatni promień w mm.')
        except ValueError as exc:
            messagebox.showerror('Promień',str(exc),parent=self);return False
        self.result=dict(edge=self.edge.current(),sweep=sweep,radius=radius,derive=self.derive.get())
        return True


class SketchTab(ttk.Frame):
    def __init__(self, parent, on_accept):
        super().__init__(parent)
        self.on_accept = on_accept
        self.version = 0
        self.auto_busy = False
        self.analysis_stale = False
        self.auto_queue = queue.Queue()
        self.detected_index = 0
        self.detection = None
        self.auto_words = []
        self.ocr_available = False
        self.ocr_diagnostics = {}
        self.tesseract_override = None
        self.auto_questions = []
        self.question_relation = None
        self.arc_specs = {}
        self.arc_original = {}

        self.model = None
        self.source_path = None
        self.source_image = None
        self.source_png = None
        self.threshold = tk.DoubleVar(value=205)
        self.binary_preview = tk.BooleanVar(value=False)
        self.preview_job = None
        self.analysis_region = None
        self.region_select = False
        self.region_start = None
        self.gap = tk.IntVar(value=1)
        self.display_image = None
        self.rotation = 0
        self.points = []
        self.edge_values = []
        self.extra = []
        self.closed = False
        self.full_size = False
        self.source_zoom = None
        self.source_panning = False
        self.source_render_key = None
        self.source_background_key = None
        self.source_background = None
        self.large_window = None
        self.large_preview = None
        self.large_source_key = None
        self.image_origin = (0, 0)
        self.image_factor = 1
        sidebar = ttk.Frame(self)
        sidebar.pack(side='left', fill='y')
        scroll = tk.Canvas(sidebar, width=360, highlightthickness=0)
        bar = ttk.Scrollbar(sidebar, orient='vertical', command=scroll.yview)
        bar.pack(side='right', fill='y')
        scroll.pack(side='left', fill='both', expand=True)
        scroll.configure(yscrollcommand=bar.set)
        panel = ttk.Frame(scroll, padding=12)
        window = scroll.create_window((0, 0), window=panel, anchor='nw')
        panel.bind('<Configure>', lambda _: scroll.configure(scrollregion=scroll.bbox('all')))
        scroll.bind('<Configure>', lambda e: scroll.itemconfigure(window, width=e.width))
        ttk.Label(panel, text='Szkic → dowolny kontur', font=('Arial', 16, 'bold')).pack(anchor='w')
        ttk.Button(panel, text='Wczytaj szkic PDF / obraz', command=self.load).pack(fill='x', pady=5)
        self.source_label = ttk.Label(panel, text='Wczytaj szkic i odczytaj lokalnie albo zaznacz narożniki ręcznie.', wraplength=325)
        self.source_label.pack(anchor='w')
        self.auto_button = ttk.Button(panel, text='Wykryj obrys i odczytaj wymiary lokalnie', command=self.auto_read, state='disabled')
        self.auto_button.pack(fill='x', pady=5)
        ttk.Label(panel,text='Próg jasności (czułość odczytu)').pack(anchor='w')
        ttk.Scale(panel,from_=80,to=245,variable=self.threshold,command=self.threshold_changed).pack(fill='x')
        self.threshold_label=ttk.Label(panel,text='205 — zwiększ dla jasnych kresek, zmniejsz dla tła.',wraplength=325)
        self.threshold_label.pack(anchor='w')
        ttk.Checkbutton(panel,text='Pokaż czarno-biały obraz do odczytu',variable=self.binary_preview,command=self.draw_source).pack(anchor='w')
        ttk.Button(panel,text='Zaznacz obszar samego obrysu',command=self.select_region).pack(fill='x',pady=2)
        ttk.Button(panel,text='Użyj całej strony',command=self.clear_region).pack(fill='x',pady=2)
        self.region_label=ttk.Label(panel,text='Obszar: cała strona',wraplength=325)
        self.region_label.pack(anchor='w')
        ttk.Label(panel,text='Domykanie przerw w kreskach (px):').pack(anchor='w')
        gap_spin=ttk.Spinbox(panel,from_=0,to=3,textvariable=self.gap,state='readonly',width=5,command=self.gap_changed)
        gap_spin.pack(anchor='w',pady=2)
        self.propose_arcs=tk.BooleanVar(value=True)
        ttk.Checkbutton(panel,text='Proponuj łuki — promienie do potwierdzenia',variable=self.propose_arcs,command=self.arcs_changed).pack(anchor='w')
        self.autoload = tk.BooleanVar(value=True)
        ttk.Checkbutton(panel,text='Odczytuj automatycznie po wczytaniu',variable=self.autoload).pack(anchor='w')
        self.detected_choice = ttk.Combobox(panel, state='disabled')
        self.detected_choice.pack(fill='x')
        self.detected_choice.bind('<<ComboboxSelected>>', self.choose_detection)
        self.auto_status = ttk.Label(panel, text='Obrys działa bez dodatkowych instalacji. OCR wymaga lokalnego Tesseract. Dane nie są wysyłane.', wraplength=325)
        self.auto_status.pack(anchor='w', pady=3)
        ttk.Button(panel,text='Diagnostyka OCR — pokaż przyczynę',command=self.show_ocr_diagnostics).pack(fill='x',pady=2)
        ttk.Button(panel,text='Wskaż zainstalowany tesseract.exe',command=self.choose_tesseract).pack(fill='x',pady=2)
        ttk.Button(panel, text='Uzupełnij tylko brakujące wymiary', command=self.ask_missing).pack(fill='x', pady=3)
        ttk.Button(panel,text='Sprawdź łuki / podaj promienie',command=self.edit_arc).pack(fill='x',pady=3)
        for text,command in [('Obróć szkic o 90°',self.rotate_preview),('Podgląd 100% / dopasuj',self.toggle_size)]:
            ttk.Button(panel,text=text,command=command).pack(fill='x',pady=2)
        manual_container=ttk.Frame(panel)
        manual_container.pack(fill='x',pady=5)
        self.manual_enabled=tk.BooleanVar(value=False)
        ttk.Checkbutton(manual_container,text='Korekta ręczna (opcjonalnie)',variable=self.manual_enabled,command=self.toggle_manual).pack(anchor='w')
        self.manual_frame=ttk.Frame(manual_container)
        ttk.Label(self.manual_frame, text='1. Klikaj narożniki po obwodzie (bez powtarzania pierwszego).\n2. Zamknij kontur.\n3. Wpisz różnice współrzędnych w mm lub wymiary między punktami.', wraplength=325).pack(anchor='w', pady=7)
        self.orthogonal = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.manual_frame, text='Podpowiadaj poziom/pion (tylko kierunek)', variable=self.orthogonal).pack(anchor='w')
        for text, command in [('Zamknij kontur', self.close_outline), ('Cofnij ostatni narożnik', self.undo), ('Wyczyść narożniki i wymiary', self.clear)]:
            ttk.Button(self.manual_frame, text=text, command=command).pack(fill='x', pady=2)
        ttk.Label(self.manual_frame, text='ΔX: w prawo +, w lewo −. ΔY: w dół +, w górę −.\n0 oznacza tę samą współrzędną. Puste pole = nieznany wymiar. Długości nie są mierzone z obrazka.', wraplength=325).pack(anchor='w', pady=7)
        self.edges_frame = ttk.Frame(self.manual_frame)
        self.edges_frame.pack(fill='x')
        ttk.Label(self.manual_frame, text='Wymiary dodatkowe / wyrównanie punktów:').pack(anchor='w', pady=(8, 2))
        self.extra_list = tk.Listbox(self.manual_frame, height=4, width=36)
        self.extra_list.pack(fill='x')
        ttk.Button(self.manual_frame, text='Dodaj wymiar między punktami', command=self.add_dimension).pack(fill='x', pady=2)
        ttk.Button(self.manual_frame, text='Usuń zaznaczony wymiar', command=self.remove_dimension).pack(fill='x', pady=2)
        ttk.Button(self.manual_frame, text='Zbuduj i sprawdź kontur', command=self.build).pack(fill='x', pady=8)
        self.confirm = tk.BooleanVar(value=False)
        ttk.Checkbutton(panel, text='Potwierdzam kontur i wymiary', variable=self.confirm, command=self.confirmed).pack(anchor='w')
        self.transfer = ttk.Button(panel, text='Zatwierdź i przejdź do układania', command=self.accept, state='disabled')
        self.transfer.pack(fill='x', pady=3)
        self.export = ttk.Button(panel, text='Zapisz sam kontur do PDF 1:1', command=self.save, state='disabled')
        self.export.pack(fill='x', pady=3)
        self.status = ttk.Label(panel, text='Wczytaj szkic, sprawdź wykryty obrys i uzupełnij tylko brakujące wymiary.', wraplength=325)
        self.status.pack(anchor='w', pady=5)
        content = ttk.Frame(self, padding=8)
        content.pack(side='right', fill='both', expand=True)
        self.source_heading=ttk.Label(content,text='Szkic: sprawdź automatycznie wykryty czerwony obrys')
        self.source_heading.pack(anchor='w')
        zoom_bar=ttk.Frame(content)
        zoom_bar.pack(fill='x',pady=3)
        for text,command in [('−',lambda:self.zoom_source(1/1.25)),
                             ('+',lambda:self.zoom_source(1.25)),
                             ('100%',lambda:self.zoom_source(absolute=1)),
                             ('Dopasuj',lambda:self.zoom_source(fit=True))]:
            ttk.Button(zoom_bar,text=text,command=command,takefocus=False).pack(side='left',padx=(0,3))
        self.source_zoom_label=ttk.Label(zoom_bar,text='Dopasuj')
        self.source_zoom_label.pack(side='left',padx=4)
        ttk.Button(zoom_bar,text='Duży podgląd',command=self.open_large_preview,takefocus=False).pack(side='left',padx=4)
        holder = ttk.Frame(content)
        holder.pack(fill='both', expand=True)
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.source_canvas = tk.Canvas(holder, background='#edf0f4', highlightthickness=0, height=300)
        self.source_canvas.grid(row=0, column=0, sticky='nsew')
        sx = ttk.Scrollbar(holder, orient='horizontal', command=self.source_canvas.xview)
        sy = ttk.Scrollbar(holder, orient='vertical', command=self.source_canvas.yview)
        sx.grid(row=1, column=0, sticky='ew')
        sy.grid(row=0, column=1, sticky='ns')
        self.source_canvas.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        self.source_canvas.bind('<Configure>', lambda _: self.draw_source())
        self.source_canvas.bind('<Button-1>', self.click)
        self.source_canvas.bind('<B1-Motion>',self.drag_region)
        self.source_canvas.bind('<ButtonRelease-1>',self.finish_region)
        self.source_canvas.bind('<MouseWheel>',self.source_wheel)
        self.source_canvas.bind('<Button-4>',lambda e:self.source_wheel(e,1))
        self.source_canvas.bind('<Button-5>',lambda e:self.source_wheel(e,-1))
        ttk.Label(content, text='Kontur obliczony z wymiarów — długości boków w mm').pack(anchor='w', pady=(8, 2))
        preview=ttk.Frame(content)
        preview.pack(fill='both',expand=True)
        preview.rowconfigure(0,weight=1)
        preview.columnconfigure(0,weight=1)
        self.canvas = tk.Canvas(preview, background='#e9eef4', highlightthickness=0, height=280)
        self.canvas.grid(row=0,column=0,sticky='nsew')
        table_holder=ttk.Frame(preview)
        table_holder.grid(row=0,column=1,sticky='ns',padx=(8,0))
        self.edge_table=ttk.Treeview(table_holder,columns=('side','length'),show='headings',height=8)
        self.edge_table.heading('side',text='Odcinek')
        self.edge_table.heading('length',text='Długość [mm]')
        self.edge_table.column('side',width=95,stretch=False)
        self.edge_table.column('length',width=95,anchor='e',stretch=False)
        table_scroll=ttk.Scrollbar(table_holder,command=self.edge_table.yview)
        table_scroll.pack(side='right',fill='y')
        self.edge_table.configure(yscrollcommand=table_scroll.set)
        self.edge_table.pack(side='left',fill='y',expand=True)
        self.canvas.bind('<Configure>', lambda _: self.draw())
        self.after(100, self.poll_auto)

    def toggle_manual(self):
        if self.manual_enabled.get():
            self.manual_frame.pack(fill='x')
            self.source_heading.config(text='Korekta ręczna: klikaj narożniki po obwodzie szkicu')
        else:
            self.manual_frame.pack_forget()
            self.source_heading.config(text='Szkic: sprawdź automatycznie wykryty czerwony obrys')

    def invalidate(self, *args):
        self.version += 1
        self.model = None
        self.confirm.set(False)
        self.transfer.config(state='disabled')
        self.export.config(state='disabled')
        self.status.config(text='Zbuduj kontur z aktualnych wymiarów.' if self.manual_enabled.get() else 'Sprawdź wykryty obrys i kliknij „Uzupełnij tylko brakujące wymiary”.')
        self.draw()

    def load(self):
        path = filedialog.askopenfilename(filetypes=[('Szkic PDF lub obraz', '*.pdf *.png *.jpg *.jpeg *.bmp')])
        if not path:
            return
        try:
            png = preview_png(path)
            image = tk.PhotoImage(data=png)
        except Exception as exc:
            messagebox.showerror('Import szkicu', str(exc))
            return
        self.source_path, self.source_image = path, image
        self.source_png = png
        self.source_zoom = None
        self.source_panning = False
        self.analysis_region = None
        self.region_select = False
        self.region_label.config(text='Obszar: cała strona')
        self.rotation = 0
        self.detection = None
        self.detected_choice.set('')
        self.detected_choice.config(state='disabled', values=())
        self.auto_button.config(state='disabled' if self.auto_busy else 'normal')
        self.reset()
        self.source_label.config(text=Path(path).name + '\nMożesz odczytać obrys lokalnie lub wskazać narożniki ręcznie.')
        self.draw_source()
        if self.autoload.get():
            self.auto_read()

    def reset(self):
        self.analysis_stale = False
        self.ocr_diagnostics = {}
        self.arc_specs = {}
        self.arc_original = {}
        self.points = []
        self.auto_questions = []
        self.question_relation = None
        self.closed = False
        self.extra = []
        self.edge_values = []
        self.render_edges()
        self.render_extra()
        self.invalidate()
        self.draw_source()

    def clear(self):
        if self.points and not messagebox.askyesno('Wyczyść kontur', 'Usunąć wszystkie narożniki i przypisane wymiary?'):
            return
        self.reset()

    def auto_read(self):
        if self.auto_busy or not self.source_path:
            return
        if self.closed and not messagebox.askyesno('Odczyt szkicu', 'Nowy odczyt zastąpi obecny kontur i wymiary. Kontynuować?'):
            return
        try:
            png=self.source_png or preview_png(self.source_path,self.rotation)
            threshold=round(self.threshold.get())
            region=self.analysis_region
            gap=self.gap.get()
            propose_arcs=self.propose_arcs.get()
        except Exception as exc:
            messagebox.showerror('Odczyt szkicu',str(exc));return
        executable=self.tesseract_override or find_tesseract()
        self.ocr_available=bool(executable)
        self.invalidate()
        version=self.version
        self.auto_busy=True
        self.auto_button.config(state='disabled')
        self.auto_status.config(text='Wykrywanie obrysu i lokalny OCR…' if executable else 'Wykrywanie obrysu… Brak Tesseract; zapytam o wymiary, których nie da się wyliczyć.')
        def worker():
            try:
                detection=detect_contours(png,threshold,region=region,gap=gap)
                if propose_arcs:
                    detection.curve_candidates=[suggest_arcs(points) for points in detection.raw_contours]
                diagnostics={}
                words=ocr_numbers(detection.mask,executable,diagnostics=diagnostics)
                self.auto_queue.put((version,detection,words,None,diagnostics))
            except Exception as exc:
                self.auto_queue.put((version,None,[],str(exc),{}))
        threading.Thread(target=worker,daemon=True).start()

    def poll_auto(self):
        try:
            version,detection,words,error,diagnostics=self.auto_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            self.auto_busy=False
            self.auto_button.config(state='normal' if self.source_path else 'disabled')
            if version!=self.version:
                self.auto_status.config(text='Pominięto nieaktualny odczyt — szkic lub kontur został zmieniony.')
            elif error:
                self.auto_status.config(text=error)
                messagebox.showerror('Lokalny odczyt',error)
            else:
                self.analysis_stale=False
                self.ocr_diagnostics=diagnostics
                self.detection,self.auto_words=detection,words
                self.detected_choice.config(state='readonly',values=[f'Obrys {i+1} — {len(points)} narożników' for i,points in enumerate(detection.contours)])
                self.detected_choice.current(0)
                self.choose_detection()
        self.after(100,self.poll_auto)

    def choose_detection(self,event=None):
        if self.analysis_stale:
            if event is not None:
                self.detected_choice.current(self.detected_index)
            self.check_analysis();return
        if self.detection is None or self.detected_choice.current()<0:
            return
        if event is not None and self.closed and not messagebox.askyesno('Inny obrys','Zmiana wykrytego obrysu wyczyści wymiary. Kontynuować?'):
            self.detected_choice.current(self.detected_index)
            return
        self.detected_index = self.detected_choice.current()
        self.points=list(self.detection.contours[self.detected_choice.current()])
        self.arc_specs = {}
        self.arc_original = {}
        if self.detection.curve_candidates:
            proposed,specs=self.detection.curve_candidates[self.detected_choice.current()]
            if specs:
                self.points=list(proposed)
                self.arc_specs={i:dict(spec) for i,spec in specs.items()}
        self.closed=True
        edges,extra=topology(self.points)
        self.edge_values=[(tk.StringVar(value=str(e['dx'])),tk.StringVar(value=str(e['dy']))) for e in edges]
        accepted,self.auto_questions=match_dimensions(self.points,self.detection.mask,self.auto_words)
        self.extra=extra+accepted
        self.render_edges();self.render_extra();self.invalidate();self.draw_source()
        self.ocr_diagnostics.update(matched=len(accepted),uncertain=len(self.auto_questions))
        status=self.ocr_diagnostics.get('status')
        if status in ('not_installed','launch_failure','missing_eng','run_failure'):
            ocr_note=' OCR nie działa — otwórz diagnostykę, aby zobaczyć przyczynę.'
        elif status=='partial':
            ocr_note=' Część prób OCR zakończyła się błędem — szczegóły są w diagnostyce.'
        elif not self.auto_words:
            ocr_note=' OCR wykonał odczyt, ale nie rozpoznał cyfr.'
        elif not accepted:
            ocr_note=f' OCR rozpoznał {len(self.auto_words)} liczb, ale nie dopasował pewnych wymiarów.'
        else:
            ocr_note=''
        self.auto_status.config(text=f'Wykryto {len(self.points)} narożników. OCR dopasował {len(accepted)} wymiarów; niepewne: {len(self.auto_questions)}.{ocr_note} Sprawdź czerwony obrys, potem uzupełnij tylko brakujące wymiary.')
        if self.arc_specs:
            self.auto_status.config(text=self.auto_status.cget('text')+f'\nPropozycje łuków: {len(self.arc_specs)}. Potwierdź ich końce, kierunek i promień. Inne zaokrąglenia mogą pozostać niewykryte.')
        if self.detection.warnings:
            self.auto_status.config(text=self.auto_status.cget('text')+'\n'+'\n'.join(self.detection.warnings))
        # Obrys musi być sprawdzony przed użyciem: użytkownik wybiera, kiedy
        # rozpocząć pytania, aby nie ukrywać czerwonego podglądu dialogiem.

    def choose_tesseract(self):
        path=filedialog.askopenfilename(title='Wskaż tesseract.exe',filetypes=[('Tesseract','tesseract.exe')])
        if not path:
            return
        if Path(path).name.lower()!='tesseract.exe':
            messagebox.showerror('Silnik OCR','Wskaż plik o nazwie tesseract.exe z instalacji Tesseract OCR.')
            return
        self.tesseract_override=Path(path)
        try:
            save_tesseract(path)
        except (OSError,ValueError) as exc:
            self.auto_status.config(text='Wybrano Tesseract na tę sesję, ale nie udało się zapisać ustawienia.')
            messagebox.showerror('Zapis ustawień',str(exc))
        else:
            self.auto_status.config(text='Zapamiętano Tesseract na kolejne uruchomienia. Ponów odczyt szkicu.')

    def show_ocr_diagnostics(self):
        dialog=tk.Toplevel(self)
        dialog.title('Diagnostyka lokalnego OCR')
        dialog.geometry('700x500')
        text=tk.Text(dialog,wrap='word',padx=12,pady=12)
        scrollbar=ttk.Scrollbar(dialog,command=text.yview)
        scrollbar.pack(side='right',fill='y')
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(fill='both',expand=True)
        report=format_ocr_report(self.ocr_diagnostics)
        text.insert('1.0',report)
        text.configure(state='disabled')
        def save():
            path=filedialog.asksaveasfilename(defaultextension='.txt',initialfile='Diagnostyka_OCR.txt',filetypes=[('Raport tekstowy','*.txt')])
            if path:
                try:
                    Path(path).write_text(report,encoding='utf-8')
                except OSError as exc:
                    messagebox.showerror('Zapis raportu',str(exc),parent=dialog)
        ttk.Button(dialog,text='Zapisz raport do pliku',command=save).pack(fill='x')

    def current_edges(self):
        edges=[dict(dx=dx.get(),dy=dy.get()) for dx,dy in self.edge_values]
        for i,spec in self.arc_specs.items():
            if i<len(edges):
                edges[i]['arc']={key:spec[key] for key in ('radius','sweep')}
        return edges

    def edit_arc(self,index=None):
        if not self.closed:
            messagebox.showinfo('Łuki','Najpierw wykryj lub zamknij obrys.');return False
        explicit_index=index is not None
        if index is None:
            selected=self.edge_table.selection()
            index=self.edge_table.index(selected[0]) if selected else 0
        locked=explicit_index
        def select_preview(i):
            a,b=self.points[i],self.points[(i+1)%len(self.points)]
            question=dict(start=i,end=(i+1)%len(self.points),axis='x',
                          image_line=(*a,*b),label_bounds=(min(a[0],b[0])-30,min(a[1],b[1])-30,max(a[0],b[0])+30,max(a[1],b[1])+30))
            self.question_relation=question;self.draw_source();self.update_idletasks()
            png=question_crop(self.source_png,question,include_line=True) if self.source_png else None
            return self.arc_specs.get(i,{}),png
        spec,png=select_preview(index)
        result=ArcQuestion(self,len(self.points),index,spec,png=png,on_select=select_preview,locked=locked).result
        self.question_relation=None;self.draw_source()
        if result is None:
            return False
        index=result['edge']
        a,b=self.points[index],self.points[(index+1)%len(self.points)]
        delta=(b[0]-a[0],b[1]-a[1])
        if result['derive'] and abs(result['sweep'] or 0)==90 and min(abs(delta[0]),abs(delta[1]))<.01:
            messagebox.showerror('Końce łuku','Ćwiartka wymaga dwóch różnych poziomów X i Y. Sprawdź końce i rodzaj łuku.')
            return False
        if result['sweep'] is None:
            self.arc_specs.pop(index,None)
            if index in self.arc_original:
                for variable,value in zip(self.edge_values[index],self.arc_original.pop(index)):
                    variable.set(value)
        else:
            if index not in self.arc_original:
                self.arc_original[index]=tuple(variable.get() for variable in self.edge_values[index])
            self.arc_specs[index]={**self.arc_specs.get(index,{}),'radius':result['radius'],'sweep':result['sweep']}
            if result['derive']:
                a,b=self.points[index],self.points[(index+1)%len(self.points)]
                delta=(b[0]-a[0],b[1]-a[1]);radius=result['radius']
                if abs(result['sweep'])==90:
                    offsets=[radius*(1 if value>0 else -1) for value in delta]
                else:
                    axis=0 if abs(delta[0])>abs(delta[1]) else 1
                    offsets=[0,0];offsets[axis]=2*radius*(1 if delta[axis]>0 else -1)
                for variable,value in zip(self.edge_values[index],offsets):
                    variable.set(f'{value:g}')
        self.invalidate();return True

    def ask_missing(self):
        if not self.check_analysis():
            return
        if not self.closed:
            messagebox.showinfo('Obrys','Najpierw wykryj obrys lub zaznacz narożniki i zamknij kontur.')
            return
        for index in list(self.arc_specs):
            if self.arc_specs[index].get('radius') is None and not self.edit_arc(index):
                return
        while True:
            try:
                model=build_contour(self.current_edges(),self.extra)
            except ValueError as exc:
                if not str(exc).startswith('Brakuje wymiarów'):
                    messagebox.showerror('Sprawdź wymiary',str(exc));return
            else:
                self.model=model
                self.confirm.set(False);self.confirmed();self.draw()
                self.status.config(text=f"Kontur gotowy: {model.dimensions['width']:g} × {model.dimensions['height']:g} mm. Porównaj ze szkicem i zatwierdź.")
                return
            while self.auto_questions and known_dimension(self.current_edges(),self.extra,self.auto_questions[0]) is not None:
                self.auto_questions.pop(0)
            if self.auto_questions:
                question=self.auto_questions.pop(0)
                suggestion=question['value'] if len(question['candidates'])==1 else None
            else:
                question=missing_dimension(self.points,self.current_edges(),self.extra)
                suggestion=None
            if question is None:
                return
            self.question_relation=question
            self.draw_source();self.update_idletasks()
            title='Uzupełnij wymiar ze szkicu'
            if question.get('source')=='unread_label':
                text='Nie udało się odczytać liczby przy podświetlonej linii. Jaki wymiar jest tutaj zapisany?'
            elif suggestion is not None:
                text=f'OCR odczytał {suggestion:g} mm, ale wynik nie jest pewny. Potwierdź lub popraw liczbę przy podświetlonej linii.'
            elif question.get('image_line'):
                text='OCR podał różne odczyty tej samej linii. Wpisz prawidłowy wymiar ze szkicu.'
            else:
                text='Nie znaleziono jednoznacznej linii wymiarowej dla tej odległości. Podaj wymiar wskazany niebieską strzałką, jeśli znasz go ze szkicu, lub anuluj.'
            text+='\nAnuluj zachowa dotychczasową pracę.'
            preview_question=dict(question)
            if not preview_question.get('image_line'):
                a,b=self.points[question['start']],self.points[question['end']]
                preview_question['context_bounds']=(min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1]))
                if question['axis']=='x':
                    preview_question['image_line']=(a[0],(a[1]+b[1])/2,b[0],(a[1]+b[1])/2)
                else:
                    preview_question['image_line']=((a[0]+b[0])/2,a[1],(a[0]+b[0])/2,b[1])
            source=self.source_png or (self.detection.png if self.detection is not None else None)
            png=question_crop(source,preview_question,include_line=True) if source else None
            value=DimensionQuestion(self,title,text,png=png,initial=suggestion).result
            self.question_relation=None;self.draw_source()
            if value is None:
                if 'candidates' in question:
                    self.auto_questions.insert(0,question)
                return
            if not isfinite(value):
                messagebox.showerror('Wymiar','Wpisz skończoną liczbę.');return
            item={key:question[key] for key in ('start','end','axis')}
            item['value']=value
            self.extra.append(item);self.render_extra();self.invalidate()

    def check_analysis(self):
        if self.analysis_stale:
            messagebox.showinfo('Ponów odczyt','Zmieniono ustawienia analizy. Kliknij „Wykryj obrys i odczytaj wymiary lokalnie”, zanim uzupełnisz wymiary lub zbudujesz kontur.')
            return False
        return True

    def arcs_changed(self):
        self.analysis_stale=True;self.invalidate()
        self.auto_status.config(text='Zmieniono wyszukiwanie łuków. Ponów wykrywanie obrysu.')

    def select_region(self):
        if self.source_image is None:
            messagebox.showinfo('Obszar obrysu','Najpierw wczytaj szkic.');return
        self.region_select=True
        self.region_start=None
        self.source_canvas.configure(cursor='crosshair')
        self.source_heading.config(text='Przeciągnij prostokąt wokół całej formatki, zostawiając linie wymiarowe na zewnątrz.')

    def clear_region(self):
        self.analysis_region=None;self.region_select=False;self.region_start=None
        self.source_canvas.configure(cursor='')
        self.region_label.config(text='Obszar: cała strona')
        self.source_heading.config(text='Szkic: sprawdź automatycznie wykryty czerwony obrys')
        self.analysis_stale=True
        self.invalidate();self.draw_source()
        self.auto_status.config(text='Wybrano całą stronę. Ponów wykrywanie obrysu.')

    def gap_changed(self):
        self.analysis_stale=True
        self.invalidate()
        self.auto_status.config(text='Zmieniono domykanie przerw. Ponów wykrywanie i sprawdź małe detale obrysu.')

    def source_position(self,event):
        c=self.source_canvas
        x=(c.canvasx(event.x)-self.image_origin[0])*self.image_factor
        y=(c.canvasy(event.y)-self.image_origin[1])*self.image_factor
        return (max(0,min(self.source_image.width(),x)),max(0,min(self.source_image.height(),y)))

    def drag_region(self,event):
        if self.source_panning:
            self.source_canvas.scan_dragto(event.x,event.y,gain=1)
            return
        if not self.region_select or self.region_start is None:
            return
        x,y=self.source_position(event);a,b=self.region_start
        self.source_canvas.delete('region-drag')
        self.source_canvas.create_rectangle(10+a/self.image_factor,10+b/self.image_factor,
                                           10+x/self.image_factor,10+y/self.image_factor,
                                           outline='#2763b5',width=2,dash=(4,3),tags=('region-drag',))

    def finish_region(self,event):
        if self.source_panning:
            self.source_panning=False
            self.source_canvas.configure(cursor='')
            return
        if not self.region_select or self.region_start is None:
            return
        x,y=self.source_position(event);a,b=self.region_start
        self.region_start=None
        if abs(x-a)<20 or abs(y-b)<20:
            return
        self.analysis_region=(min(x,a),min(y,b),max(x,a),max(y,b))
        self.region_select=False;self.source_canvas.configure(cursor='')
        self.region_label.config(text='Obszar: zaznaczona formatka. OCR nadal czyta wymiary z całej strony.')
        self.source_heading.config(text='Szkic: sprawdź automatycznie wykryty czerwony obrys')
        self.analysis_stale=True
        self.invalidate();self.draw_source()
        self.auto_status.config(text='Wybrano obszar. Kliknij „Wykryj obrys i odczytaj wymiary lokalnie”.')

    def click(self, event):
        if self.region_select and self.source_image is not None:
            self.region_start=self.source_position(event)
            return
        if (not self.manual_enabled.get() or self.closed) and self.source_image is not None:
            self.source_panning=True
            self.source_canvas.scan_mark(event.x,event.y)
            self.source_canvas.configure(cursor='fleur')
            return
        if not self.manual_enabled.get() or self.source_image is None or self.closed:
            return
        if len(self.points) >= 500:
            messagebox.showinfo('Limit narożników', 'Kontur może mieć maksymalnie 500 narożników.')
            return
        c = self.source_canvas
        x = (c.canvasx(event.x) - self.image_origin[0]) * self.image_factor
        y = (c.canvasy(event.y) - self.image_origin[1]) * self.image_factor
        if not (0 <= x <= self.source_image.width() and 0 <= y <= self.source_image.height()):
            return
        if any(abs(x-px) + abs(y-py) < 3 for px, py in self.points):
            return
        self.points.append((x, y))
        self.invalidate()
        self.draw_source()

    def close_outline(self):
        if self.closed:
            return
        if len(self.points) < 3:
            messagebox.showinfo('Narożniki', 'Zaznacz co najmniej trzy narożniki.')
            return
        self.closed = True
        self.analysis_stale=False
        self.edge_values = []
        for i, (x, y) in enumerate(self.points):
            xx, yy = self.points[(i+1) % len(self.points)]
            dx, dy = '', ''
            if self.orthogonal.get():
                if abs(xx-x) > 5 * abs(yy-y):
                    dy = '0'
                elif abs(yy-y) > 5 * abs(xx-x):
                    dx = '0'
            self.edge_values.append((tk.StringVar(value=dx), tk.StringVar(value=dy)))
        self.render_edges()
        self.invalidate()
        self.draw_source()

    def undo(self):
        if not self.points:
            return
        if self.closed:
            if not messagebox.askyesno('Edycja narożników', 'Otwarcie konturu wyczyści przypisane wymiary. Kontynuować?'):
                return
            self.closed = False
            self.edge_values = []
            self.arc_specs = {}
            self.arc_original = {}
            self.extra = []
            self.render_edges()
            self.render_extra()
        self.auto_questions = []
        self.question_relation = None
        self.points.pop()
        self.invalidate()
        self.draw_source()

    def render_edges(self):
        for child in self.edges_frame.winfo_children():
            child.destroy()
        if not self.closed:
            return
        for col, text in enumerate(('Bok', 'ΔX [mm]', 'ΔY [mm]')):
            ttk.Label(self.edges_frame, text=text).grid(row=0, column=col, sticky='w')
        for i, (dx, dy) in enumerate(self.edge_values):
            ttk.Label(self.edges_frame, text=f'P{i+1} → P{(i+1)%len(self.points)+1}').grid(row=i+1, column=0, padx=(0, 5))
            for col, variable in enumerate((dx, dy), 1):
                ttk.Entry(self.edges_frame, textvariable=variable, width=11).grid(row=i+1, column=col, padx=2, pady=2)
                variable.trace_add('write', self.invalidate)

    def add_dimension(self):
        if not self.closed:
            messagebox.showinfo('Najpierw kontur', 'Najpierw zaznacz narożniki i zamknij kontur.')
            return
        dialog = tk.Toplevel(self)
        dialog.title('Wymiar między punktami')
        dialog.transient(self.winfo_toplevel())
        panel = ttk.Frame(dialog, padding=15)
        panel.pack(fill='both', expand=True)
        widgets = []
        for label in ('Punkt początkowy', 'Punkt końcowy'):
            ttk.Label(panel, text=label).pack(anchor='w')
            widget = ttk.Combobox(panel, state='readonly', values=[f'P{i+1}' for i in range(len(self.points))])
            widget.pack(fill='x', pady=3)
            widgets.append(widget)
        widgets[0].current(0)
        widgets[1].current(1)
        ttk.Label(panel, text='Oś wymiaru:').pack(anchor='w')
        axis = ttk.Combobox(panel, state='readonly', values=('X — poziomo', 'Y — pionowo'))
        axis.current(0)
        axis.pack(fill='x', pady=3)
        ttk.Label(panel, text='Różnica w mm (prawo/dół +, lewo/góra −):').pack(anchor='w')
        value = ttk.Entry(panel)
        value.pack(fill='x', pady=3)
        ttk.Label(panel, text='0 oznacza wyrównanie punktów w tej osi. Nie wpisuj długości skośnego odcinka zamiast jego rzutu.', wraplength=320).pack(anchor='w', pady=5)
        def apply():
            from sketch import number
            try:
                parsed = number(value.get(), 'Wymiar')
                if parsed is None or widgets[0].current() == widgets[1].current():
                    raise ValueError('Wybierz dwa różne punkty i wpisz wymiar.')
            except ValueError as exc:
                messagebox.showerror('Wymiar', str(exc), parent=dialog)
                return
            self.extra.append(dict(start=widgets[0].current(), end=widgets[1].current(), axis='x' if axis.current()==0 else 'y', value=parsed))
            self.render_extra()
            self.invalidate()
            dialog.destroy()
        ttk.Button(panel, text='Dodaj wymiar', command=apply).pack(fill='x', pady=5)
        dialog.grab_set()

    def render_extra(self):
        self.extra_list.delete(0, 'end')
        for item in self.extra:
            self.extra_list.insert('end', f"P{item['start']+1} → P{item['end']+1}: {item['axis'].upper()} = {item['value']:g} mm")

    def remove_dimension(self):
        selected = self.extra_list.curselection()
        if selected:
            self.extra.pop(selected[0])
            self.render_extra()
            self.invalidate()

    def rotate_preview(self):
        if not self.source_path:
            return
        if self.points and not messagebox.askyesno('Obrót szkicu', 'Obrót wyczyści narożniki i ich wymiary. Kontynuować?'):
            return
        rotation = (self.rotation + 90) % 360
        try:
            png = preview_png(self.source_path, rotation)
            image = tk.PhotoImage(data=png)
        except Exception as exc:
            messagebox.showerror('Podgląd', str(exc))
            return
        self.rotation, self.source_image = rotation, image
        self.source_png = png
        self.source_zoom = None
        self.source_panning = False
        self.analysis_region = None
        self.region_select = False
        self.region_start = None
        self.source_canvas.configure(cursor='')
        self.region_label.config(text='Obszar: cała strona')
        self.detection = None
        self.detected_choice.set('')
        self.detected_choice.config(state='disabled',values=())
        self.reset()

    def toggle_size(self):
        self.zoom_source(absolute=1,fit=self.source_zoom is not None)

    def zoom_source(self,multiplier=1,event=None,absolute=None,fit=False):
        if self.source_image is None:
            return
        c=self.source_canvas
        anchor=(event.x,event.y) if event is not None else (c.winfo_width()/2,c.winfo_height()/2)
        source=((c.canvasx(anchor[0])-10)*self.image_factor,
                (c.canvasy(anchor[1])-10)*self.image_factor)
        requested=absolute if absolute is not None else multiplier/self.image_factor
        self.source_zoom=None if fit else bounded_scale(self.source_image.width(),self.source_image.height(),requested)
        self.full_size=self.source_zoom==1
        self.draw_source()
        if fit:
            c.xview_moveto(0);c.yview_moveto(0)
        else:
            width=max(c.winfo_width(),self.display_image.width()+20)
            height=max(c.winfo_height(),self.display_image.height()+20)
            c.xview_moveto((10+source[0]/self.image_factor-anchor[0])/width)
            c.yview_moveto((10+source[1]/self.image_factor-anchor[1])/height)

    def source_wheel(self,event,direction=None):
        if direction is None:
            delta=getattr(event,'delta',0)
            if not delta:
                return 'break'
            direction=1 if delta>0 else -1
        self.zoom_source(1.25 if direction>0 else 1/1.25,event=event)
        return 'break'

    def threshold_changed(self, value=None):
        self.threshold_label.config(text=f'{round(self.threshold.get())} — zwiększ dla jasnych kresek, zmniejsz dla tła.')
        if self.source_image is None:
            return
        self.analysis_stale=True
        self.invalidate()
        self.auto_status.config(text='Zmieniono próg. Ponów wykrywanie, aby zastosować go do obrysu i OCR.')
        if self.preview_job is not None:
            self.after_cancel(self.preview_job)
        self.preview_job=self.after(150,self.refresh_source_preview)

    def refresh_source_preview(self):
        self.preview_job=None
        self.draw_source()

    def source_background_png(self):
        key=(id(self.source_image),self.binary_preview.get(),round(self.threshold.get()))
        if key!=self.source_background_key:
            png=self.source_png
            if not png:
                png=self.source_image.tk.call(self.source_image,'data','-format','png')
            if self.binary_preview.get():
                import pymupdf as fitz
                mask=monochrome(png,round(self.threshold.get()))
                samples=((~mask).astype('uint8')*255).tobytes()
                pix=fitz.Pixmap(fitz.csGRAY,mask.shape[1],mask.shape[0],samples,False)
                png=pix.tobytes('png')
            self.source_background,self.source_background_key=png,key
        return self.source_background

    def open_large_preview(self):
        if self.source_image is None:
            messagebox.showinfo('Duży podgląd','Najpierw wczytaj szkic.');return
        if self.large_window is not None and self.large_window.winfo_exists():
            self.large_window.deiconify();self.large_window.lift();return
        dialog=tk.Toplevel(self)
        self.large_window=dialog
        dialog.title('Duży podgląd szkicu i wykrytego obrysu')
        width=min(1200,max(600,dialog.winfo_screenwidth()-100))
        height=min(850,max(400,dialog.winfo_screenheight()-100))
        dialog.geometry(f'{width}x{height}')
        dialog.minsize(540,360)
        ttk.Label(dialog,text='Podgląd narożników i pytanego wymiaru. Zbliżenie nie zmienia geometrii.',wraplength=700).pack(anchor='w',padx=8,pady=5)
        self.large_preview=OverlayZoomPreview(dialog,self.source_background_png(),
            overlay=lambda canvas,scale:self.draw_source_overlays(canvas,scale,(0,0)),
            width=width-40,height=height-110)
        self.large_preview.pack(fill='both',expand=True,padx=8,pady=(0,8))
        self.large_source_key=self.source_background_key
        def close():
            self.large_window=None;self.large_preview=None;self.large_source_key=None
            dialog.destroy()
        dialog.protocol('WM_DELETE_WINDOW',close)
        dialog.lift()

    def draw_source(self):
        c = self.source_canvas
        c.delete('all')
        if self.source_image is None:
            return
        scale=self.source_zoom
        if scale is None:
            scale=min(1,max(1,c.winfo_width()-20)/self.source_image.width(),
                      max(1,c.winfo_height()-20)/self.source_image.height())
        scale=bounded_scale(self.source_image.width(),self.source_image.height(),scale)
        png=self.source_background_png()
        key=(self.source_background_key,scale)
        if key!=self.source_render_key:
            self.display_image=photo_from_png(png,scale,master=c)
            self.source_render_key=key
        self.source_zoom_label.config(text=f'{scale*100:.0f}%')
        self.image_factor = 1/scale
        self.image_origin = (10, 10)
        c.create_image(10, 10, image=self.display_image, anchor='nw')
        c.configure(scrollregion=(0,0,max(c.winfo_width(),self.display_image.width()+20),max(c.winfo_height(),self.display_image.height()+20)))
        self.draw_source_overlays(c,scale)
        if self.large_window is not None and self.large_window.winfo_exists():
            if self.large_source_key!=self.source_background_key:
                self.large_preview.set_image(png)
                self.large_source_key=self.source_background_key
            else:
                self.large_preview.refresh_overlay()

    def draw_source_overlays(self,c,scale,origin=(10,10)):
        ox,oy=origin
        def coordinates(values):
            return tuple((ox if i%2==0 else oy)+v*scale for i,v in enumerate(values))
        if self.analysis_region:
            c.create_rectangle(*coordinates(self.analysis_region),outline='#2763b5',dash=(4,3),width=2,tags=('analysis-region',))
        xy = [(ox+x*scale,oy+y*scale) for x,y in self.points]
        if len(xy)>1:
            count=len(xy) if self.closed else len(xy)-1
            for i in range(count):
                path=self.arc_specs.get(i,{}).get('source_path')
                line=[(ox+x*scale,oy+y*scale) for x,y in path] if path else [xy[i],xy[(i+1)%len(xy)]]
                c.create_line(*[v for p in line for v in p],fill='#ce302d',width=2)
        if self.question_relation is not None:
            item=self.question_relation
            if item.get('image_line'):
                line=coordinates(item['image_line'])
            else:
                a,b=xy[item['start']],xy[item['end']]
                if item['axis']=='x':
                    line=(a[0],(a[1]+b[1])/2,b[0],(a[1]+b[1])/2)
                else:
                    line=((a[0]+b[0])/2,a[1],(a[0]+b[0])/2,b[1])
            if item.get('label_bounds'):
                c.create_rectangle(*coordinates(item['label_bounds']),outline='#f09000',width=3)
            c.create_line(*line,fill='#005de0',width=3,arrow='both',tags=('question-line',))
        for i,(x,y) in enumerate(xy):
            c.create_oval(x-3,y-3,x+3,y+3,fill='#ce302d',outline='white')
            c.create_text(x+5,y-8,text=f'P{i+1}',fill='#a60000',anchor='w',tags=('source-point-label',))

    def build(self):
        if not self.check_analysis():
            return
        self.invalidate()
        if not self.closed:
            messagebox.showinfo('Kontur', 'Najpierw zaznacz narożniki i zamknij kontur.')
            return
        try:
            self.model = build_contour(self.current_edges(), self.extra)
        except ValueError as exc:
            self.status.config(text=str(exc))
            messagebox.showerror('Uzupełnij lub popraw wymiary', str(exc))
            return
        d=self.model.dimensions
        self.status.config(text=f"Obliczone wymiary: {d['width']:g} × {d['height']:g} mm. Sprawdź kontur i zatwierdź.")
        self.draw()

    def confirmed(self):
        state='normal' if self.model and self.confirm.get() else 'disabled'
        self.transfer.config(state=state)
        self.export.config(state=state)

    def draw(self):
        c=self.canvas
        c.delete('all')
        self.edge_table.delete(*self.edge_table.get_children())
        if self.model is None:
            return
        from shapely.geometry import Point
        d=self.model.dimensions
        w,h=d['width'],d['height']
        cw,ch=max(180,c.winfo_width()),max(180,c.winfo_height())
        scale=max(.001,min((cw-160)/w,(ch-130)/h))
        ox,oy=(cw-w*scale)/2,(ch-h*scale)/2
        vertices=self.model.vertices
        screen=[(ox+x*scale,oy+y*scale) for x,y in vertices]
        outline=[(ox+x*scale,oy+y*scale) for x,y in self.model.polygon.exterior.coords]
        c.create_polygon(*[v for p in outline for v in p],fill='#71b7dc',outline='#285b79',width=2)
        def mm(value):
            return f'{value:.3f}'.rstrip('0').rstrip('.').replace('.',',')
        def label(x,y,text,angle=0,tag='dimension'):
            item=c.create_text(x,y,text=text,angle=angle,fill='#193b54',tags=(tag,))
            bounds=c.bbox(item)
            background=c.create_rectangle(bounds,fill='#e9eef4',outline='',tags=('dimension-background',))
            c.tag_lower(background,item)
        # Wymiary całkowite poza obrysem.
        c.create_line(ox,oy-34,ox+w*scale,oy-34,arrow='both',fill='#496779')
        label(cw/2,oy-45,mm(w)+' mm',tag='overall-dimension')
        c.create_line(ox-45,oy,ox-45,oy+h*scale,arrow='both',fill='#496779')
        label(ox-58,ch/2,mm(h)+' mm',angle=90,tag='overall-dimension')
        covered=set()
        for i,(x,y) in enumerate(vertices):
            xx,yy=vertices[(i+1)%len(vertices)]
            dx,dy=xx-x,yy-y
            segment=self.model.segments[i]
            length=segment['length']
            is_arc=segment['kind']=='arc'
            self.edge_table.insert('', 'end',values=(f'{"Łuk" if is_arc else "Bok"} {i+1}',mm(length)))
            chord=hypot(dx,dy)
            nx,ny=-dy/chord,dx/chord
            if self.model.polygon.contains(Point((x+xx)/2+nx*.01,(y+yy)/2+ny*.01)):
                nx,ny=-nx,-ny
            ax,ay=screen[i];bx,by=screen[(i+1)%len(screen)]
            angle=90 if abs(dx)<.001 else 0
            mid=segment['midpoint']
            label(ox+mid[0]*scale+nx*19,oy+mid[1]*scale+ny*19,
                  'R'+mm(segment['radius']) if is_arc else mm(length),
                  angle=0 if is_arc else angle,tag='radius-dimension' if is_arc else 'edge-dimension')
            if is_arc:
                continue
            if abs(dy)<.001:
                covered.add(('x',round(min(x,xx),3),round(max(x,xx),3)))
            if abs(dx)<.001:
                covered.add(('y',round(min(y,yy),3),round(max(y,yy),3)))
        # Podane wymiary grubości, które nie są długością pojedynczego boku.
        # Rysuj je pośrodku konturu; jest to pozycja etykiety, nie pomiar skanu.
        for item in self.extra:
            if not item['value'] or item['start']>=len(vertices) or item['end']>=len(vertices):
                continue
            axis=item['axis'];index=0 if axis=='x' else 1
            start,end=sorted((vertices[item['start']][index],vertices[item['end']][index]))
            key=(axis,round(start,3),round(end,3))
            if key in covered:
                continue
            covered.add(key)
            if axis=='x':
                line=(ox+start*scale,ch/2,ox+end*scale,ch/2)
                label((line[0]+line[2])/2,ch/2-12,mm(end-start),tag='given-dimension')
            else:
                line=(cw/2,oy+start*scale,cw/2,oy+end*scale)
                label(cw/2+12,(line[1]+line[3])/2,mm(end-start),angle=90,tag='given-dimension')
            c.create_line(*line,arrow='both',fill='#496779')
        area=f'{self.model.polygon.area/1_000_000:.8f}'.rstrip('0').rstrip('.').replace('.',',')
        c.create_text(cw/2,ch-20,text=f'Pole: {area} m² • długości boków w mm',tags=('area-label',))

    def accept(self):
        if self.model and self.confirm.get():
            self.on_accept(self.model.polygon)

    def save(self):
        if not self.model or not self.confirm.get():
            return
        path=filedialog.asksaveasfilename(defaultextension='.pdf',initialfile='Kontur_1do1.pdf',filetypes=[('PDF 1:1','*.pdf')])
        if not path:
            return
        d=self.model.dimensions
        try:
            export_pdf(path,NestResult([self.model.polygon],d['width'],d['height'],0,0))
            messagebox.showinfo('Zapisano kontur','Zapisano kontur w skali 1:1, bez numerów punktów i linii wymiarowych.')
        except Exception as exc:
            messagebox.showerror('Eksport',str(exc))
