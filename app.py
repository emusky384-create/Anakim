"""NoAI-Watermark - GUI de escritorio (Windows)."""
import queue
import sys
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

SUPPORTED = (".png", ".jpg", ".jpeg", ".webp")
CTRLREGEN_ID = "yepengliu/ctrlregen"
DEFAULT_MODEL = "Lykon/dreamshaper-8"


class QueueStream:
    """Sustituye stdout/stderr (None en builds sin consola) por la cola de log."""
    def __init__(self, q):
        self.q, self.buf = q, ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf or "\r" in self.buf:
            idx = min(i for i in (self.buf.find("\n"), self.buf.find("\r")) if i >= 0)
            line, self.buf = self.buf[:idx].strip(), self.buf[idx + 1:]
            if line:
                self.q.put(("log", line))

    def flush(self):
        if self.buf.strip():
            self.q.put(("log", self.buf.strip()))
            self.buf = ""

    def isatty(self):
        return False


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NoAI-Watermark")
        self.geometry("860x700")
        self.minsize(760, 620)
        self.queue = queue.Queue()
        self.files = []
        self.stop_flag = threading.Event()
        self.worker = None

        self.out_dir = tk.StringVar()
        self.strength = tk.DoubleVar(value=0.15)
        self.steps = tk.IntVar(value=50)
        self.profile = tk.StringVar(value="default")
        self.device = tk.StringVar(value="auto")
        self.model = tk.StringVar(value=DEFAULT_MODEL)
        self.hf_token = tk.StringVar()
        self.suffix = tk.StringVar(value="_cleaned")

        self._build_ui()
        self.after(100, self._pump)

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        top = ttk.Frame(self)
        top.pack(fill="both", expand=True, **pad)

        bar = ttk.Frame(top)
        bar.pack(fill="x")
        ttk.Button(bar, text="Añadir imágenes", command=self.add_files).pack(side="left")
        ttk.Button(bar, text="Añadir carpeta", command=self.add_folder).pack(side="left", padx=6)
        ttk.Button(bar, text="Quitar", command=self.remove_sel).pack(side="left")
        ttk.Button(bar, text="Vaciar", command=self.clear_all).pack(side="left", padx=6)

        box = ttk.Frame(top)
        box.pack(fill="both", expand=True, pady=6)
        self.listbox = tk.Listbox(box, selectmode="extended", height=7)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        out = ttk.Frame(top)
        out.pack(fill="x")
        ttk.Label(out, text="Carpeta de salida:").pack(side="left")
        ttk.Entry(out, textvariable=self.out_dir).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(out, text="Elegir…", command=self.pick_out).pack(side="left")

        cfg = ttk.LabelFrame(self, text="Ajustes")
        cfg.pack(fill="x", **pad)

        r1 = ttk.Frame(cfg)
        r1.pack(fill="x", pady=3)
        ttk.Label(r1, text="Fuerza (0.04 mín · 0.15 normal · 0.7 máximo):").pack(side="left")
        ttk.Scale(r1, from_=0.0, to=1.0, variable=self.strength, length=260).pack(side="left", padx=8)
        self.lbl_str = ttk.Label(r1, text="0.15")
        self.lbl_str.pack(side="left")
        self.strength.trace_add("write", lambda *_: self.lbl_str.config(text=f"{self.strength.get():.2f}"))

        r2 = ttk.Frame(cfg)
        r2.pack(fill="x", pady=3)
        ttk.Label(r2, text="Pasos:").pack(side="left")
        ttk.Spinbox(r2, from_=10, to=150, textvariable=self.steps, width=6).pack(side="left", padx=6)
        ttk.Label(r2, text="Pipeline:").pack(side="left", padx=(16, 4))
        cb = ttk.Combobox(r2, textvariable=self.profile, values=("default", "ctrlregen"), width=12, state="readonly")
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", self._profile_changed)
        ttk.Label(r2, text="Dispositivo:").pack(side="left", padx=(16, 4))
        ttk.Combobox(r2, textvariable=self.device, values=("auto", "cpu", "cuda"), width=8, state="readonly").pack(side="left")

        r3 = ttk.Frame(cfg)
        r3.pack(fill="x", pady=3)
        ttk.Label(r3, text="Modelo HF:").pack(side="left")
        ttk.Entry(r3, textvariable=self.model).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Label(r3, text="Sufijo:").pack(side="left")
        ttk.Entry(r3, textvariable=self.suffix, width=12).pack(side="left", padx=6)

        r4 = ttk.Frame(cfg)
        r4.pack(fill="x", pady=3)
        ttk.Label(r4, text="HF token (opcional):").pack(side="left")
        ttk.Entry(r4, textvariable=self.hf_token, show="*").pack(side="left", fill="x", expand=True, padx=6)

        act = ttk.Frame(self)
        act.pack(fill="x", **pad)
        self.btn_run = ttk.Button(act, text="Eliminar marca de agua", command=self.start_regen)
        self.btn_run.pack(side="left")
        ttk.Button(act, text="Solo limpiar metadatos IA", command=self.start_meta).pack(side="left", padx=6)
        ttk.Button(act, text="Analizar metadatos", command=self.start_check).pack(side="left")
        self.btn_stop = ttk.Button(act, text="Detener", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=6)

        logf = ttk.LabelFrame(self, text="Registro")
        logf.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(logf, height=12, wrap="word", state="disabled")
        lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")

    def _profile_changed(self, _=None):
        self.model.set(CTRLREGEN_ID if self.profile.get() == "ctrlregen" else DEFAULT_MODEL)

    def add_files(self):
        for p in filedialog.askopenfilenames(
            title="Selecciona imágenes",
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.webp"), ("Todos", "*.*")],
        ):
            self._add(Path(p))

    def add_folder(self):
        d = filedialog.askdirectory(title="Carpeta con imágenes")
        if not d:
            return
        for p in sorted(Path(d).iterdir()):
            if p.suffix.lower() in SUPPORTED:
                self._add(p)

    def _add(self, p):
        if p.suffix.lower() not in SUPPORTED or str(p) in self.files:
            return
        self.files.append(str(p))
        self.listbox.insert("end", p.name)

    def remove_sel(self):
        for i in reversed(self.listbox.curselection()):
            self.listbox.delete(i)
            del self.files[i]

    def clear_all(self):
        self.listbox.delete(0, "end")
        self.files.clear()

    def pick_out(self):
        d = filedialog.askdirectory(title="Carpeta de salida")
        if d:
            self.out_dir.set(d)

    def write(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _pump(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self.write(payload)
                elif kind == "done":
                    self._finish(payload)
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def _target(self, src: Path) -> Path:
        base = Path(self.out_dir.get()) if self.out_dir.get() else src.parent
        return base / f"{src.stem}{self.suffix.get() or '_cleaned'}{src.suffix}"

    def _guard(self):
        if not self.files:
            messagebox.showinfo("Sin archivos", "Añade al menos una imagen.")
            return False
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("En curso", "Ya hay un proceso activo.")
            return False
        return True

    def _launch(self, fn):
        self.stop_flag.clear()
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.write("=" * 60)
        self.worker = threading.Thread(target=fn, daemon=True)
        self.worker.start()

    def _finish(self, ok):
        self.btn_run.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.write("Proceso finalizado.\n")

    def stop(self):
        self.stop_flag.set()
        self.write("Deteniendo tras la imagen actual…")

    # ── tareas ──
    def start_regen(self):
        if self._guard():
            self._launch(self._regen)

    def start_meta(self):
        if self._guard():
            self._launch(self._meta)

    def start_check(self):
        if self._guard():
            self._launch(self._check)

    def _regen(self):
        ok = True
        try:
            from watermark_remover import WatermarkRemover
            dev = self.device.get()
            self.write(f"Cargando modelo {self.model.get()} ({dev})…")
            remover = WatermarkRemover(
                model_id=self.model.get().strip(),
                device=dev,
                hf_token=self.hf_token.get().strip() or None,
                progress_callback=lambda m: self.queue.put(("log", m)),
            )
            remover.preload()
            for i, f in enumerate(self.files, 1):
                if self.stop_flag.is_set():
                    self.write("Cancelado por el usuario.")
                    break
                src = Path(f)
                dst = self._target(src)
                self.write(f"[{i}/{len(self.files)}] {src.name}")
                remover.remove_watermark(
                    image_path=src, output_path=dst,
                    strength=self.strength.get(),
                    num_inference_steps=int(self.steps.get()),
                )
        except Exception:
            ok = False
            self.write(traceback.format_exc())
        finally:
            self.queue.put(("done", ok))

    def _meta(self):
        ok = True
        try:
            from metadata_handler import remove_ai_metadata
            for i, f in enumerate(self.files, 1):
                src = Path(f)
                dst = self._target(src)
                dst.parent.mkdir(parents=True, exist_ok=True)
                remove_ai_metadata(src, dst)
                self.write(f"[{i}/{len(self.files)}] metadatos IA eliminados: {dst.name}")
        except Exception:
            ok = False
            self.write(traceback.format_exc())
        finally:
            self.queue.put(("done", ok))

    def _check(self):
        ok = True
        try:
            from metadata_handler import has_ai_metadata, extract_ai_metadata
            for f in self.files:
                p = Path(f)
                found = has_ai_metadata(p)
                self.write(f"{p.name}: {'CON metadatos IA' if found else 'limpio'}")
                if found:
                    for k, v in (extract_ai_metadata(p) or {}).items():
                        self.write(f"   {k}: {str(v)[:100]}")
        except Exception:
            ok = False
            self.write(traceback.format_exc())
        finally:
            self.queue.put(("done", ok))


if __name__ == "__main__":
    app = App()
    stream = QueueStream(app.queue)
    sys.stdout = stream
    sys.stderr = stream
    app.mainloop()
