"""
scratch/scratch_construct.py
================================================================================
SCRATCHPAD DE TESTE — verificação da LÓGICA de BaseConstructPipeline.construct()
================================================================================

OBJETIVO
    Verificar, de forma flexível e SEM carregar nenhum modelo pesado (BLIP,
    spaCy, sentence-transformers, ffmpeg), se a LÓGICA de `construct()` está
    correta. Aqui `construct` é IMPORTADO do módulo real (não copiado) — se o
    código-fonte mudar, este scratchpad exercita a versão nova automaticamente.

O QUE SIGNIFICA "A LÓGICA DE construct() ESTÁ CORRETA"
    `construct()` é um ORQUESTRADOR: ele não computa nada por si: encadeia 7
    chamadas a componentes/métodos pesados. Logo, sua "lógica" NÃO é "as legendas
    ficam boas" (isso é a lógica DOS COMPONENTES, testada em outros scratchpads).
    A lógica de construct() é o GRAFO DE DEPENDÊNCIAS:
        (1) todas as 7 etapas são executadas;
        (2) na ORDEM correta;
        (3) com o ENCADEAMENTO de dados correto — a saída de uma etapa entra
            como argumento da próxima (ex.: o denoiser recebe as legendas do
            captioning; a segmentação recebe os scores JÁ recomputados sobre as
            legendas denoised, não os scores brutos).
    Verificar isso é um TESTE DE INTERAÇÃO (o que foi chamado, em que ordem, com
    quais argumentos), NÃO um teste de valor. Por isso usamos DUBLÊS (spies) no
    lugar dos componentes reais: cada dublê apenas registra que foi chamado e
    devolve um marcador sintético rastreável.

COMO RODAR
    Da raiz do repositório:   python scratch/scratch_construct.py
    Ou interativo:            ipython -i scratch/scratch_construct.py
    (cenário (ii): este arquivo é AUTOSSUFICIENTE — não depende do conftest.py
     do aparato pytest. Todo o substrato mínimo está aqui embaixo.)

COMO REPLICAR ISTO PARA OUTROS TRECHOS
    Antes de escrever o scratchpad de um trecho, pergunte:
      "este trecho COMPUTA UM VALOR ou COORDENA outras peças?"
        - Coordena  -> teste de INTERAÇÃO (dublês + asserções de ordem/args),
                       como aqui.
        - Computa   -> teste de VALOR (amostra sintética + assert no resultado);
                       use `bare()` se o método usar self.cfg + poucos atributos.
================================================================================
"""

