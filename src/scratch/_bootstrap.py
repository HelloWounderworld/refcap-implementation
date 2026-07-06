# scratch/_bootstrap.py — carregue no topo de um scratchpad:  from _bootstrap import *
# (ou embuta este bloco no próprio scratchpad, para torná-lo 100% autossuficiente)
import os, sys, random, types
import numpy as np

# (1) RESOLUÇÃO DE IMPORT (= source setup.sh): o repo não é pip-instalável
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# (2) DETERMINISMO
os.environ.setdefault("PYTHONHASHSEED", "0")
random.seed(0); np.random.seed(0)
try:
    import torch; torch.manual_seed(0)
except ImportError:
    pass

# (3) SHIM DE DEPENDÊNCIA FRÁGIL — torchtext quebra ao carregar com torch recente.
#     A maioria da lógica (construct, denoise, kernel) NÃO usa GloVe; então stubamos
#     torchtext em sys.modules para a cadeia de import resolver, sem instalar nada.
#     Inócuo se torchtext funcionar (o try passa).
try:
    from torchtext.vocab import Vectors  # noqa: F401
except Exception:
    _tt = types.ModuleType("torchtext"); _ttv = types.ModuleType("torchtext.vocab")
    _ttv.Vectors = object; _tt.vocab = _ttv
    sys.modules.setdefault("torchtext", _tt); sys.modules.setdefault("torchtext.vocab", _ttv)

# (4) BYPASS DE __init__ — instancia sem carregar pesos e injeta só os atributos usados
def bare(cls, **attrs):
    obj = object.__new__(cls)
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj

# (5) CFG FALSO reutilizável
from types import SimpleNamespace
def make_cfg(**overrides):
    base = dict(device="cpu", figsim_denoise_thr=0.4, denoise_window_width=2,
                prop_kernel_width=5, prop_score_thr=0.2, prop_min_cnt=2, prop_max_cnt=5,
                min_prop_size=3, prop_sim_type="it", retrieve_sent_ratio=0.5,
                key_policy="max_mean", max_key_cnt_per_proposal=50)
    base.update(overrides); return SimpleNamespace(**base)

# (6) DUBLÊ (spy) para testar ORQUESTRADORES por interação
class Spy:
    def __init__(self, name, journal, return_value):
        self.name, self.journal, self.return_value = name, journal, return_value
    def __call__(self, *a, **kw):
        self.journal.append((self.name, kw)); return self.return_value

# (7) GERADORES SINTÉTICOS reutilizáveis (para testes de VALOR)
def two_block_sim(n=20):
    import torch
    m = torch.zeros(n, n); m[:n//2, :n//2] = 1.0; m[n//2:, n//2:] = 1.0; return m

# (8) visualização
import matplotlib.pyplot as plt
