"""
scratch/scratch_denoise.py
================================================================================
SCRATCHPAD DE TESTE (tipo VALOR) — verificação da LÓGICA de
WindowSimDenoiser.denoise_caption()  (o SWi-Den, Eq. 2 do artigo)
================================================================================

CONTRASTE COM scratch_construct.py
    - scratch_construct.py testa um ORQUESTRADOR → teste de INTERAÇÃO (dublês).
    - ESTE arquivo testa LÓGICA PURA (uma transformação entrada→saída) →
      teste de VALOR: monto uma AMOSTRA sintética, rodo o método REAL, e faço
      `assert` no RESULTADO. É o segundo dos dois moldes.

COMO RODAR
    python scratch/scratch_denoise.py
    ipython -i scratch/scratch_denoise.py   # inspecionar `meta` depois

O QUE denoise_caption FAZ (lido do código, window.py:20-35)
    Recebe meta['frame_captions'] = {fid(str): {...}} e raw_scores (TENSOR,
    casado por POSIÇÃO). Percorre os frames em ordem; se score > θd, o frame vira
    "âncora" (last_high_id). Se score <= θd E há âncora E o gap ao anchor <= W,
    a legenda do frame é SUBSTITUÍDA por uma cópia da legenda da âncora.

ACHADO CRÍTICO QUE ESTE SCRATCHPAD REVELA (código vs artigo)
    last_high_id é inicializado como a string '0' (sentinela = "nenhuma âncora"),
    mas '0' é TAMBÉM um id de frame válido. A Eq. 2 do paper NÃO tem exceção para
    o frame 0. Logo, há um BUG DE COLISÃO DE SENTINELA: se o frame '0' for a
    âncora, o teste `last_high_id != '0'` (linha 33) falha e o denoising é
    silenciosamente PULADO para os frames seguintes. O Caso D abaixo prova isso.
================================================================================
"""

# =============================================================================
# BLOCO 0 — SUBSTRATO (idêntico em espírito ao _bootstrap.py; embutido p/ ser
#           autossuficiente, conforme o cenário escolhido)
# =============================================================================
import os
import sys
import random
import types

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
random.seed(0)

# Shim defensivo do torchtext (inócuo se ele funcionar) — ver scratch_construct.py
try:
    from torchtext.vocab import Vectors  # noqa: F401
except Exception:
    _tt = types.ModuleType("torchtext"); _ttv = types.ModuleType("torchtext.vocab")
    _ttv.Vectors = object; _tt.vocab = _ttv
    sys.modules.setdefault("torchtext", _tt); sys.modules.setdefault("torchtext.vocab", _ttv)

from types import SimpleNamespace
import torch


def bare(cls, **attrs):
    """Instancia sem __init__ (não carrega BLIP) e injeta só o necessário."""
    obj = object.__new__(cls)
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


# =============================================================================
# BLOCO 1 — GERADOR DE AMOSTRA SINTÉTICA
# =============================================================================
def make_meta(captions):
    """
    Constrói um `meta` no formato que denoise_caption espera.
    `captions` é uma lista de strings; cada frame recebe {'cap': <string>}, com
    id sequencial em STRING ('0','1',...). O 'cap' é um marcador rastreável: se
    o frame X for denoised a partir da âncora Y, meta[...][X]['cap'] == cap de Y.
    """
    return {
        "frame_captions": {str(i): {"cap": c} for i, c in enumerate(captions)}
    }


def caps_of(meta):
    """Extrai a lista de legendas na ordem dos frames (para asserção)."""
    return [m["cap"] for m in meta["frame_captions"].values()]


# =============================================================================
# BLOCO 2 — INSTANCIA O MÉTODO REAL SEM CARREGAR PESOS
# =============================================================================
from pipeline.denoiser.window import WindowSimDenoiser

# denoise_caption usa APENAS self.cfg.figsim_denoise_thr e .denoise_window_width.
cfg = SimpleNamespace(figsim_denoise_thr=0.4, denoise_window_width=2)
denoiser = bare(WindowSimDenoiser, cfg=cfg)   # sem __init__ → sem BLIP


# =============================================================================
# BLOCO 3 — CASOS DE TESTE (amostra → roda o REAL → assert no valor)
# =============================================================================
print("=" * 66)
print("SWi-Den (denoise_caption) — verificação de lógica por VALOR")
print("θd =", cfg.figsim_denoise_thr, "| janela W =", cfg.denoise_window_width)
print("=" * 66)

