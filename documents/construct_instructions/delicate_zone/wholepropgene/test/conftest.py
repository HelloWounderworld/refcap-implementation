"""Configuração do pytest para os testes do WholePropGenerator.

O QUE ESTE ARQUIVO FAZ
----------------------
Injeta *stubs* em `sys.modules` ANTES de qualquer import de `pipeline`, para
que a suíte rode sem torch, spacy, sentence-transformers, modelos BLIP ou
vídeos. Só é preciso `numpy` e `pytest`.

O que é STUB e o que é REAL:
  STUB : torch, spacy, tqdm, sentence_transformers, utils.*
  REAL : pipeline/propgenerator/base.py       (registry, decorador, ABC)
         pipeline/propgenerator/WholePropGener.py  (o componente sob teste)
         pipeline/propgenerator/__init__.py   (a linha de registro)

Manter `base.py` e `__init__.py` reais é deliberado: são eles que definem o
registro e a herança, e testar contra stubs deles não provaria que o
componente se registra no repositório de verdade.

⚠️ ESCOPO DOS STUBS
Este `conftest.py` afeta TODA a pasta onde está. Se você adicionar testes que
precisem do torch de verdade, coloque-os em outra pasta, com o próprio
conftest — senão eles receberão o stub.

ONDE ESTA PASTA PODE FICAR
Em QUALQUER nível DENTRO do repositório clonado. A raiz é localizada subindo
até achar `pipeline/propgenerator/base.py`. Exemplos que funcionam:
    <repo>/test/
    <repo>/tests/
    <repo>/test/whole_test/
    <repo>/qualquer/coisa/aqui/
O que NÃO funciona é pôr a pasta FORA do repositório — aí não há como
encontrar `pipeline` e `utils`.
"""
import sys
import types
import pathlib

import numpy as np
import pytest

# --------------------------------------------------------------------------- #
# Torna a raiz do repositório importável (para `pipeline` e `utils`).
#
# A raiz é localizada SUBINDO a partir deste arquivo até encontrar o marcador
# `pipeline/propgenerator/base.py`. Isso torna a suíte independente do nível:
# ela funciona em <repo>/test/, <repo>/tests/whole/, <repo>/a/b/c/, etc.
#
# (A alternativa ingênua — `parent.parent` — obrigaria a pasta a estar
#  exatamente um nível abaixo da raiz.)
# --------------------------------------------------------------------------- #
_MARCADOR = pathlib.Path("pipeline") / "propgenerator" / "base.py"


def _encontrar_raiz_do_repo(inicio: pathlib.Path) -> pathlib.Path:
    for candidato in [inicio, *inicio.parents]:
        if (candidato / _MARCADOR).is_file():
            return candidato
    raise RuntimeError(
        f"Não encontrei a raiz do RefCap subindo a partir de {inicio}.\n"
        f"Esperava achar '{_MARCADOR}' em algum diretório ancestral.\n"
        f"Coloque a pasta de testes DENTRO do repositório clonado."
    )


_RAIZ_REPO = _encontrar_raiz_do_repo(pathlib.Path(__file__).resolve().parent)
if str(_RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_REPO))


# --------------------------------------------------------------------------- #
# FakeTensor — ndarray com a API mínima de torch.Tensor que o componente usa
# --------------------------------------------------------------------------- #
class FakeTensor(np.ndarray):
    """`np.ndarray` com `.to()`, `.cpu()`, `.t()` e `.numpy()`.

    O componente chama esses métodos em tensores do PyTorch. Como aqui não há
    device nem grafo, todos são identidade (exceto `.t()`, que transpõe).
    """

    def to(self, *args, **kwargs):
        return self

    def cpu(self):
        return self

    def t(self):
        return self.T.view(FakeTensor)

    def numpy(self):
        return np.asarray(self)


def ft(array_like):
    """Embrulha algo num FakeTensor."""
    return np.asarray(array_like, dtype=float).view(FakeTensor)


# --------------------------------------------------------------------------- #
# Registro dos stubs em sys.modules
# --------------------------------------------------------------------------- #
def _modulo(nome, **atributos):
    m = types.ModuleType(nome)
    for k, v in atributos.items():
        setattr(m, k, v)
    sys.modules[nome] = m
    return m


class _ContextoVazio:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


# --- torch -------------------------------------------------------------- #
ARQUIVOS_SALVOS_TORCH = {}


def _torch_save(obj, caminho):
    ARQUIVOS_SALVOS_TORCH[str(caminho)] = obj


_torch = _modulo(
    "torch",
    no_grad=lambda: _ContextoVazio(),
    save=_torch_save,
    Tensor=FakeTensor,
)
# `QMPropGener.py` faz `import torch.nn.functional as F`
_nn = _modulo("torch.nn")
_modulo("torch.nn.functional", conv2d=None)
_torch.nn = _nn
_nn.functional = sys.modules["torch.nn.functional"]

# --- tqdm --------------------------------------------------------------- #
_modulo("tqdm", tqdm=lambda iteravel, *a, **kw: iteravel)

# --- spacy -------------------------------------------------------------- #
_modulo("spacy", load=lambda nome: object())

