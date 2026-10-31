"""Atualização automática do FundoLimpo.

Ao abrir, o app consulta a última versão publicada no repositório PÚBLICO de downloads
(github.com/<REPO>/releases/latest). Se for mais nova que a instalada, pergunta ao usuário,
baixa o FundoLimpo-Setup.exe e roda o instalador em modo silencioso; o instalador fecha o app,
atualiza por cima e abre o app de novo.

Para lançar uma versão nova: suba VERSION em app.py e rode ./commit.sh (veja o LEIA-ME).
"""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import tempfile
import urllib.request

REPO = "admirjuniorgit/FundoLimpo"              # repositório público (código + instaladores nas Releases)
ASSET = "FundoLimpo-Setup.exe"                   # nome fixo do instalador em cada release
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PAGE = f"https://github.com/{REPO}/releases/latest"
DIRECT_LINK = f"https://github.com/{REPO}/releases/latest/download/{ASSET}"
TIMEOUT = 8


def parse_version(v: str) -> tuple[int, ...]:
    """'v1.10.2' -> (1, 10, 2). Partes não numéricas viram 0."""
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(remote: str, local: str) -> bool:
    r, l = parse_version(remote), parse_version(local)
    n = max(len(r), len(l))
    return r + (0,) * (n - len(r)) > l + (0,) * (n - len(l))


def can_self_update() -> bool:
    """Só a versão instalada (exe empacotado no Windows) se atualiza; a de desenvolvimento não."""
    if os.environ.get("FUNDOLIMPO_SEM_ATUALIZACAO"):
        return False
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "FundoLimpo-updater",
                                               "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl.create_default_context())


def check(current: str) -> dict | None:
    """Retorna {'version', 'url', 'notes', 'size'} se houver versão nova; None se não houver ou sem internet."""
    try:
        with _get(API_LATEST) as r:
            data = json.load(r)
    except Exception:
        return None
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = str(data.get("tag_name", ""))
    if not is_newer(tag, current):
        return None
    asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET), None)
    if not asset:
        asset = next((a for a in data.get("assets", []) if str(a.get("name", "")).lower().endswith(".exe")), None)
    if not asset:
        return None
    url = str(asset.get("browser_download_url", ""))
    if not url.startswith("https://github.com/"):
        return None
    return {"version": tag.lstrip("vV"), "url": url, "notes": (data.get("body") or "").strip(),
            "size": int(asset.get("size") or 0)}


def download(info: dict, progress=None) -> str:
    """Baixa o instalador para a pasta temporária. progress(fração 0..1) é chamado durante o download."""
    dest_dir = os.path.join(tempfile.gettempdir(), "FundoLimpo-update")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"FundoLimpo-Setup-{info['version']}.exe")
    part = dest + ".part"
    with _get(info["url"]) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or info.get("size") or 0)
        got = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if progress and total:
                progress(min(1.0, got / total))
    if info.get("size") and os.path.getsize(part) != info["size"]:
        os.remove(part)
        raise IOError("download incompleto")
    os.replace(part, dest)
    return dest


def run_installer(path: str) -> bool:
    """Roda o Setup em modo silencioso (o Windows pede permissão de administrador).
    O Setup fecha o FundoLimpo, instala por cima e abre o app de novo no final."""
    import ctypes
    params = "/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS"
    rc = ctypes.windll.shell32.ShellExecuteW(None, "open", path, params, None, 1)
    return rc > 32
