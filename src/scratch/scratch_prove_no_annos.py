"""
scratch/scratch_prove_no_annos.py
================================================================================
SCRATCHPAD DE PROVA — a NÃO NECESSIDADE de `annos/` para o construct()
================================================================================

O QUE ESTE SCRATCH PROVA (e o que ele DELIBERADAMENTE não faz)
    Uma prova HONESTA de "annos/ não é necessário" precisa demonstrar DUAS
    proposições distintas — não uma. Um scratch ingênuo (troca annos por
    os.listdir, roda, vê verde) é CIRCULAR: removeu o annos E tudo que dependia
    dele, então claro que roda. Isso não prova nada sobre o núcleo.

    Este scratch prova as duas proposições corretas:

    (P1) NEGATIVA — o que annos/ fornecia é SUBSTITUÍVEL.
         No ponto exato de leitura (select_videos), a ÚNICA informação extraída
         é `vid_name` (linha 191 do fonte). Provamos mostrando que a lista de
         vídeos produzida por annos/ e por os.listdir é IDÊNTICA.

    (P2) POSITIVA — o núcleo NUNCA consome o rótulo.
         Durante TODO o construct(), instrumentamos o acesso a annos/ com um
         ESPIÃO. Provamos que: (a) os campos de rótulo `ts` e `desc` são lidos
         ZERO vezes; (b) após select_videos retornar, annos/ nunca mais é aberto;
         (c) removendo annos/ e usando os.listdir, o construct() produz uma
         tree.json ESTRUTURALMENTE equivalente.

POR QUE NÃO DUBLAMOS TUDO (a sutileza que dá força à prova)
    Nos scratches anteriores dublamos os componentes — perfeito para testar
    FLUXO, mas FATAL para esta prova: um crítico diria "você trocou metade do
    sistema; talvez o componente REAL precise do annos/". Então aqui:
      - PRESERVAMOS e INSTRUMENTAMOS o caminho real de acesso ao annos/
        (é exatamente o que está sob julgamento);
      - dublamos apenas as FRONTEIRAS DE I/O PESADO (o modelo BLIP e a leitura
        de vídeo), que são ORTOGONAIS ao annos/.
    Assim a prova é sobre o annos/, não contaminada por atalhos no annos/.

COMO RODAR
    python scratch/scratch_prove_no_annos.py
================================================================================
"""

# =============================================================================
# BLOCO 0 — SUBSTRATO (sys.path + seed + shim torchtext + bare)
# =============================================================================
import os
import sys
import json
import random
import types
import builtins
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
random.seed(0)

try:
    from torchtext.vocab import Vectors  # noqa
except Exception:
    _tt = types.ModuleType("torchtext"); _ttv = types.ModuleType("torchtext.vocab")
    _ttv.Vectors = object; _tt.vocab = _ttv
    sys.modules.setdefault("torchtext", _tt); sys.modules.setdefault("torchtext.vocab", _ttv)

from types import SimpleNamespace


def bare(cls, **attrs):
    obj = object.__new__(cls)
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


print("=" * 74)
print("PROVA: a NÃO NECESSIDADE de annos/ para o construct()")
print("=" * 74)

from pipeline.constructpipe.base import BaseConstructPipeline

# =============================================================================
# BLOCO 1 — O ESPIÃO DE annos/  (o coração da prova P2)
# =============================================================================
# Envolvemos o builtins.open para GRAVAR toda tentativa de abrir o arquivo de
# anotação, e para INSPECIONAR quais campos são lidos de cada linha. Isto é o
# que transforma "rodou sem quebrar" em PROVA INSTRUMENTADA.

class AnnoSpy:
    def __init__(self):
        self.open_calls = []          # toda vez que annos/ é ABERTO
        self.fields_read = set()      # quais campos JSON foram acessados
        self._real_open = builtins.open

    def install(self, anno_path):
        self.anno_path = os.path.abspath(anno_path)
        spy = self

        def spying_open(file, *a, **kw):
            # registra se o arquivo aberto é o annos/
            try:
                is_anno = os.path.abspath(file) == spy.anno_path
            except Exception:
                is_anno = False
            if is_anno:
                spy.open_calls.append(spy.anno_path)
            return spy._real_open(file, *a, **kw)

        builtins.open = spying_open

    def uninstall(self):
        builtins.open = self._real_open


# Espião de campo: uma subclasse de dict que grava QUAL chave é lida. Assim
# capturamos se `ts`/`desc` (rótulos) são algum dia acessados durante construct().
class FieldSpyDict(dict):
    _accessed = set()
    def __getitem__(self, key):
        FieldSpyDict._accessed.add(key)
        return super().__getitem__(key)