# =============================================================================
# BLOCO 0 — SUBSTRATO MÍNIMO (resolve as 2 fricções do RefCap, uma vez)
# =============================================================================
# Fricção 1: o repositório NÃO é pip-instalável (sem setup.py/pyproject.toml);
#            a resolução de import é via PYTHONPATH. Injetamos a raiz no sys.path
#            — é o equivalente Python de `source setup.sh`.
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Determinismo (irrelevante para este teste de interação, mas é boa higiene e
# você vai querer em scratchpads de VALOR).
import random
random.seed(0)

# --- Blindagem defensiva contra dependência transitiva FRÁGIL ----------------
# construct() NÃO usa torchtext/GloVe (isso vive em capTree.encode_keys, que não
# é exercitado aqui). Mas base.py importa capTree, que importa torchtext no topo.
# torchtext é descontinuado e QUEBRA com torch recente (o .so não carrega). Se
# ele estiver ausente/quebrado, instalamos um STUB mínimo em sys.modules para a
# cadeia de import resolver — sem instalar nada, sem tocar o caminho sob teste.
# No seu ambiente refcap-test (torch 2.2.0 + torchtext 0.17.0, ambos pinados no
# requirements.txt), o `try` passa e esta blindagem é INÓCUA. Ela é o análogo,
# em nível de import, do "mocke o GloVe no T0/T1" do relatório de infraestrutura.
import types
try:
    from torchtext.vocab import Vectors  # noqa: F401  (só testa se resolve)
except Exception:
    _tt = types.ModuleType("torchtext")
    _ttv = types.ModuleType("torchtext.vocab")
    _ttv.Vectors = object  # placeholder; jamais instanciado neste teste
    _tt.vocab = _ttv
    sys.modules.setdefault("torchtext", _tt)
    sys.modules.setdefault("torchtext.vocab", _ttv)

from types import SimpleNamespace


def bare(cls, **attrs):
    """
    Instancia `cls` SEM chamar seu __init__ (via object.__new__) e injeta à mão
    apenas os atributos passados. É a chave para trechos cujo __init__ é hostil.

    Aqui isto é INDISPENSÁVEL: BaseConstructPipeline.__init__ (base.py:37) faz
    os.listdir(video_root), lê annos/ via select_videos, carrega o BLIP e cria
    diretórios em disco — três razões independentes pelas quais instanciar
    normalmente num scratchpad é impossível. Com bare(), pulamos tudo isso e
    injetamos SÓ os 4 atributos que construct() de fato usa.
    """
    obj = object.__new__(cls)
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


# =============================================================================
# BLOCO 1 — O DUBLÊ (spy): grava toda chamada num diário compartilhado
# =============================================================================
class Spy:
    """
    Um dublê de teste que:
      - registra CADA chamada (nome, kwargs) num diário compartilhado `journal`,
        na ordem em que ocorrem;
      - devolve um MARCADOR sintético rastreável (ex.: "<captions>") para que
        possamos seguir o dado fluindo de uma etapa para a próxima.

    Não há biblioteca envolvida: é ~10 linhas de Python puro. (unittest.mock.Mock
    faria o mesmo; preferimos explícito aqui para o scratchpad ser transparente.)
    """
    def __init__(self, name, journal, return_value):
        self.name = name
        self.journal = journal
        self.return_value = return_value

    def __call__(self, *args, **kwargs):
        # Grava a interação: quem foi chamado e com quais argumentos nomeados.
        self.journal.append((self.name, kwargs))
        return self.return_value


# =============================================================================
# BLOCO 2 — MONTAGEM DO EXPERIMENTO
# =============================================================================
# Importa a CLASSE REAL do módulo (não copia a função). construct() é um método
# de instância, então importamos a classe e chamamos o método na instância bare.
from pipeline.constructpipe.base import BaseConstructPipeline

# Diário compartilhado: todos os dublês escrevem aqui, preservando a ordem.
journal = []

# cfg falso: construct() lê apenas atributos de caminho para montar strings.
# Damos valores-sentinela; nada toca disco porque os métodos de escrita também
# serão dublês (ver abaixo).
cfg = SimpleNamespace(
    meta_dir="META",
    raw_capframe_scores_dir="RAW_SCORES",
    collection="mycorpus",
    caption_generator="blip",
    exp_dir="EXP",
    denoised_capframe_scores_file="denoised_scores.pt",
)

# Marcadores sintéticos rastreáveis — cada etapa "produz" um destes, e nós
# verificamos que ele reaparece como argumento da etapa seguinte.
CAPTIONS        = "<captions>"
FEATURES        = "<features>"
RAW_SCORES      = "<raw_scores>"
DENOISED_CAPS   = "<denoised_captions>"
DENOISED_SCORES = "<denoised_scores>"
PROPOSALS       = "<proposals>"
TREE_META       = "<tree_meta>"

# Instancia a classe REAL sem __init__, injetando só o que construct() usa:
pipe = bare(
    BaseConstructPipeline,
    cfg=cfg,
    vid_list=["v1.mp4", "v2.mp4"],  # construct() só repassa isto adiante
    # Os 3 COMPONENTES (atributos setados no __init__ real) viram dublês:
    caption_generator=Spy("caption_generator", journal, return_value=CAPTIONS),
    caption_denoiser=Spy("caption_denoiser", journal, return_value=DENOISED_CAPS),
    proposal_generator=Spy("proposal_generator", journal, return_value=PROPOSALS),
)

# ATENÇÃO — o ponto sutil: compute_frame_features, compute_capframe_scores e
# build_tree_meta são MÉTODOS DA PRÓPRIA INSTÂNCIA. Se não os substituirmos,
# construct() executaria a lógica pesada real deles. Então os sobrescrevemos na
# instância com dublês também. Note que compute_capframe_scores é chamado DUAS
# vezes (scores brutos e denoised): um único dublê registra ambas as chamadas,
# e devolvemos valores diferentes por chamada para rastrear o encadeamento.
pipe.compute_frame_features = Spy("compute_frame_features", journal, return_value=FEATURES)
pipe.build_tree_meta = Spy("build_tree_meta", journal, return_value=TREE_META)


# compute_capframe_scores precisa devolver RAW na 1ª chamada e DENOISED na 2ª —
# um Spy simples devolve sempre o mesmo valor. Fazemos um dublê com estado:
class ScoresSpy:
    def __init__(self, journal, sequence):
        self.journal = journal
        self.sequence = list(sequence)
        self.i = 0

    def __call__(self, *args, **kwargs):
        self.journal.append(("compute_capframe_scores", kwargs))
        rv = self.sequence[self.i]
        self.i += 1
        return rv


pipe.compute_capframe_scores = ScoresSpy(journal, sequence=[RAW_SCORES, DENOISED_SCORES])


# =============================================================================
# BLOCO 3 — EXECUÇÃO DO FLUXO REAL
# =============================================================================
# Chama o construct() REAL (importado). Ele vai encadear os dublês. Nada pesado
# roda; nada toca disco; é instantâneo.
result = pipe.construct()


# =============================================================================
# BLOCO 4 — VERIFICAÇÃO DA LÓGICA (asserções sobre INTERAÇÃO, não sobre valor)
# =============================================================================
# Extraímos só os nomes das chamadas, na ordem em que ocorreram.
called_in_order = [name for (name, _kwargs) in journal]
kwargs_by_call = journal  # lista de (name, kwargs)

print("Ordem das chamadas registradas:")
for i, (name, kwargs) in enumerate(journal, 1):
    print(f"  {i}. {name}({', '.join(f'{k}=...' for k in kwargs)})")
print()

# --- Verificação (1): todas as 7 etapas rodaram, exatamente uma vez cada
#     (com compute_capframe_scores rodando DUAS vezes, por design). ---
expected_sequence = [
    "caption_generator",
    "compute_frame_features",
    "compute_capframe_scores",   # 1ª: scores brutos
    "caption_denoiser",
    "compute_capframe_scores",   # 2ª: scores sobre legendas denoised
    "proposal_generator",
    "build_tree_meta",
]
assert called_in_order == expected_sequence, (
    f"ORDEM/ETAPAS INCORRETAS.\n  esperado: {expected_sequence}\n  obtido:   {called_in_order}"
)
print("[OK] (1) As 7 etapas rodaram na ORDEM correta (scores recomputados 2x).")

# --- Verificação (2): ENCADEAMENTO DE DADOS — a saída de cada etapa entra na
#     próxima. Este é o coração da lógica de construct(). ---

# 2a. O denoiser recebe as legendas produzidas pelo captioning.
denoiser_call = next(kw for (n, kw) in kwargs_by_call if n == "caption_denoiser")
assert denoiser_call.get("captions") == CAPTIONS, \
    "O denoiser NÃO recebeu as legendas do captioning."
assert denoiser_call.get("raw_scores") == RAW_SCORES, \
    "O denoiser NÃO recebeu os scores BRUTOS."
print("[OK] (2a) O denoiser recebe as legendas do captioning + os scores brutos.")

# 2b. PONTO CRÍTICO: a 2ª chamada de scores usa as legendas DENOISED (não as brutas).
scores_calls = [kw for (n, kw) in kwargs_by_call if n == "compute_capframe_scores"]
assert scores_calls[0].get("captions") == CAPTIONS, \
    "1ª chamada de scores deveria usar as legendas BRUTAS."
assert scores_calls[1].get("captions") == DENOISED_CAPS, \
    "2ª chamada de scores deveria usar as legendas DENOISED — este é o refino do RefCap."
print("[OK] (2b) Scores recomputados sobre as legendas DENOISED (o refino: raw -> denoised).")

# 2c. PONTO CRÍTICO: a segmentação recebe os scores RECOMPUTADOS (denoised),
#     não os brutos — senão a Quality-Mask usaria qualidade desatualizada.
propgen_call = next(kw for (n, kw) in kwargs_by_call if n == "proposal_generator")
assert propgen_call.get("captions") == DENOISED_CAPS, \
    "A segmentação deveria receber as legendas DENOISED."
assert propgen_call.get("scores") == DENOISED_SCORES, \
    "A segmentação deveria receber os scores DENOISED (recomputados), não os brutos."
assert propgen_call.get("all_frame_features") == FEATURES, \
    "A segmentação deveria receber as features de frame."
print("[OK] (2c) A segmentação recebe legendas + scores DENOISED + features.")

# 2d. build_tree_meta recebe os proposals gerados, e construct() devolve o que
#     build_tree_meta devolveu.
tree_call = next(kw for (n, kw) in kwargs_by_call if n == "build_tree_meta")
# build_tree_meta(proposals) é posicional no fonte; o Spy grava só kwargs, então
# verificamos o retorno final como proxy do encadeamento terminal.
assert result == TREE_META, \
    "construct() deveria retornar o resultado de build_tree_meta."
print("[OK] (2d) construct() retorna o tree_meta produzido pela última etapa.")

print()
print("=" * 60)
print("LÓGICA DE construct() VERIFICADA: fluxo, ordem e encadeamento corretos.")
print("Nenhum modelo carregado; nenhum disco tocado; execução instantânea.")
print("=" * 60)


# =============================================================================
# BLOCO 5 — PROMOÇÃO A TESTE FORMAL (quando/se você quiser travar isto)
# =============================================================================
# Para promover ao aparato pytest, o recorte é mínimo: mova os BLOCOS 1–4 para
# tests/integration/test_construct_flow.py, embrulhe as asserções numa função
# `def test_construct_flow():`, e — se o conftest.py compartilhar o substrato —
# `bare` e os dublês vêm de lá (sem reescrita). O scratchpad frouxo e o teste
# formal compartilham o mesmo substrato; a promoção é um RECORTE, não uma cópia.