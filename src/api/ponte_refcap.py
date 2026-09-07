"""Ponte entre a API e o RefCap: sys.path e caminhos absolutos.

DUAS ARMADILHAS QUE ESTE MÓDULO RESOLVE
---------------------------------------

0) ONDE ESTE DIRETORIO PODE FICAR
   Os dois arranjos funcionam, sem alterar codigo:

       (A) ao LADO do RefCap          (B) DENTRO do RefCap
           projeto/                       projeto/
           |- src/   <- RefCap            `- src/   <- RefCap
           `- api/                           `- api/

   A raiz e' localizada por MARCADOR (pipeline/propgenerator/base.py), nao por
   caminho fixo. REFCAP_ROOT, se definida, tem precedencia sobre a descoberta.

1) COMO IMPORTAR O RefCap
   O RefCap usa imports ABSOLUTOS DE TOPO (`from pipeline.denoiser import *`,
   `import utils.basic_utils`). Portanto a RAIZ DO RefCap precisa estar em
   `sys.path` — e não o diretório-pai dela.

   ✓ FUNCIONA : sys.path += [".../src"]  ->  from pipeline... import
   ✗ QUEBRA   : sys.path += ["..."]      ->  from src.pipeline... import
                (verificado: ModuleNotFoundError: No module named 'utils')

2) OS CAMINHOS DO cfg SÃO RELATIVOS
   `config/cfg.py` traz defaults como `meta_dir="meta"`, `res_dir="results"`,
   `anno_dir="annos"`. Se o serviço rodar com CWD=api/, esses caminhos
   resolveriam para `api/meta`, `api/results` — e não para dentro do RefCap.

   A solução adotada aqui é preencher o cfg com caminhos ABSOLUTOS, em vez de
   fazer os.chdir(). Assim o CWD do processo fica livre para logs, uploads
   temporários e qualquer caminho do seu próprio código.
"""
from __future__ import annotations

import os
import pathlib
import sys

# --------------------------------------------------------------------------- #
# Localização do RefCap — funciona nos DOIS arranjos possíveis
# --------------------------------------------------------------------------- #
# A raiz é localizada por um MARCADOR (`pipeline/propgenerator/base.py`), não
# por caminho fixo. Isso torna o serviço agnóstico ao layout:
#
#   (A) api/ AO LADO do RefCap          (B) api/ DENTRO do RefCap
#       projeto/                            projeto/
#       ├── src/    <- RefCap               └── src/    <- RefCap
#       └── api/                                └── api/
#
# A variável de ambiente REFCAP_ROOT, se definida, tem precedência sobre tudo.
_AQUI = pathlib.Path(__file__).resolve().parent

_MARCADOR = pathlib.Path("pipeline") / "propgenerator" / "base.py"

# Nomes usuais da pasta do RefCap quando ela é IRMÃ da api/.
_NOMES_IRMAOS = ("src", "RefCap", "refcap")


def _e_raiz(caminho: pathlib.Path) -> bool:
    return (caminho / _MARCADOR).is_file()


def _descobrir_raiz() -> pathlib.Path:
    """Descobre a raiz do RefCap, cobrindo os dois arranjos.

    Ordem de tentativa:
      1. REFCAP_ROOT (se definida) — precedência absoluta
      2. subindo a partir daqui    — cobre o arranjo (B), api/ DENTRO
      3. irmãos com nome usual     — cobre o arranjo (A), api/ AO LADO
    """
    definida = os.environ.get("REFCAP_ROOT")
    if definida:
        raiz = pathlib.Path(definida).resolve()
        if not _e_raiz(raiz):
            raise RuntimeError(
                f"REFCAP_ROOT aponta para {raiz}, mas '{_MARCADOR}' não existe lá."
            )
        return raiz

    # (B) api/ dentro do RefCap: subindo, achamos a raiz
    for candidato in [_AQUI, *_AQUI.parents]:
        if _e_raiz(candidato):
            return candidato

    # (A) api/ ao lado do RefCap: procuramos entre os irmãos
    for nome in _NOMES_IRMAOS:
        candidato = (_AQUI.parent / nome).resolve()
        if _e_raiz(candidato):
            return candidato

    raise RuntimeError(
        f"RefCap não encontrado a partir de {_AQUI}.\n"
        f"Procurei por '{_MARCADOR}':\n"
        f"  - subindo a árvore de diretórios (api/ dentro do RefCap)\n"
        f"  - nos irmãos {_NOMES_IRMAOS} (api/ ao lado do RefCap)\n"
        f"Defina REFCAP_ROOT apontando para a raiz do RefCap."
    )


RAIZ_REFCAP = _descobrir_raiz()


def nomes_de_topo_do_refcap() -> set[str]:
    """Os nomes que o RefCap ocupa no topo — pacotes e módulos."""
    nomes = set()
    for p in RAIZ_REFCAP.iterdir():
        if p.name.startswith((".", "__")):
            continue
        if p.is_dir():
            nomes.add(p.name)
        elif p.suffix == ".py":
            nomes.add(p.stem)
    return nomes


