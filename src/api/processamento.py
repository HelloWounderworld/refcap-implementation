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

# ★★★ O ÚNICO PONTO QUE CONHECE O FORMATO DO CAMINHO ★★★
#
# O contrato acordado é:
#     scene_video_path = <prefixo>/{program_id}/{video_id}/{scene_id}.mp4
#
# O RefCap identifica cada vídeo pelo NOME-BASE do arquivo — que hoje é o
# `scene_id`. Isso funciona porque, dentro de um mesmo `program_id`, o
# `scene_id` é único (premissa confirmada com o time).
#
# SE O FORMATO DA REQUISIÇÃO MUDAR, MUDE AQUI E MAIS NADA:
#
#   "scene_id"            -> o nome-base é o próprio scene_id  (padrão hoje)
#   "video_id__scene_id"  -> use se um dia o scene_id repetir entre video_id
#                            do MESMO program_id
#
# Trocar esta constante altera apenas como a cena é registrada no annos e no
# cache. Todo o resto do pipeline — agrupamento, build, resposta — continua
# igual, para requisição única e em lote.
IDENTIFICADOR = "scene_id"


def montar_identificador(item: "SceneItem", nome_do_arquivo: str) -> str:
    """Devolve o nome-base com que o RefCap vai registrar esta cena.

    `nome_do_arquivo` é o stem do arquivo encontrado no disco — usado quando
    o IDENTIFICADOR é "scene_id", porque é ele que o RefCap vê no os.listdir.
    """
    if IDENTIFICADOR == "video_id__scene_id":
        if not item.video_id:
            raise CenaNaoResolvida(
                ErrorCode.INVALID_REQUEST,
                f"IDENTIFICADOR exige `video_id`, ausente na cena "
                f"'{item.scene_id}'",
            )
        return f"{item.video_id}__{item.scene_id}"
    return nome_do_arquivo

MODEL_NAME_PADRAO = os.environ.get("REFCAP_MODEL_NAME", "refcap")
MODEL_VERSION_PADRAO = os.environ.get("REFCAP_MODEL_VERSION", "v1")


class ErrorCode:
    """Códigos de erro do contrato, por cena.

    Cada um mapeia uma causa distinta — a ideia é que o consumidor consiga
    decidir o que fazer sem ler a mensagem em texto livre.
    """

    #: payload malformado, campo obrigatório faltando, pedido vazio
    INVALID_REQUEST = "INVALID_REQUEST"
    #: o `scene_video_path` não existe no disco
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    #: o caminho existe, mas não há vídeo com aquele `scene_id`
    SCENE_NOT_FOUND = "SCENE_NOT_FOUND"
    #: o pipeline rodou e não produziu legenda (vídeo < 1s, decodificação falhou)
    CAPTION_FAILED = "CAPTION_FAILED"
    #: exceção inesperada em qualquer ponto
    INTERNAL_ERROR = "INTERNAL_ERROR"


# --------------------------------------------------------------------------- #
# Contratos
# --------------------------------------------------------------------------- #
class SceneItem(BaseModel):
    """Uma cena a legendar."""
    scene_id: str
    video_id: str | None = None
    program_id: str | None = None
    scene_video_path: str = Field(
        ...,
        description="Caminho da cena. Aceita o arquivo de vídeo OU o diretório "
                    "que o contém (nesse caso o arquivo é procurado lá dentro).",
    )


class CaptionRequest(BaseModel):
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
    items: list[SceneItem] | None = None

    # --- controles opcionais ---
    callback_url: str | None = None
    assincrono: bool = Field(
        default=False,
        description="Override manual do modo. Acima do limiar de itens a API já "
                    "muda sozinha para assíncrono; este campo força um dos dois.",
    )
    proposal_generator: str = "whole"
    force: bool = Field(
        default=False,
        description="Reprocessa as cenas desta requisição, limpando o cache "
                    "delas (legendas, features e scores). NUNCA é automático — "
                    "só quando explicitamente pedido.",
    )

    # ⚠️ `collection` foi REMOVIDO do contrato de propósito.
    #
    # Ele agora é DERIVADO do `program_id`: um só identificador governa os
    # cinco caminhos do RefCap (annos, os 3 caches de meta/, e results/).
    # Aceitar um override aqui quebraria o isolamento entre programas — dois
    # programas com o mesmo `collection` compartilhariam cache, e o segundo
    # receberia as legendas do primeiro, em silêncio.
    #
    # As rotas de diagnóstico são a única exceção: elas usam um `collection`
    # próprio ("diagnostics") para não contaminar dados reais.

    def como_itens(self) -> list[SceneItem]:
        """Normaliza as duas formas numa lista única.

        Cena única vira um lote de um. Todo o resto do código trata só listas —
        não há dois caminhos de execução para manter.
        """
        if self.items:
            return list(self.items)
        if self.scene_id and self.scene_video_path:
            return [SceneItem(
                scene_id=self.scene_id,
                video_id=self.video_id,
                program_id=self.program_id,
                scene_video_path=self.scene_video_path,
            )]
        return []


