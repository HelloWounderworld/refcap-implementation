"""Serviço FastAPI do RefCap — o terreno preparado.

O QUE ESTE ARQUIVO JÁ FAZ
-------------------------
    supervisord -> uvicorn -> FastAPI
                              |
                              +-- startup: carrega os 3 modelos UMA vez
                              |            (estado permanente)
                              |
                              +-- POST /jobs  -> cria job, devolve job_id
                              |                  (executa em fila serializada)
                              +-- GET  /jobs/{id} -> consulta o estado
                              +-- GET  /health    -> os modelos estão prontos?
                              |
                              +-- shutdown: libera os modelos

O QUE FALTA (marcado com  ### AQUI ENTRA O SEU PIPELINE ###)
------------------------------------------------------------
A função `processar_job` tem o esqueleto pronto e um ponto claramente marcado
onde você vai:
    1. tratar o que veio na requisição (vídeos, parâmetros)
    2. conferir / atualizar as listas de annos
    3. montar o cfg com os campos que decidir
    4. chamar build(cfg, modelos)

Nada do resto do serviço muda quando você preencher isso.

RODAR EM DESENVOLVIMENTO
    uvicorn app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import pathlib
import traceback

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from carregador import ModelosResidentes
from jobs import EstadoJob, Job, RegistroDeJobs
from processamento import (MODEL_NAME_PADRAO, MODEL_VERSION_PADRAO, CaptionRequest,
                           ErrorCode, processar_pedido, ranquear_keywords)
from ponte_refcap import RAIZ_REFCAP, montar_cfg, preparar_sys_path

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
log = logging.getLogger("refcap.api")


# --------------------------------------------------------------------------- #
# Configuração do serviço (via ambiente — o supervisord define)
# --------------------------------------------------------------------------- #
class ConfigServico:
    """Configuração via ambiente — o supervisord define no bloco `environment=`.

    ⚠️ REFCAP_*_MODEL devem ser CAMINHOS ABSOLUTOS para os modelos locais.
    Os defaults abaixo são repo-ids do Hub e só servem se houver rede. Num
    servidor offline, deixar o default faz o from_pretrained() tentar baixar,
    falhar, e o processo morrer — o que no supervisord vira loop de reinício.

    Valide os caminhos antes de subir:
        python validar_modelos_locais.py --caption <dir> --itm <dir> --st <dir>
    """
    device = os.environ.get("REFCAP_DEVICE", "cuda")
    caption_model = os.environ.get("REFCAP_CAPTION_MODEL", "Salesforce/blip-image-captioning-large")
    blip_itm_model = os.environ.get("REFCAP_BLIP_ITM_MODEL", "Salesforce/blip-itm-base-coco")
    sentence_transformer = os.environ.get("REFCAP_SENTENCE_TRANSFORMER", "paraphrase-distilroberta-v2")
    carregar_no_startup = os.environ.get("REFCAP_CARREGAR_MODELOS", "1") == "1"


# --------------------------------------------------------------------------- #
# Estado do processo — vive enquanto o serviço viver
# --------------------------------------------------------------------------- #
modelos = ModelosResidentes()
registro = RegistroDeJobs()


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    """Startup e shutdown.

    ★ É AQUI que o carregamento acontece — UMA vez, quando o supervisord sobe o
    processo. A partir daí os modelos ficam residentes e cada requisição os usa
    sem recarregar.
    """
    log.info("iniciando serviço — RefCap em %s", RAIZ_REFCAP)
    preparar_sys_path()

    if ConfigServico.carregar_no_startup:
        modelos.carregar(
            caption_model=ConfigServico.caption_model,
            blip_itm_model=ConfigServico.blip_itm_model,
            sentence_transformer=ConfigServico.sentence_transformer,
            device=ConfigServico.device,
        )
    else:
        # Modo de desenvolvimento: sobe o serviço sem GPU/modelos para testar rotas.
        log.warning("REFCAP_CARREGAR_MODELOS=0 — subindo SEM os modelos")

    yield

    log.info("encerrando serviço")
    modelos.liberar()


app = FastAPI(
    title="RefCap API",
    description="Captioning de vídeos com os modelos do RefCap residentes em memória.",
    version="0.1.0",
    lifespan=ciclo_de_vida,
)


# --------------------------------------------------------------------------- #
# Contratos
# --------------------------------------------------------------------------- #
class RespostaAssincrona(BaseModel):
    """Devolvida apenas quando o pedido traz `"assincrono": true`."""
    job_id: str
    estado: str
    consultar_em: str


# --------------------------------------------------------------------------- #
# ★ O ponto onde o SEU pipeline entra
# --------------------------------------------------------------------------- #

def _keys_da_cena(props: dict, no_do_tree: dict | None, nome_base: str) -> list:
    """Extrai as palavras-chave, com o proposals.json como fonte primária.

    O `build_tree_meta` (constructpipe/base.py:178-179) propaga `keys` da
    proposta para o nó filho, então as duas fontes têm o mesmo conteúdo. Ler do
    proposals.json é mais direto; o tree_meta fica como alternativa.
    """
    prop = ((props or {}).get(nome_base, {}).get("proposals") or [{}])[0]
    if prop.get("keys"):
        return prop["keys"]
    for filho in (no_do_tree or {}).get("subs", []):
        if filho.get("keys"):
            return filho["keys"]
    return []


def processar_job(job: Job) -> dict:
    """Executa um job completo: pipeline + captioning + resposta.

    O pipeline (escrever annos, agrupar por diretório, decidir collection,
    tratar cache) e a transformação da saída vivem em `processamento.py` —
    aqui só ligamos as peças do serviço.

    Os modelos JÁ ESTÃO CARREGADOS: `modelos.como_dict()` devolve o dicionário
    no formato que o `build()` do RefCap espera, e ele NÃO recarrega nada.
    """
    pedido = CaptionRequest(**job.entrada)
    return processar_pedido(
        pedido=pedido,
        job_id=job.id,
        montar_cfg=montar_cfg,
        modelos=modelos,
        config_servico=ConfigServico,
    )


# --------------------------------------------------------------------------- #
# Rotas
# --------------------------------------------------------------------------- #
@app.get("/health", summary="Os modelos estão residentes?")
async def health() -> dict:
    return {
        "servico": "ok",
        "refcap_root": str(RAIZ_REFCAP),
        "modelos": modelos.diagnostico(),
        "jobs_na_fila": registro.quantos_na_fila(),
    }


@app.post("/jobs", summary="Processa um job e devolve o resultado")
async def criar_job(pedido: CaptionRequest, tarefas: BackgroundTasks):
    """Por padrão AGUARDA o processamento e devolve o resultado completo.

    ★ MODO PADRÃO (síncrono) — `"assincrono"` ausente ou `false`
        A conexão fica aberta até o job terminar, e a resposta traz:

            {"state": "concluded",
             "summary": {"total": N, "ok": N, "errors": 0},
             "items": [ {scene_id, scene_caption_en, keywords_en, ...} ],
             "groups": [...], "seconds": 12.3}

        ⚠️ A fila continua serializando: se outro job estiver rodando, este
        espera a vez. Com lotes grandes, a conexão pode cair por timeout de
        proxy — nesse caso use o modo assíncrono.

    MODO ASSÍNCRONO — `"assincrono": true`
        Devolve 202 + `job_id` na hora e processa em segundo plano. Consulte
        por `GET /jobs/{id}`, ou informe `callback_url` para ser avisado.

    Em AMBOS os modos o job fica registrado e pode ser reconsultado depois.
    """
    # A guarda NÃO pode depender de `carregar_no_startup`: se o serviço subiu
    # com REFCAP_CARREGAR_MODELOS=0, os modelos não existem e o build() não tem
    # como rodar. Sem esta checagem, o erro apareceria só lá dentro, como 500.
    if not modelos.pronto:
        raise HTTPException(503, {
            "erro": "modelos não carregados",
            "carregar_no_startup": ConfigServico.carregar_no_startup,
            "dica": ("suba o serviço sem REFCAP_CARREGAR_MODELOS=0 para carregar "
                     "os modelos no startup"),
        })

    job = registro.criar(entrada=pedido.model_dump(), callback_url=pedido.callback_url)

    # --- modo assíncrono: devolve na hora ------------------------------- #
    if pedido.assincrono:
        tarefas.add_task(registro.executar, job, processar_job)
        return JSONResponse(
            status_code=202,
            content=RespostaAssincrona(
                job_id=job.id,
                estado=job.estado.value,
                consultar_em=f"/jobs/{job.id}",
            ).model_dump(),
        )

    # --- modo padrão: AGUARDA e devolve o resultado --------------------- #
    # `executar` já roda a tarefa numa thread (asyncio.to_thread) e sob a trava
    # da fila — então aguardar aqui NÃO bloqueia o loop de eventos: o /health e
    # o GET /jobs continuam respondendo durante o processamento.
    await registro.executar(job, processar_job)

    resultado = job.resultado or {}
    corpo = {
        # `job_id` NÃO entra: o rastreio acordado é por program_id + scene_id,
        # e o resultado fica persistido em results/response/{program_id}/.
        "state": job.estado.value,
        **(resultado if isinstance(resultado, dict) else {"resultado": resultado}),
    }
    if job.erro:
        corpo["message"] = job.erro
        corpo["error_code"] = ErrorCode.INTERNAL_ERROR
    # 200 quando concluiu; 500 quando o job falhou por inteiro (falhas de cena
    # individual vêm como status:"error" dentro de items, com HTTP 200).
    return JSONResponse(
        status_code=200 if job.estado == EstadoJob.CONCLUIDO else 500,
        content=corpo,
    )


@app.get("/jobs/{job_id}", summary="Consulta o estado de um job")
async def consultar_job(job_id: str) -> dict:
    job = registro.obter(job_id)
    if job is None:
        raise HTTPException(404, f"job {job_id} não encontrado")
    return job.como_dict()


@app.get("/jobs", summary="Lista os jobs recentes")
async def listar_jobs(limite: int = 50) -> dict:
    return {"jobs": registro.listar(limite)}

# --------------------------------------------------------------------------- #
# ★ ROTA DE TESTE — construct de ponta a ponta com UM vídeo
# --------------------------------------------------------------------------- #
@app.get("/teste/construct", summary="[TESTE] roda o construct num vídeo só")
def teste_construct(
    video: str,
    collection: str = "teste_api",
    proposal_generator: str = "whole",
    force: bool = True,
) -> dict:
    """Executa o pipeline COMPLETO num único vídeo, com os modelos residentes.

    Serve para confirmar, pela interface do FastAPI, que:
      1. os modelos carregados no startup são de fato reaproveitados;
      2. o `build()` roda as 7 etapas sem recarregar nada;
      3. o `WholePropGenerator` produz o ranking.

    PARÂMETROS
        video     nome do arquivo em `video_root` (ex.: "cena_001.mp4")
        collection  isola os artefatos deste teste (default: "teste_api")
        proposal_generator  "whole" (o seu) ou "qm" (o original)
        force  apaga os caches deste `collection` antes de rodar, para
                      forçar o processamento de verdade

    ⚠️ É SÍNCRONA de propósito: você vê o resultado direto no navegador.
       Para produção use POST /jobs, que é assíncrono e serializado.

    EXEMPLO
        GET /teste/construct?video=cena_001.mp4
    """
    import json
    import shutil
    import time

    # A guarda NÃO pode depender de `carregar_no_startup`: se o serviço subiu
    # com REFCAP_CARREGAR_MODELOS=0, os modelos não existem e o build() não tem
    # como rodar. Sem esta checagem, o erro apareceria só lá dentro, como 500.
    if not modelos.pronto:
        raise HTTPException(503, {
            "erro": "modelos não carregados",
            "carregar_no_startup": ConfigServico.carregar_no_startup,
            "dica": ("suba o serviço sem REFCAP_CARREGAR_MODELOS=0 para carregar "
                     "os modelos no startup"),
        })

    t_inicio = time.perf_counter()
    nome_base = video.rsplit(".", 1)[0]
    passos: list[str] = []

    # --- 1. o arquivo existe? --------------------------------------------- #
    cfg_base = montar_cfg()
    caminho_video = os.path.join(cfg_base.video_root, video)
    if not os.path.isfile(caminho_video):
        disponiveis = sorted(os.listdir(cfg_base.video_root))[:20] \
            if os.path.isdir(cfg_base.video_root) else []
        raise HTTPException(404, {
            "erro": f"vídeo não encontrado: {caminho_video}",
            "video_root": cfg_base.video_root,
            "primeiros_arquivos_la": disponiveis,
        })
    passos.append(f"vídeo encontrado: {caminho_video}")

    # --- 2. o annos ------------------------------------------------------- #
    # ★ SEM ISTO O TESTE "PASSA" SEM PROCESSAR NADA.
    # `select_videos` (constructpipe/base.py:186-203) só mantém vídeos cujo
    # `vid_name` esteja no arquivo de anotações — os demais são DESCARTADOS
    # EM SILÊNCIO, sem erro e sem aviso.
    dir_anno = os.path.join(cfg_base.anno_dir, collection)
    os.makedirs(dir_anno, exist_ok=True)
    caminho_anno = os.path.join(dir_anno, cfg_base.anno_file)
    with open(caminho_anno, "w", encoding="utf-8") as f:
        f.write(json.dumps({"vid_name": nome_base}, ensure_ascii=False) + "\n")
    passos.append(f"annos escrito: {caminho_anno}")

    # --- 3. limpar caches deste collection -------------------------------- #
    # Os 3 artefatos de meta_dir são chaveados por `collection` e têm lógica de
    # PULAR vídeo já processado. Sem limpar, uma segunda chamada reaproveitaria
    # o cache e o BLIP não rodaria — o teste passaria sem testar.
    if force:
        alvos = [
            os.path.join(cfg_base.meta_dir, cfg_base.captions_dir,
                         f"{collection}_{cfg_base.caption_generator}.jsonl"),
            os.path.join(cfg_base.meta_dir, cfg_base.raw_capframe_scores_dir,
                         f"{collection}_{cfg_base.caption_generator}.pt"),
            os.path.join(cfg_base.meta_dir, cfg_base.framefeatures_dir,
                         f"{collection}.pt"),
        ]
        apagados = [a for a in alvos if os.path.isfile(a) and (os.remove(a) or True)]
        passos.append(f"caches limpos: {len(apagados)}")

    # --- 4. montar o cfg -------------------------------------------------- #
    cfg = montar_cfg(
        collection=collection,
        construct_name=f"teste_{int(time.time())}",
        caption_generator="blip",
        proposal_generator=proposal_generator,
        device=ConfigServico.device,
        caption_model=ConfigServico.caption_model,
        blip_itm_model=ConfigServico.blip_itm_model,
        sentence_transformer=ConfigServico.sentence_transformer,
    )
    passos.append(f"cfg montado (collection={collection}, propgen={proposal_generator})")

    # --- 5. ★ o build com os modelos JÁ CARREGADOS ------------------------ #
    from construct import build

    gpu_antes = ModelosResidentes.estado_da_gpu()
    log.info("[teste] chamando build() com modelos residentes ...")
    try:
        tree_meta = build(cfg, modelos.como_dict())
    except Exception as exc:
        log.exception("[teste] build falhou")
        raise HTTPException(500, {
            "erro": f"{type(exc).__name__}: {exc}",
            "passos_ate_falhar": passos,
            "exp_dir": getattr(cfg, "exp_dir", None),
        }) from exc

    gpu_depois = ModelosResidentes.estado_da_gpu()
    passos.append("build() concluído")

    # --- 6. montar a resposta --------------------------------------------- #
    resultado_video = (tree_meta or {}).get(nome_base)
    propostas = []
    if resultado_video:
        for filho in resultado_video.get("subs", []):
            propostas.append({
                "st": filho.get("st"),
                "ed": filho.get("ed"),
                "legenda": (filho.get("caps") or [None])[0],
                "keywords": filho.get("keys", [])[:10],
            })

    ranking = None
    # `exp_dir` é injetado pelo build() (construct.py); se por algum motivo
    # não estiver definido, degradamos em vez de estourar com AttributeError.
    exp_dir = getattr(cfg, "exp_dir", None)
    caminho_props = os.path.join(exp_dir, cfg.proposals_file) if exp_dir else None
    if os.path.isfile(caminho_props):
        with open(caminho_props, encoding="utf-8") as f:
            props_bruto = json.load(f)
        dados = props_bruto.get(nome_base, {})
        if dados.get("proposals"):
            p0 = dados["proposals"][0]
            ranking = {
                "rank_by": p0.get("rank_by"),
                "n_raw": p0.get("n_raw"),
                "n_distinct": p0.get("n_distinct"),
                "ranking": p0.get("ranking"),
                "warning": p0.get("warning"),
            }

    # ★ a resposta no FORMATO ACORDADO (o mesmo do POST /jobs)
    # `scene_id` aqui é o nome-base do arquivo, já que a rota de teste não
    # recebe um scene_id próprio.
    p0 = (ranking or {})
    legenda_escolhida = (propostas[0]["legenda"] if propostas else None)
    resposta_cena = {
        "scene_id": nome_base,
        "scene_caption_en": legenda_escolhida,
        # as keys vêm do proposals.json (a fonte), com o tree_meta como
        # alternativa — o build_tree_meta as propaga em constructpipe:178-179
        "keywords_en": [
            k.model_dump() for k in ranquear_keywords(
                _keys_da_cena(props_bruto, resultado_video, nome_base),
                legenda_escolhida or "",
                modelos.sentence_transformer,
            )
        ],
        "model_name": MODEL_NAME_PADRAO,
        "model_version": MODEL_VERSION_PADRAO,
        "status": "success" if legenda_escolhida else "error",
    }

    return {
        # ★ O CONTRATO DE SAÍDA no topo, idêntico ao do POST /jobs e ao de cada
        # item da rota de lote. Assim as três produzem o mesmo formato.
        **resposta_cena,
        "ok": True,
        "video": video,
        "seconds": round(time.perf_counter() - t_inicio, 2),
        "passos": passos,
        "exp_dir": exp_dir,
        "proposals_json": caminho_props,
        "propostas": propostas,
        "ranking": ranking,
        "modelos_reaproveitados": {
            "gpu_alocado_mb_antes": gpu_antes.get("alocado_mb"),
            "gpu_alocado_mb_depois": gpu_depois.get("alocado_mb"),
            "nota": ("se os dois valores forem próximos e > 0, os modelos "
                     "continuam residentes: o build NÃO recarregou nada"),
        },
        "tree_meta": tree_meta,
    }

# --------------------------------------------------------------------------- #
# ★ ROTA DE TESTE EM LOTE — um diretório inteiro de .mp4
# --------------------------------------------------------------------------- #
@app.get("/teste/construct-lote", summary="[TESTE] roda o construct num DIRETÓRIO de vídeos")
def teste_construct_lote(
    diretorio: str,
    collection: str = "teste_lote",
    proposal_generator: str = "whole",
    force: bool = False,
    limite: int = 0,
    extensoes: str = ".mp4",
) -> dict:
    """Processa TODOS os vídeos de um diretório numa única execução do build().

    DIFERENÇA PARA `/teste/construct`
        Aquela rota processa UM vídeo — não por limitação do RefCap, mas porque
        escreve uma única linha no arquivo de anotações. O pipeline sempre foi
        nativo de lote: `constructpipe/base.py:43` faz `os.listdir(video_root)`
        e as 7 etapas recebem a lista inteira.

        Esta rota escreve TODAS as entradas no annos, e o build() roda uma vez
        sobre o conjunto — que é exatamente o comportamento do
        `bash scripts/construct.sh`.

    ★ O CACHE (a diferença de default que importa)
        `force=False` por padrão, ao contrário da rota de um vídeo.
        Num lote, limpar seria destrutivo: você perderia o trabalho já feito
        de todos os vídeos daquele `collection`.

        Com o cache preservado, os vídeos já processados são PULADOS pelo
        próprio RefCap:
            BlipCapGener.py:18        já legendado  -> pula
            constructpipe:105         já pontuado   -> pula
            constructpipe:133         já extraído   -> pula
        A resposta informa quantos estavam em cache antes de rodar.

    PARÂMETROS
        diretorio   caminho da pasta com os vídeos (vira o video_root desta
                    execução)
        collection  isola os artefatos e o cache deste lote
        proposal_generator  "whole" (o seu) ou "qm" (o original)
        force  se True, apaga os caches deste `collection` antes de
                      rodar, forçando reprocessamento de tudo
        limite      processa no máximo N vídeos (0 = todos); útil para um teste
                    rápido antes de rodar o conjunto inteiro
        extensoes   filtro, separado por vírgula (ex.: ".mp4,.avi")

    ⚠️ É SÍNCRONA. Um diretório grande pode estourar o timeout do HTTP.
       Use `limite` para testar antes, e o POST /jobs para produção.

    EXEMPLOS
        GET /teste/construct-lote?diretorio=/dados/minhas_cenas
        GET /teste/construct-lote?diretorio=/dados/cenas&limite=5
        GET /teste/construct-lote?diretorio=/dados/cenas&force=true
    """
    import json
    import time

    if ConfigServico.carregar_no_startup and not modelos.pronto:
        raise HTTPException(503, "modelos ainda não carregados")

    t_inicio = time.perf_counter()
    passos: list[str] = []

    # --- 1. o diretório existe e tem vídeos? ------------------------------ #
    if not os.path.isdir(diretorio):
        raise HTTPException(404, {"erro": f"diretório não encontrado: {diretorio}"})

    sufixos = tuple(e.strip().lower() for e in extensoes.split(",") if e.strip())
    arquivos = sorted(
        f for f in os.listdir(diretorio)
        if os.path.isfile(os.path.join(diretorio, f)) and f.lower().endswith(sufixos)
    )
    if not arquivos:
        raise HTTPException(404, {
            "erro": f"nenhum arquivo {sufixos} em {diretorio}",
            "primeiros_arquivos_la": sorted(os.listdir(diretorio))[:20],
        })

    total_encontrado = len(arquivos)
    if limite > 0:
        arquivos = arquivos[:limite]
    nomes_base = [a.rsplit(".", 1)[0] for a in arquivos]
    passos.append(f"{total_encontrado} arquivo(s) encontrado(s); {len(arquivos)} selecionado(s)")

    # --- 2. montar o cfg -------------------------------------------------- #
    # O `diretorio` vira o video_root DESTA execução: o build() faz
    # os.listdir(cfg.video_root), então é dele que a lista sai.
    cfg = montar_cfg(
        video_root=diretorio,
        collection=collection,
        construct_name=f"lote_{int(time.time())}",
        caption_generator="blip",
        proposal_generator=proposal_generator,
        device=ConfigServico.device,
        caption_model=ConfigServico.caption_model,
        blip_itm_model=ConfigServico.blip_itm_model,
        sentence_transformer=ConfigServico.sentence_transformer,
    )
    passos.append(f"cfg montado (collection={collection}, propgen={proposal_generator})")

    # --- 3. ★ o que JÁ está em cache? ------------------------------------- #
    # Lido ANTES de rodar, para a resposta poder dizer o que era novo.
    caminho_cache = os.path.join(
        cfg.meta_dir, cfg.captions_dir, f"{collection}_{cfg.caption_generator}.jsonl"
    )
    ja_em_cache: set[str] = set()
    if os.path.isfile(caminho_cache):
        with open(caminho_cache, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    ja_em_cache.add(json.loads(linha)["vid_name"])
                except (json.JSONDecodeError, KeyError):
                    continue

    em_cache = [n for n in nomes_base if n in ja_em_cache]
    novos = [n for n in nomes_base if n not in ja_em_cache]
    passos.append(f"cache: {len(em_cache)} já processado(s), {len(novos)} novo(s)")

    # --- 4. limpar o cache (só se pedido) --------------------------------- #
    apagados: list[str] = []
    if force:
        alvos = [
            caminho_cache,
            os.path.join(cfg.meta_dir, cfg.raw_capframe_scores_dir,
                         f"{collection}_{cfg.caption_generator}.pt"),
            os.path.join(cfg.meta_dir, cfg.framefeatures_dir, f"{collection}.pt"),
        ]
        for a in alvos:
            if os.path.isfile(a):
                os.remove(a)
                apagados.append(a)
        em_cache, novos = [], nomes_base
        passos.append(f"cache LIMPO: {len(apagados)} arquivo(s) apagado(s)")
    else:
        passos.append("cache PRESERVADO (default) — vídeos já processados serão pulados")

    # --- 5. escrever o annos com TODOS os vídeos -------------------------- #
    # ★ É AQUI que a rota de um vídeo difere desta: lá escrevo UMA linha.
    # `select_videos` (constructpipe/base.py:186-203) só mantém o que estiver
    # neste arquivo — os demais são descartados EM SILÊNCIO.
    dir_anno = os.path.join(cfg.anno_dir, collection)
    os.makedirs(dir_anno, exist_ok=True)
    caminho_anno = os.path.join(dir_anno, cfg.anno_file)
    with open(caminho_anno, "w", encoding="utf-8") as f:
        for nb in nomes_base:
            f.write(json.dumps({"vid_name": nb}, ensure_ascii=False) + "\n")
    passos.append(f"annos escrito com {len(nomes_base)} entrada(s): {caminho_anno}")

    # --- 6. ★ o build com os modelos JÁ CARREGADOS ------------------------ #
    from construct import build

    gpu_antes = ModelosResidentes.estado_da_gpu()
    log.info("[lote] build() com %d vídeo(s), modelos residentes ...", len(nomes_base))
    try:
        tree_meta = build(cfg, modelos.como_dict())
    except Exception as exc:
        log.exception("[lote] build falhou")
        raise HTTPException(500, {
            "erro": f"{type(exc).__name__}: {exc}",
            "passos_ate_falhar": passos,
            "exp_dir": getattr(cfg, "exp_dir", None),
        }) from exc

    gpu_depois = ModelosResidentes.estado_da_gpu()
    passos.append("build() concluído")

    # --- 7. montar a resposta --------------------------------------------- #
    tree_meta = tree_meta or {}

    # o ranking de cada vídeo vem do proposals.json
    # `exp_dir` é injetado pelo build() (construct.py). Usamos getattr porque,
    # se o build falhar muito cedo, o atributo pode não existir — e a resposta
    # de diagnóstico não deve quebrar por causa disso.
    exp_dir = getattr(cfg, "exp_dir", None)
    caminho_props = os.path.join(exp_dir, cfg.proposals_file) if exp_dir else None
    props = {}
    if caminho_props and os.path.isfile(caminho_props):
        with open(caminho_props, encoding="utf-8") as f:
            props = json.load(f)

    por_video = []
    itens_resposta = []          # ★ o contrato acordado, um por cena
    for nb in nomes_base:
        no = tree_meta.get(nb)
        dados = props.get(nb, {})
        p0 = (dados.get("proposals") or [{}])[0]
        legenda = p0.get("cap")

        # --- o formato acordado, idêntico ao do POST /jobs --- #
        item = {
            "scene_id": nb,
            "scene_caption_en": legenda,
            "keywords_en": [
                k.model_dump() for k in ranquear_keywords(
                    _keys_da_cena(props, no, nb), legenda or "",
                    modelos.sentence_transformer)
            ],
            "model_name": MODEL_NAME_PADRAO,
            "model_version": MODEL_VERSION_PADRAO,
            "status": "success" if legenda else "error",
        }
        if not legenda:
            item["erro"] = ("o pipeline não produziu legenda; verifique se o "
                            "vídeo foi decodificado (duração < 1s = zero frames)")
        itens_resposta.append(item)

        # --- e o diagnóstico do teste, que a rota de produção não traz --- #
        por_video.append({
            "video": nb,
            "processado": no is not None,
            "estava_em_cache": nb in em_cache,
            "duracao": (no or {}).get("duration"),
            "legenda": legenda,
            "n_raw": p0.get("n_raw"),
            "n_distinct": p0.get("n_distinct"),
            "rank_by": p0.get("rank_by"),
            "warning": p0.get("warning"),
        })

    processados = sum(1 for v in por_video if v["processado"])
    ausentes = [v["video"] for v in por_video if not v["processado"]]

    return {
        "ok": True,
        # ★ o contrato de saída: uma entrada por cena, igual à do POST /jobs
        "items": itens_resposta,
        "diretorio": diretorio,
        "seconds": round(time.perf_counter() - t_inicio, 2),
        "summary": {
            "encontrados_no_diretorio": total_encontrado,
            "selecionados": len(nomes_base),
            "no_tree_meta": processados,
            "estavam_em_cache": len(em_cache),
            "eram_novos": len(novos),
            "ausentes_no_resultado": ausentes,
        },
        "cache": {
            "arquivo": caminho_cache,
            "limpo": force,
            "apagados": apagados,
        },
        "passos": passos,
        "exp_dir": exp_dir,
        "proposals_json": caminho_props,
        "tree_json": os.path.join(exp_dir, cfg.tree_file) if exp_dir else None,
        "por_video": por_video,
        "modelos_reaproveitados": {
            "gpu_alocado_mb_antes": gpu_antes.get("alocado_mb"),
            "gpu_alocado_mb_depois": gpu_depois.get("alocado_mb"),
            "nota": ("valores próximos e > 0 = os modelos continuam residentes; "
                     "o build NÃO recarregou nada, mesmo com o lote inteiro"),
        },
    }


# --------------------------------------------------------------------------- #
# Execução direta
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    # ⚠️ SEM este bloco, `python app.py` não sobe servidor nenhum: o módulo é
    # importado, o objeto `app` é criado, e o processo termina. O lifespan
    # NUNCA roda — e portanto os modelos nunca são carregados.
    #
    # Em produção quem sobe é o supervisord chamando o uvicorn direto:
    #     uvicorn app:app --host 0.0.0.0 --port 8000
    # Este bloco existe para desenvolvimento e diagnóstico.
    import uvicorn

    uvicorn.run(
        "app:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        # reload=False de propósito: com reload, o uvicorn cria um processo
        # filho e recarrega o app a cada mudança de arquivo — os modelos seriam
        # recarregados junto, o que anula o estado permanente.
        reload=False,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )
