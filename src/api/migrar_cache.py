#!/usr/bin/env python3
"""
migrar_cache.py — move os artefatos de um `collection` antigo para o novo.

POR QUE ESTE SCRIPT EXISTE
--------------------------
A Etapa 2 mudou o `collection` do RefCap para o `program_id`. Os artefatos
gravados antes estão sob o nome antigo (o que os testes usaram), e o serviço
passará a procurar sob o `program_id` — sem achar nada.

Sem migrar, o primeiro processamento de cada programa roda o BLIP do zero,
descartando trabalho já feito.

OS QUATRO ARTEFATOS
    annos/{de}/                     →  annos/{para}/
    meta/captions/{de}_blip.jsonl   →  meta/captions/{para}_blip.jsonl
    meta/framefeatures/{de}.pt      →  meta/framefeatures/{para}.pt
    meta/scores/{de}_blip.pt        →  meta/scores/{para}_blip.pt

⚠️ O `results/construct/{de}/` NÃO é migrado de propósito: ele é área de
   trabalho da última execução, e o `construct_name` mudou de formato. O que
   importa preservar é o CACHE — que é o que evita rodar o BLIP de novo.

USO
    # 1. SEMPRE simule primeiro
    python migrar_cache.py --de teste_api --para meu_programa --simular

    # 2. só então migre
    python migrar_cache.py --de teste_api --para meu_programa

    # descobrir o que existe hoje
    python migrar_cache.py --listar
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys

LARG = 76


def titulo(t: str) -> None:
    print("\n" + "=" * LARG)
    print(f" {t}")
    print("=" * LARG)


# --------------------------------------------------------------------------- #
def raiz_refcap() -> pathlib.Path:
    """Localiza a raiz do RefCap pela mesma regra que o serviço usa."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from ponte_refcap import RAIZ_REFCAP  # noqa: PLC0415

    return RAIZ_REFCAP


def caminhos_do(raiz: pathlib.Path, cfg, colecao: str) -> list[dict]:
    """Os quatro artefatos de um `collection`, com o status de cada."""
    itens = [
        {
            "nome": "annos",
            "caminho": raiz / cfg.anno_dir / colecao,
            "tipo": "dir",
        },
        {
            "nome": "cache de legendas",
            "caminho": raiz / cfg.meta_dir / cfg.captions_dir
            / f"{colecao}_{cfg.caption_generator}.jsonl",
            "tipo": "jsonl",
        },
        {
            "nome": "features de frame",
            "caminho": raiz / cfg.meta_dir / cfg.framefeatures_dir / f"{colecao}.pt",
            "tipo": "pt",
        },
        {
            "nome": "scores",
            "caminho": raiz / cfg.meta_dir / cfg.raw_capframe_scores_dir
            / f"{colecao}_{cfg.caption_generator}.pt",
            "tipo": "pt",
        },
    ]
    for i in itens:
        c = i["caminho"]
        i["existe"] = c.exists()
        i["cenas"] = _contar_cenas(c, i["tipo"]) if i["existe"] else None
    return itens


def _contar_cenas(caminho: pathlib.Path, tipo: str) -> int | str:
    """Quantas cenas há no artefato — para o --simular mostrar o que se ganha."""
    try:
        if tipo == "jsonl":
            with open(caminho, encoding="utf-8") as f:
                return sum(1 for linha in f if linha.strip())
        if tipo == "dir":
            # o annos guarda uma linha por vídeo no arquivo de anotações
            arquivos = list(caminho.glob("*.jsonl"))
            if not arquivos:
                return 0
            with open(arquivos[0], encoding="utf-8") as f:
                return sum(1 for linha in f if linha.strip())
        if tipo == "pt":
            # ler o .pt exige torch; evitamos a dependência aqui
            return "?"
    except Exception:  # noqa: BLE001 — contar é diagnóstico, não pode falhar
        return "?"
    return "?"


# ⚠️ O default de `caption_generator` no cfg.py do RefCap é "minigpt", mas a
# API SEMPRE usa "blip" — é ele que nomeia os arquivos de cache. Usar o default
# faria o script procurar `{collection}_minigpt.jsonl` e não achar nada.
CAPTION_GENERATOR = os.environ.get("REFCAP_CAPTION_GENERATOR", "blip")


def _carregar_cfg(raiz: pathlib.Path):
    sys.path.insert(0, str(raiz))
    from config import BuildArguments  # noqa: PLC0415

    cfg = BuildArguments()
    cfg.caption_generator = CAPTION_GENERATOR
    return cfg