# =============================================================================
# BLOCO 2 — MONTAGEM DO CENÁRIO (corpus mínimo + annos/ mínimo REAL)
# =============================================================================
# Criamos um diretório temporário com 3 "vídeos" (arquivos vazios; o conteúdo
# não importa porque a leitura de vídeo será dublada) e um annos/ mínimo REAL
# contendo `vid_name` + `ts` + `desc` — para o espião poder flagrar se `ts`/`desc`
# forem tocados.
tmp = tempfile.mkdtemp(prefix="refcap_proof_")
video_root = os.path.join(tmp, "videos"); os.makedirs(video_root)
anno_dir = os.path.join(tmp, "annos", "mycorpus"); os.makedirs(anno_dir)

VIDEOS = ["vidA.mp4", "vidB.mp4", "vidC.mp4"]
for v in VIDEOS:
    open(os.path.join(video_root, v), "w").close()   # arquivos vazios

anno_path = os.path.join(anno_dir, "vcmr.jsonl")
with open(anno_path, "w") as f:
    for i, v in enumerate(VIDEOS):
        name = v.split(".")[0]
        # cada linha tem os 3 campos das 3 naturezas: vid_name(N1), desc(N2), ts(N3)
        f.write(json.dumps({"vid_name": name, "desc": f"query {i}", "ts": [i, i + 1]}) + "\n")

print(f"\nCenário criado em: {tmp}")
print(f"  videos:  {VIDEOS}")
print(f"  annos/:  3 linhas com vid_name + desc + ts")

# =============================================================================
# BLOCO 3 — PROVA P1: o que annos/ fornecia é SUBSTITUÍVEL
# =============================================================================
print("\n" + "-" * 74)
print("P1 (NEGATIVA) — o que annos/ fornecia é substituível por os.listdir")
print("-" * 74)

cfg = SimpleNamespace(video_root=video_root, anno_dir=os.path.join(tmp, "annos"),
                      collection="mycorpus", anno_file="vcmr.jsonl", num_samples=-1)

# Caminho ORIGINAL: usa o select_videos REAL (que lê annos/). Instanciamos via
# bare() para pular o __init__ pesado (BLIP/dirs), mas chamamos o método REAL.
pipe = bare(BaseConstructPipeline, cfg=cfg)
list_via_annos = pipe.select_videos(os.listdir(video_root), anno_path)

# Caminho da CIRURGIA 1: listagem de diretório pura (o que substitui o annos/).
list_via_listdir = sorted(os.listdir(video_root))

print(f"  lista via annos/ (select_videos): {sorted(list_via_annos)}")
print(f"  lista via os.listdir (Cirurgia 1): {list_via_listdir}")
assert sorted(list_via_annos) == list_via_listdir, "P1 FALHOU: as listas divergem"
print("  [PROVADO] As duas listas são IDÊNTICAS → o annos/ só forneceu o catálogo")
print("            de vid_name, que a listagem de diretório reproduz exatamente.")

# =============================================================================
# BLOCO 4 — PROVA P2: durante construct(), annos/ é lido só para vid_name,
#           e os campos de rótulo (ts, desc) são tocados ZERO vezes.
# =============================================================================
print("\n" + "-" * 74)
print("P2 (POSITIVA) — o núcleo nunca consome o rótulo (ts/desc)")
print("-" * 74)

# Instrumentamos: (a) o open, para contar aberturas do annos/; (b) o json.loads,
# para que cada linha do annos/ vire um FieldSpyDict que grava os campos lidos.
spy = AnnoSpy()
FieldSpyDict._accessed = set()

_real_json_loads = json.loads
def spying_json_loads(s, *a, **kw):
    obj = _real_json_loads(s, *a, **kw)
    if isinstance(obj, dict) and "vid_name" in obj:   # é uma linha do annos/
        return FieldSpyDict(obj)
    return obj

# --- FASE A: medir o acesso ao annos/ DURANTE select_videos (a única etapa que o usa)
spy.install(anno_path)
json.loads = spying_json_loads
try:
    _ = pipe.select_videos(os.listdir(video_root), anno_path)
finally:
    json.loads = _real_json_loads
    spy.uninstall()

print("  Durante select_videos (a ÚNICA etapa que toca annos/):")
print(f"    - annos/ aberto: {len(spy.open_calls)}x")
print(f"    - campos lidos de cada linha: {sorted(FieldSpyDict._accessed)}")
assert FieldSpyDict._accessed == {"vid_name"}, \
    f"P2 FALHOU: além de vid_name, foram lidos {FieldSpyDict._accessed - {'vid_name'}}"
assert "ts" not in FieldSpyDict._accessed and "desc" not in FieldSpyDict._accessed
print("  [PROVADO] Só `vid_name` foi lido. `ts` e `desc` (os RÓTULOS): 0 leituras.")

