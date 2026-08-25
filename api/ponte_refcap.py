"""Ponte entre a API e o RefCap: sys.path e caminhos absolutos.

DUAS ARMADILHAS QUE ESTE MÓDULO RESOLVE
---------------------------------------

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
# Localização do RefCap
# --------------------------------------------------------------------------- #
# Por padrão, assume a estrutura:
#     <projeto>/
#     ├── src/   <- RefCap
#     └── api/   <- este serviço
# Pode ser sobrescrito pela variável de ambiente REFCAP_ROOT (útil no
# supervisord, em containers, ou se você renomear os diretórios).
_AQUI = pathlib.Path(__file__).resolve().parent

RAIZ_REFCAP = pathlib.Path(
    os.environ.get("REFCAP_ROOT", _AQUI.parent / "src")
).resolve()

_MARCADOR = pathlib.Path("pipeline") / "propgenerator" / "base.py"


def _validar_raiz() -> None:
    if not (RAIZ_REFCAP / _MARCADOR).is_file():
        raise RuntimeError(
            f"RefCap não encontrado em {RAIZ_REFCAP}.\n"
            f"Esperava achar '{_MARCADOR}' lá dentro.\n"
            f"Defina REFCAP_ROOT apontando para a raiz do RefCap."
        )


def preparar_sys_path() -> None:
    """Põe a RAIZ do RefCap no sys.path. Idempotente."""
    _validar_raiz()
    caminho = str(RAIZ_REFCAP)
    if caminho not in sys.path:
        sys.path.insert(0, caminho)


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