# --------------------------------------------------------------------------- #
def listar(raiz: pathlib.Path, cfg) -> int:
    """Mostra quais `collection` existem hoje — para você escolher os pares."""
    titulo("COLLECTIONS ENCONTRADOS")

    encontrados: dict[str, list[str]] = {}

    dir_annos = raiz / cfg.anno_dir
    if dir_annos.is_dir():
        for d in sorted(p for p in dir_annos.iterdir() if p.is_dir()):
            encontrados.setdefault(d.name, []).append("annos")

    dir_caps = raiz / cfg.meta_dir / cfg.captions_dir
    if dir_caps.is_dir():
        sufixo = f"_{cfg.caption_generator}.jsonl"
        for f in sorted(dir_caps.glob(f"*{sufixo}")):
            encontrados.setdefault(f.name[: -len(sufixo)], []).append("legendas")

    dir_feat = raiz / cfg.meta_dir / cfg.framefeatures_dir
    if dir_feat.is_dir():
        for f in sorted(dir_feat.glob("*.pt")):
            encontrados.setdefault(f.stem, []).append("features")

    if not encontrados:
        print(f"  nenhum artefato encontrado sob {raiz}")
        return 1

    print(f"  {'collection':<34} artefatos presentes")
    print("  " + "-" * (LARG - 4))
    for nome, arts in sorted(encontrados.items()):
        print(f"  {nome:<34} {', '.join(arts)}")

    print(f"""
  Para migrar um deles:
      python migrar_cache.py --de <collection> --para <program_id> --simular
""")
    return 0


# --------------------------------------------------------------------------- #
def migrar(raiz: pathlib.Path, cfg, de: str, para: str, simular: bool) -> int:
    titulo(f"{'SIMULAÇÃO' if simular else 'MIGRAÇÃO'}:  {de}  →  {para}")

    if de == para:
        print("  ✗ origem e destino são iguais — nada a fazer")
        return 1

    origem = caminhos_do(raiz, cfg, de)
    destino = caminhos_do(raiz, cfg, para)

    # --- 1. a origem tem algo? --------------------------------------- #
    presentes = [i for i in origem if i["existe"]]
    if not presentes:
        print(f"  ✗ nenhum artefato encontrado para o collection '{de}'")
        print(f"\n  Use --listar para ver o que existe.")
        return 1

    # --- 2. o destino está livre? ------------------------------------ #
    # ⚠️ Recusamos destino ocupado em vez de sobrescrever: fundir dois caches
    # é decisão do operador, não do script. Uma fusão errada mistura cenas de
    # programas diferentes — exatamente o erro silencioso que a Etapa 2 evita.
    ocupados = [i for i in destino if i["existe"]]
    if ocupados and not simular:
        print(f"  ✗ o destino '{para}' JÁ TEM artefatos:")
        for i in ocupados:
            print(f"      {i['nome']:<20} {i['caminho']}")
        print(f"""
  RECUSANDO a migração para não misturar dois conjuntos.

  Se você quer mesmo unir os dois, faça manualmente e com cuidado — ou
  escolha um `program_id` de destino ainda não usado.
""")
        return 1

    # --- 3. o plano --------------------------------------------------- #
    print(f"\n  {'artefato':<20} {'origem':<10} {'cenas':<7} destino")
    print("  " + "-" * (LARG - 4))
    for o, d in zip(origem, destino):
        status = "existe" if o["existe"] else "ausente"
        cenas = str(o["cenas"]) if o["cenas"] is not None else "-"
        marca = "⚠️ OCUPADO" if d["existe"] else "livre"
        print(f"  {o['nome']:<20} {status:<10} {cenas:<7} {marca}")

    print(f"\n  origem  : {raiz}")
    for o in presentes:
        print(f"      {o['caminho'].relative_to(raiz)}")

    if simular:
        print(f"""
  ── SIMULAÇÃO — nada foi alterado ──

  {len(presentes)} de 4 artefato(s) seriam movidos.
  {'⚠️ O destino tem artefatos: a migração real seria RECUSADA.' if ocupados else '✓ Destino livre.'}

  Para executar de verdade:
      python migrar_cache.py --de {de} --para {para}
""")
        return 0

    # --- 4. mover ----------------------------------------------------- #
    print()
    movidos = 0
    for o, d in zip(origem, destino):
        if not o["existe"]:
            print(f"  · {o['nome']:<20} ausente na origem — pulado")
            continue
        d["caminho"].parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(o["caminho"]), str(d["caminho"]))
        print(f"  ✓ {o['nome']:<20} → {d['caminho'].relative_to(raiz)}")
        movidos += 1

    print(f"""
  {movidos} artefato(s) movido(s).

  ★ CONFIRME A MIGRAÇÃO processando uma cena JÁ CONHECIDA:
    ela deve ser PULADA pelo cache, não reprocessada. Se o BLIP rodar de
    novo, o cache não foi encontrado no caminho novo.
""")
    return 0


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--de", help="o collection atual (ex.: teste_api)")
    ap.add_argument("--para", help="o program_id de destino")
    ap.add_argument("--simular", action="store_true",
                    help="mostra o que faria, sem tocar em nada")
    ap.add_argument("--listar", action="store_true",
                    help="lista os collections existentes")
    args = ap.parse_args()

    raiz = raiz_refcap()
    cfg = _carregar_cfg(raiz)

    print("=" * LARG)
    print(" MIGRAÇÃO DE CACHE — collection antigo → program_id")
    print("=" * LARG)
    print(f"  RefCap em: {raiz}")

    if args.listar:
        return listar(raiz, cfg)

    if not args.de or not args.para:
        print("\n  Informe --de e --para, ou use --listar.")
        ap.print_help()
        return 1

    return migrar(raiz, cfg, args.de, args.para, args.simular)


if __name__ == "__main__":
    sys.exit(main())
