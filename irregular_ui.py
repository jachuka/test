"""Zakładka importu obrysów i eksportu PDF."""
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
from math import isfinite
from shapely import affinity
from irregular import read_vector_pdf, read_scan, nest, export_pdf


class IrregularTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.contours = []
        self.shape = None
        self.result = None
        self.busy = False
        self.messages = queue.Queue()
        self.cancel = threading.Event()
        panel = ttk.Frame(self, padding=15)
        panel.pack(side='left', fill='y')
        ttk.Label(panel, text='Kształty nieregularne', font=('Arial', 17, 'bold')).pack(anchor='w')
        self.buttons = []
        for text, command in [('Wczytaj PDF wektorowy 1:1', self.load_vector), ('Wczytaj skan PDF / PNG / JPG', self.load_scan)]:
            button = ttk.Button(panel, text=text, command=command)
            button.pack(fill='x', pady=5)
            self.buttons.append(button)
        ttk.Label(panel, text='Obrys z pierwszej strony:').pack(anchor='w', pady=(8, 0))
        self.selector = ttk.Combobox(panel, state='readonly', width=36)
        self.selector.pack(fill='x')
        self.selector.bind('<<ComboboxSelected>>', self.select)
        self.source = ttk.Label(panel, text='Nie wczytano pliku.', wraplength=300)
        self.source.pack(anchor='w', pady=5)
        self.fields = []
        for label, default in [('Szerokość arkusza [mm]', '3050'), ('Wysokość arkusza [mm]', '2050'), ('Odstęp między formatkami [mm]', '5'), ('Margines od brzegu [mm]', '10')]:
            ttk.Label(panel, text=label).pack(anchor='w', pady=(6, 1))
            entry = ttk.Entry(panel)
            entry.insert(0, default)
            entry.pack(fill='x')
            self.fields.append(entry)
        self.rotate = tk.BooleanVar(value=True)
        ttk.Checkbutton(panel, text='Obroty 0°, 90°, 180°, 270°', variable=self.rotate).pack(anchor='w', pady=7)
        ttk.Label(panel, text='Jeden wybrany obrys, maksymalnie 1000 kopii.\nSzukanie trwa do 15 sekund.', wraplength=300).pack(anchor='w')
        self.run = ttk.Button(panel, text='Ułóż formatki', command=self.compute)
        self.run.pack(fill='x', pady=5)
        self.stop = ttk.Button(panel, text='Przerwij szukanie', command=self.cancel.set, state='disabled')
        self.stop.pack(fill='x')
        self.save = ttk.Button(panel, text='Zapisz układ do PDF 1:1', command=self.save_pdf, state='disabled')
        self.save.pack(fill='x', pady=5)
        self.status = ttk.Label(panel, text='Wczytaj i sprawdź obrys w podglądzie.', wraplength=300)
        self.status.pack(anchor='w', pady=5)
        ttk.Label(panel, text='Heurystyka — bez gwarancji optimum. Otwory są traktowane jako materiał. Krzywe przybliżane odcinkami (0,05 mm). Skan wymaga kontroli obrysu i kalibracji. Eksportuj i drukuj w skali 100%.', wraplength=300).pack(anchor='w', pady=5)
        self.canvas = tk.Canvas(self, background='#e9eef4', highlightthickness=0)
        self.canvas.pack(side='right', fill='both', expand=True, padx=15, pady=15)
        self.canvas.bind('<Configure>', lambda _: self.draw())
        self.after(100, self.poll)

    def load_vector(self):
        path = filedialog.askopenfilename(filetypes=[('PDF wektorowy', '*.pdf')])
        if not path:
            return
        try:
            contours = read_vector_pdf(path)
            self.loaded(contours, path, False)
        except Exception as exc:
            messagebox.showerror('Import PDF', str(exc))

    def load_scan(self):
        path = filedialog.askopenfilename(filetypes=[('PDF i obrazy', '*.pdf *.png *.jpg *.jpeg *.bmp')])
        if not path:
            return
        threshold = simpledialog.askinteger('Kontrast skanu', 'Próg ciemności 1–254 (domyślnie 180).\nCiemne obrysy na białym tle.', initialvalue=180, minvalue=1, maxvalue=254)
        if threshold is None:
            return
        try:
            contours = read_scan(path, threshold)
            self.loaded(contours, path, True)
        except Exception as exc:
            messagebox.showerror('Import skanu', str(exc))

    def loaded(self, contours, path, scan):
        self.contours = contours
        self.scan = scan
        labels = []
        for i, p in enumerate(contours):
            _, _, w, h = p.bounds
            labels.append(f'{i + 1}. {w:.2f} × {h:.2f} ' + ('px' if scan else 'mm'))
        self.selector['values'] = labels
        self.selector.current(0)
        self.source.config(text=f'{Path(path).name} — wybierz obrys i sprawdź jego kształt. Pozostałe obrysy nie są częścią formatki.')
        self.select()

    def select(self, event=None):
        if self.busy or self.selector.current() < 0:
            return
        self.shape = self.contours[self.selector.current()]
        self.result = None
        self.save.config(state='disabled')
        if self.scan:
            # Pokaż obrys przed pytaniem o jego rzeczywisty rozmiar.
            self.draw()
            self.update_idletasks()
            width = simpledialog.askfloat('Kalibracja skanu', 'Podaj rzeczywistą szerokość WYBRANEGO obrysu w mm.\nNie szerokość kartki ani całego obrazu.', minvalue=0.001)
            if width is None or not isfinite(width):
                self.shape = None
                self.status.config(text='Kalibracja anulowana. Wybierz obrys ponownie.')
                self.draw()
                return
            factor = width / self.shape.bounds[2]
            self.shape = affinity.scale(self.shape, xfact=factor, yfact=factor, origin=(0, 0))
        w, h = self.shape.bounds[2:]
        self.status.config(text=f'Podgląd jednej formatki: {w:.2f} × {h:.2f} mm.\nSprawdź obrys przed układaniem.')
        self.draw()

    def compute(self):
        if self.busy:
            return
        if self.shape is None:
            messagebox.showinfo('Brak obrysu', 'Najpierw wczytaj i wybierz obrys.')
            return
        try:
            values = [float(e.get().strip().replace(',', '.')) for e in self.fields]
            if not all(isfinite(v) for v in values) or min(values[:2]) <= 0 or min(values[2:]) < 0:
                raise ValueError('Wymiary muszą być dodatnie, odstęp i margines nieujemne.')
        except ValueError as exc:
            messagebox.showerror('Nieprawidłowe dane', str(exc))
            return
        self.busy = True
        self.cancel.clear()
        for button in self.buttons + [self.run, self.save]:
            button.config(state='disabled')
        self.selector.config(state='disabled')
        self.stop.config(state='normal')
        self.status.config(text='Szukanie układu… do 15 sekund. Możesz przerwać.')
        shape, rotate = self.shape, self.rotate.get()
        def worker():
            try:
                self.messages.put(('ok', nest(shape, *values, rotate=rotate, cancel=self.cancel)))
            except Exception as exc:
                self.messages.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            kind, value = self.messages.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            for button in self.buttons + [self.run]:
                button.config(state='normal')
            self.selector.config(state='readonly')
            self.stop.config(state='disabled')
            if kind == 'error':
                self.status.config(text='Obliczenie nie powiodło się.')
                self.save.config(state='normal' if self.result and self.result.shapes else 'disabled')
                messagebox.showerror('Układanie', value)
            else:
                self.result = value
                count = len(value.shapes)
                area = sum(p.area for p in value.shapes)
                self.status.config(text=f'Znaleziono: {count} formatek\nWykorzystanie: {area / (value.width * value.height):.1%}\nArkusz wyniku: {value.width:g} × {value.height:g} mm\nOdstęp: {value.gap:g}, margines: {value.margin:g} mm\n' + ('Osiągnięto limit / przerwano — wynik częściowy.' if value.limited else 'Zakończono szukanie heurystyczne.'))
                self.save.config(state='normal' if count else 'disabled')
                self.draw()
        self.after(100, self.poll)

    def draw(self):
        c = self.canvas
        c.delete('all')
        if self.result:
            w, h, polys = self.result.width, self.result.height, self.result.shapes
            caption = 'Układ wynikowy — eksport PDF zapisuje ten układ'
        elif self.shape is not None:
            w, h = self.shape.bounds[2:]
            polys = [self.shape]
            caption = 'Podgląd wybranego obrysu'
        else:
            return
        cw, ch = max(120, c.winfo_width()), max(120, c.winfo_height())
        scale = min((cw - 60) / w, (ch - 80) / h)
        ox, oy = (cw - w * scale) / 2, (ch - h * scale) / 2 + 10
        c.create_text(cw / 2, 18, text=caption)
        c.create_rectangle(ox, oy, ox + w * scale, oy + h * scale, fill='white', outline='#34445a')
        if self.result and 2 * self.result.margin < min(w, h):
            m = self.result.margin
            c.create_rectangle(ox + m * scale, oy + m * scale, ox + (w - m) * scale, oy + (h - m) * scale, outline='#d08030', dash=(4, 3))
        for poly in polys:
            points = [v for x, y in poly.exterior.coords for v in (ox + x * scale, oy + y * scale)]
            c.create_polygon(points, fill='#71b7dc', outline='#285b79')
        c.create_text(cw / 2, ch - 15, text=f'{w:.2f} × {h:.2f}' + (' px (przed kalibracją)' if self.result is None and getattr(self, 'scan', False) and self.shape is not None and self.shape in self.contours else ' mm'))

    def save_pdf(self):
        if self.busy or not self.result or not self.result.shapes:
            return
        path = filedialog.asksaveasfilename(defaultextension='.pdf', filetypes=[('PDF 1:1', '*.pdf')], initialfile='Uklad_formatek.pdf')
        if not path:
            return
        try:
            export_pdf(path, self.result)
            messagebox.showinfo('Eksport zakończony', 'Zapisano układ w skali 1:1.\nPrzy druku wybierz 100% / rzeczywisty rozmiar, bez dopasowania do strony.')
        except Exception as exc:
            messagebox.showerror('Eksport PDF', str(exc))
