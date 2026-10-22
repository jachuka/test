"""Edytor dowolnego konturu wielokątnego ze szkicu, wyłącznie lokalny."""
import queue
import threading
from math import ceil, isfinite
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from sketch import build_contour, preview_png
from irregular import NestResult, export_pdf
from auto_sketch import detect_contours, topology, find_tesseract, ocr_numbers, match_dimensions, missing_dimension, known_dimension


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
        self.auto_questions = []
        self.question_relation = None

        self.model = None
        self.source_path = None
        self.source_image = None
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
        self.autoload = tk.BooleanVar(value=True)
        ttk.Checkbutton(panel,text='Odczytuj automatycznie po wczytaniu',variable=self.autoload).pack(anchor='w')
        self.detected_choice = ttk.Combobox(panel, state='disabled')
        self.detected_choice.pack(fill='x')
        self.detected_choice.bind('<<ComboboxSelected>>', self.choose_detection)
        self.auto_status = ttk.Label(panel, text='Obrys działa bez dodatkowych instalacji. OCR wymaga lokalnego Tesseract. Dane nie są wysyłane.', wraplength=325)
        self.auto_status.pack(anchor='w', pady=3)
        ttk.Button(panel, text='Uzupełnij tylko brakujące wymiary', command=self.ask_missing).pack(fill='x', pady=3)
        ttk.Label(panel, text='1. Klikaj narożniki po obwodzie (bez powtarzania pierwszego).\n2. Zamknij kontur.\n3. Wpisz różnice współrzędnych w mm lub wymiary między punktami.', wraplength=325).pack(anchor='w', pady=7)
        self.orthogonal = tk.BooleanVar(value=True)
        ttk.Checkbutton(panel, text='Podpowiadaj poziom/pion (tylko kierunek)', variable=self.orthogonal).pack(anchor='w')
        for text, command in [('Zamknij kontur', self.close_outline), ('Cofnij ostatni narożnik', self.undo), ('Wyczyść narożniki i wymiary', self.clear), ('Obróć szkic o 90°', self.rotate_preview), ('Podgląd 100% / dopasuj', self.toggle_size)]:
            ttk.Button(panel, text=text, command=command).pack(fill='x', pady=2)
        ttk.Label(panel, text='ΔX: w prawo +, w lewo −. ΔY: w dół +, w górę −.\n0 oznacza tę samą współrzędną. Puste pole = nieznany wymiar. Długości nie są mierzone z obrazka.', wraplength=325).pack(anchor='w', pady=7)
        self.edges_frame = ttk.Frame(panel)
        self.edges_frame.pack(fill='x')
        ttk.Label(panel, text='Wymiary dodatkowe / wyrównanie punktów:').pack(anchor='w', pady=(8, 2))
        self.extra_list = tk.Listbox(panel, height=4, width=36)
        self.extra_list.pack(fill='x')
        ttk.Button(panel, text='Dodaj wymiar między punktami', command=self.add_dimension).pack(fill='x', pady=2)
        ttk.Button(panel, text='Usuń zaznaczony wymiar', command=self.remove_dimension).pack(fill='x', pady=2)
        ttk.Button(panel, text='Zbuduj i sprawdź kontur', command=self.build).pack(fill='x', pady=8)
        self.confirm = tk.BooleanVar(value=False)
        ttk.Checkbutton(panel, text='Potwierdzam kontur i wymiary', variable=self.confirm, command=self.confirmed).pack(anchor='w')
        self.transfer = ttk.Button(panel, text='Zatwierdź i przejdź do układania', command=self.accept, state='disabled')
        self.transfer.pack(fill='x', pady=3)
        self.export = ttk.Button(panel, text='Zapisz sam kontur do PDF 1:1', command=self.save, state='disabled')
        self.export.pack(fill='x', pady=3)
        self.status = ttk.Label(panel, text='Obsługiwane są kontury z odcinków, w tym skośnych i wklęsłych. Łuki wymagają konturu wektorowego PDF. Brak automatycznego odczytu pisma.', wraplength=325)
        self.status.pack(anchor='w', pady=5)
        content = ttk.Frame(self, padding=8)
        content.pack(side='right', fill='both', expand=True)
        ttk.Label(content, text='Szkic: zaznacz kolejne narożniki; czerwone odcinki wskazują ich kolejność').pack(anchor='w')
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
        ttk.Label(content, text='Kontur obliczony z wymiarów — numeracja jest zgodna ze szkicem').pack(anchor='w', pady=(8, 2))
        self.canvas = tk.Canvas(content, background='#e9eef4', highlightthickness=0, height=280)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda _: self.draw())
        self.after(100, self.poll_auto)

    def invalidate(self, *args):
        self.version += 1
        self.model = None
        self.confirm.set(False)
        self.transfer.config(state='disabled')
        self.export.config(state='disabled')
        self.status.config(text='Zbuduj kontur z aktualnych wymiarów. Współrzędne kliknięć określają tylko kolejność i podpowiedź kierunku, nie długości.')
        self.draw()

    def load(self):
        path = filedialog.askopenfilename(filetypes=[('Szkic PDF lub obraz', '*.pdf *.png *.jpg *.jpeg *.bmp')])
        if not path:
            return
        try:
            image = tk.PhotoImage(data=preview_png(path))
        except Exception as exc:
            messagebox.showerror('Import szkicu', str(exc))
            return
        self.source_path, self.source_image = path, image
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
            png=preview_png(self.source_path,self.rotation)
        except Exception as exc:
            messagebox.showerror('Odczyt szkicu',str(exc));return
        executable=find_tesseract()
        self.ocr_available=bool(executable)
        self.invalidate()
        version=self.version
        self.auto_busy=True
        self.auto_button.config(state='disabled')
        self.auto_status.config(text='Wykrywanie obrysu i lokalny OCR…' if executable else 'Wykrywanie obrysu… Brak Tesseract; zapytam o wymiary, których nie da się wyliczyć.')
        def worker():
            try:
                detection=detect_contours(png)
                words=ocr_numbers(detection.mask,executable) if executable else []
                self.auto_queue.put((version,detection,words,None))
            except Exception as exc:
                self.auto_queue.put((version,None,[],str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def poll_auto(self):
        try:
            version,detection,words,error=self.auto_queue.get_nowait()
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
        ocr_note=' Brak Tesseract — cyfry trzeba uzupełnić.' if not self.ocr_available else (' OCR nie odczytał cyfr.' if not self.auto_words else '')
        self.auto_status.config(text=f'Wykryto {len(self.points)} narożników. OCR dopasował {len(accepted)} wymiarów; niepewne: {len(self.auto_questions)}.{ocr_note} Sprawdź czerwony obrys, potem uzupełnij tylko brakujące wymiary.')
        # Obrys musi być sprawdzony przed użyciem: użytkownik wybiera, kiedy
        # rozpocząć pytania, aby nie ukrywać czerwonego podglądu dialogiem.

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
            title=f"Wymiar P{question['start']+1} → P{question['end']+1} w osi {question['axis'].upper()}"
            text='Sprawdź niebieskie oznaczenie na szkicu. Podaj rzeczywistą odległość w mm (nie długość skośną).'
            if suggestion is not None:
                text+=f'\nOCR nie jest pewny: odczytał {suggestion:g}. Potwierdź lub popraw.'
            text+='\nAnuluj pozostawi kontur do dalszego uzupełnienia.'
            value=simpledialog.askfloat(title,text,initialvalue=suggestion,minvalue=0)
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
        if self.source_image is None or self.closed:
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
            image = tk.PhotoImage(data=preview_png(self.source_path, rotation))
        except Exception as exc:
            messagebox.showerror('Podgląd', str(exc))
            return
        self.rotation, self.source_image = rotation, image
        self.detection = None
        self.detected_choice.set('')
        self.detected_choice.config(state='disabled',values=())
        self.reset()

    def toggle_size(self):
        self.full_size = not self.full_size
        self.draw_source()

    def draw_source(self):
        c = self.source_canvas
        c.delete('all')
        if self.source_image is None:
            return
        factor = 1 if self.full_size else max(1, ceil(self.source_image.width()/max(1,c.winfo_width()-20)), ceil(self.source_image.height()/max(1,c.winfo_height()-20)))
        self.display_image = self.source_image.subsample(factor, factor)
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
            a,b=xy[item['start']],xy[item['end']]
            if item['axis']=='x':
                line=(a[0],(a[1]+b[1])/2,b[0],(a[1]+b[1])/2)
            else:
                line=((a[0]+b[0])/2,a[1],(a[0]+b[0])/2,b[1])
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
        if self.model is None:
            return
        d=self.model.dimensions
        w,h=d['width'],d['height']
        cw,ch=max(120,c.winfo_width()),max(120,c.winfo_height())
        scale=max(.001,min((cw-100)/w,(ch-80)/h))
        ox,oy=(cw-w*scale)/2,(ch-h*scale)/2
        c.create_polygon(*[v for x,y in self.model.polygon.exterior.coords for v in (ox+x*scale,oy+y*scale)],fill='#71b7dc',outline='#285b79',width=2)
        for i,(x,y) in enumerate(self.model.vertices):
            c.create_text(ox+x*scale+5,oy+y*scale-10,text=f'P{i+1}',anchor='w')
        c.create_text(cw/2,18,text=f'{w:g} × {h:g} mm')
        c.create_text(cw/2,ch-16,text=f'{len(self.model.vertices)} narożników • pole {self.model.polygon.area:g} mm²')

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
