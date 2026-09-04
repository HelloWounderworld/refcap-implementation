"""Persistência: o histórico durável das respostas, e a fusão do proposals.

O QUE ESTE MÓDULO RESOLVE
-------------------------
1. GRAVAR o resultado de cada cena em disco, para que ele sobreviva ao
   processo e possa ser consultado depois — sem reprocessar.

2. FUNDIR o `proposals.json`, que o RefCap SOBRESCREVE a cada `build()`.

3. LIMPAR o cache de cenas específicas (o `force`), sem afetar as demais.

★ POR QUE A FUSÃO É NECESSÁRIA
    Verificado no RefCap:
        meta/captions/*.jsonl      append          → cumulativo ✓
        meta/framefeatures/*.pt    lê, soma, grava → cumulativo ✓
        meta/scores/*.pt           idem            → cumulativo ✓
        results/.../proposals.json save_json direto → SOBRESCREVE ✗
        results/.../tree.json      idem             → SOBRESCREVE ✗

    Com `construct_name=""`, todos os grupos de uma requisição escrevem no
    MESMO `exp_dir`. Sem fusão, o grupo 2 apagaria o proposals do grupo 1
    dentro da própria requisição — e a requisição seguinte apagaria tudo.

★ POR QUE DOIS FORMATOS DE RESPONSE
    responses.jsonl   append, cumulativo. Barato de escrever e resistente:
                      uma linha corrompida não invalida as outras.
    scenes/{id}.json  um arquivo por cena. Leitura direta sem varrer o
                      jsonl, e atualização de uma cena é só sobrescrever.

    O jsonl é o histórico (guarda todas as versões, com timestamp); o
    arquivo por cena é o estado atual.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
from datetime import datetime, timezone

log = logging.getLogger(__name__)

#: subdiretório de response, dentro de `res_dir`
DIR_RESPONSE = "response"


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Caminhos
# --------------------------------------------------------------------------- #
def dir_response(res_dir: str, program_id: str) -> pathlib.Path:
    """`{res_dir}/response/{program_id}/`"""
    return pathlib.Path(res_dir) / DIR_RESPONSE / program_id


def caminho_jsonl(res_dir: str, program_id: str) -> pathlib.Path:
    return dir_response(res_dir, program_id) / "responses.jsonl"


def caminho_cena(res_dir: str, program_id: str, scene_id: str) -> pathlib.Path:
    return dir_response(res_dir, program_id) / "scenes" / f"{scene_id}.json"


# --------------------------------------------------------------------------- #
# Gravar
# --------------------------------------------------------------------------- #
def gravar_respostas(
    res_dir: str,
    program_id: str,
    respostas: list[dict],
    extras_por_cena: dict | None = None,
) -> dict:
    """Grava nos DOIS formatos e devolve um resumo do que foi escrito.

    `respostas` são os dicts do contrato (scene_id, scene_caption_en, ...).
    `extras_por_cena` mapeia scene_id → diagnóstico adicional (ranking
    completo, n_raw, n_distinct, warnings) — guardamos tudo, como acordado.

    ⚠️ CONCORRÊNCIA: quem garante que só um job escreve por vez é a fila
    serializada do `jobs.py`. Este módulo NÃO tem trava própria.
    """
    if not respostas:
        return {"gravadas": 0, "jsonl": None, "scenes": None}

    base = dir_response(res_dir, program_id)
    dir_scenes = base / "scenes"
    dir_scenes.mkdir(parents=True, exist_ok=True)

    jsonl = caminho_jsonl(res_dir, program_id)
    extras = extras_por_cena or {}
    momento = _agora()

    with open(jsonl, "a", encoding="utf-8") as f:
        for r in respostas:
            scene_id = r.get("scene_id")
            if not scene_id:
                continue

            registro = {
                **r,
                "program_id": program_id,
                "timestamp": momento,
            }
            extra = extras.get(scene_id)
            if extra:
                registro["diagnostics"] = extra

            # 1) append no histórico — todas as versões ficam
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")

            # 2) arquivo por cena — sobrescreve, é o estado atual
            with open(caminho_cena(res_dir, program_id, scene_id), "w",
                      encoding="utf-8") as fc:
                json.dump(registro, fc, ensure_ascii=False, indent=2)

    log.info("[%s] %d resposta(s) persistida(s) em %s",
             program_id, len(respostas), base)
    return {
        "gravadas": len(respostas),
        "jsonl": str(jsonl),
        "scenes": str(dir_scenes),
    }


# --------------------------------------------------------------------------- #
# Ler
# --------------------------------------------------------------------------- #
def ler_respostas(
    res_dir: str,
    program_id: str,
    scene_ids: list[str] | None = None,
) -> list[dict]:
    """Lê o estado ATUAL de cada cena (os arquivos por cena, não o histórico).

    Sem `scene_ids`, devolve todas. Cenas pedidas que não existem são
    simplesmente omitidas — quem chama decide se isso é erro.
    """
    dir_scenes = dir_response(res_dir, program_id) / "scenes"
    if not dir_scenes.is_dir():
        return []

    if scene_ids:
        arquivos = [dir_scenes / f"{s}.json" for s in scene_ids]
        arquivos = [a for a in arquivos if a.is_file()]
    else:
        arquivos = sorted(dir_scenes.glob("*.json"))

    saida = []
    for a in arquivos:
        try:
            with open(a, encoding="utf-8") as f:
                saida.append(json.load(f))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("resposta ilegível em %s: %s", a, exc)
    return saida


def historico_da_cena(res_dir: str, program_id: str, scene_id: str) -> list[dict]:
    """Todas as versões de uma cena, do jsonl — em ordem cronológica."""
    jsonl = caminho_jsonl(res_dir, program_id)
    if not jsonl.is_file():
        return []
    versoes = []
    with open(jsonl, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                r = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if r.get("scene_id") == scene_id:
                versoes.append(r)
    return versoes


# --------------------------------------------------------------------------- #
# Fundir o proposals.json
# --------------------------------------------------------------------------- #
def fundir_proposals(exp_dir: str, proposals_file: str) -> dict:
    """Funde o `proposals.json` recém-escrito com o acumulado do programa.

    ★ CHAMAR LOGO APÓS CADA `build()`, dentro do laço de grupos.

    O RefCap grava ali apenas as cenas do grupo atual. Mantemos um acumulado
    ao lado (`proposals_acumulado.json`), fundimos os dois por `vid_name`, e
    regravamos AMBOS — assim o `proposals.json` que o resto do sistema lê
    passa a conter o programa inteiro.

    Cenas reprocessadas SOBRESCREVEM as versões antigas (o novo vence).
    """
    if not exp_dir:
        return {"fundidas": 0, "total": 0}

    atual = pathlib.Path(exp_dir) / proposals_file
    acumulado = pathlib.Path(exp_dir) / "proposals_acumulado.json"

    if not atual.is_file():
        return {"fundidas": 0, "total": 0}

    with open(atual, encoding="utf-8") as f:
        novas = json.load(f)

    anteriores = {}
    if acumulado.is_file():
        try:
            with open(acumulado, encoding="utf-8") as f:
                anteriores = json.load(f)
        except json.JSONDecodeError:
            log.warning("acumulado ilegível em %s — recomeçando dele", acumulado)

    # o novo vence: dict-unpacking com `novas` por último
    fundido = {**anteriores, **novas}

    for destino in (acumulado, atual):
        with open(destino, "w", encoding="utf-8") as f:
            json.dump(fundido, f, ensure_ascii=False, indent=2)

    log.info("proposals fundido: %d nova(s), %d no total",
             len(novas), len(fundido))
    return {"fundidas": len(novas), "total": len(fundido)}


# --------------------------------------------------------------------------- #
# Limpeza cirúrgica de cache (o `force`)
# --------------------------------------------------------------------------- #
def limpar_cache_das_cenas(cfg, collection: str, nomes_base: list[str]) -> dict:
    """Remove APENAS as cenas indicadas dos três caches.

    ⚠️ CUSTO: os dois `.pt` são carregados INTEIROS na memória para que uma
    chave seja removida. Num programa com centenas de cenas isso pesa — é o
    preço do escopo cirúrgico. Como o `force` é manual, o custo só aparece
    quando explicitamente pedido.

    Devolve quantas entradas foram removidas de cada artefato.
    """
    if not nomes_base:
        return {}

    alvo = set(nomes_base)
    resultado: dict[str, int] = {}

    # --- 1. legendas: reescreve o jsonl sem as linhas daquelas cenas --- #
    caminho = os.path.join(
        cfg.meta_dir, cfg.captions_dir,
        f"{collection}_{cfg.caption_generator}.jsonl")
    if os.path.isfile(caminho):
        mantidas, removidas = [], 0
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                linha_limpa = linha.strip()
                if not linha_limpa:
                    continue
                try:
                    if json.loads(linha_limpa).get("vid_name") in alvo:
                        removidas += 1
                        continue
                except json.JSONDecodeError:
                    pass          # linha ilegível: preserva, não é nosso papel
                mantidas.append(linha_limpa)
        if removidas:
            with open(caminho, "w", encoding="utf-8") as f:
                for linha in mantidas:
                    f.write(linha + "\n")
        resultado["captions"] = removidas

    # --- 2 e 3. os dois .pt: carrega, remove as chaves, regrava -------- #
    #
    # O import é tardio E tolerante: a limpeza do cache de LEGENDAS (acima)
    # não depende do torch, e é ela que decide se o BLIP roda de novo. Se o
    # torch faltar, avisamos e seguimos com a limpeza parcial em vez de
    # derrubar a requisição inteira.
    try:
        import torch  # noqa: PLC0415
    except ImportError:
        log.warning(
            "torch indisponível: o force limpou as legendas, mas não os "
            "caches .pt de features/scores. Eles serão recalculados apenas "
            "se o vídeo mudar de tamanho."
        )
        resultado["framefeatures"] = "torch ausente"
        resultado["scores"] = "torch ausente"
        return resultado

    for rotulo, caminho_pt in (
        ("framefeatures",
         os.path.join(cfg.meta_dir, cfg.framefeatures_dir, f"{collection}.pt")),
        ("scores",
         os.path.join(cfg.meta_dir, cfg.raw_capframe_scores_dir,
                      f"{collection}_{cfg.caption_generator}.pt")),
    ):
        if not os.path.isfile(caminho_pt):
            continue
        try:
            dados = torch.load(caminho_pt)
        except Exception as exc:  # noqa: BLE001 — cache ilegível não derruba
            log.warning("cache %s ilegível (%s) — pulando", caminho_pt, exc)
            continue
        if not isinstance(dados, dict):
            log.warning("cache %s não é dict — pulando", caminho_pt)
            continue
        removidas = 0
        for nb in list(dados.keys()):
            if nb in alvo:
                del dados[nb]
                removidas += 1
        if removidas:
            torch.save(dados, caminho_pt)
        resultado[rotulo] = removidas

    log.info("[%s] force: removidas %s", collection, resultado)
    return resultado
