"""FundoLimpo — remove o fundo da webcam (sem fundo verde) e entrega numa câmera virtual.

Fluxo: webcam -> RVM (recorte com transparência) -> fundo novo (desfoque / imagem / cor) -> câmera virtual
(a "FundoLimpo Camera", própria do app — aparece como webcam no OBS, Streamlabs, Discord, Teams, Meet, Zoom etc.).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time

import cv2
import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "fundolimpo"

from fundolimpo.compose import Compositor          # noqa: E402
from fundolimpo.matting import Matter              # noqa: E402
from fundolimpo import vcam as vcam_mod            # noqa: E402
from fundolimpo import updater                     # noqa: E402

APP = "FundoLimpo"
VERSION = "1.2.0"
RESOLUTIONS = {"640 x 480": (640, 480), "1280 x 720 (HD)": (1280, 720), "1920 x 1080 (Full HD)": (1920, 1080)}
QUALITIES = {"Máxima qualidade": "maxima", "Equilibrada": "equilibrada", "Rápida (PC fraco)": "rapida"}
EFFECTS = {"Desfocar o fundo": "desfoque", "Imagem de fundo": "imagem", "Cor sólida": "cor"}
OWN_OUTPUTS = ("obs virtual", "unity video capture", "fundolimpo")  # nunca usar a própria saída como entrada

DEFAULTS = {
    "camera": 0, "camera_name": "", "resolution": "1280 x 720 (HD)", "fps": 30, "quality": "equilibrada",
    "effect": "desfoque", "blur": 60, "image": "", "color": [0, 177, 64], "firmeza": 0,
    "force_cpu": False, "enabled": True,
}


# ── configurações ────────────────────────────────────────────────────────────
def settings_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "settings.json")


def load_settings() -> dict:
    s = dict(DEFAULTS)
    try:
        with open(settings_path(), encoding="utf-8") as f:
            s.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except Exception:
        pass
    return s


def save_settings(s: dict) -> None:
    try:
        p = settings_path()
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2, ensure_ascii=False)
        os.replace(p + ".tmp", p)
    except Exception:
        pass


# ── câmeras ──────────────────────────────────────────────────────────────────
def list_cameras() -> list[tuple[int, str]]:
    """[(índice DirectShow, nome)], sem as câmeras virtuais de saída (evita loop de imagem)."""
    names: list[str] = []
    try:
        from pygrabber.dshow_graph import FilterGraph  # só Windows
        names = FilterGraph().get_input_devices()
    except Exception:
        names = []
    if not names:
        return [(i, f"Câmera {i}") for i in range(4)]
    return [(i, n) for i, n in enumerate(names) if not any(o in n.lower() for o in OWN_OUTPUTS)]


def open_camera(index: int, w: int, h: int, fps: int):
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))  # webcams USB só dão 720p/1080p a 30 fps em MJPG
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


# ── motor (thread de processamento) ──────────────────────────────────────────
class Engine(threading.Thread):
    def __init__(self, settings: dict):
        super().__init__(daemon=True)
        self.s = settings
        self.comp = Compositor()
        self.apply_look()
        self.matter: Matter | None = None
        self.lock = threading.Lock()
        self.preview: np.ndarray | None = None
        self.preview_mask = False
        self.status = {"camera": "abrindo…", "vcam": "", "provider": "", "fps": 0.0, "ms": 0.0, "size": ""}
        self._restart = threading.Event()
        self._rebuild_model = threading.Event()
        self._stop = threading.Event()
        self._reopen_vcam = threading.Event()
        self.vcam = None
        self.vcam_missing = False

    # chamados pela interface
    def apply_look(self) -> None:
        s = self.s
        self.comp.mode, self.comp.blur, self.comp.firmeza = s["effect"], int(s["blur"]), int(s["firmeza"])
        self.comp.color = tuple(int(c) for c in s["color"])
        if s["effect"] == "imagem" and s["image"] and self.comp._img_src is None:
            self.comp.set_image(s["image"])

    def restart(self) -> None:
        self._restart.set()

    def rebuild_model(self) -> None:
        self._rebuild_model.set()

    def stop(self) -> None:
        self._stop.set()

    def _build_model(self) -> None:
        self.status["provider"] = "carregando modelo…"
        self.matter = Matter(force_cpu=bool(self.s["force_cpu"]), quality=self.s["quality"])
        self.status["provider"] = self.matter.provider_label

    def _ensure_vcam(self, w: int, h: int) -> None:
        """Mantém a "FundoLimpo Camera" aberta; só recria se o tamanho mudar (assim o OBS não perde a fonte)."""
        if self.vcam is not None and (self.vcam.width, self.vcam.height) == (w, h):
            return
        if self.vcam is not None:
            self.vcam.close()
            self.vcam = None
        if not vcam_mod.is_registered():
            self.status["vcam"] = "A câmera \"FundoLimpo Camera\" ainda não está instalada — clique em \"Instalar câmera\"."
            self.vcam_missing = True
            return
        self.vcam_missing = False
        try:
            self.vcam = vcam_mod.VirtualCamera(w, h)
            self.status["vcam"] = f"Saindo na câmera \"{vcam_mod.NAME}\" ({w}x{h})."
        except Exception as e:
            self.status["vcam"] = "Câmera virtual: " + str(e)

    def reopen_vcam(self) -> None:
        self._reopen_vcam.set()

    def run(self) -> None:
        try:
            self._build_model()
        except Exception as e:
            self.status["provider"] = "erro ao carregar o modelo: " + str(e)
            return
        while not self._stop.is_set():
            self._restart.clear()
            w, h = RESOLUTIONS.get(self.s["resolution"], (1280, 720))
            fps = int(self.s["fps"])
            cap = open_camera(int(self.s["camera"]), w, h, fps)
            if cap is None:
                self.status["camera"] = "não consegui abrir a câmera (está em uso por outro app?)"
                if self._restart.wait(2.0) or self._stop.is_set():
                    continue
                continue
            ok, frame = cap.read()
            if not ok:
                cap.release()
                self.status["camera"] = "a câmera não enviou imagem"
                self._restart.wait(2.0)
                continue
            H, W = frame.shape[:2]
            self.status["camera"] = "ok"
            self.status["size"] = f"{W}x{H}"
            OW, OH = W - W % 4, H - H % 4   # a câmera virtual exige múltiplos de 4
            self._ensure_vcam(OW, OH)
            self.matter.reset()
            t_last, fps_ema, fails = time.perf_counter(), 0.0, 0
            while not (self._stop.is_set() or self._restart.is_set()):
                if self._rebuild_model.is_set():
                    self._rebuild_model.clear()
                    try:
                        self._build_model()
                    except Exception as e:
                        self.status["provider"] = "erro: " + str(e)
                ok, frame = cap.read()
                if not ok or frame is None:
                    fails += 1
                    if fails > 30:
                        self.status["camera"] = "a câmera parou de responder — reabrindo"
                        break
                    continue
                fails = 0
                if frame.shape[:2] != (H, W):
                    frame = cv2.resize(frame, (W, H))
                self.matter.quality = self.s["quality"]
                if self.s["enabled"]:
                    a = self.matter.alpha(frame)
                    out = self.comp.compose(frame, a)
                    self.status["ms"] = self.matter.last_ms
                else:
                    a, out = None, frame
                if self._reopen_vcam.is_set():
                    self._reopen_vcam.clear()
                    if self.vcam is not None:
                        self.vcam.close()
                        self.vcam = None
                    self._ensure_vcam(OW, OH)
                if self.vcam is not None:
                    try:
                        self.vcam.send(out if (OW, OH) == (W, H) else out[:OH, :OW])
                        n = self.vcam.connected()
                        base = f"Saindo na câmera \"{vcam_mod.NAME}\" ({OW}x{OH})"
                        self.status["vcam"] = base + (" — em uso por um app ✓" if n else " — nenhum app usando ainda.")
                    except Exception as e:
                        self.vcam = None
                        self.status["vcam"] = "a câmera virtual parou: " + str(e)
                now = time.perf_counter()
                dt, t_last = now - t_last, now
                fps_ema = fps_ema * 0.9 + (1.0 / max(dt, 1e-3)) * 0.1
                self.status["fps"] = fps_ema
                show = (a * 255).astype(np.uint8) if (self.preview_mask and a is not None) else out
                pw = 480
                ph = int(show.shape[0] * pw / show.shape[1])
                small = cv2.resize(show, (pw, ph), interpolation=cv2.INTER_AREA)
                with self.lock:
                    self.preview = small
            cap.release()
        if self.vcam is not None:
            self.vcam.close()


# ── interface ────────────────────────────────────────────────────────────────
def run_ui() -> None:
    import tkinter as tk
    from tkinter import colorchooser, filedialog, messagebox, ttk

    from PIL import Image, ImageTk

    s = load_settings()
    cams = list_cameras()
    if cams and s["camera"] not in [i for i, _ in cams]:
        match = [i for i, n in cams if n == s.get("camera_name")]
        s["camera"] = match[0] if match else cams[0][0]

    eng = Engine(s)
    eng.start()

    root = tk.Tk()
    root.title(f"{APP} {VERSION}")
    root.configure(bg="#0f1420")
    root.minsize(520, 600)
    try:
        from fundolimpo.matting import resource_path
        ico = resource_path("icone.png")
        if not os.path.exists(ico):
            ico = resource_path("instalador", "icone.png")
        root.iconphoto(True, tk.PhotoImage(file=ico))
    except Exception:
        pass
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except Exception:
        pass
    BG, PANEL, FG, MUTED, ACC = "#0f1420", "#171e2e", "#e8edf5", "#8a9bb5", "#3fb6ff"
    st.configure(".", background=BG, foreground=FG, fieldbackground=PANEL)
    st.configure("TLabel", background=BG, foreground=FG)
    st.configure("Muted.TLabel", foreground=MUTED)
    st.configure("TCheckbutton", background=BG, foreground=FG)
    st.configure("TRadiobutton", background=BG, foreground=FG)
    st.configure("TButton", background=PANEL, foreground=FG)
    st.configure("Horizontal.TScale", background=BG)
    st.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=FG, arrowcolor=FG, bordercolor="#2a3550")
    st.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", FG)],
           selectbackground=[("readonly", PANEL)], selectforeground=[("readonly", FG)])
    root.option_add("*TCombobox*Listbox.background", PANEL)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACC)
    st.configure("TScale", background=BG, troughcolor="#26314a")
    st.map("TCheckbutton", background=[("active", BG)])
    st.map("TRadiobutton", background=[("active", BG)])

    prev = tk.Label(root, bg="#000", width=480, height=270)
    prev.pack(padx=12, pady=(12, 6))

    body = ttk.Frame(root)
    body.pack(fill="x", padx=12)
    body.columnconfigure(1, weight=1)

    def changed(*_):
        save_settings(s)
        eng.apply_look()

    row = 0

    def label(text):
        nonlocal row
        ttk.Label(body, text=text).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))

    # ligar/desligar + ver máscara
    v_enabled = tk.BooleanVar(value=s["enabled"])
    v_mask = tk.BooleanVar(value=False)
    top = ttk.Frame(body)
    top.grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 6))
    ttk.Checkbutton(top, text="Remover fundo", variable=v_enabled,
                    command=lambda: (s.__setitem__("enabled", v_enabled.get()), changed())).pack(side="left")
    ttk.Checkbutton(top, text="Ver máscara (prévia)", variable=v_mask,
                    command=lambda: setattr(eng, "preview_mask", v_mask.get())).pack(side="left", padx=16)
    row += 1

    # câmera
    label("Câmera")
    cam_names = [n for _, n in cams]
    v_cam = tk.StringVar(value=next((n for i, n in cams if i == s["camera"]), cam_names[0] if cam_names else ""))
    cb_cam = ttk.Combobox(body, textvariable=v_cam, values=cam_names, state="readonly")
    cb_cam.grid(row=row, column=1, sticky="ew")

    def on_cam(_=None):
        i = cam_names.index(v_cam.get())
        s["camera"], s["camera_name"] = cams[i][0], cams[i][1]
        save_settings(s)
        eng.restart()
    cb_cam.bind("<<ComboboxSelected>>", on_cam)
    row += 1

    label("Resolução")
    v_res = tk.StringVar(value=s["resolution"])
    cb_res = ttk.Combobox(body, textvariable=v_res, values=list(RESOLUTIONS), state="readonly")
    cb_res.grid(row=row, column=1, sticky="ew")
    cb_res.bind("<<ComboboxSelected>>", lambda _=None: (s.__setitem__("resolution", v_res.get()), save_settings(s), eng.restart()))
    row += 1

    label("Desempenho")
    qrev = {v: k for k, v in QUALITIES.items()}
    v_q = tk.StringVar(value=qrev.get(s["quality"], "Equilibrada"))
    cb_q = ttk.Combobox(body, textvariable=v_q, values=list(QUALITIES), state="readonly")
    cb_q.grid(row=row, column=1, sticky="ew")
    cb_q.bind("<<ComboboxSelected>>", lambda _=None: (s.__setitem__("quality", QUALITIES[v_q.get()]), changed()))
    row += 1

    # efeito
    label("Fundo")
    erev = {v: k for k, v in EFFECTS.items()}
    v_eff = tk.StringVar(value=erev.get(s["effect"], "Desfocar o fundo"))
    effbox = ttk.Frame(body)
    effbox.grid(row=row, column=1, sticky="w")
    for name in EFFECTS:
        ttk.Radiobutton(effbox, text=name, value=name, variable=v_eff,
                        command=lambda: (s.__setitem__("effect", EFFECTS[v_eff.get()]), changed(), refresh_extra())).pack(side="left", padx=(0, 10))
    row += 1

    extra = ttk.Frame(body)
    extra.grid(row=row, column=0, columnspan=2, sticky="ew", pady=2)
    extra.columnconfigure(1, weight=1)
    row += 1

    v_blur = tk.IntVar(value=s["blur"])
    lbl_blur = ttk.Label(extra, text="Intensidade do desfoque")
    sc_blur = ttk.Scale(extra, from_=5, to=100, variable=v_blur,
                        command=lambda _=None: (s.__setitem__("blur", int(v_blur.get())), changed()))
    lbl_img = ttk.Label(extra, text=os.path.basename(s["image"]) or "nenhuma imagem", style="Muted.TLabel")

    def pick_image():
        p = filedialog.askopenfilename(title="Imagem de fundo", filetypes=[("Imagens", "*.jpg *.jpeg *.png *.bmp *.webp")])
        if p:
            s["image"] = p
            eng.comp.set_image(p)
            lbl_img.configure(text=os.path.basename(p))
            changed()
    btn_img = ttk.Button(extra, text="Escolher imagem…", command=pick_image)

    def pick_color():
        b, g, r = s["color"]
        res = colorchooser.askcolor(color=f"#{r:02x}{g:02x}{b:02x}", title="Cor do fundo")
        if res and res[0]:
            r, g, b = (int(x) for x in res[0])
            s["color"] = [b, g, r]
            changed()
    btn_col = ttk.Button(extra, text="Escolher cor…", command=pick_color)
    lbl_col = ttk.Label(extra, text="Verde padrão serve como chroma key no OBS/edição.", style="Muted.TLabel")

    def refresh_extra():
        for w in extra.winfo_children():
            w.grid_forget()
        e = s["effect"]
        if e == "desfoque":
            lbl_blur.grid(row=0, column=0, sticky="w", padx=(0, 10))
            sc_blur.grid(row=0, column=1, sticky="ew")
        elif e == "imagem":
            btn_img.grid(row=0, column=0, sticky="w", padx=(0, 10))
            lbl_img.grid(row=0, column=1, sticky="w")
        else:
            btn_col.grid(row=0, column=0, sticky="w", padx=(0, 10))
            lbl_col.grid(row=0, column=1, sticky="w")
    refresh_extra()

    label("Firmeza da borda")
    v_f = tk.IntVar(value=s["firmeza"])
    ttk.Scale(body, from_=0, to=100, variable=v_f,
              command=lambda _=None: (s.__setitem__("firmeza", int(v_f.get())), changed())).grid(row=row, column=1, sticky="ew")
    row += 1
    ttk.Label(body, text="Aumente se aparecer um contorno do fundo em volta de você.", style="Muted.TLabel").grid(row=row, column=1, sticky="w")
    row += 1

    v_cpu = tk.BooleanVar(value=s["force_cpu"])
    ttk.Checkbutton(body, text="Usar só o processador (se a placa de vídeo der problema)", variable=v_cpu,
                    command=lambda: (s.__setitem__("force_cpu", v_cpu.get()), save_settings(s), eng.rebuild_model())
                    ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))
    row += 1

    status = ttk.Label(root, text="", style="Muted.TLabel", justify="left", wraplength=500)
    status.pack(fill="x", padx=12, pady=(10, 4))

    camrow = ttk.Frame(root)
    camrow.pack(fill="x", padx=12, pady=(0, 12))

    def do_install():
        btn_install.configure(state="disabled", text="Instalando… (confirme o aviso do Windows)")
        root.update_idletasks()
        ok = vcam_mod.register()
        btn_install.configure(state="normal", text="Instalar câmera \"FundoLimpo Camera\"")
        if ok:
            eng.reopen_vcam()
            messagebox.showinfo(APP, "Câmera instalada! No OBS/Streamlabs adicione uma fonte \"Dispositivo de captura de vídeo\" "
                                     "e escolha \"FundoLimpo Camera\". Em Discord/Teams/Meet, escolha essa câmera nas configurações de vídeo.")
        else:
            messagebox.showwarning(APP, "Não consegui instalar a câmera (o aviso do Windows foi recusado?). Tente de novo.")

    def do_uninstall():
        if not messagebox.askyesno(APP, "Remover a \"FundoLimpo Camera\" do Windows? (dá pra instalar de novo depois)"):
            return
        if eng.vcam is not None:
            eng.vcam.close()
            eng.vcam = None
        vcam_mod.unregister()
        eng.reopen_vcam()

    btn_install = ttk.Button(camrow, text="Instalar câmera \"FundoLimpo Camera\"", command=do_install)
    btn_uninstall = ttk.Button(camrow, text="Remover câmera", command=do_uninstall)

    photo = {"img": None}

    def tick():
        with eng.lock:
            frame = eng.preview
        if frame is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB if frame.ndim == 2 else cv2.COLOR_BGR2RGB)
            photo["img"] = ImageTk.PhotoImage(Image.fromarray(rgb))
            prev.configure(image=photo["img"], width=rgb.shape[1], height=rgb.shape[0])
        x = eng.status
        cam_line = "Câmera: " + (x["size"] if x["camera"] == "ok" else x["camera"])
        proc = f"Processando em: {x['provider']}"
        if x["ms"]:
            proc += f" · {x['ms']:.0f} ms por quadro"
        status.configure(text=f"{cam_line} · {x['fps']:.0f} fps\n{proc}\n{x['vcam']}")
        if eng.vcam_missing:
            if not btn_install.winfo_ismapped():
                btn_uninstall.pack_forget()
                btn_install.pack(side="left")
        elif not btn_uninstall.winfo_ismapped():
            btn_install.pack_forget()
            btn_uninstall.pack(side="right")
        root.after(40, tick)

    def on_close():
        eng.stop()
        save_settings(s)
        root.after(200, root.destroy)

    root.protocol("WM_DELETE_WINDOW", on_close)

    # ── atualização automática ──
    upd = {"info": None, "done": False, "progress": None, "file": None, "error": None}

    def upd_check():
        upd["info"] = updater.check(VERSION)
        upd["done"] = True

    def upd_poll_check():
        if not upd["done"]:
            root.after(500, upd_poll_check)
            return
        info = upd["info"]
        if not info:
            return
        notes = info["notes"][:600]
        msg = (f"Há uma versão nova do {APP}: {info['version']} (você tem a {VERSION}).\n\n"
               + (notes + "\n\n" if notes else "")
               + "Atualizar agora? O app fecha, atualiza e abre de novo sozinho.")
        if not messagebox.askyesno(f"{APP} — atualização", msg):
            return
        upd["progress"] = 0.0
        threading.Thread(target=upd_download, args=(info,), daemon=True).start()
        upd_poll_download()

    def upd_download(info):
        try:
            upd["file"] = updater.download(info, lambda p: upd.__setitem__("progress", p))
        except Exception as e:  # sem internet, arquivo corrompido etc.
            upd["error"] = str(e) or e.__class__.__name__

    def upd_poll_download():
        if upd["error"]:
            root.title(f"{APP} {VERSION}")
            messagebox.showwarning(APP, "Não consegui baixar a atualização.\n\n"
                                        f"Você pode baixar manualmente em:\n{updater.DIRECT_LINK}")
            return
        if not upd["file"]:
            root.title(f"{APP} {VERSION} — baixando atualização… {upd['progress'] * 100:.0f}%")
            root.after(300, upd_poll_download)
            return
        root.title(f"{APP} {VERSION} — instalando atualização…")
        if updater.run_installer(upd["file"]):
            on_close()  # o instalador espera o app fechar, atualiza e reabre
        else:
            root.title(f"{APP} {VERSION}")
            messagebox.showwarning(APP, "A atualização foi cancelada (o aviso do Windows foi recusado?).\n"
                                        "Ela será oferecida de novo na próxima vez que abrir o app.")

    if updater.can_self_update():
        threading.Thread(target=upd_check, daemon=True).start()
        root.after(1500, upd_poll_check)

    tick()
    root.mainloop()


# ── modo teste (sem câmera) ──────────────────────────────────────────────────
def run_test(inp: str, out: str, force_cpu: bool, effect: str, repeat: int) -> None:
    m = Matter(force_cpu=force_cpu, quality="maxima")
    c = Compositor()
    c.mode = effect
    img = cv2.imdecode(np.fromfile(inp, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit("não consegui ler " + inp)
    a = None
    for _ in range(max(1, repeat)):  # repetir deixa a memória temporal convergir, como num vídeo parado
        a = m.alpha(img)
    res = c.compose(img, a)
    base, _ext = os.path.splitext(out)
    cv2.imencode(".png", res)[1].tofile(base + ".png")
    cv2.imencode(".png", (a * 255).astype(np.uint8))[1].tofile(base + "-mascara.png")
    print(f"{m.provider_label}: {m.last_ms:.1f} ms/quadro em {img.shape[1]}x{img.shape[0]} -> {base}.png e {base}-mascara.png")


def main() -> None:
    ap = argparse.ArgumentParser(prog=APP)
    ap.add_argument("--teste", nargs=2, metavar=("ENTRADA", "SAIDA"), help="processa uma foto e salva o resultado (sem câmera)")
    ap.add_argument("--efeito", default="cor", choices=["desfoque", "imagem", "cor"])
    ap.add_argument("--cpu", action="store_true", help="força o processador")
    ap.add_argument("--repetir", type=int, default=4)
    args = ap.parse_args()
    if args.teste:
        run_test(args.teste[0], args.teste[1], args.cpu, args.efeito, args.repetir)
    else:
        run_ui()


if __name__ == "__main__":
    main()
