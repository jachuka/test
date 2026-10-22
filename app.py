"""Uruchom: python app.py (Python 3.10+ z Tkinter)."""
import tkinter as tk
from tkinter import ttk, messagebox
from packing import calculate


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Formatki — kalkulator arkusza")
        self.geometry("1100x740")
        self.minsize(850, 600)
        self.layout = None
        self.dimensions = None
        panel = ttk.Frame(self, padding=20)
        panel.pack(side="left", fill="y")
        ttk.Label(panel, text="Kalkulator formatek", font=("Arial", 18, "bold")).pack(anchor="w", pady=(0, 20))
        self.fields = []
        for label, default in (("Szerokość arkusza [mm]", "2000"), ("Wysokość arkusza [mm]", "1000"), ("Szerokość formatki [mm]", "300"), ("Wysokość formatki [mm]", "200"), ("Odstęp między formatkami [mm]", "5"), ("Margines od każdego brzegu [mm]", "10")):
            ttk.Label(panel, text=label).pack(anchor="w", pady=(8, 3))
            entry = ttk.Entry(panel, width=30)
            entry.insert(0, default)
            entry.pack(fill="x")
            self.fields.append(entry)
        self.rotate = tk.BooleanVar(value=True)
        ttk.Checkbutton(panel, text="Zezwalaj na obrót o 90°", variable=self.rotate).pack(anchor="w", pady=16)
        ttk.Button(panel, text="Oblicz rozmieszczenie", command=self.compute).pack(fill="x")
        self.result = ttk.Label(panel, text="", wraplength=270, font=("Arial", 12))
        self.result.pack(anchor="w", pady=20)
        ttk.Label(panel, text="Układy pasowe: wynik może być niższy od optimum dla układów nieregularnych. Odstęp oznacza wolną przestrzeń między krawędziami; uwzględnij w nim szerokość cięcia.", wraplength=270).pack(anchor="w")
        right = ttk.Frame(self, padding=15)
        right.pack(side="right", fill="both", expand=True)
        ttk.Label(right, text="Podgląd arkusza • wszystkie wymiary w milimetrach").pack(anchor="w")
        self.canvas = tk.Canvas(right, background="#e9eef4", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, pady=12)
        self.canvas.bind("<Configure>", self.draw)
        self.bind("<Return>", lambda _: self.compute())
        self.compute()

    def compute(self):
        try:
            values = [float(e.get().strip().replace(",", ".")) for e in self.fields]
            layout = calculate(*values, rotate=self.rotate.get())
        except ValueError as exc:
            messagebox.showerror("Nieprawidłowe dane", str(exc))
            return
        self.layout, self.dimensions = layout, values
        w, h, pw, ph, gap, margin = values
        count = len(layout.rectangles)
        self.result.config(text=f"Liczba formatek: {count}\nWykorzystanie powierzchni: {count * pw * ph / (w * h):.1%}\n\n{layout.description}")
        self.draw()

    def draw(self, event=None):
        if self.layout is None:
            return
        c = self.canvas
        c.delete("all")
        w, h, _, _, _, margin = self.dimensions
        cw, ch = max(c.winfo_width(), 100), max(c.winfo_height(), 100)
        scale = min((cw - 60) / w, (ch - 70) / h)
        ox, oy = (cw - w * scale) / 2, (ch - h * scale) / 2
        c.create_rectangle(ox, oy, ox + w * scale, oy + h * scale, fill="white", outline="#34445a", width=2)
        if w > 2 * margin and h > 2 * margin:
            c.create_rectangle(ox + margin * scale, oy + margin * scale, ox + (w - margin) * scale, oy + (h - margin) * scale, outline="#d08030", dash=(4, 3))
        for x, y, pw, ph in self.layout.rectangles:
            c.create_rectangle(ox + x * scale, oy + y * scale, ox + (x + pw) * scale, oy + (y + ph) * scale, fill="#71b7dc", outline="#285b79")
        c.create_text(cw / 2, oy - 15, text=f"{w:g} mm")
        c.create_text(ox + w * scale + 16, ch / 2, text=f"{h:g} mm", angle=90)


if __name__ == "__main__":
    App().mainloop()
