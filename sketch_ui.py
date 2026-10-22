"""Edytor dowolnego konturu wielokątnego ze szkicu, wyłącznie lokalny."""
import queue
import threading
from math import ceil, isfinite, hypot
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from sketch import build_contour, preview_png
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
        ttk.Label(master,text=self.prompt,wraplength=450).pack(anchor='w',pady=5)
        if self.png:
            self.photo=tk.PhotoImage(data=self.png)
            factor=max(1,min(3,450//max(1,self.photo.width()),330//max(1,self.photo.height())))
            self.photo=self.photo.zoom(factor,factor)
            ttk.Label(master,image=self.photo).pack(pady=8)
            ttk.Label(master,text='Fragment szkicu: niebieska linia i ramka wskazują pytany wymiar.').pack()
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


class SketchTab(ttk.Frame):
    def __init__(self, parent, on_accept):
        super().__init__(parent)
        self.on_accept = on_accept
        self.version = 0
        self.auto_busy = False
        self.auto_queue = queue.Queue()
        self.detected_index = 0
        self.detection = None
        self.auto_words = []
        self.ocr_available = False
        self.ocr_diagnostics = {}
        self.tesseract_override = None
        self.auto_questions = []
        self.question_relation = None

        self.model = None
        self.source_path = None
        self.source_image = None
        self.source_png = None
        self.threshold = tk.DoubleVar(value=205)
        self.binary_preview = tk.BooleanVar(value=False)
        self.preview_job = None
        self.display_image = None
        self.rotation = 0
        self.points = []
        self.edge_values = []
        self.extra = []
        self.closed = False
        self.full_size = False
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
        self.ocr_diagnostics = {}
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
                detection=detect_contours(png,threshold)
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
                self.ocr_diagnostics=diagnostics
                self.detection,self.auto_words=detection,words
                self.detected_choice.config(state='readonly',values=[f'Obrys {i+1} — {len(points)} narożników' for i,points in enumerate(detection.contours)])
                self.detected_choice.current(0)
                self.choose_detection()
        self.after(100,self.poll_auto)

    def choose_detection(self,event=None):
        if self.detection is None or self.detected_choice.current()<0:
            return
        if event is not None and self.closed and not messagebox.askyesno('Inny obrys','Zmiana wykrytego obrysu wyczyści wymiary. Kontynuować?'):
            self.detected_choice.current(self.detected_index)
            return
        self.detected_index = self.detected_choice.current()
        self.points=list(self.detection.contours[self.detected_choice.current()])
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
        return [dict(dx=dx.get(),dy=dy.get()) for dx,dy in self.edge_values]

    def ask_missing(self):
        if not self.closed:
            messagebox.showinfo('Obrys','Najpierw wykryj obrys lub zaznacz narożniki i zamknij kontur.')
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
            png=question_crop(self.detection.png,question) if self.detection is not None else None
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

    def click(self, event):
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
        self.detection = None
        self.detected_choice.set('')
        self.detected_choice.config(state='disabled',values=())
        self.reset()

    def toggle_size(self):
        self.full_size = not self.full_size
        self.draw_source()

    def threshold_changed(self, value=None):
        self.threshold_label.config(text=f'{round(self.threshold.get())} — zwiększ dla jasnych kresek, zmniejsz dla tła.')
        if self.source_image is None:
            return
        self.invalidate()
        self.auto_status.config(text='Zmieniono próg. Ponów wykrywanie, aby zastosować go do obrysu i OCR.')
        if self.preview_job is not None:
            self.after_cancel(self.preview_job)
        self.preview_job=self.after(150,self.refresh_source_preview)

    def refresh_source_preview(self):
        self.preview_job=None
        self.draw_source()

    def draw_source(self):
        c = self.source_canvas
        c.delete('all')
        if self.source_image is None:
            return
        factor = 1 if self.full_size else max(1, ceil(self.source_image.width()/max(1,c.winfo_width()-20)), ceil(self.source_image.height()/max(1,c.winfo_height()-20)))
        image=self.source_image
        if self.binary_preview.get() and self.source_png:
            import pymupdf as fitz
            mask=monochrome(self.source_png,round(self.threshold.get()))
            samples=((~mask).astype('uint8')*255).tobytes()
            pix=fitz.Pixmap(fitz.csGRAY,mask.shape[1],mask.shape[0],samples,False)
            image=tk.PhotoImage(data=pix.tobytes('png'))
        self.display_image = image.subsample(factor, factor)
        self.image_factor = factor
        self.image_origin = (10, 10)
        c.create_image(10, 10, image=self.display_image, anchor='nw')
        c.configure(scrollregion=(0,0,max(c.winfo_width(),self.display_image.width()+20),max(c.winfo_height(),self.display_image.height()+20)))
        xy = [(10+x/factor,10+y/factor) for x,y in self.points]
        if len(xy)>1:
            line = xy + ([xy[0]] if self.closed else [])
            c.create_line(*[v for p in line for v in p], fill='#ce302d', width=2)
        if self.question_relation is not None:
            item=self.question_relation
            if item.get('image_line'):
                line=tuple(10+v/factor for v in item['image_line'])
            else:
                a,b=xy[item['start']],xy[item['end']]
                if item['axis']=='x':
                    line=(a[0],(a[1]+b[1])/2,b[0],(a[1]+b[1])/2)
                else:
                    line=((a[0]+b[0])/2,a[1],(a[0]+b[0])/2,b[1])
            if item.get('label_bounds'):
                bounds=tuple(10+v/factor for v in item['label_bounds'])
                c.create_rectangle(*bounds,outline='#f09000',width=3)
            c.create_line(*line,fill='#005de0',width=3,arrow='both')
        for i,(x,y) in enumerate(xy):
            c.create_oval(x-3,y-3,x+3,y+3,fill='#ce302d',outline='white')
            c.create_text(x+5,y-8,text=f'P{i+1}',fill='#a60000',anchor='w')

    def build(self):
        self.invalidate()
        if not self.closed:
            messagebox.showinfo('Kontur', 'Najpierw zaznacz narożniki i zamknij kontur.')
            return
        try:
            self.model = build_contour([dict(dx=dx.get(),dy=dy.get()) for dx,dy in self.edge_values], self.extra)
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
        c.create_polygon(*[v for p in screen for v in p],fill='#71b7dc',outline='#285b79',width=2)
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
            length=hypot(dx,dy)
            self.edge_table.insert('', 'end',values=(f'Bok {i+1}',mm(length)))
            nx,ny=-dy/length,dx/length
            if self.model.polygon.contains(Point((x+xx)/2+nx*.01,(y+yy)/2+ny*.01)):
                nx,ny=-nx,-ny
            ax,ay=screen[i];bx,by=screen[(i+1)%len(screen)]
            angle=90 if abs(dx)<.001 else 0
            label((ax+bx)/2+nx*19,(ay+by)/2+ny*19,mm(length),angle=angle,tag='edge-dimension')
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
