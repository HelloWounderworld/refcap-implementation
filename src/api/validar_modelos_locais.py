#!/usr/bin/env python3
"""
validar_modelos_locais.py — confere se os diretórios locais dos modelos estão
no formato que o `from_pretrained()` aceita.

POR QUE ISTO IMPORTA
--------------------
Quando você move um modelo do cache do HuggingFace para um diretório local,
existem DUAS estruturas possíveis — e só uma funciona direto:

  ✓ LAYOUT PLANO (snapshot)          ✗ LAYOUT DE CACHE (o do ~/.cache)
    /modelos/blip-caption/             /modelos/models--Salesforce--blip.../
    ├── config.json                    ├── blobs/
    ├── model.safetensors              ├── refs/
    ├── preprocessor_config.json       └── snapshots/
    ├── tokenizer_config.json              └── a1b2c3.../      <- os arquivos
    └── vocab.txt                              ├── config.json  (links p/ blobs)
                                               └── ...
    from_pretrained("/modelos/         from_pretrained("/modelos/models--...")
       blip-caption")  -> OK              -> FALHA

  No layout de cache você precisa OU apontar para `snapshots/<hash>/`,
  OU definir HF_HOME para o diretório que CONTÉM a pasta `hub/`.

★ POR QUE ISSO CAUSA LOOP NO SUPERVISORD
  Se o caminho estiver errado, o `from_pretrained()` interpreta como repo-id do
  Hub e tenta BAIXAR. Sem rede, falha; o processo morre; o supervisord reinicia.
  Resultado: o log mostra o carregamento várias vezes, com PIDs diferentes.

  A recomendação: defina HF_HUB_OFFLINE=1. Com ela, uma falha de caminho vira
  erro IMEDIATO e explícito, em vez de espera de rede seguida de erro obscuro.

USO
    python validar_modelos_locais.py /caminho/dos/modelos
    python validar_modelos_locais.py --caption /m/blip-cap --itm /m/blip-itm --st /m/sbert
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

LARG = 76

# Arquivos que cada tipo de modelo precisa ter no diretório.
PESOS = ("model.safetensors", "pytorch_model.bin", "model.ckpt.index", "flax_model.msgpack")

EXIGENCIAS = {
    "blip": {
        "obrigatorios": ["config.json"],
        "pesos": True,
        "processador": ["preprocessor_config.json"],
        "tokenizador": ["tokenizer_config.json", "vocab.txt"],
        "descricao": "BlipForConditionalGeneration / BlipForImageTextRetrieval + BlipProcessor",
    },
    "sentence_transformer": {
        "obrigatorios": ["modules.json", "config.json"],
        "pesos": True,
        "processador": [],
        "tokenizador": ["tokenizer_config.json"],
        "descricao": "SentenceTransformer",
        "extra_dirs": ["1_Pooling"],
    },
}


def titulo(t: str) -> None:
    print("\n" + "=" * LARG)
    print(f" {t}")
    print("=" * LARG)


def detectar_layout(caminho: pathlib.Path) -> tuple[str, pathlib.Path | None]:
    """Descobre se é layout plano, de cache, ou desconhecido.

    Devolve (layout, caminho_correto_a_usar).
    """
    if not caminho.exists():
        return "inexistente", None

    if (caminho / "config.json").is_file():
        return "plano", caminho

    # layout de cache: tem snapshots/<hash>/
    snapshots = caminho / "snapshots"
    if snapshots.is_dir():
        hashes = [d for d in snapshots.iterdir() if d.is_dir()]
        if hashes:
            mais_recente = max(hashes, key=lambda d: d.stat().st_mtime)
            return "cache", mais_recente
        return "cache_vazio", None

    # pode ser um diretório PAI contendo vários models--*
    filhos_cache = [d for d in caminho.iterdir() if d.is_dir() and d.name.startswith("models--")]
    if filhos_cache:
        return "pai_de_cache", None

    return "desconhecido", None


def validar(nome: str, caminho_str: str, tipo: str) -> bool:
    print(f"\n  ── {nome}")
    print(f"     caminho informado: {caminho_str}")

    caminho = pathlib.Path(caminho_str).expanduser()

    # É um repo-id do Hub, não um caminho?
    if not caminho.is_absolute() and not caminho.exists() and "/" in caminho_str:
        print(f"     ⚠️ parece um REPO-ID do Hub ('{caminho_str}'), não um caminho local.")
        print(f"        Sem rede, o from_pretrained() vai FALHAR aqui.")
        return False

    layout, usar = detectar_layout(caminho)

    if layout == "inexistente":
        print(f"     ✗ o diretório NÃO EXISTE")
        return False

    if layout == "cache":
        print(f"     ⚠️ LAYOUT DE CACHE detectado")
        print(f"        from_pretrained() NÃO aceita este diretório direto.")
        print(f"        USE ESTE CAMINHO:")
        print(f"            {usar}")
        caminho = usar
    elif layout == "pai_de_cache":
        print(f"     ⚠️ isto parece o diretório PAI de um cache do HuggingFace")
        print(f"        (contém pastas 'models--*'). Ou aponte para o snapshot")
        print(f"        de cada modelo, ou defina HF_HOME para o pai de 'hub/'.")
        return False
    elif layout == "cache_vazio":
        print(f"     ✗ há 'snapshots/' mas está vazio")
        return False
    elif layout == "desconhecido":
        print(f"     ✗ não achei config.json nem estrutura de cache")
        listagem = sorted(p.name for p in caminho.iterdir())[:8]
        print(f"        conteúdo: {listagem}")
        return False
    else:
        print(f"     ✓ layout plano")

    # --- confere os arquivos ---
    exig = EXIGENCIAS[tipo]
    faltando: list[str] = []

    for arq in exig["obrigatorios"]:
        if not (caminho / arq).is_file():
            faltando.append(arq)

    if exig["pesos"]:
        tem_peso = any((caminho / p).is_file() for p in PESOS)
        # safetensors pode estar fragmentado
        if not tem_peso:
            tem_peso = any(caminho.glob("*.safetensors")) or any(caminho.glob("*.bin"))
        if not tem_peso:
            faltando.append(f"pesos ({' ou '.join(PESOS[:2])})")

    for arq in exig["processador"] + exig["tokenizador"]:
        if not (caminho / arq).is_file():
            faltando.append(arq)

    for d in exig.get("extra_dirs", []):
        if not (caminho / d).is_dir():
            faltando.append(f"{d}/ (diretório)")

    if faltando:
        print(f"     ✗ FALTAM: {', '.join(faltando)}")
        print(f"        esperado para: {exig['descricao']}")
        return False

    tamanho = sum(f.stat().st_size for f in caminho.rglob("*") if f.is_file())
    print(f"     ✓ completo — {tamanho / 1024**3:.2f} GB")
    print(f"     ✓ use exatamente: {caminho}")
    return True


def bloco_offline() -> None:
    titulo("MODO OFFLINE — recomendado quando os modelos são locais")
    hho = os.environ.get("HF_HUB_OFFLINE")
    tro = os.environ.get("TRANSFORMERS_OFFLINE")
    hf_home = os.environ.get("HF_HOME")
    print(f"  HF_HUB_OFFLINE       = {hho or '(não definida)'}")
    print(f"  TRANSFORMERS_OFFLINE = {tro or '(não definida)'}")
    print(f"  HF_HOME              = {hf_home or '(não definida)'}")
    if hho != "1":
        print("""
  ⚠️ Sem HF_HUB_OFFLINE=1, um caminho errado faz o from_pretrained() tentar
     a REDE. Num servidor sem saída, isso vira espera + erro obscuro — e no
     supervisord, um loop de reinício difícil de diagnosticar.

     Defina no supervisord.conf:
         HF_HUB_OFFLINE="1",
         TRANSFORMERS_OFFLINE="1"

     Com elas, caminho errado = erro IMEDIATO e explícito.
