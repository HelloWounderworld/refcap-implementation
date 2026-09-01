"""Processamento de jobs: dos contratos da requisição até a resposta.

O QUE ESTE MÓDULO RESOLVE
-------------------------
As rotas `/teste/construct` e `/teste/construct-lote` provaram que o
reaproveitamento dos modelos funciona. O que faltava ao `POST /jobs` eram os
cinco passos do pipeline ANTES do captioning:

    1. escrever o annos com os vídeos pedidos
    2. aceitar um diretório
    3. ler/limpar cache com controle
    4. isolar por collection
    5. usar o video_root do pedido

Este módulo faz os cinco, e mais a transformação da saída do RefCap para o
formato de resposta acordado.

★ A RESTRIÇÃO QUE MOLDA O DESENHO
    `constructpipe/base.py:43` faz `os.listdir(cfg.video_root)` — UM diretório
    por execução. Como as cenas ficam em

        /caminho/{program_id}/{video_id}/{scene_id}

    um lote com `video_id` diferentes está espalhado por VÁRIOS diretórios e
    NÃO cabe numa única chamada de `build()`.

    A solução: AGRUPAR os itens por diretório e chamar `build()` uma vez por
    grupo. Cenas do mesmo vídeo são processadas juntas (eficiente), e cenas de
    vídeos diferentes viram execuções separadas.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import re
import time
from collections import defaultdict

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# Extensões aceitas ao resolver o caminho de uma cena.
EXTENSOES_VIDEO = (".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v")

MODEL_NAME_PADRAO = os.environ.get("REFCAP_MODEL_NAME", "refcap")
MODEL_VERSION_PADRAO = os.environ.get("REFCAP_MODEL_VERSION", "v1")


# --------------------------------------------------------------------------- #
# Contratos
# --------------------------------------------------------------------------- #
class ItemDeCena(BaseModel):
    """Uma cena a legendar."""
    scene_id: str
    video_id: str | None = None
    program_id: str | None = None
    scene_video_path: str = Field(
        ...,
        description="Caminho da cena. Aceita o arquivo de vídeo OU o diretório "
                    "que o contém (nesse caso o arquivo é procurado lá dentro).",
    )


class PedidoDeJob(BaseModel):
    """Aceita as DUAS formas acordadas, sem endpoint separado.

    Cena única:
        {"scene_id": "...", "video_id": "...", "program_id": "...",
         "scene_video_path": "/caminho/..."}

    Lote:
        {"items": [ {...}, {...} ]}
    """
    # --- forma "cena única" (campos no nível de cima) ---
    scene_id: str | None = None
    video_id: str | None = None
    program_id: str | None = None
    scene_video_path: str | None = None

    # --- forma "lote" ---
    items: list[ItemDeCena] | None = None

    # --- controles opcionais ---
    callback_url: str | None = None
    assincrono: bool = Field(
        default=False,
        description="Se True, devolve 202 + job_id na hora e processa em segundo "
                    "plano (consulte por GET /jobs/{id}). O default False AGUARDA "
                    "o processamento e devolve o resultado completo.",
    )
    proposal_generator: str = "whole"
    limpar_cache: bool = False
    collection: str | None = Field(
        default=None,
        description="Isola artefatos e cache. Quando omitido, usa o program_id "
                    "— cenas do mesmo programa compartilham cache.",
    )

    def como_itens(self) -> list[ItemDeCena]:
        """Normaliza as duas formas numa lista única.

        Cena única vira um lote de um. Todo o resto do código trata só listas —
        não há dois caminhos de execução para manter.
        """
        if self.items:
            return list(self.items)
        if self.scene_id and self.scene_video_path:
            return [ItemDeCena(
                scene_id=self.scene_id,
                video_id=self.video_id,
                program_id=self.program_id,
                scene_video_path=self.scene_video_path,
            )]
        return []


class PalavraChave(BaseModel):
    token: str
    weight: float


class RespostaDeCena(BaseModel):
    scene_id: str
    scene_caption_en: str | None = None
    keywords_en: list[PalavraChave] = Field(default_factory=list)
    model_name: str = MODEL_NAME_PADRAO
    model_version: str = MODEL_VERSION_PADRAO
    status: str = "success"
    erro: str | None = None


# --------------------------------------------------------------------------- #
# Resolução de caminho
# --------------------------------------------------------------------------- #
def resolver_cena(item: ItemDeCena) -> tuple[str, str, str]:
    """Descobre o diretório e o arquivo da cena.

    O `scene_video_path` acordado é `/caminho/{program_id}/{video_id}/{scene_id}`
    — sem extensão explícita. Isso é ambíguo, então tratamos os três casos:

        1. é um ARQUIVO existente        -> usa direto
        2. é um arquivo SEM extensão     -> tenta cada extensão conhecida
        3. é um DIRETÓRIO                -> procura lá dentro um vídeo cujo
                                            nome-base seja o scene_id

    Devolve (diretorio, nome_do_arquivo, nome_base).
    Levanta FileNotFoundError com mensagem diagnóstica se não achar.
    """
    caminho = pathlib.Path(item.scene_video_path)

    # caso 1: arquivo existente
    if caminho.is_file():
        return str(caminho.parent), caminho.name, caminho.stem

    # caso 2: falta a extensão
    for ext in EXTENSOES_VIDEO:
        candidato = caminho.with_suffix(ext)
        if candidato.is_file():
            return str(candidato.parent), candidato.name, candidato.stem

    # caso 3: é um diretório — procura pelo scene_id lá dentro
    if caminho.is_dir():
        for ext in EXTENSOES_VIDEO:
            candidato = caminho / f"{item.scene_id}{ext}"
            if candidato.is_file():
                return str(caminho), candidato.name, candidato.stem
        # último recurso: um único vídeo no diretório
        videos = sorted(
            p for p in caminho.iterdir()
            if p.is_file() and p.suffix.lower() in EXTENSOES_VIDEO
        )
        if len(videos) == 1:
            return str(caminho), videos[0].name, videos[0].stem
        raise FileNotFoundError(
            f"diretório {caminho} tem {len(videos)} vídeo(s); "
            f"nenhum chamado '{item.scene_id}'"
        )

    raise FileNotFoundError(
        f"não encontrei a cena '{item.scene_id}' em {item.scene_video_path} "
        f"(tentei como arquivo, com as extensões {EXTENSOES_VIDEO}, e como diretório)"
    )


# --------------------------------------------------------------------------- #
# Palavras-chave com peso
# --------------------------------------------------------------------------- #
_PALAVRA = re.compile(r"[a-z0-9']+")


def ranquear_keywords(
    keys: list[str],
    caption: str,
    modelo_texto=None,
    maximo: int = 10,
) -> list[PalavraChave]:
    """Ordena as palavras-chave por aderência à legenda escolhida.

    POR QUE ISTO É NECESSÁRIO
        O campo `keys` do proposal traz substantivos e verbos de TODAS as
        legendas de TODOS os frames da cena (WholePropGener._coletar_keywords).
        Muitas não têm relação com a legenda que venceu o ranking. Este passo
        filtra e ordena pela relação com ela.

    COMO O PESO É CALCULADO
        Combina dois sinais:

        (a) PRESENÇA LITERAL — a palavra aparece na legenda?
            Sinal forte e inequívoco. Peso base 1.0.

        (b) SIMILARIDADE SEMÂNTICA — cosseno entre o embedding da palavra e o
            da legenda, no espaço do sentence-transformer (JÁ CARREGADO, então
            não custa carregamento novo). Captura relação sem repetição literal
            ("cooking" x "a woman preparing food").

        O peso final é `(a) * 0.6 + (b) * 0.4`, normalizado em [0, 1].

    ⚠️ LIMITE DECLARADO
        Esta ponderação é uma DECISÃO DE PROJETO, não um resultado medido. Não
        há referência para dizer qual peso é "certo". Comparar um token isolado
        a uma frase via embeddings é ruidoso — é por isso que a presença
        literal domina a fórmula. Se depois você tiver exemplos anotados, os
        pesos 0.6/0.4 são o primeiro lugar a calibrar.
    """
    if not keys or not caption:
        return []

    unicas = list(dict.fromkeys(k.strip().lower() for k in keys if k and k.strip()))
    if not unicas:
        return []

    tokens_legenda = set(_PALAVRA.findall(caption.lower()))
    presenca = [1.0 if k in tokens_legenda else 0.0 for k in unicas]

    # --- sinal semântico ---
    semantica = [0.0] * len(unicas)
    if modelo_texto is not None:
        try:
            from sentence_transformers import util as sim_util

            emb = modelo_texto.encode(unicas + [caption], convert_to_tensor=True)
            sims = sim_util.cos_sim(emb[:-1], emb[-1:])
            brutos = [float(s) for s in sims.reshape(-1)]
            # cosseno vive em [-1,1]; reescalamos para [0,1]
            semantica = [max(0.0, min(1.0, (b + 1.0) / 2.0)) for b in brutos]
        except Exception as exc:  # noqa: BLE001 — o peso não pode derrubar o job
            log.warning("similaridade semântica indisponível (%s); usando só presença", exc)

    resultado = [
        PalavraChave(token=k, weight=round(0.6 * p + 0.4 * s, 4))
        for k, p, s in zip(unicas, presenca, semantica)
    ]
    resultado.sort(key=lambda x: x.weight, reverse=True)
    return resultado[:maximo]


# --------------------------------------------------------------------------- #
# O pipeline
# --------------------------------------------------------------------------- #
def _limpar_caches(cfg, collection: str) -> list[str]:
    """Apaga os 3 artefatos de meta_dir chaveados por `collection`."""
    alvos = [
        os.path.join(cfg.meta_dir, cfg.captions_dir,
                     f"{collection}_{cfg.caption_generator}.jsonl"),
        os.path.join(cfg.meta_dir, cfg.raw_capframe_scores_dir,
                     f"{collection}_{cfg.caption_generator}.pt"),
        os.path.join(cfg.meta_dir, cfg.framefeatures_dir, f"{collection}.pt"),
    ]
    apagados = []
    for a in alvos:
        if os.path.isfile(a):
            os.remove(a)
            apagados.append(a)
    return apagados


def _escrever_annos(cfg, collection: str, nomes_base: list[str]) -> str:
    """Escreve o arquivo de anotações com os vídeos deste grupo.

    ★ SEM ISTO NADA É PROCESSADO. `select_videos` (constructpipe/base.py:186-203)
    só mantém vídeos cujo `vid_name` esteja aqui — os demais são descartados
    EM SILÊNCIO, sem erro e sem aviso.
    """
    dir_anno = os.path.join(cfg.anno_dir, collection)
    os.makedirs(dir_anno, exist_ok=True)
    caminho = os.path.join(dir_anno, cfg.anno_file)
    with open(caminho, "w", encoding="utf-8") as f:
        for nb in nomes_base:
            f.write(json.dumps({"vid_name": nb}, ensure_ascii=False) + "\n")
    return caminho


def processar_pedido(
    pedido: PedidoDeJob,
    job_id: str,
    montar_cfg,
    modelos,
    config_servico,
) -> dict:
    """Executa o pipeline completo e devolve a resposta no formato acordado.

    `montar_cfg` e `modelos` vêm do serviço — mantê-los como parâmetros deixa
    esta função testável sem subir o FastAPI.
    """
    t0 = time.perf_counter()
    itens = pedido.como_itens()
    if not itens:
        raise ValueError(
            "pedido vazio: informe `scene_id` + `scene_video_path`, ou `items`"
        )

    # --- PASSO 1: resolver os caminhos ------------------------------------ #
    resolvidos: list[dict] = []
    falhas: list[RespostaDeCena] = []
    for item in itens:
        try:
            diretorio, arquivo, nome_base = resolver_cena(item)
            resolvidos.append({
                "item": item, "diretorio": diretorio,
                "arquivo": arquivo, "nome_base": nome_base,
            })
        except FileNotFoundError as exc:
            falhas.append(RespostaDeCena(
                scene_id=item.scene_id, status="error", erro=str(exc)))

    if not resolvidos:
        return {
            "items": [f.model_dump() for f in falhas],
            "resumo": {"total": len(itens), "ok": 0, "erros": len(falhas)},
            "segundos": round(time.perf_counter() - t0, 2),
        }

    # --- PASSO 2: agrupar por diretório ------------------------------------ #
    # ★ `build()` lista UM diretório (constructpipe/base.py:43). Cenas de
    # `video_id` diferentes estão em diretórios diferentes -> um build por grupo.
    grupos: dict[str, list[dict]] = defaultdict(list)
    for r in resolvidos:
        grupos[r["diretorio"]].append(r)

    # --- PASSO 3: decidir o collection ------------------------------------- #
    # Precedência: o que o pedido mandou > program_id > job_id.
    # Usar o program_id faz cenas do mesmo programa COMPARTILHAREM cache — o que
    # é desejável, já que costumam ser reprocessadas juntas.
    def collection_de(grupo: list[dict]) -> str:
        if pedido.collection:
            return pedido.collection
        pid = grupo[0]["item"].program_id
        return pid if pid else f"job_{job_id[:12]}"

    # --- PASSO 4: rodar um build por grupo --------------------------------- #
    from construct import build

    por_cena: dict[str, RespostaDeCena] = {}
    diagnostico_grupos = []

    for diretorio, grupo in grupos.items():
        collection = collection_de(grupo)
        nomes_base = [g["nome_base"] for g in grupo]

        cfg = montar_cfg(
            video_root=diretorio,                       # ← PASSO 5: do pedido
            collection=collection,                      # ← PASSO 4: isolamento
            construct_name=f"job_{job_id[:12]}",
            caption_generator="blip",
            proposal_generator=pedido.proposal_generator,
            device=config_servico.device,
            caption_model=config_servico.caption_model,
            blip_itm_model=config_servico.blip_itm_model,
            sentence_transformer=config_servico.sentence_transformer,
        )

        # quem já está em cache (lido ANTES de rodar)
        caminho_cache = os.path.join(
            cfg.meta_dir, cfg.captions_dir,
            f"{collection}_{cfg.caption_generator}.jsonl")
        ja_em_cache = set()
        if os.path.isfile(caminho_cache):
            with open(caminho_cache, encoding="utf-8") as f:
                for linha in f:
                    linha = linha.strip()
                    if linha:
                        try:
                            ja_em_cache.add(json.loads(linha)["vid_name"])
                        except (json.JSONDecodeError, KeyError):
                            pass

        apagados = _limpar_caches(cfg, collection) if pedido.limpar_cache else []
        if apagados:
            ja_em_cache = set()

        caminho_anno = _escrever_annos(cfg, collection, nomes_base)

        log.info("[job %s] build() em %s: %d cena(s), collection=%s",
                 job_id[:8], diretorio, len(nomes_base), collection)
        tree_meta = build(cfg, modelos.como_dict()) or {}

        # --- PASSO 6: transformar a saída ---------------------------------- #
        exp_dir = getattr(cfg, "exp_dir", None)
        props = {}
        if exp_dir:
            caminho_props = os.path.join(exp_dir, cfg.proposals_file)
            if os.path.isfile(caminho_props):
                with open(caminho_props, encoding="utf-8") as f:
                    props = json.load(f)

        for g in grupo:
            nb, scene_id = g["nome_base"], g["item"].scene_id
            dados = props.get(nb, {})
            proposta = (dados.get("proposals") or [{}])[0]
            legenda = proposta.get("cap")

            if not legenda:
                por_cena[scene_id] = RespostaDeCena(
                    scene_id=scene_id, status="error",
                    erro=(f"o pipeline não produziu legenda para '{nb}'. "
                          f"Verifique se o vídeo foi decodificado "
                          f"(duração < 1s produz zero frames)."))
                continue

            por_cena[scene_id] = RespostaDeCena(
                scene_id=scene_id,
                scene_caption_en=legenda,
                keywords_en=ranquear_keywords(
                    proposta.get("keys", []), legenda, modelos.sentence_transformer),
                status="success",
            )

        diagnostico_grupos.append({
            "diretorio": diretorio,
            "collection": collection,
            "cenas": len(nomes_base),
            "estavam_em_cache": len([n for n in nomes_base if n in ja_em_cache]),
            "cache_limpo": bool(apagados),
            "annos": caminho_anno,
            "exp_dir": exp_dir,
        })

    # --- resposta ---------------------------------------------------------- #
    resultado = [por_cena[i.scene_id] for i in itens if i.scene_id in por_cena]
    resultado += falhas
    ok = sum(1 for r in resultado if r.status == "success")

    return {
        "items": [r.model_dump(exclude_none=True) for r in resultado],
        "resumo": {"total": len(itens), "ok": ok, "erros": len(resultado) - ok},
        "grupos": diagnostico_grupos,
        "segundos": round(time.perf_counter() - t0, 2),
    }
