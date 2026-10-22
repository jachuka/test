"""Wspomagane odtwarzanie szkicu: użytkownik określa typ i wymiary."""
from math import ceil
from pathlib import Path
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from sketch import build_shape, LABELS, preview_png
from irregular import NestResult, export_pdf
from sketch_ai import read_sketch, DEFAULT_MODEL


class SketchTab(ttk.Frame):
    def __init__(self, parent, on_accept):
        super().__init__(parent)
        self.on_accept = on_accept
        self.revision = 0
        self.ai_busy = False
        self.ai_messages = queue.Queue()
        self.api_key = os.environ.get('FORMATKI_OPENAI_API_KEY') or os.environ.get('OPENAI_API_KEY', '')
        self.ai_model = DEFAULT_MODEL
        self.ai_report = 'Nie wykonywano odczytu AI.'

        self.model = None
        self.source_path = None
        self.rotation = 0
        self.source_image = None
        self.display_image = None
        sidebar = ttk.Frame(self)
        sidebar.pack(side='left', fill='y')
        scroll_canvas = tk.Canvas(sidebar, width=345, highlightthickness=0)
        scrollbar = ttk.Scrollbar(sidebar, orient='vertical', command=scroll_canvas.yview)
        scrollbar.pack(side='right', fill='y')
        scroll_canvas.pack(side='left', fill='y', expand=True)
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        panel = ttk.Frame(scroll_canvas, padding=12)
        window = scroll_canvas.create_window((0, 0), window=panel, anchor='nw')
        panel.bind('<Configure>', lambda _: scroll_canvas.configure(scrollregion=scroll_canvas.bbox('all')))
        scroll_canvas.bind('<Configure>', lambda event: scroll_canvas.itemconfigure(window, width=event.width))
        ttk.Label(panel, text='Szkic → kontur', font=('Arial', 17, 'bold')).pack(anchor='w')
        ttk.Button(panel, text='Wczytaj szkic PDF / obraz', command=self.load).pack(fill='x', pady=6)
        self.source_label = ttk.Label(panel, text='Wczytaj szkic lub utwórz kontur z wymiarów.', wraplength=310)
        self.source_label.pack(anchor='w')
        self.rotate_source = ttk.Button(panel, text='Obróć podgląd szkicu o 90°', command=self.rotate_preview, state='disabled')
        self.rotate_source.pack(fill='x', pady=3)
        ttk.Button(panel, text='Ustawienia AI / klucz dostępu', command=self.ai_settings).pack(fill='x', pady=3)
        self.ai_button = ttk.Button(panel, text='Odczytaj szkic przez OpenAI', command=self.read_ai, state='disabled')
        self.ai_button.pack(fill='x', pady=3)
        ttk.Label(panel, text='Wysyła podgląd pierwszej strony do OpenAI. Wymaga internetu i środków na koncie API. Wynik zawsze sprawdź.', wraplength=310).pack(anchor='w')
        self.ai_status = ttk.Label(panel, text='AI: brak odczytu.', wraplength=310)
        self.ai_status.pack(anchor='w', pady=2)
        ttk.Button(panel, text='Pokaż odczyt AI i niejasności', command=self.show_report).pack(fill='x', pady=3)
        ttk.Label(panel, text='Typ kształtu (wybierz na podstawie szkicu):').pack(anchor='w', pady=(8, 2))
        self.kind = ttk.Combobox(panel, state='readonly', values=('U', 'L', 'Prostokąt'))
        self.kind.set('U')
        self.kind.pack(fill='x')
        self.kind.bind('<<ComboboxSelected>>', self.refresh_fields)
        self.values, self.rows = {}, {}
        for key, label in LABELS.items():
            frame = ttk.Frame(panel)
            frame.pack(fill='x', pady=3)
            ttk.Label(frame, text=label + ' [mm]').pack(anchor='w')
            variable = tk.StringVar()
            entry = ttk.Entry(frame, textvariable=variable)
            entry.pack(fill='x')
            variable.trace_add('write', self.invalidate)
            self.values[key] = variable
            self.rows[key] = (frame, entry)
        ttk.Label(panel, text='Pola pozostają puste, dopóki nie podasz wymiarów. Wymiary wycięcia są opcjonalne, jeśli wynikają z pozostałych; jeśli je podasz, sprawdzę zgodność.', wraplength=310).pack(anchor='w', pady=5)
        ttk.Button(panel, text='Zbuduj i sprawdź kontur', command=self.build).pack(fill='x', pady=4)
        self.confirm = tk.BooleanVar(value=False)
        ttk.Checkbutton(panel, text='Potwierdzam kształt i wymiary', variable=self.confirm, command=self.confirmed).pack(anchor='w', pady=3)
        self.transfer = ttk.Button(panel, text='Zatwierdź i przejdź do układania', command=self.accept, state='disabled')
        self.transfer.pack(fill='x', pady=3)
        self.export = ttk.Button(panel, text='Zapisz sam kontur do PDF 1:1', command=self.save, state='disabled')
        self.export.pack(fill='x', pady=3)
        self.status = ttk.Label(panel, text='Nie określaj wymiarów z proporcji zdjęcia.', wraplength=310)
        self.status.pack(anchor='w', pady=5)
        content = ttk.Frame(self, padding=8)
        content.pack(side='right', fill='both', expand=True)
        ttk.Label(content, text='Szkic źródłowy — podgląd bez skali pomiarowej').pack(anchor='w')
        self.source_canvas = tk.Canvas(content, background='#edf0f4', highlightthickness=0, height=280)
        self.source_canvas.pack(fill='both', expand=True)
        self.source_canvas.bind('<Configure>', lambda _: self.draw_source())
        ttk.Label(content, text='Odtworzony kontur — na podstawie zatwierdzanych wymiarów').pack(anchor='w', pady=(8, 2))
        self.canvas = tk.Canvas(content, background='#e9eef4', highlightthickness=0, height=280)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda _: self.draw())
        self.refresh_fields()
        self.after(100, self.poll_ai)

    def refresh_fields(self, event=None):
        kind = self.kind.get()
        active = {'width', 'height'}
        if kind in ('U', 'L'):
            active.update(('top', 'left', 'inner_width', 'inner_height'))
        if kind == 'U':
            active.add('right')
        for key, (_, entry) in self.rows.items():
            entry.config(state='normal' if key in active else 'disabled')
        self.invalidate()

    def invalidate(self, *args):
        self.revision += 1
        self.model = None
        if hasattr(self, 'confirm'):
            self.confirm.set(False)
            self.transfer.config(state='disabled')
            self.export.config(state='disabled')
            self.status.config(text='Wpisz wymiary i kliknij „Zbuduj i sprawdź kontur”.')
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
        self.rotate_source.config(state="normal")
        self.ai_button.config(state='disabled' if self.ai_busy else 'normal')
        self.ai_report = 'Nie wykonywano odczytu AI dla tego szkicu.'
        self.ai_status.config(text='AI: wczytano nowy szkic; poprzedni odczyt nie obowiązuje.')
        for variable in self.values.values():
            variable.set('')
        self.invalidate()
        self.source_label.config(text=f'{Path(path).name}\nWpisz typ i wymiary lub użyj przycisku odczytu AI. AI nie zatwierdza konturu.')
        self.draw_source()

    def rotate_preview(self):
        if not self.source_path:
            return
        rotation = (self.rotation + 90) % 360
        try:
            image = tk.PhotoImage(data=preview_png(self.source_path, rotation))
        except Exception as exc:
            messagebox.showerror('Podgląd szkicu', str(exc))
            return
        self.rotation, self.source_image = rotation, image
        self.invalidate()
        self.draw_source()

    def ai_settings(self):
        dialog = tk.Toplevel(self)
        dialog.title('OpenAI API — ustawienia tej sesji')
        dialog.transient(self.winfo_toplevel())
        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Klucz OpenAI API (nie hasło do ChatGPT):').pack(anchor='w')
        key = ttk.Entry(frame, show='•', width=55)
        key.insert(0, self.api_key)
        key.pack(fill='x', pady=5)
        ttk.Label(frame, text='Model z obsługą obrazu i Structured Outputs:').pack(anchor='w')
        model = ttk.Entry(frame)
        model.insert(0, self.ai_model)
        model.pack(fill='x', pady=5)
        ttk.Label(frame, text='Klucz pozostaje w pamięci do zamknięcia aplikacji. Nie jest zapisywany w plikach.\nKorzystanie z API rozliczane jest oddzielnie od abonamentu ChatGPT.', wraplength=420).pack(anchor='w', pady=8)
        def apply():
            self.api_key, self.ai_model = key.get().strip(), model.get().strip()
            dialog.destroy()
        ttk.Button(frame, text='Zastosuj na tę sesję', command=apply).pack(fill='x')
        dialog.grab_set()

    def read_ai(self):
        if self.ai_busy or not self.source_path:
            return
        if not self.api_key:
            self.ai_settings()
            return
        try:
            png = preview_png(self.source_path, self.rotation)
        except Exception as exc:
            messagebox.showerror('Podgląd dla AI', str(exc))
            return
        key, model = self.api_key, self.ai_model
        self.ai_busy = True
        self.ai_button.config(state='disabled')
        # Żaden poprzedni kontur nie pozostaje zatwierdzony podczas odczytu.
        self.invalidate()
        revision = self.revision
        self.ai_status.config(text='AI odczytuje szkic… zwykle kilkanaście sekund. Limit połączenia: 90 s.')
        def worker():
            try:
                result = read_sketch(png, key, model)
                self.ai_messages.put((revision, 'ok', result))
            except ValueError as exc:
                self.ai_messages.put((revision, 'error', str(exc)))
            except Exception:
                # Surowe błędy sieciowe i zawartość żądań nie trafiają do interfejsu.
                self.ai_messages.put((revision, 'error', 'Nie udało się odczytać szkicu. Spróbuj ponownie lub wpisz wymiary ręcznie.'))
        threading.Thread(target=worker, daemon=True).start()

    def poll_ai(self):
        try:
            revision, status, result = self.ai_messages.get_nowait()
        except queue.Empty:
            pass
        else:
            self.ai_busy = False
            self.ai_button.config(state='normal' if self.source_path else 'disabled')
            if revision != self.revision:
                self.ai_status.config(text='Odrzucono nieaktualny odczyt AI — szkic lub wymiary zostały zmienione. Możesz odczytać ponownie.')
            elif status == 'error':
                self.ai_status.config(text=result)
                messagebox.showerror('Odczyt AI', result)
            else:
                self.ai_report = result.report
                self.kind.set('' if result.kind == 'Nieznany' else result.kind)
                self.refresh_fields()
                for name, variable in self.values.items():
                    value = result.dimensions.get(name)
                    variable.set('' if value is None else f'{value:g}')
                self.ai_status.config(text='Odczytano propozycję. Sprawdź przypisanie wymiarów oraz raport niejasności. Nic nie zostało zatwierdzone.')
                try:
                    self.model = build_shape(self.kind.get(), {key: variable.get() for key, variable in self.values.items()})
                except ValueError as exc:
                    self.status.config(text=str(exc))
                else:
                    self.status.config(text='Kontur z propozycji AI. Porównaj wszystkie wymiary ze szkicem, dopiero potem zatwierdź.')
                    self.draw()
                self.show_report()
        self.after(100, self.poll_ai)

    def show_report(self):
        dialog = tk.Toplevel(self)
        dialog.title('Odczyt AI — propozycje i niejasności')
        dialog.geometry('650x500')
        text = tk.Text(dialog, wrap='word', padx=12, pady=12)
        scrollbar = ttk.Scrollbar(dialog, command=text.yview)
        scrollbar.pack(side='right', fill='y')
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(fill='both', expand=True)
        text.insert('1.0', self.ai_report)
        text.configure(state='disabled')

    def draw_source(self):
        c = self.source_canvas
        c.delete('all')
        if self.source_image is None:
            c.create_text(max(100, c.winfo_width()) / 2, max(100, c.winfo_height()) / 2, text='Tu pojawi się szkic klienta.')
            return
        factor = max(1, ceil(self.source_image.width() / max(1, c.winfo_width() - 16)), ceil(self.source_image.height() / max(1, c.winfo_height() - 16)))
        self.display_image = self.source_image.subsample(factor, factor)
        c.create_image(c.winfo_width() / 2, c.winfo_height() / 2, image=self.display_image)

    def build(self):
        self.invalidate()
        try:
            self.model = build_shape(self.kind.get(), {key: variable.get() for key, variable in self.values.items()})
        except ValueError as exc:
            self.status.config(text=str(exc))
            messagebox.showerror('Uzupełnij lub popraw wymiary', str(exc))
            return
        d = self.model.dimensions
        summary = f"Zewnętrzne: {d['width']:g} × {d['height']:g} mm"
        if 'inner_width' in d:
            summary += f"\nWycięcie: {d['inner_width']:g} × {d['inner_height']:g} mm"
        self.status.config(text=summary + '\nSprawdź podgląd i zaznacz potwierdzenie.')
        self.draw()

    def confirmed(self):
        state = 'normal' if self.model and self.confirm.get() else 'disabled'
        self.transfer.config(state=state)
        self.export.config(state=state)

    def draw(self):
        c = self.canvas
        c.delete('all')
        if self.model is None:
            return
        d = self.model.dimensions
        w, h = d['width'], d['height']
        cw, ch = max(120, c.winfo_width()), max(120, c.winfo_height())
        scale = min((cw - 130) / w, (ch - 100) / h)
        scale = max(scale, 0.001)
        ox, oy = (cw - w * scale) / 2, (ch - h * scale) / 2
        points = [v for x, y in self.model.polygon.exterior.coords for v in (ox + x * scale, oy + y * scale)]
        c.create_polygon(points, fill='#71b7dc', outline='#285b79', width=2)
        def label(x, y, text):
            # Białe tło ułatwia odczyt wymiarów również na wąskich ramionach.
            item = c.create_text(x, y, text=text, fill='#172b40')
            rect = c.create_rectangle(c.bbox(item), fill='white', outline='')
            c.tag_lower(rect, item)
        label(cw / 2, oy - 18, f'Szerokość zewnętrzna: {w:g} mm')
        c.create_text(ox - 22, ch / 2, text=f'Zewn. {h:g} mm', angle=90)
        if 'top' in d:
            label(cw / 2, oy + d['top'] * scale / 2, f"Poprzeczka {d['top']:g} mm")
            label(ox + d['left'] * scale / 2, oy + h * scale + 15, f"Lewe {d['left']:g}")
            if 'right' in d:
                label(ox + (w - d['right'] / 2) * scale, oy + h * scale + 15, f"Prawe {d['right']:g}")
            label(cw / 2, oy + (d['top'] + h) * scale / 2,
                  f"Wycięcie\n{d['inner_width']:g} × {d['inner_height']:g} mm")

    def accept(self):
        if self.model and self.confirm.get():
            self.on_accept(self.model.polygon)

    def save(self):
        if not self.model or not self.confirm.get():
            return
        path = filedialog.asksaveasfilename(defaultextension='.pdf', initialfile='Kontur_1do1.pdf', filetypes=[('PDF 1:1', '*.pdf')])
        if not path:
            return
        d = self.model.dimensions
        try:
            export_pdf(path, NestResult([self.model.polygon], d['width'], d['height'], 0, 0))
            messagebox.showinfo('Zapisano kontur', 'PDF ma zewnętrzne wymiary formatki. Zapisano kontur 1:1 bez opisów i linii wymiarowych.')
        except Exception as exc:
            messagebox.showerror('Eksport konturu', str(exc))
