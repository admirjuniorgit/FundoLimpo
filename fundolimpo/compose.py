"""Monta a imagem final: pessoa por cima de um fundo novo (desfoque, imagem ou cor)."""
from __future__ import annotations

import cv2
import numpy as np


def refine_alpha(a: np.ndarray, firmeza: int) -> np.ndarray:
    """firmeza 0..100: 0 = borda macia (como o modelo entrega); 100 = borda bem firme.
    Útil quando o fundo é parecido com a roupa/pele e aparece um "halo"."""
    if firmeza <= 0:
        return a
    k = firmeza / 100.0
    lo, hi = 0.5 * k * 0.6, 1.0 - 0.5 * k * 0.6   # estreita a faixa de transição
    return np.clip((a - lo) * (1.0 / (hi - lo)), 0.0, 1.0)


def blur_background(frame: np.ndarray, forca: int) -> np.ndarray:
    """Desfoque rápido: reduz, desfoca e amplia (bem mais leve que um desfoque grande em tela cheia)."""
    forca = max(1, min(100, forca))
    H, W = frame.shape[:2]
    scale = 0.25
    small = cv2.resize(frame, (max(1, int(W * scale)), max(1, int(H * scale))), interpolation=cv2.INTER_AREA)
    sigma = 1.0 + forca * 0.18
    small = cv2.GaussianBlur(small, (0, 0), sigma)
    return cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)


def fit_image(img: np.ndarray, W: int, H: int) -> np.ndarray:
    """Ajusta a imagem de fundo para preencher W x H sem distorcer (corta as sobras)."""
    h, w = img.shape[:2]
    s = max(W / w, H / h)
    nw, nh = max(W, int(round(w * s))), max(H, int(round(h * s)))
    r = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    x, y = (nw - W) // 2, (nh - H) // 2
    return np.ascontiguousarray(r[y:y + H, x:x + W])


class Compositor:
    def __init__(self):
        self.mode = "desfoque"      # desfoque | imagem | cor
        self.blur = 60
        self.color = (0, 177, 64)   # BGR — verde-chroma por padrão (útil para OBS/edição)
        self.firmeza = 0
        self._img_src = None
        self._img_cache = None      # (W, H, img)

    def set_image(self, path: str | None) -> bool:
        self._img_cache = None
        if not path:
            self._img_src = None
            return False
        data = np.fromfile(path, dtype=np.uint8)  # aceita caminhos com acento no Windows
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        self._img_src = img
        return img is not None

    def background(self, frame: np.ndarray) -> np.ndarray:
        H, W = frame.shape[:2]
        if self.mode == "imagem" and self._img_src is not None:
            if not self._img_cache or self._img_cache[:2] != (W, H):
                self._img_cache = (W, H, fit_image(self._img_src, W, H))
            return self._img_cache[2]
        if self.mode == "cor":
            bg = np.empty_like(frame)
            bg[:] = self.color
            return bg
        return blur_background(frame, self.blur)

    def compose(self, frame: np.ndarray, alpha: np.ndarray) -> np.ndarray:
        a = refine_alpha(alpha, self.firmeza).astype(np.float32, copy=False)
        bg = self.background(frame)
        # cv2.blendLinear faz frame*a + bg*(1-a) em C, bem mais rápido que numpy
        return cv2.blendLinear(frame, bg, a, 1.0 - a)