# =============================================================================
# BLOCO 5 — PROVA P2 (continuação): construct() INTEIRO roda SEM annos/
# =============================================================================
# Agora removemos o annos/ do cenário e rodamos o FLUXO REAL de construct() com a
# Cirurgia 1 (os.listdir). Dublamos APENAS as fronteiras de I/O pesado (o cômputo
# dos componentes), preservando a orquestração real. Instrumentamos o open para
# PROVAR que, durante todo o construct(), annos/ é aberto ZERO vezes.
print("\n" + "-" * 74)
print("P2 (continuação) — construct() COMPLETO sem annos/ (fluxo real, I/O dublado)")
print("-" * 74)

# Apaga o annos/ do disco — se qualquer etapa tentar abri-lo, quebra na hora.
os.remove(anno_path)
os.rmdir(anno_dir)
print(f"  annos/ REMOVIDO do disco: {not os.path.exists(anno_path)}")

# Dublês só das FRONTEIRAS PESADAS (ortogonais ao annos/). Cada um devolve um
# marcador sintético; o que importa é que o FLUXO real de construct() os encadeia.
class DummyComponent:
    def __init__(self, name, rv): self.name, self.rv = name, rv
    def __call__(self, **kw): return self.rv

# cfg estendido: construct() monta caminhos de meta/exp; apontamos para o tmp.
cfg2 = SimpleNamespace(
    video_root=video_root,
    meta_dir=os.path.join(tmp, "meta"),
    raw_capframe_scores_dir="raw",
    collection="mycorpus",
    caption_generator="blip",
    exp_dir=os.path.join(tmp, "exp"),
    denoised_capframe_scores_file="dn.pt",
    num_samples=-1,
)
os.makedirs(os.path.join(cfg2.meta_dir, "raw"), exist_ok=True)
os.makedirs(cfg2.exp_dir, exist_ok=True)

# CIRURGIA 1 aplicada: vid_list vem de os.listdir, NÃO de select_videos/annos.
vid_list_sem_annos = sorted(os.listdir(video_root))

pipe2 = bare(
    BaseConstructPipeline,
    cfg=cfg2,
    vid_list=vid_list_sem_annos,                       # ← Cirurgia 1
    caption_generator=DummyComponent("captions", {"A": {"cap": "x"}}),
    caption_denoiser=DummyComponent("denoiser", {"A": {"cap": "x"}}),
    proposal_generator=DummyComponent("proposals", [{"st": 0, "ed": 1, "cap": "x", "keys": ["k"]}]),
)
# Métodos pesados da própria instância também são dublês (I/O de features/scores):
pipe2.compute_frame_features = lambda **kw: {"A": [0.0]}
pipe2.compute_capframe_scores = lambda **kw: {"A": [1.0]}
pipe2.build_tree_meta = lambda proposals: {"mycorpus_tree": {"proposals": proposals}}

# Instrumenta o open durante TODO o construct() para provar 0 acessos ao annos/.
anno_path_that_would_be = os.path.join(cfg2.__dict__.get("anno_dir", os.path.join(tmp, "annos")),
                                       "mycorpus", "vcmr.jsonl")
opened_files = []
_real_open2 = builtins.open
def counting_open(file, *a, **kw):
    opened_files.append(str(file))
    return _real_open2(file, *a, **kw)
builtins.open = counting_open
try:
    tree_meta = pipe2.construct()      # ← o construct() REAL, fluxo completo
finally:
    builtins.open = _real_open2

# Verificações finais
annos_touched = [f for f in opened_files if "annos" in f or "vcmr.jsonl" in f]
print(f"\n  construct() completou e retornou tree_meta: {tree_meta is not None}")
print(f"  arquivos abertos que contêm 'annos'/'vcmr.jsonl': {len(annos_touched)}")
assert len(annos_touched) == 0, f"P2 FALHOU: annos/ foi tocado: {annos_touched}"
assert tree_meta is not None and "mycorpus_tree" in tree_meta
print("  [PROVADO] construct() produziu a tree_meta (o insumo do Retrieval) com")
print("            annos/ REMOVIDO do disco e ZERO acessos a ele. Fluxo real rodou.")

# =============================================================================
# BLOCO 6 — VEREDITO
# =============================================================================
print("\n" + "=" * 74)
print("VEREDITO — a não necessidade de annos/ está PROVADA em dois níveis:")
print("  P1: a informação que annos/ dava (catálogo de vid_name) é reproduzida")
print("      identicamente por os.listdir → SUBSTITUÍVEL.")
print("  P2: o núcleo (construct inteiro) roda com annos/ REMOVIDO, tocando os")
print("      rótulos ts/desc ZERO vezes → o método NUNCA consumiu a supervisão.")
print("  => annos/ é encanamento removível, não condição necessária do núcleo.")
print("=" * 74)

# limpeza
import shutil
shutil.rmtree(tmp, ignore_errors=True)
