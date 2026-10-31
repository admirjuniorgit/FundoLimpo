"""Recorte da pessoa (matting) com o Robust Video Matting (RVM, MobileNetV3) em ONNX.

Por que RVM: é um modelo *temporal* — guarda um estado entre os quadros (r1..r4), então a borda não
"treme" de um quadro para o outro e fios de cabelo saem com transparência real (alpha), não um
recorte binário. É a mesma ideia do NVIDIA Broadcast, mas aberto e rodando em qualquer placa.

Execução: ONNX Runtime com DirectML (qualquer GPU DirectX 12 no Windows: NVIDIA, AMD, Intel),
CUDA se existir, ou processador como último recurso.
"""
from __future__ import annotations

import os
import sys
import time

import cv2
import numpy as np
import onnxruntime as ort

PREFERRED = ["DmlExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]

# Largura em que o modelo processa a imagem, por modo de desempenho. A máscara volta para o
# tamanho da câmera no final (o RVM já tem um refinador interno que preserva a borda).
QUALITY_WIDTH = {"maxima": 0, "equilibrada": 960, "rapida": 640}
# Tamanho (lado maior) em que a rede principal enxerga a imagem — é o que mais pesa no tempo.
QUALITY_TARGET = {"maxima": 512, "equilibrada": 416, "rapida": 288}


def resource_path(*parts: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, *parts)


def choose_providers(force_cpu: bool = False) -> list[str]:
    available = ort.get_available_providers()
    if force_cpu:
        return ["CPUExecutionProvider"]
    return [p for p in PREFERRED if p in available] or ["CPUExecutionProvider"]


PROVIDER_LABEL = {
    "DmlExecutionProvider": "Placa de vídeo (DirectML)",
    "CUDAExecutionProvider": "Placa NVIDIA (CUDA)",
    "CPUExecutionProvider": "Processador (CPU)",
}


class Matter:
    def __init__(self, model_path: str | None = None, force_cpu: bool = False, quality: str = "equilibrada"):
        self.model_path = model_path or resource_path("modelo", "rvm_mobilenetv3_fp32.onnx")
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.log_severity_level = 3
        providers = choose_providers(force_cpu)
        if "DmlExecutionProvider" in providers:
            # o DirectML pede execução sequencial e sem padrão de memória
            opts.enable_mem_pattern = False
            opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        try:
            self.sess = ort.InferenceSession(self.model_path, sess_options=opts, providers=providers)
        except Exception:
            # driver/placa sem suporte: cai para o processador
            self.sess = ort.InferenceSession(self.model_path, sess_options=opts, providers=["CPUExecutionProvider"])
        self.provider = self.sess.get_providers()[0]
        self.quality = quality
        self.reset()

    @property
    def provider_label(self) -> str:
        return PROVIDER_LABEL.get(self.provider, self.provider)

    def reset(self) -> None:
        """Zera a memória temporal (trocou de câmera, resolução ou a cena mudou muito)."""
        z = np.zeros((1, 1, 1, 1), dtype=np.float32)
        self.rec = [z, z, z, z]
        self._shape = None
        self.last_ms = 0.0

    def downsample_ratio(self, h: int, w: int) -> float:
        # Recomendação dos autores: o lado maior, depois do downsample interno, entre ~256 e 512 px.
        return float(min(1.0, QUALITY_TARGET.get(self.quality, 416) / max(h, w)))

    def alpha(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Recebe um quadro BGR uint8 e devolve a máscara alpha float32 (0..1) do mesmo tamanho."""
        H, W = frame_bgr.shape[:2]
        tw = QUALITY_WIDTH.get(self.quality, 960)
        if tw and W > tw:
            h, w = int(round(H * tw / W)), tw
            small = cv2.resize(frame_bgr, (w, h), interpolation=cv2.INTER_AREA)
        else:
            h, w, small = H, W, frame_bgr
        if self._shape != (h, w):
            self.reset()
            self._shape = (h, w)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        src = np.ascontiguousarray(rgb.transpose(2, 0, 1)[None], dtype=np.float32) * (1.0 / 255.0)
        t = time.perf_counter()
        fgr, pha, *rec = self.sess.run(None, {
            "src": src, "r1i": self.rec[0], "r2i": self.rec[1], "r3i": self.rec[2], "r4i": self.rec[3],
            "downsample_ratio": np.array([self.downsample_ratio(h, w)], dtype=np.float32),
        })
        self.last_ms = (time.perf_counter() - t) * 1000.0
        self.rec = rec
        a = pha[0, 0]
        if (h, w) != (H, W):
            a = cv2.resize(a, (W, H), interpolation=cv2.INTER_LINEAR)
        return np.clip(a, 0.0, 1.0, out=a)
