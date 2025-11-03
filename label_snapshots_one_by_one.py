# file: label_snapshots_one_by_one_resizable_with_notes.py
# Requires: Python 3.x, Pillow -> pip install pillow
import os, re, csv, time, tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

# ==== CONFIG (adjust to your filenames) ====================================
SUBJECT_ID_REGEX = re.compile(r'^(?P<id>[^_]+)', re.IGNORECASE)  # default: before first underscore
TYPE_RULES = [
    ("noErode", re.compile(r'no[-_ ]?Erode', re.IGNORECASE)),
    ("innerErode",    re.compile(r'(?<!non)[-_ ]?innerErode', re.IGNORECASE)),
    ("wholebrain",     re.compile(r'wholebrain', re.IGNORECASE)),
]
VALID_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}
BTN_FONT = ("Arial", 20)
INFO_FONT = ("Arial", 14)
STATUS_FONT = ("Arial", 12)
# ==========================================================================

class OneByOneLabeler:
    def __init__(self, root):
        self.root = root
        self.root.title("Amyloid PET Snapshot Reading, Keys=(Y/N/U, ←/→, Notes=E)")
        self.root.minsize(1000, 750)

        folder = filedialog.askdirectory(title="Select folder with snapshots")
        if not folder:
            root.destroy(); return
        self.folder = folder

        # Collect images
        self.items = []
        for fn in sorted(os.listdir(folder)):
            p = os.path.join(folder, fn)
            if not os.path.isfile(p): continue
            ext = os.path.splitext(fn)[1].lower()
            if ext not in VALID_EXTS: continue
            sid = self._extract_subject_id(fn)
            stype = self._infer_type(fn)
            self.items.append({
                "filename": fn,
                "path": p,
                "subject_id": sid,
                "snapshot_type": stype
            })

        if not self.items:
            messagebox.showerror("No images", "No valid images found."); root.destroy(); return

        # Fresh session (no resume). Timestamped CSV.
        ts = time.strftime("%Y%m%d_%H%M%S")
        self.csv_path = os.path.join(folder, f"labels_{ts}.csv")
        self.labels = {}          # filename -> label ("yes"/"no"/"undefined"/"")
        self.notes  = {}          # filename -> notes text
        self.index = 0            # start at first image

        # ===== UI =====
        # Top info bar
        top = tk.Frame(root)
        top.pack(fill="x", padx=8, pady=6)
        self.info_var = tk.StringVar()
        tk.Label(top, textvariable=self.info_var, font=INFO_FONT).pack(side="left")

        # Resizable canvas for image
        self.canvas = tk.Canvas(root, bd=1, relief="sunken", highlightthickness=0, bg="#111")
        self.canvas.pack(fill="both", expand=True, padx=8, pady=8)

        # Buttons row
        btns = tk.Frame(root)
        btns.pack(pady=8)
        tk.Button(btns, text="← Prev",        width=10, font=BTN_FONT, command=self.prev_item).grid(row=0, column=0, padx=6)
        tk.Button(btns, text="Yes (Y)",       width=12, font=BTN_FONT, command=lambda: self.save_label("yes")).grid(row=0, column=1, padx=6)
        tk.Button(btns, text="No (N)",        width=12, font=BTN_FONT, command=lambda: self.save_label("no")).grid(row=0, column=2, padx=6)
        tk.Button(btns, text="Undefined (U)", width=14, font=BTN_FONT, command=lambda: self.save_label("undefined")).grid(row=0, column=3, padx=6)
        tk.Button(btns, text="Notes (E)",     width=12, font=BTN_FONT, command=self.edit_notes).grid(row=0, column=4, padx=6)
        tk.Button(btns, text="Next →",        width=10, font=BTN_FONT, command=self.next_item).grid(row=0, column=5, padx=6)

        # Status
        self.status_var = tk.StringVar()
        tk.Label(root, textvariable=self.status_var, fg="gray", font=STATUS_FONT).pack(pady=4)

        # Key bindings
        root.bind("<Left>",  lambda e: self.prev_item())
        root.bind("<Right>", lambda e: self.next_item())
        root.bind("y",       lambda e: self.save_label("yes"))
        root.bind("Y",       lambda e: self.save_label("yes"))
        root.bind("n",       lambda e: self.save_label("no"))
        root.bind("N",       lambda e: self.save_label("no"))
        root.bind("u",       lambda e: self.save_label("undefined"))
        root.bind("U",       lambda e: self.save_label("undefined"))
        root.bind("e",       lambda e: self.edit_notes())
        root.bind("E",       lambda e: self.edit_notes())

        # For scaling
        self._current_pil = None   # original PIL image for the current item
        self._photo = None         # Tk PhotoImage reference
        self.canvas.bind("<Configure>", lambda e: self._render_scaled())  # redraw on resize

        # Initial render
        self.render()
        self.root.after(50, self._render_scaled)

    # ---------- helpers ----------
    def _extract_subject_id(self, fn):
        m = SUBJECT_ID_REGEX.search(fn)
        return m.group("id") if m else ""

    def _infer_type(self, fn):
        for name, pat in TYPE_RULES:
            if pat.search(fn): return name
        low = fn.lower()
        if "erod" in low and "non" in low: return "noneroded"
        if "erod" in low: return "eroded"
        if "whole" in low: return "whole"
        return ""

    def _write_csv(self):
        fieldnames = ["filename","subject_id","snapshot_type","label","timestamp","path","notes"]
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            for it in self.items:
                fn = it["filename"]
                w.writerow({
                    "filename": fn,
                    "subject_id": it["subject_id"],
                    "snapshot_type": it["snapshot_type"],
                    "label": self.labels.get(fn, ""),
                    "timestamp": now,
                    "path": it["path"],
                    "notes": self.notes.get(fn, "")
                })

    # ---------- UI actions ----------
    def render(self):
        it = self.items[self.index]
        fn = it["filename"]
        stype = it["snapshot_type"] or "(unknown type)"
        sid = it["subject_id"] or "(no ID)"
        lab = self.labels.get(fn, "(unlabeled)")
        pos = f"{self.index+1}/{len(self.items)}"
        has_note = " 📝" if self.notes.get(fn) else ""
        self.info_var.set(f"{pos} | Subject: {sid} | Type: {stype} | File: {fn} | Label: {lab}{has_note}")

        try:
            self._current_pil = Image.open(it["path"]).convert("RGBA")
        except Exception as e:
            self._current_pil = None
            self.canvas.delete("all")
            self.canvas.create_text(
                self.canvas.winfo_width()//2 or 400,
                self.canvas.winfo_height()//2 or 300,
                text=f"Failed to load image:\n{fn}\n{e}",
                fill="white"
            )
            return

        self._render_scaled()

        done = sum(1 for it2 in self.items if self.labels.get(it2["filename"],""))
        self.status_var.set(f"Labeled {done}/{len(self.items)} | CSV: {os.path.basename(self.csv_path)}")

    def _render_scaled(self):
        if self._current_pil is None:
            return
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        margin = 16
        tw = max(1, cw - margin)
        th = max(1, ch - margin)
        iw, ih = self._current_pil.size
        scale = min(tw / iw, th / ih)
        new_w = max(1, int(iw * scale))
        new_h = max(1, int(ih * scale))
        img_resized = self._current_pil.resize((new_w, new_h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(img_resized)
        self.canvas.delete("all")
        self.canvas.create_image(cw//2, ch//2, image=self._photo, anchor="center")

    def save_label(self, label):
        fn = self.items[self.index]["filename"]
        self.labels[fn] = label
        self._write_csv()
        self.next_item()

    def prev_item(self):
        if self.index > 0:
            self.index -= 1
            self.render()

    def next_item(self):
        if self.index < len(self.items) - 1:
            self.index += 1
            self.render()

    def edit_notes(self):
        """Open a modal window to edit notes for the current image."""
        it = self.items[self.index]
        fn = it["filename"]
        existing = self.notes.get(fn, "")

        win = tk.Toplevel(self.root)
        win.title(f"Notes — {fn}")
        win.geometry("800x420")
        win.transient(self.root)
        win.grab_set()

        tk.Label(
            win,
            text=f"Subject: {it['subject_id']}   |   Type: {it['snapshot_type']}   |   File: {fn}",
            font=("Arial", 12)
        ).pack(anchor="w", padx=10, pady=6)

        frame = tk.Frame(win); frame.pack(fill="both", expand=True, padx=10, pady=6)
        scroll = tk.Scrollbar(frame)
        text = tk.Text(frame, wrap="word", yscrollcommand=scroll.set, font=("Arial", 13))
        scroll.config(command=text.yview)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.insert("1.0", existing)

        def do_save():
            self.notes[fn] = text.get("1.0", "end-1c")
            self._write_csv()
            win.destroy()
            # refresh info line to show 📝
            self.render()

        btns = tk.Frame(win); btns.pack(pady=8)
        tk.Button(btns, text="Save (Ctrl+Enter)", width=18, font=("Arial", 14), command=do_save).grid(row=0, column=0, padx=8)
        tk.Button(btns, text="Close (Esc)",       width=12, font=("Arial", 14), command=win.destroy).grid(row=0, column=1, padx=8)

        win.bind("<Control-Return>", lambda e: do_save())
        win.bind("<Escape>",         lambda e: win.destroy())

if __name__ == "__main__":
    root = tk.Tk()
    app = OneByOneLabeler(root)
    try:
        root.mainloop()
    except Exception as e:
        messagebox.showerror("Error", str(e))
