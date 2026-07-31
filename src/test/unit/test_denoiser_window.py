# tests/unit/test_denoiser_window.py — PROMOVIDO de scratch/scratch_denoise.py
import torch

def _meta(caps):
    return {"frame_captions": {str(i): {"cap": c} for i, c in enumerate(caps)}}

def _caps(meta):
    return [m["cap"] for m in meta["frame_captions"].values()]

def test_forward_propagation(denoiser):
    """A) frame baixo dentro da janela recebe a legenda da âncora anterior."""
    out = denoiser.denoise_caption(_meta(["CAP0", "CAP1", "CAP2"]),
                                   torch.tensor([0.9, 0.9, 0.1]))
    assert _caps(out) == ["CAP0", "CAP1", "CAP1"]

def test_causal_only(denoiser):
    """B) frame baixo ANTES de qualquer âncora fica inalterado."""
    out = denoiser.denoise_caption(_meta(["LOW0", "HIGH1", "OK2"]),
                                   torch.tensor([0.1, 0.9, 0.9]))
    assert _caps(out)[0] == "LOW0"

def test_window_boundary(denoiser):
    """C) frame com gap>W NÃO é denoised."""
    out = denoiser.denoise_caption(_meta(["CAP0", "ANCHOR1", "LOW2", "LOW3", "FAR4"]),
                                   torch.tensor([0.9, 0.9, 0.1, 0.1, 0.1]))
    assert _caps(out) == ["CAP0", "ANCHOR1", "ANCHOR1", "ANCHOR1", "FAR4"]

def test_sentinel_collision_bug(denoiser):
    """D) DOCUMENTA a divergência código-vs-artigo: âncora no frame '0' é
    invisível (colide com o sentinela), então o frame 1 NÃO é denoised —
    contrariando a Eq. 2. Se alguém corrigir o denoiser, este teste avisa."""
    out = denoiser.denoise_caption(_meta(["ANCHOR0", "LOW1"]),
                                   torch.tensor([0.9, 0.1]))
    assert _caps(out) == ["ANCHOR0", "LOW1"]   # comportamento ATUAL (bugado)