def checar_colisoes(dir_api: pathlib.Path | None = None) -> list[str]:
    """Detecta módulos da API que SOMBREIAM nomes de topo do RefCap.

    ★ POR QUE ISTO EXISTE
        O `api/` fica dentro da raiz do RefCap, e o diretório do app entra em
        `sys.path` ANTES dela. Então um `api/pipeline.py` ocupa o nome
        `pipeline` em `sys.modules`, e o `from pipeline.denoiser import *` do
        construct.py falha com uma mensagem que não diz a causa:

            ModuleNotFoundError: No module named 'pipeline.denoiser';
                                 'pipeline' is not a package

        Aconteceu de verdade. Esta checagem transforma isso num aviso claro,
        no startup, em vez de um erro obscuro na primeira requisição.
    """
    dir_api = dir_api or _AQUI
    do_refcap = nomes_de_topo_do_refcap()
    colisoes = []
    for p in dir_api.iterdir():
        if p.name.startswith((".", "__")):
            continue
        nome = p.stem if p.suffix == ".py" else (p.name if p.is_dir() else None)
        if nome and nome in do_refcap:
            colisoes.append(nome)
    return sorted(colisoes)


def preparar_sys_path(avisar_colisoes: bool = True) -> None:
    """Põe a RAIZ do RefCap no sys.path. Idempotente."""
    caminho = str(RAIZ_REFCAP)
    if caminho not in sys.path:
        sys.path.insert(0, caminho)

    if avisar_colisoes:
        colisoes = checar_colisoes()
        if colisoes:
            raise RuntimeError(
                f"COLISÃO DE NOMES entre a API e o RefCap: {colisoes}\n"
                f"\n"
                f"Os módulos acima existem em ambos, e o do api/ vence — o que\n"
                f"quebra os imports internos do RefCap com mensagens como\n"
                f"  \"No module named 'X.y'; 'X' is not a package\".\n"
                f"\n"
                f"Renomeie o(s) arquivo(s) em {dir(_AQUI) and _AQUI}.\n"
                f"Nomes ocupados pelo RefCap: {sorted(nomes_de_topo_do_refcap())}"
            )


# --------------------------------------------------------------------------- #
# Construção do cfg com caminhos absolutos
# --------------------------------------------------------------------------- #
# Campos de `config/cfg.py` cujo default é RELATIVO e que precisam virar
# absolutos para o serviço funcionar de qualquer CWD.
_CAMPOS_DE_CAMINHO = (
    "anno_dir",      # cfg.py:5   -> "annos"
    "meta_dir",      # cfg.py:9   -> "meta"
    "res_dir",       # cfg.py:14  -> "results"
    "video_root",    # cfg.py:35
)
# Nota: captions_dir, framefeatures_dir, raw_capframe_scores_dir e construct_dir
# também são relativos, MAS o RefCap sempre os usa em os.path.join(meta_dir, X)
# ou os.path.join(res_dir, X). Como as bases viram absolutas, eles seguem junto.


def montar_cfg(**sobrescritas):
    """Monta um `BuildArguments` sem passar pela linha de comando.

    O `construct.py` original faz `HfArgumentParser(...).parse_args_into_dataclasses()`,
    que lê `sys.argv` — inviável num serviço. Aqui instanciamos direto.

    Todos os campos de caminho viram ABSOLUTOS, ancorados em RAIZ_REFCAP.

    ⚠️ `cfg.exp_dir` NÃO é definido aqui: ele é injetado pelo `build()` do
    RefCap (construct.py), a partir de res_dir/construct_dir/collection/construct_name.
    Não tente defini-lo antes — seria sobrescrito.
    """
    preparar_sys_path()
    from config import BuildArguments  # noqa: PLC0415 — só após o sys.path

    cfg = BuildArguments()

    # 1) torna os caminhos absolutos
    for campo in _CAMPOS_DE_CAMINHO:
        valor = getattr(cfg, campo, None)
        if isinstance(valor, str) and valor and not os.path.isabs(valor):
            setattr(cfg, campo, str(RAIZ_REFCAP / valor))

    # 2) aplica o que o chamador pediu (já em absoluto, se for caminho)
    for chave, valor in sobrescritas.items():
        if not hasattr(cfg, chave):
            raise AttributeError(
                f"BuildArguments não tem o campo {chave!r}. "
                f"Se for um campo novo, declare-o em config/cfg.py."
            )
        setattr(cfg, chave, valor)

    return cfg


def caminho_no_refcap(*partes) -> str:
    """Monta um caminho absoluto dentro do RefCap. Ex.: caminho_no_refcap('meta')."""
    return str(RAIZ_REFCAP.joinpath(*partes))