""")
    else:
        print("  ✓ modo offline ativo — falhas de caminho serão imediatas e claras")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base", nargs="?", help="diretório que contém os 3 modelos")
    ap.add_argument("--caption", help="caminho do BLIP de captioning")
    ap.add_argument("--itm", help="caminho do BLIP-ITM")
    ap.add_argument("--st", help="caminho do sentence-transformer")
    args = ap.parse_args()

    print("=" * LARG)
    print(" VALIDAÇÃO DOS MODELOS LOCAIS")
    print("=" * LARG)

    alvos: list[tuple[str, str, str]] = []

    if args.caption or args.itm or args.st:
        if args.caption:
            alvos.append(("caption_model (BLIP captioning)", args.caption, "blip"))
        if args.itm:
            alvos.append(("blip_itm_model (BLIP-ITM)", args.itm, "blip"))
        if args.st:
            alvos.append(("sentence_transformer", args.st, "sentence_transformer"))
    elif args.base:
        base = pathlib.Path(args.base).expanduser()
        titulo(f"Explorando {base}")
        if not base.is_dir():
            print(f"  ✗ não é um diretório")
            return 1
        subdirs = sorted(d for d in base.iterdir() if d.is_dir())
        print(f"  {len(subdirs)} subdiretório(s):")
        for d in subdirs:
            layout, _ = detectar_layout(d)
            print(f"    {d.name:<50} [{layout}]")
        print("""
  Rode de novo apontando cada modelo explicitamente:
      python validar_modelos_locais.py --caption <dir> --itm <dir> --st <dir>
""")
        bloco_offline()
        return 0
    else:
        # tenta pelas variáveis de ambiente do serviço
        mapa = [
            ("caption_model (BLIP captioning)", "REFCAP_CAPTION_MODEL", "blip"),
            ("blip_itm_model (BLIP-ITM)", "REFCAP_BLIP_ITM_MODEL", "blip"),
            ("sentence_transformer", "REFCAP_SENTENCE_TRANSFORMER", "sentence_transformer"),
        ]
        for nome, var, tipo in mapa:
            valor = os.environ.get(var)
            if valor:
                alvos.append((f"{nome}  [{var}]", valor, tipo))
        if not alvos:
            print("\n  Nenhum caminho informado e nenhuma REFCAP_*_MODEL definida.")
            print("  Use:  python validar_modelos_locais.py /caminho/dos/modelos")
            return 1

    titulo("Validando cada modelo")
    resultados = [validar(n, c, t) for n, c, t in alvos]

    bloco_offline()

    titulo("RESULTADO")
    ok = sum(resultados)
    print(f"  {ok} de {len(resultados)} modelo(s) prontos para uso local")
    if ok < len(resultados):
        print("""
  Enquanto algum estiver incorreto, o serviço vai falhar no startup — e o
  supervisord vai reiniciá-lo em loop. Corrija os caminhos no
  supervisord.conf (bloco environment=) antes de subir.
""")
        return 1
    print("\n  ✓ Aponte estes caminhos nas variáveis REFCAP_*_MODEL do supervisord.conf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
