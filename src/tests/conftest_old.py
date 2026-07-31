import os, sys, random
from types import SimpleNamespace
import numpy as np
import pytest

# (1) RESOLUÇÃO DE IMPORT — o repo não é pip-instalável; injeta a raiz no sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# (2) DETERMINISMO GLOBAL
os.environ.setdefault("PYTHONHASHSEED", "0")   # afeta ordenação de set/dict (Keyword Set é set!)

@pytest.fixture(autouse=True)
def _seed_everything():
    random.seed(0); np.random.seed(0)
    try:
        import torch; torch.manual_seed(0)
    except ImportError:
        pass

# (3) CFG FALSO — SimpleNamespace com os NOMES REAIS dos parâmetros do RefCap
@pytest.fixture
def cfg():
    return SimpleNamespace(
        device="cpu",
        figsim_denoise_thr=0.4, denoise_window_width=2,          # SWi-Den
        prop_kernel_width=5, prop_score_thr=0.2, prop_min_cnt=2,  # QM-Gen
        prop_max_cnt=5, min_prop_size=3, prop_sim_type="it",
        retrieve_sent_ratio=0.5, key_policy="max_mean",           # Retrieval
        max_key_cnt_per_proposal=50,
    )

# (4) INSTANCIAÇÃO SEM CARREGAR PESOS — bypass de __init__ para métodos de lógica pura
@pytest.fixture
def denoiser(cfg):
    from pipeline.denoiser.window import WindowSimDenoiser
    obj = object.__new__(WindowSimDenoiser)   # NÃO chama __init__ → não carrega BLIP
    obj.cfg = cfg                              # injeta só o que denoise_caption usa
    return obj

# (5) ENTRADA SINTÉTICA (exemplo)
@pytest.fixture
def two_block_sim():
    """Matriz com duas metades distintas → fronteira conhecida no meio."""
    import torch
    n = 20; m = torch.zeros(n, n); m[:10, :10] = 1.0; m[10:, 10:] = 1.0
    return m
