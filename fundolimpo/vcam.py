"""Câmera virtual própria do FundoLimpo ("FundoLimpo Camera").

É um filtro DirectShow de "dispositivo de vídeo" (baseado no softcam, licença MIT, renomeado e com GUID próprio),
então aparece como webcam no OBS, Streamlabs, Discord, Zoom, Teams, navegador etc. — sem precisar do OBS.

A DLL precisa ser registrada no Windows uma vez (pede permissão de administrador). O registro guarda o caminho
da DLL: se a pasta do app mudar de lugar, registre de novo (o app detecta e oferece).
"""
from __future__ import annotations

import ctypes
import os
import struct
import sys

import numpy as np

from .matting import resource_path

CLSID = "{C858F59A-A4E6-4E81-9542-2209A8B5AAD6}"
NAME = "FundoLimpo Camera"


def dll_path(arch: str | None = None) -> str:
    arch = arch or ("x64" if struct.calcsize("P") == 8 else "x86")
    return resource_path("camera", arch, "fundolimpo_cam.dll")


def registered_path() -> str | None:
    """Caminho da DLL registrada no Windows (visão 64 bits), ou None."""
    if sys.platform != "win32":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{CLSID}\InprocServer32") as k:
            v, _ = winreg.QueryValueEx(k, "")
            return str(v)
    except OSError:
        return None


def is_registered() -> bool:
    p = registered_path()
    return bool(p) and os.path.normcase(os.path.abspath(p)) == os.path.normcase(os.path.abspath(dll_path("x64")))


def _run_elevated(args: str) -> bool:
    """Roda `cmd /c <args>` como administrador (um único aviso do UAC) e espera terminar."""
    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]

    SEE_MASK_NOCLOSEPROCESS = 0x40
    info = SHELLEXECUTEINFOW(cbSize=ctypes.sizeof(SHELLEXECUTEINFOW), fMask=SEE_MASK_NOCLOSEPROCESS,
                             lpVerb="runas", lpFile=os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"),
                             lpParameters="/c " + args, nShow=0)
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        return False  # usuário recusou o UAC
    ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, 60000)
    code = wintypes.DWORD()
    ctypes.windll.kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(info.hProcess)
    return code.value == 0


def _regsvr_cmd(unregister: bool) -> str:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    flag = "/u /s" if unregister else "/s"
    parts = [f'"{os.path.join(root, "System32", "regsvr32.exe")}" {flag} "{dll_path("x64")}"']
    x86 = dll_path("x86")
    wow = os.path.join(root, "SysWOW64", "regsvr32.exe")
    if os.path.exists(x86) and os.path.exists(wow):  # para apps de 32 bits também enxergarem a câmera
        parts.append(f'"{wow}" {flag} "{x86}"')
    return '"' + " && ".join(parts) + '"'


def register() -> bool:
    return _run_elevated(_regsvr_cmd(False)) and is_registered()


def unregister() -> bool:
    return _run_elevated(_regsvr_cmd(True))


class VirtualCamera:
    """Envia quadros BGR (uint8, H x W x 3, de cima para baixo) para a "FundoLimpo Camera"."""

    def __init__(self, width: int, height: int):
        if sys.platform != "win32":
            raise RuntimeError("a câmera virtual só existe no Windows")
        if width % 4 or height % 4:
            raise ValueError("largura e altura precisam ser múltiplos de 4")
        self.dll = ctypes.CDLL(dll_path())
        self.dll.scCreateCamera.restype = ctypes.c_void_p
        self.dll.scCreateCamera.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_float]
        self.dll.scDeleteCamera.argtypes = [ctypes.c_void_p]
        self.dll.scSendFrame.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.dll.scIsConnected.restype = ctypes.c_bool
        self.dll.scIsConnected.argtypes = [ctypes.c_void_p]
        # framerate 0 = cada quadro sai na hora em que é enviado (a webcam real já dita o ritmo)
        self.cam = self.dll.scCreateCamera(width, height, 0.0)
        if not self.cam:
            raise RuntimeError("não deu para criar a câmera (outro FundoLimpo já está aberto?)")
        self.width, self.height = width, height
        self.device = NAME

    def send(self, frame_bgr: np.ndarray) -> None:
        f = frame_bgr if frame_bgr.flags["C_CONTIGUOUS"] else np.ascontiguousarray(frame_bgr)
        self.dll.scSendFrame(self.cam, f.ctypes.data)

    def connected(self) -> bool:
        return bool(self.dll.scIsConnected(self.cam))

    def close(self) -> None:
        if self.cam:
            self.dll.scDeleteCamera(self.cam)
            self.cam = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
