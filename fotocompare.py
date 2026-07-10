import os, sys, hashlib, shutil, json, re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from PIL import Image, ExifTags
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

CONFIG_FILE = Path.home() / ".fotocompare_config.json"
APP_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
IMG_EXTS = {'.jpg','.jpeg','.png','.webp','.bmp','.tiff','.tif','.gif','.heic','.heif'}

def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}

def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

def hash_file(path, full=False):
    if full:
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read(65536)).hexdigest()

def get_exif_date(path):
    if not HAS_PILLOW:
        return None
    try:
        img = Image.open(path)
        exif = img.getexif()
        tags = dict(exif.items())
        if hasattr(exif, 'get_ifd'):
            tags.update(exif.get_ifd(0x8769))
        for tag_id, value in tags.items():
            name = ExifTags.TAGS.get(tag_id, '')
            if name in ('DateTimeOriginal', 'DateTime'):
                return str(value)
    except Exception:
        pass
    return None

def parse_date_str(s):
    for fmt in ('%Y:%m:%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y:%m:%d'):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None

def is_generic_name(name):
    stem = Path(name).stem
    patterns = [
        r'^[fF][oO][tT][oO]\d+$', r'^[iI][mM][gG]_\d+$',
        r'^[iI][mM][gG]\d+$', r'^[dD][sS][cC][fF]\d+$',
        r'^[dD][sS][cC]\d+$', r'^[pP][iI][cC]\d+$',
        r'^[pP][hH][oO][tT][oO]\d+$', r'^[iI][mM][aA][gG][eE]\d+$',
        r'^[iI][mM][gG][eE]\d+$', r'^[fF][oO][tT][oO]\d+$',
        r'^[uU][nN][tT][iI][tT][lL][eE][dD]\d*$',
    ]
    return any(re.match(p, stem) for p in patterns)

def get_trash_dir():
    if sys.platform == 'linux':
        return Path.home() / '.local' / 'share' / 'Trash' / 'files'
    elif sys.platform == 'darwin':
        return Path.home() / '.Trash'
    elif sys.platform == 'win32':
        return None
    return Path.home() / '.Trash'

def walk_images(root):
    for p in Path(root).rglob('*'):
        if p.is_file() and p.suffix.lower() in IMG_EXTS:
            yield p


class FotocompareApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FOTO COMPARE")
        try:
            icon_path = APP_DIR / 'pngaaa.com-4830752.png'
            if icon_path.exists():
                icon = tk.PhotoImage(file=str(icon_path))
                self.root.iconphoto(True, icon)
            self.root.iconphoto(True, icon)
        except Exception:
            pass
        self.root.geometry("850x650")
        self.root.minsize(700, 500)
        self.config = load_config()
        self.duplicates = []
        self.src_hashes = {}
        self.setup_ui()

    def setup_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # Source
        row = 0
        ttk.Label(main, text="Sorgente (originali):").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.src_var = tk.StringVar()
        recent = self.config.get('recent', [])
        if len(recent) > 0:
            self.src_var.set(recent[0])
        ttk.Entry(main, textvariable=self.src_var, width=60).grid(row=row, column=1, padx=5, sticky=tk.EW)
        ttk.Button(main, text="Sfoglia", command=lambda: self.browse(self.src_var)).grid(row=row, column=2)

        # Target
        row = 1
        ttk.Label(main, text="Target (da scan):").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.tgt_var = tk.StringVar()
        if len(recent) > 1:
            self.tgt_var.set(recent[1])
        ttk.Entry(main, textvariable=self.tgt_var, width=60).grid(row=row, column=1, padx=5, sticky=tk.EW)
        ttk.Button(main, text="Sfoglia", command=lambda: self.browse(self.tgt_var)).grid(row=row, column=2)

        # Buttons
        row = 2
        btnf = ttk.Frame(main)
        btnf.grid(row=row, column=0, columnspan=3, pady=8, sticky=tk.W)
        ttk.Button(btnf, text="Scan", command=self.scan).pack(side=tk.LEFT, padx=2)
        self.rename_btn = ttk.Button(btnf, text="Rinomina source", command=self.rename_source_files, state=tk.DISABLED)
        self.rename_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(btnf, text="Info", command=self.show_info).pack(side=tk.LEFT, padx=2)

        # Progress
        row = 3
        self.prog = ttk.Progressbar(main, mode='indeterminate')
        self.prog.grid(row=row, column=0, columnspan=3, sticky=tk.EW, pady=4)
        self.prog.grid_remove()

        # Tree
        row = 4
        cols = ('file', 'src_match', 'size', 'hash')
        self.tree = ttk.Treeview(main, columns=cols, show='headings', height=12)
        self.tree.heading('file', text='File duplicato (target)')
        self.tree.heading('src_match', text='Match in source')
        self.tree.heading('size', text='Dimensione')
        self.tree.heading('hash', text='Hash (64KB)')
        self.tree.column('file', width=350)
        self.tree.column('src_match', width=300)
        self.tree.column('size', width=90)
        self.tree.column('hash', width=90)
        self.tree.grid(row=row, column=0, columnspan=3, sticky=tk.NSEW, pady=5)

        sb = ttk.Scrollbar(main, orient=tk.VERTICAL, command=self.tree.yview)
        sb.grid(row=row, column=3, sticky=tk.NS)
        self.tree.configure(yscrollcommand=sb.set)

        main.grid_rowconfigure(row, weight=1)
        main.grid_columnconfigure(1, weight=1)

        # Status
        row = 5
        self.status = ttk.Label(main, text="Pronto")
        self.status.grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=2)

        # Bind selection
        self.tree.bind('<<TreeviewSelect>>', self.on_select)

    def browse(self, var):
        d = filedialog.askdirectory(title="Seleziona directory")
        if d:
            var.set(d)

    def set_status(self, msg):
        self.status.config(text=msg)
        self.root.update_idletasks()

    def show_info(self):
        n = len(self.tree.get_children())
        messagebox.showinfo("Fotocompare", f"Duplicati trovati: {n}")

    def on_select(self, event):
        pass

    def scan(self):
        src = self.src_var.get()
        tgt = self.tgt_var.get()
        if not src or not tgt:
            messagebox.showerror("Errore", "Seleziona entrambe le directory")
            return
        if not Path(src).is_dir():
            messagebox.showerror("Errore", f"Sorgente non valida:\n{src}")
            return
        if not Path(tgt).is_dir():
            messagebox.showerror("Errore", f"Target non valida:\n{tgt}")
            return

        # Save recent
        cfg = load_config()
        cfg['recent'] = [src, tgt]
        save_config(cfg)

        # Clear
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.duplicates = []
        self.src_hashes = {}
        self.rename_btn.config(state=tk.DISABLED)

        self.prog.grid()
        self.prog.start()
        self.set_status("Indicizzazione source...")

        # Build source hash map: (size, hash64k) -> path
        src_files = list(walk_images(src))
        self.src_hashes = {}
        with ThreadPoolExecutor(max_workers=8) as pool:
            fut_map = {pool.submit(hash_file, f, False): f for f in src_files}
            for fut in as_completed(fut_map):
                f = fut_map[fut]
                try:
                    h = fut.result()
                except Exception:
                    continue
                sz = f.stat().st_size
                self.src_hashes.setdefault(sz, {})[h] = f

        # Scan target
        self.set_status("Scansione target per duplicati...")
        tgt_files = list(walk_images(tgt))
        dups = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            fut_map = {pool.submit(hash_file, f, False): f for f in tgt_files}
            for fut in as_completed(fut_map):
                f = fut_map[fut]
                try:
                    h = fut.result()
                except Exception:
                    continue
                sz = f.stat().st_size
                if sz in self.src_hashes and h in self.src_hashes[sz]:
                    src_match = self.src_hashes[sz][h]
                    dups.append((src_match, f, sz, h))

        self.prog.stop()
        self.prog.grid_remove()

        if not dups:
            self.set_status("Nessun duplicato trovato")
            messagebox.showinfo("Risultato", "Nessun duplicato trovato")
            return

        for src_match, dup_file, sz, h in dups:
            self.tree.insert('', tk.END, values=(
                str(dup_file.parent.name) + '/' + dup_file.name,
                str(src_match.parent.name) + '/' + src_match.name,
                f"{sz // 1024} KB",
                h[:12]
        ))

        self.duplicates = dups
        self.rename_btn.config(state=tk.NORMAL if any(is_generic_name(f.name) for _, f, _, _ in dups) else tk.NORMAL)
        self.set_status(f"Trovati {len(dups)} duplicati")
        self.ask_destination()

    def ask_destination(self):
        win = tk.Toplevel(self.root)
        win.title("Sposta duplicati")
        win.geometry("550x180")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        ttk.Label(win, text="Destinazione file duplicati:", font=('', 10, 'bold')).pack(pady=(15,5))

        dest_var = tk.StringVar()
        trash = get_trash_dir()
        if trash:
            dest_var.set(str(trash))
        else:
            dest_var.set(str(Path.home() / "Duplicati"))

        f = ttk.Frame(win, padding=5)
        f.pack(fill=tk.X, padx=15)
        ttk.Entry(f, textvariable=dest_var, width=55).pack(side=tk.LEFT, padx=3)
        ttk.Button(f, text="Sfoglia", command=lambda: dest_var.set(filedialog.askdirectory(title="Scegli destinazione") or dest_var.get())).pack(side=tk.LEFT)

        bf = ttk.Frame(win)
        bf.pack(pady=15)
        ttk.Button(bf, text="Sposta duplicati", command=lambda: self.move_duplicates(dest_var.get(), win)).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="Annulla", command=win.destroy).pack(side=tk.LEFT, padx=5)

    def move_duplicates(self, dest, win):
        if not dest:
            messagebox.showerror("Errore", "Nessuna destinazione selezionata")
            return
        dp = Path(dest)
        try:
            dp.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile creare destinazione:\n{e}")
            return

        moved = 0
        for src_match, dup_file, _, _ in self.duplicates:
            try:
                target = dp / dup_file.name
                if target.exists():
                    stem, ext = dup_file.stem, dup_file.suffix
                    c = 1
                    while target.exists():
                        target = dp / f"{stem}_{c}{ext}"
                        c += 1
                shutil.move(str(dup_file), str(target))
                moved += 1
            except Exception as e:
                messagebox.showerror("Errore", f"Spostamento fallito: {dup_file.name}\n{e}")

        win.destroy()
        self.set_status(f"Spostati {moved}/{len(self.duplicates)} duplicati in {dest}")
        if moved:
            # Refresh tree: remove moved entries
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.duplicates = []
            messagebox.showinfo("Completato", f"Spostati {moved} file duplicati in:\n{dest}")

    def rename_source_files(self):
        src = Path(self.src_var.get())
        if not src.is_dir():
            return

        to_rename = [f for f in src.rglob('*') if f.is_file() and f.suffix.lower() in IMG_EXTS and is_generic_name(f.name)]
        if not to_rename:
            messagebox.showinfo("Rinomina", "Nessun file con nome generico trovato in source")
            return

        renamed = 0
        skipped = 0
        changes = []

        for f in to_rename:
            dt = get_exif_date(f)
            if not dt:
                skipped += 1
                continue
            parsed = parse_date_str(dt)
            if not parsed:
                skipped += 1
                continue
            new_name = parsed.strftime("%Y-%m-%d_%H%M%S") + f.suffix.lower()
            new_path = f.parent / new_name
            if new_path.exists():
                c = 1
                while new_path.exists():
                    new_path = f.parent / f"{parsed.strftime('%Y-%m-%d_%H%M%S')}_{c}{f.suffix.lower()}"
                    c += 1
            changes.append((f, new_path))

        if not changes:
            messagebox.showinfo("Rinomina", f"Nessun file rinominabile. {skipped} senza EXIF data scatto.")
            return

        # Preview
        lines = [f"{f.name} → {p.name}" for f, p in changes]
        preview = "\n".join(lines[:30])
        if len(lines) > 30:
            preview += f"\n... e altri {len(lines)-30}"

        ok = messagebox.askyesno("Rinomina anteprima",
            f"Rinominare {len(changes)} file?\n{skipped} saltati (no EXIF).\n\n{preview}")
        if not ok:
            return

        for f, new_path in changes:
            try:
                f.rename(new_path)
                renamed += 1
            except Exception as e:
                messagebox.showerror("Errore", f"Rinomina fallita: {f.name}\n{e}")

        self.set_status(f"Rinominati {renamed} file, saltati {skipped}")
        messagebox.showinfo("Completato", f"Rinominati: {renamed}\nSaltati (no EXIF): {skipped}")


def main():
    root = tk.Tk()
    app = FotocompareApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
