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


def caminho_summary(res_dir: str, program_id: str) -> pathlib.Path:
    """O arquivo ATIVO de summaries. Os rotacionados ficam ao lado."""
    return dir_response(res_dir, program_id) / "summary" / "summaries.json"


def caminho_history(res_dir: str, program_id: str) -> pathlib.Path:
    return dir_response(res_dir, program_id) / "history" / "history.jsonl"


#: Acima deste tamanho, o summaries.json é rotacionado: renomeado com a data
#: e hora, e um novo é começado. A hora entra no nome porque um programa
#: ativo pode passar do limite mais de uma vez no mesmo dia.
LIMITE_SUMMARY_BYTES = int(os.environ.get("REFCAP_SUMMARY_MAX_BYTES", 5 * 1024 * 1024))


def _data_legivel(dt: datetime) -> str:
    """DD-MM-YYYY HH:MM:SS — para leitura humana.

    Guardamos TAMBÉM o ISO em `timestamp`: este formato não ordena
    lexicograficamente ('01-12-2026' viria antes de '08-09-2026'), então o
    ISO é o campo que se usa para ordenar e filtrar por código.
    """
    return dt.strftime("%d-%m-%Y %H:%M:%S")


# --------------------------------------------------------------------------- #
# Gravar
# --------------------------------------------------------------------------- #
def gravar_respostas(
    res_dir: str,
    program_id: str,
    respostas: list[dict],
    extras_por_cena: dict | None = None,
) -> dict:
    """Grava o ESTADO ATUAL do programa, em três lugares.

    ★ COMO O responses.jsonl FUNCIONA
        Uma linha só, com o envelope do programa inteiro:

            {"program_id": ..., "items": [ ...todas as cenas... ],
             "updated_at": ...}

        A cada requisição o arquivo é lido, as cenas novas são MESCLADAS por
        `scene_id` (a nova vence), e o conjunto é reescrito. Cenas ausentes
        da requisição permanecem.

    ★ O QUE É SUBSTITUÍDO VAI PARA O history
        Quando o merge sobrescreve uma cena, a versão antiga é registrada em
        `history/history.jsonl` — senão ela se perderia, já que o
        `scenes/{id}.json` também sobrescreve.

    ⚠️ CONCORRÊNCIA: quem garante que só um job escreve por vez é a fila
    serializada do `jobs.py`. Este módulo NÃO tem trava própria.
    """
    if not respostas:
        return {"written": 0, "jsonl": None, "scenes_dir": None}

    base = dir_response(res_dir, program_id)
    dir_scenes = base / "scenes"
    dir_scenes.mkdir(parents=True, exist_ok=True)

    extras = extras_por_cena or {}
    agora = datetime.now(timezone.utc)
    momento = agora.isoformat()
    jsonl = caminho_jsonl(res_dir, program_id)

    # --- 1. carrega o envelope anterior --------------------------------- #
    anteriores: dict[str, dict] = {}
    if jsonl.is_file():
        try:
            with open(jsonl, encoding="utf-8") as f:
                linha = f.readline().strip()
            if linha:
                envelope = json.loads(linha)
                for it in envelope.get("items", []):
                    if it.get("scene_id"):
                        anteriores[it["scene_id"]] = it
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("envelope ilegível em %s (%s) — recomeçando", jsonl, exc)

    # --- 2. mescla, guardando o que for substituído --------------------- #
    substituidas = []
    for r in respostas:
        scene_id = r.get("scene_id")
        if not scene_id:
            continue

        registro = {**r, "timestamp": momento}
        extra = extras.get(scene_id)
        if extra:
            registro["diagnostics"] = extra

        if scene_id in anteriores:
            substituidas.append(anteriores[scene_id])

        anteriores[scene_id] = registro

        # o arquivo por cena — acesso direto, sem varrer o envelope
        with open(caminho_cena(res_dir, program_id, scene_id), "w",
                  encoding="utf-8") as fc:
            json.dump({**registro, "program_id": program_id}, fc,
                      ensure_ascii=False, indent=2)

    # --- 3. reescreve o envelope ---------------------------------------- #
    envelope = {
        "program_id": program_id,
        "items": [anteriores[k] for k in sorted(anteriores)],
        "updated_at": momento,
    }
    with open(jsonl, "w", encoding="utf-8") as f:
        f.write(json.dumps(envelope, ensure_ascii=False) + "\n")

    # --- 4. o que foi substituído vai para o history --------------------- #
    if substituidas:
        gravar_history(res_dir, program_id, substituidas, agora,
                       {"written": len(respostas), "jsonl": str(jsonl),
                        "scenes_dir": str(dir_scenes)})

    log.info("[%s] %d cena(s) gravada(s); %d substituída(s); %d no total",
             program_id, len(respostas), len(substituidas), len(anteriores))
    return {
        "written": len(respostas),
        "replaced": len(substituidas),
        "total_in_program": len(anteriores),
        "jsonl": str(jsonl),
        "scenes_dir": str(dir_scenes),
    }