# --- Caso A: PROPAGAÇÃO NORMAL PARA FRENTE -----------------------------------
# frame 1 é âncora alta; frame 2 é baixo, dentro da janela → deve receber a
# legenda da âncora (frame 1). frame 0 é alto (mas note o Caso D depois).
meta = make_meta(["CAP0", "CAP1", "CAP2"])
scores = torch.tensor([0.9, 0.9, 0.1])   # frame2 baixo, gap ao anchor(1) = 1 <= W
out = denoiser.denoise_caption(meta, scores)
got = caps_of(out)
assert got == ["CAP0", "CAP1", "CAP1"], f"Caso A falhou: {got}"
print("[OK] A) Propagação normal: frame baixo dentro da janela recebe a legenda da âncora.")
print(f"       ['CAP0','CAP1','CAP2'] --denoise--> {got}")

# --- Caso B: CAUSALIDADE (só para frente) ------------------------------------
# frame 0 é BAIXO e não há âncora antes dele → deve ficar INALTERADO
# (o denoiser nunca olha para frente; last_high_id ainda é o sentinela).
meta = make_meta(["LOW0", "HIGH1", "OK2"])
scores = torch.tensor([0.1, 0.9, 0.9])   # frame0 baixo, sem âncora anterior
out = denoiser.denoise_caption(meta, scores)
got = caps_of(out)
assert got[0] == "LOW0", f"Caso B falhou: frame 0 deveria ficar inalterado, veio {got}"
print("[OK] B) Causalidade: frame baixo ANTES de qualquer âncora fica inalterado.")
print(f"       ['LOW0','HIGH1','OK2'] --denoise--> {got}")

# --- Caso C: FRONTEIRA DA JANELA ---------------------------------------------
# frame 1 é âncora; frames 2,3,4 são baixos. Como 2 e 3 são baixos, NÃO viram
# novas âncoras → o anchor permanece o frame 1. Assim: frame2(gap1) e frame3
# (gap2) são denoised para a legenda da âncora; frame4(gap3 > W=2) NÃO é.
# (Nota: a 1ª versão deste caso tinha os frames intermediários ALTOS por engano;
#  o scratchpad pegou o erro na hora — o loop de exploração funcionando.)
meta = make_meta(["CAP0", "ANCHOR1", "LOW2", "LOW3", "FAR4"])
scores = torch.tensor([0.9, 0.9, 0.1, 0.1, 0.1])  # âncora só no frame 1
out = denoiser.denoise_caption(meta, scores)
got = caps_of(out)
assert got == ["CAP0", "ANCHOR1", "ANCHOR1", "ANCHOR1", "FAR4"], f"Caso C falhou: {got}"
print("[OK] C) Janela: frames dentro de W recebem a âncora; frame com gap>W NÃO.")
print(f"       frame4 gap=3 > W=2  →  permanece 'FAR4':  {got}")

# --- Caso D: O BUG DE COLISÃO DE SENTINELA (código vs artigo) -----------------
# frame 0 é âncora ALTA; frame 1 é baixo, dentro da janela (gap=1<=W).
# PELO ARTIGO (Eq. 2): frame 1 deveria receber a legenda da âncora (frame 0).
# PELO CÓDIGO: como last_high_id vira '0' (== sentinela), o guard `!= '0'`
# falha e o frame 1 NÃO é denoised. Este teste DOCUMENTA a divergência.
meta = make_meta(["ANCHOR0", "LOW1"])
scores = torch.tensor([0.9, 0.1])        # frame0 âncora, frame1 baixo, gap=1<=W
out = denoiser.denoise_caption(meta, scores)
got = caps_of(out)

expected_by_paper = ["ANCHOR0", "ANCHOR0"]   # o que a Eq. 2 prescreve
actual_by_code    = ["ANCHOR0", "LOW1"]      # o que o código faz (bug)

assert got == actual_by_code, f"Comportamento do código mudou: {got}"
divergence = (got != expected_by_paper)
print("[!!] D) BUG REVELADO — colisão de sentinela no frame 0:")
print(f"       esperado pelo ARTIGO (Eq.2): {expected_by_paper}")
print(f"       obtido pelo CÓDIGO:          {got}")
print(f"       divergência código-vs-artigo confirmada: {divergence}")

print()
print("=" * 66)
print("LÓGICA VERIFICADA (A,B,C) + DIVERGÊNCIA DOCUMENTADA (D).")
print("Nenhum modelo carregado; execução instantânea.")
print("=" * 66)


# =============================================================================
# BLOCO 4 — PROMOÇÃO A TESTE FORMAL
# =============================================================================
# Cada `assert` acima vira um `def test_...()` em tests/unit/test_denoiser_window.py.
# O Caso D em especial merece virar teste permanente: ele trava a divergência
# código-vs-artigo, de modo que, se alguém "corrigir" o denoiser, o teste sinaliza
# a mudança de comportamento — conhecimento executável, não anotação perdida.