# --- sentence_transformers ---------------------------------------------- #
def _cos_sim(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a / np.linalg.norm(a, axis=1, keepdims=True)
    b = b / np.linalg.norm(b, axis=1, keepdims=True)
    return ft(a @ b.T)


_st_util = _modulo("sentence_transformers.util", cos_sim=_cos_sim)
_st = _modulo("sentence_transformers", util=_st_util)

# --- utils.* ------------------------------------------------------------ #
def _embedding_deterministico(textos):
    """Embedding reprodutível derivado do texto, normalizado em L2.

    Não imita o BLIP — serve para que a similaridade seja *determinística* e
    para que legendas iguais produzam vetores iguais, que é a propriedade de
    que os testes dependem.
    """
    vetores = []
    for texto in textos:
        h = [0.0] * 8
        for i, ch in enumerate(texto.lower()):
            h[i % 8] += (ord(ch) % 13) / 13.0
        v = np.array(h)
        vetores.append(v / np.linalg.norm(v))
    return ft(np.vstack(vetores))


CHAMADAS_SIM_UTILS = []


def _get_caption_features(sim_model, sim_processor, legendas, cfg):
    return _embedding_deterministico(legendas)


def _get_caption_frame_sims(sim_model, sim_processor, frame_features, legendas, cfg):
    """Reproduz o contrato REAL, INCLUSIVE o assert de shape.

    O original está em `utils/sim_utils.py:87`:
        assert frame_features.shape == cap_features.shape
    Ele é a razão de o componente chamar esta função com TODAS as N legendas,
    e não com as deduplicadas. Manter o assert aqui é o que faz o teste T12
    ter valor.
    """
    cap_features = _get_caption_features(sim_model, sim_processor, legendas, cfg)
    assert frame_features.shape == cap_features.shape, (
        f"shape mismatch: frames={frame_features.shape} caps={cap_features.shape}"
    )
    todas = ft(np.asarray(cap_features) @ np.asarray(frame_features).T)
    CHAMADAS_SIM_UTILS.append(
        {"n_legendas": len(legendas), "shape_frames": tuple(frame_features.shape)}
    )
    return ft(np.diag(np.asarray(todas))), todas


JSON_SALVO = {}


def _save_json(dados, caminho, save_pretty=False, sort_keys=False):
    JSON_SALVO[str(caminho)] = dados


def _get_nouns_verbs(nlp, legenda):
    """Stub determinístico: 'verbos' terminam em -ing; 'substantivos' têm >4 letras."""
    tokens = legenda.lower().replace(".", "").split()
    substantivos = [t for t in tokens if len(t) > 4 and not t.endswith("ing")]
    verbos = [t for t in tokens if t.endswith("ing")]
    return substantivos, verbos


_utils = _modulo("utils")
_modulo(
    "utils.sim_utils",
    get_caption_frame_sims=_get_caption_frame_sims,
    _get_caption_features=_get_caption_features,
    normalize_min_max=lambda t, dim: t,
)
_modulo("utils.basic_utils", save_json=_save_json)
_modulo("utils.tree_utils", get_nouns_verbs=_get_nouns_verbs)
_utils.sim_utils = sys.modules["utils.sim_utils"]
_utils.basic_utils = sys.modules["utils.basic_utils"]
_utils.tree_utils = sys.modules["utils.tree_utils"]


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def registry():
    """O registry REAL de `pipeline/propgenerator`, já com o "whole" registrado.

    Importar o pacote executa o `__init__.py`, que é justamente a linha de
    integração da instalação (§1.2 do manual). Se ela estiver faltando, este
    fixture falha — o que é o comportamento desejado.
    """
    from pipeline.propgenerator import PROPGEN_REGISTRY, get_propgen_class

    return {"registry": PROPGEN_REGISTRY, "get": get_propgen_class}


@pytest.fixture
def cfg(tmp_path):
    """Config mínima, com `exp_dir` num diretório temporário do pytest."""

    class Cfg:
        device = "cpu"
        exp_dir = str(tmp_path)
        proposals_file = "proposals.json"
        prop_sim_path = "prop_sims.pt"

    return Cfg()


@pytest.fixture
def models():
    class ModeloTexto:
        def encode(self, textos, **kwargs):
            return _embedding_deterministico(textos)

    return {
        "sentence_transformer": ModeloTexto(),
        "blip_itrtv_model": object(),
        "blip_itrtv_processor": object(),
    }


@pytest.fixture
def gen(registry, cfg, models):
    """Uma instância do WholePropGenerator pronta para uso."""
    CHAMADAS_SIM_UTILS.clear()
    JSON_SALVO.clear()
    ARQUIVOS_SALVOS_TORCH.clear()
    return registry["get"]("whole")(cfg, models)


# --------------------------------------------------------------------------- #
# Auxiliares para montar entradas (usados pelos testes)
# --------------------------------------------------------------------------- #
def montar_captions(vid_name, legendas, duration, chaves_str=False):
    """Monta o dicionário que o pipeline entrega ao gerador.

    `chaves_str=True` reproduz a 2ª execução, quando `frame_captions` é
    recarregado do `.jsonl` e o JSON converteu as chaves em string.
    """
    frame_captions = {}
    for i, legenda in enumerate(legendas):
        frame_captions[str(i) if chaves_str else i] = {"cap": legenda}
    return {
        "vid_name": vid_name,
        "duration": duration,
        "frame_captions": frame_captions,
    }


def features_de_frame(n, dim=8, seed=0):
    """Features visuais sintéticas, normalizadas em L2 (como as do BLIP)."""
    rng = np.random.default_rng(seed)
    f = rng.normal(size=(n, dim))
    return ft(f / np.linalg.norm(f, axis=1, keepdims=True))