def gravar_history(res_dir: str, program_id: str, substituidas: list[dict],
                   quando: datetime, persisted: dict) -> None:
    """Registra as versões SUBSTITUÍDAS — só elas.

    ★ Guardar toda versão de toda cena faria deste arquivo uma cópia do
    responses.jsonl. Aqui fica apenas o que SERIA PERDIDO pelo merge, que é
    o problema que um histórico resolve.
    """
    caminho = caminho_history(res_dir, program_id)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "a", encoding="utf-8") as f:
        for antiga in substituidas:
            f.write(json.dumps({
                "replaced_at": quando.isoformat(),
                "data": _data_legivel(quando),
                "reason": "overwritten",
                "program_id": program_id,
                "scene": antiga,
                "persisted": persisted,
            }, ensure_ascii=False) + "\n")


def gravar_summary(res_dir: str, program_id: str, entrada: dict) -> dict:
    """Acrescenta uma entrada ao summaries.json, rotacionando se preciso.

    ★ ROTAÇÃO POR TAMANHO
        Acima de LIMITE_SUMMARY_BYTES, o arquivo ativo é renomeado para
        `summaries-DD-MM-YYYY_HHMMSS.json` e um novo é começado. A HORA entra
        no nome porque um programa ativo pode passar do limite mais de uma
        vez no mesmo dia — só a data colidiria.

        A checagem é feita ANTES de acrescentar, então o arquivo pode passar
        do limite por uma entrada. É o comportamento padrão de rotação, e
        evita ter de serializar duas vezes para medir.
    """
    caminho = caminho_summary(res_dir, program_id)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    rotacionado = None
    if caminho.is_file() and caminho.stat().st_size >= LIMITE_SUMMARY_BYTES:
        agora = datetime.now(timezone.utc)
        destino = caminho.parent / f"summaries-{agora.strftime('%d-%m-%Y_%H%M%S')}.json"
        caminho.rename(destino)
        rotacionado = str(destino)
        log.info("[%s] summaries rotacionado para %s", program_id, destino.name)

    dados = {"data_summary": []}
    if caminho.is_file():
        try:
            with open(caminho, encoding="utf-8") as f:
                dados = json.load(f)
            dados.setdefault("data_summary", [])
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("summaries ilegível (%s) — recomeçando", exc)
            dados = {"data_summary": []}

    dados["data_summary"].append(entrada)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    return {"file": str(caminho), "entries": len(dados["data_summary"]),
            "rotated": rotacionado}


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
    """As versões SUBSTITUÍDAS de uma cena, em ordem cronológica.

    ★ Lê o `history/history.jsonl`, não o `responses.jsonl`. Este passou a
    guardar só o estado ATUAL; as versões antigas vão para o history quando
    o merge as substitui.

    A versão vigente NÃO está aqui — ela está em `scenes/{scene_id}.json`.
    """
    caminho = caminho_history(res_dir, program_id)
    if not caminho.is_file():
        return []
    versoes = []
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                r = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if r.get("scene", {}).get("scene_id") == scene_id:
                versoes.append(r)
    return versoes


def ler_summaries(res_dir: str, program_id: str, limite: int = 0) -> list[dict]:
    """As entradas do summaries.json ATIVO, da mais recente para a mais antiga.

    Não lê os arquivos rotacionados — eles ficam ao lado, para consulta manual.
    """
    caminho = caminho_summary(res_dir, program_id)
    if not caminho.is_file():
        return []
    try:
        with open(caminho, encoding="utf-8") as f:
            entradas = json.load(f).get("data_summary", [])
    except (json.JSONDecodeError, OSError):
        return []
    entradas = list(reversed(entradas))
    return entradas[:limite] if limite > 0 else entradas


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
        return {"merged": 0, "total": 0}

    atual = pathlib.Path(exp_dir) / proposals_file
    acumulado = pathlib.Path(exp_dir) / "proposals_acumulado.json"

    if not atual.is_file():
        return {"merged": 0, "total": 0}

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
    return {"merged": len(novas), "total": len(fundido)}


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
