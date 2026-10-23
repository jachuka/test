"""Powiększany podgląd obrazka; zmienia wyłącznie sposób wyświetlania."""
from math import isfinite, sqrt
import tkinter as tk
from tkinter import ttk
import pymupdf as fitz


MAX_SCALE = 4.0
MAX_PIXELS = 24_000_000


def bounded_scale(width, height, requested):
    """Ogranicz pamięć podglądu, nie zmieniając źródłowych współrzędnych."""
    if width <= 0 or height <= 0 or not isfinite(requested) or requested <= 0:
        raise ValueError('Nieprawidłowy rozmiar lub skala podglądu.')
    limit = min(MAX_SCALE, sqrt(MAX_PIXELS / (width * height)))
    return min(limit, max(.05, requested))


def render_png(png, scale):
    """Przeskaluj PNG na potrzeby ekranu. bounded_scale podaje użyty mnożnik."""
    pix = fitz.Pixmap(png)
    scale = bounded_scale(pix.width, pix.height, scale)
    width, height = max(1, round(pix.width * scale)), max(1, round(pix.height * scale))
    if width != pix.width or height != pix.height:
        pix = fitz.Pixmap(pix, width, height)
    return pix.tobytes('png')


def photo_from_png(png, scale, master=None):
    return tk.PhotoImage(master=master, data=render_png(png, scale))


class ZoomPreview(ttk.Frame):
    """Podgląd z paskami, przybliżaniem przy kursorze i przeciąganiem obrazu."""
    def __init__(self, parent, png, width=460, height=260):
        super().__init__(parent)
        self.png = None
        self.photo = None
        self.scale = 1.0
        self._fit_mode = True
        self._resize_job = None
        self._requested_size = width, height
        toolbar = ttk.Frame(self)
        toolbar.pack(fill='x', pady=(0, 3))
        for text, command, button_width in (
            ('−', lambda: self.zoom(1/1.25), 3),
            ('+', lambda: self.zoom(1.25), 3),
            ('100%', self.actual_size, 6),
            ('Dopasuj', self.fit, 8),
        ):
            ttk.Button(toolbar, text=text, command=command, width=button_width,
                       takefocus=False).pack(side='left', padx=(0, 3))
        self.scale_label = ttk.Label(toolbar, text='100%')
        self.scale_label.pack(side='left', padx=5)
        holder = ttk.Frame(self)
        holder.pack(fill='both', expand=True)
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(holder, width=width, height=height,
                                background='white', highlightthickness=1,
                                highlightbackground='#c4cbd1', takefocus=False)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        horizontal = ttk.Scrollbar(holder, orient='horizontal', command=self.canvas.xview)
        vertical = ttk.Scrollbar(holder, orient='vertical', command=self.canvas.yview)
        horizontal.grid(row=1, column=0, sticky='ew')
        vertical.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        self.canvas.bind('<Configure>', self._resized)
        self.canvas.bind('<MouseWheel>', self._wheel)
        self.canvas.bind('<Button-4>', lambda e: self._wheel(e, 1))
        self.canvas.bind('<Button-5>', lambda e: self._wheel(e, -1))
        self.canvas.bind('<ButtonPress-1>', self._pan_start)
        self.canvas.bind('<B1-Motion>', self._pan_move)
        self.canvas.bind('<ButtonRelease-1>', lambda _: self.canvas.configure(cursor=''))
        ttk.Label(self, text='Kółko myszy: przybliżanie. Przeciągnij obraz, aby go przesunąć.',
                  wraplength=width).pack(anchor='w', pady=(3, 0))
        self.bind('<Destroy>', self._destroyed, add='+')
        self.set_image(png)

    def set_image(self, png):
        pix = fitz.Pixmap(png)
        self.png = png
        self.image_width, self.image_height = pix.width, pix.height
        self._fit_mode = True
        self.fit()

    def _viewport(self):
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        return (width if width > 1 else self._requested_size[0],
                height if height > 1 else self._requested_size[1])

    def fit(self):
        if self.png is None:
            return
        width, height = self._viewport()
        self._fit_mode = True
        # Mały fragment powiększamy również przy pierwszym otwarciu.
        self._render(min(3.0, max(1, width-4)/self.image_width,
                         max(1, height-4)/self.image_height))
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def actual_size(self):
        self._change_scale(1.0)

    def zoom(self, factor, anchor=None):
        self._change_scale(self.scale * factor, anchor)

    def _change_scale(self, scale, anchor=None):
        if self.png is None:
            return
        width, height = self._viewport()
        x, y = anchor if anchor is not None else (width/2, height/2)
        source = self.canvas.canvasx(x)/self.scale, self.canvas.canvasy(y)/self.scale
        self._fit_mode = False
        self._render(scale)
        world_width = max(width, self.photo.width())
        world_height = max(height, self.photo.height())
        self.canvas.xview_moveto((source[0]*self.scale-x)/world_width)
        self.canvas.yview_moveto((source[1]*self.scale-y)/world_height)

    def _render(self, scale):
        self.scale = bounded_scale(self.image_width, self.image_height, scale)
        self.photo = photo_from_png(self.png, self.scale, master=self.canvas)
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, image=self.photo, anchor='nw')
        width, height = self._viewport()
        self.canvas.configure(scrollregion=(0, 0, max(width, self.photo.width()),
                                            max(height, self.photo.height())))
        self.scale_label.configure(text=f'{self.scale*100:.0f}%')

    def _wheel(self, event, direction=None):
        if direction is None:
            delta = getattr(event, 'delta', 0)
            if not delta:
                return 'break'
            direction = 1 if delta > 0 else -1
        self.zoom(1.25 if direction > 0 else 1/1.25, (event.x, event.y))
        return 'break'

    def _pan_start(self, event):
        self.canvas.scan_mark(event.x, event.y)
        self.canvas.configure(cursor='fleur')

    def _pan_move(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _resized(self, event):
        if self._fit_mode and self.png is not None:
            if self._resize_job is not None:
                self.after_cancel(self._resize_job)
            self._resize_job = self.after_idle(self._resize_fit)

    def _resize_fit(self):
        self._resize_job = None
        if self._fit_mode:
            self.fit()

    def _destroyed(self, event):
        if event.widget is self and self._resize_job is not None:
            self.after_cancel(self._resize_job)
            self._resize_job = None


class OverlayZoomPreview(ZoomPreview):
    """Powiększany obraz z ostrą nakładką wektorową w układzie źródła.

    callback overlay(canvas, scale) dodaje tylko elementy nakładki. Dzięki
    osobnemu odświeżaniu obrazu nie trzeba ponownie przeliczać, gdy zmieniają
    się punkty albo wskazany wymiar; aktualny zoom i przewinięcie pozostają.
    """
    def __init__(self, parent, png, overlay, width=900, height=600):
        self.overlay = overlay
        self._overlay_items = set()
        super().__init__(parent, png, width=width, height=height)

    def _render(self, scale):
        super()._render(scale)
        self.refresh_overlay()

    def refresh_overlay(self):
        if self._overlay_items:
            self.canvas.delete(*self._overlay_items)
        before = set(self.canvas.find_all())
        self.overlay(self.canvas, self.scale)
        self._overlay_items = set(self.canvas.find_all()) - before