class Keyword(BaseModel):
    token: str
    weight: float


class SceneResponse(BaseModel):
    """O contrato de saída, por cena. Idêntico nas três rotas."""

    scene_id: str
    scene_caption_en: str | None = None
    keywords_en: list[Keyword] = Field(default_factory=list)
    model_name: str = MODEL_NAME_PADRAO
    model_version: str = MODEL_VERSION_PADRAO
    status: str = "success"

    # Preenchidos apenas quando `status == "error"`.
    error_code: str | None = None
    message: str | None = None

    @classmethod
    def falha(cls, scene_id: str, error_code: str, message: str) -> "SceneResponse":
        """Atalho para montar uma resposta de erro sem repetir os campos."""
        return cls(scene_id=scene_id, status="error",
                   error_code=error_code, message=message)


# --------------------------------------------------------------------------- #
# Resolução de caminho
# --------------------------------------------------------------------------- #
class CenaNaoResolvida(Exception):
    """Carrega o código de erro junto com a mensagem.

    Sem isto, quem captura teria de inferir o código a partir do texto — o que
    é frágil e quebra quando a mensagem muda.
    """

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


def resolver_cena(item: SceneItem) -> tuple[str, str, str]:
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
        # ⚠️ REMOVIDO na Etapa 2: o fallback que usava o ÚNICO vídeo do
        # diretório quando nenhum batia com o scene_id.
        #
        # Motivo: legendava o arquivo errado EM SILÊNCIO, devolvendo
        # status "success" com a legenda de outra cena. Melhor falhar.
        videos = sorted(
            p for p in caminho.iterdir()
            if p.is_file() and p.suffix.lower() in EXTENSOES_VIDEO
        )
        raise CenaNaoResolvida(
            ErrorCode.SCENE_NOT_FOUND,
            f"diretório {caminho} tem {len(videos)} vídeo(s), "
            f"nenhum chamado '{item.scene_id}'",
        )

    # A distinção entre os dois códigos importa para o consumidor:
    #   FILE_NOT_FOUND  -> o caminho não existe de todo
    #   SCENE_NOT_FOUND -> o caminho existe, mas não há vídeo com esse scene_id
    if not caminho.exists():
        raise CenaNaoResolvida(
            ErrorCode.FILE_NOT_FOUND,
            f"caminho não encontrado: {item.scene_video_path}",
        )
    raise CenaNaoResolvida(
        ErrorCode.SCENE_NOT_FOUND,
        f"não encontrei a cena '{item.scene_id}' em {item.scene_video_path} "
        f"(tentei como arquivo, com as extensões {EXTENSOES_VIDEO}, e como diretório)",
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
) -> list[Keyword]:
    """Devolve as palavras-chave CONTIDAS na legenda, com peso 1.0.

    POR QUE ESTE FILTRO É NECESSÁRIO
        O campo `keys` do proposal traz substantivos e verbos de TODAS as
        legendas de TODOS os frames da cena (WholePropGener._coletar_keywords).
        Muitas não têm relação com a legenda que venceu o ranking. Aqui
        mantemos apenas as que de fato aparecem nela.

    ★ O PESO ESTÁ FIXO EM 1.0 — DE PROPÓSITO
        A ponderação anterior (ver abaixo) foi SUSPENSA até se decidir se o
        peso é sequer necessário para o retrieval, que é feito por outra API
        usando GloVe. Enquanto isso, todas as keywords entregues valem o mesmo.

        Como só entram palavras literalmente presentes na legenda, 1.0 é
        coerente: não há gradação a expressar.

    ─────────────────────────────────────────────────────────────────────────
    O CÁLCULO SUSPENSO, para quando a decisão sobre o GloVe for tomada:

        weight = 0.6 × presença_literal + 0.4 × similaridade_semântica

        (a) PRESENÇA LITERAL — a palavra aparece na legenda? Peso base 1.0.

        (b) SIMILARIDADE SEMÂNTICA — cosseno entre o embedding da palavra e o
            da legenda, no espaço do sentence-transformer. Captava relação sem
            repetição literal ("cooking" × "a woman preparing food").

        POR QUE FOI SUSPENSO, além da dúvida sobre a necessidade:
          - o `paraphrase-distilroberta-v2` foi treinado para comparar
            SENTENÇAS, não palavras isoladas — usá-lo assim é operar fora do
            domínio de treino;
          - os pesos 0.6/0.4 nunca foram calibrados: foram escolhidos por
            julgamento, sem dados anotados.

        Alternativas a avaliar quando o assunto voltar:
          1. BLIP-ITM contra o FRAME — "quão bem esta palavra descreve o que
             se vê". Mais ancorado no vídeo; exige passar os frames adiante.
          2. Um modelo com vetores de PALAVRA (spaCy _md/_lg, ou o próprio
             GloVe que o retrieval já usa).
          3. Presença literal + frequência entre as legendas dos frames.

        O parâmetro `modelo_texto` foi MANTIDO na assinatura de propósito: o
        chamador continua passando o sentence-transformer, e religar o cálculo
        não exige mudar quem chama.
    ─────────────────────────────────────────────────────────────────────────
    """
    if not keys or not caption:
        return []

    tokens_legenda = set(_PALAVRA.findall(caption.lower()))

    # dict.fromkeys preserva a ordem de primeira aparição
    unicas = list(dict.fromkeys(
        k.strip().lower() for k in keys if k and k.strip()
    ))

    presentes = [k for k in unicas if k in tokens_legenda]
    return [Keyword(token=k, weight=1.0) for k in presentes[:maximo]]


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
    pedido: CaptionRequest,
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
        raise CenaNaoResolvida(
            ErrorCode.INVALID_REQUEST,
            "pedido vazio: informe `scene_id` + `scene_video_path`, ou `items`",
        )

    # --- PASSO 1: resolver os caminhos ------------------------------------ #
    resolvidos: list[dict] = []
    falhas: list[SceneResponse] = []
    for item in itens:
        try:
            diretorio, arquivo, stem = resolver_cena(item)
            resolvidos.append({
                "item": item, "diretorio": diretorio, "arquivo": arquivo,
                # o nome-base com que o RefCap registra a cena — ver
                # IDENTIFICADOR no topo do módulo
                "nome_base": montar_identificador(item, stem),
            })
        except CenaNaoResolvida as exc:
            falhas.append(SceneResponse.falha(
                item.scene_id, exc.error_code, exc.message))

    if not resolvidos:
        return {
            "items": [f.model_dump() for f in falhas],
            "summary": {"total": len(itens), "ok": 0, "errors": len(falhas)},
            "seconds": round(time.perf_counter() - t0, 2),
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
        """O `collection` É o `program_id`. Um só identificador, cinco caminhos:

            annos/{program_id}/vcmr.jsonl
            meta/captions/{program_id}_blip.jsonl
            meta/framefeatures/{program_id}.pt
            meta/scores/{program_id}_blip.pt
            results/construct/{program_id}/

        É isso que garante que dois programas nunca se cruzem: cache, annos e
        resultados ficam todos sob o mesmo identificador.

        Sem `program_id` — caso que o contrato não prevê — cai no job_id, que
        dá isolamento total sem reaproveitar cache de ninguém.
        """
        pid = grupo[0]["item"].program_id
        return pid if pid else f"job_{job_id[:12]}"

    # --- PASSO 4: rodar um build por grupo --------------------------------- #
    from construct import build

    por_cena: dict[str, SceneResponse] = {}
    diagnostico_grupos = []

    for diretorio, grupo in grupos.items():
        collection = collection_de(grupo)
        nomes_base = [g["nome_base"] for g in grupo]

        cfg = montar_cfg(
            video_root=diretorio,                       # ← PASSO 5: do pedido
            collection=collection,                      # ← PASSO 4: isolamento
            # ★ construct_name VAZIO: o exp_dir do RefCap é
            #     res_dir/construct_dir/{collection}/{construct_name}
            #   Com "" o os.path.join colapsa o último nível, produzindo
            #     results/construct/{program_id}/
            #   Assim os artefatos do programa ficam num lugar só, cumulativo
            #   entre requisições — em vez de um diretório por job.
            construct_name="",
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

        apagados = _limpar_caches(cfg, collection) if pedido.force else []
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
                por_cena[scene_id] = SceneResponse.falha(
                    scene_id, ErrorCode.CAPTION_FAILED,
                    f"o pipeline não produziu legenda para '{nb}'. "
                    f"Verifique se o vídeo foi decodificado "
                    f"(duração < 1s produz zero frames).")
                continue

            por_cena[scene_id] = SceneResponse(
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
        "summary": {"total": len(itens), "ok": ok, "errors": len(resultado) - ok},
        "groups": diagnostico_grupos,
        "seconds": round(time.perf_counter() - t0, 2),
    }
