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
from pydantic import BaseModel, Field

from carregador import ModelosResidentes
from jobs import EstadoJob, Job, RegistroDeJobs
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
class PedidoDeJob(BaseModel):
    """O que o POST recebe.

    ⚠️ ESTE CONTRATO É PROVISÓRIO. Você ainda vai definir o formato real da
    requisição. Os campos abaixo são o mínimo para o esqueleto funcionar;
    acrescente o que precisar sem mexer no resto do serviço.
    """
    videos: list[str] = Field(
        default_factory=list,
        description="Nomes dos arquivos de vídeo a processar.",
    )
    callback_url: str | None = Field(
        default=None,
        description="Se informado, o serviço faz POST aqui quando o job terminar.",
    )
    parametros: dict = Field(
        default_factory=dict,
        description="Sobrescritas do cfg do RefCap (ex.: proposal_generator).",
    )


class RespostaDeJob(BaseModel):
    job_id: str
    estado: str
    consultar_em: str


# --------------------------------------------------------------------------- #
# ★ O ponto onde o SEU pipeline entra
# --------------------------------------------------------------------------- #
def processar_job(job: Job) -> dict:
    """Executa um job. Roda numa thread, com a fila garantindo um por vez.

    Os modelos JÁ ESTÃO CARREGADOS aqui — `modelos.como_dict()` devolve o
    dicionário no formato que o `build()` do RefCap espera.
    """
    pedido = job.entrada

    # ################################################################### #
    # ### AQUI ENTRA O SEU PIPELINE                                     ###
    # ###                                                               ###
    # ### 1. Tratar o que veio na requisição                            ###
    # ###    (validar vídeos, mover uploads para video_root, etc.)      ###
    # ###                                                               ###
    # ### 2. Conferir / atualizar as listas de annos                    ###
    # ###    O anno_path é  annos/{collection}/{anno_file}              ###
    # ###    (constructpipe/base.py:44)                                 ###
    # ###                                                               ###
    # ### 3. Decidir collection / construct_name                        ###
    # ###    -> é aqui que entra a decisão de isolamento por job        ###
    # ###       que ficou para depois                                   ###
    # ################################################################### #

    # 4. Montar o cfg (caminhos já absolutos, sem ler sys.argv)
    cfg = montar_cfg(
        device=ConfigServico.device,
        caption_model=ConfigServico.caption_model,
        blip_itm_model=ConfigServico.blip_itm_model,
        sentence_transformer=ConfigServico.sentence_transformer,
        caption_generator="blip",
        construct_name=job.id,          # provisório — ver decisão de isolamento
        **pedido.get("parametros", {}),
    )

    # 5. Chamar o núcleo do RefCap com os modelos JÁ CARREGADOS
    #    `build` é a função extraída de construct.py:main() — o CLI continua
    #    funcionando igual, e aqui pulamos o load_pretrained_models.
    from construct import build  # noqa: PLC0415 — após preparar_sys_path()

    tree_meta = build(cfg, modelos.como_dict())

    return {
        "construct_name": cfg.construct_name,
        "collection": cfg.collection,
        "exp_dir": cfg.exp_dir,
        "videos_no_tree": list(tree_meta.keys()) if tree_meta else [],
        "tree_meta": tree_meta,
    }


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


@app.post("/jobs", response_model=RespostaDeJob, status_code=202,
          summary="Cria um job de processamento")
async def criar_job(pedido: PedidoDeJob, tarefas: BackgroundTasks) -> RespostaDeJob:
    """Devolve 202 + job_id imediatamente; o processamento roda em segundo plano.

    Se `callback_url` for informado, o serviço faz POST lá ao terminar — mas o
    GET /jobs/{id} continua disponível para reconsulta.
    """
    if ConfigServico.carregar_no_startup and not modelos.pronto:
        raise HTTPException(503, "modelos ainda não carregados")

    job = registro.criar(entrada=pedido.model_dump(), callback_url=pedido.callback_url)
    tarefas.add_task(registro.executar, job, processar_job)
    return RespostaDeJob(
        job_id=job.id,
        estado=job.estado.value,
        consultar_em=f"/jobs/{job.id}",
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
    limpar_cache: bool = True,
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
        limpar_cache  apaga os caches deste `collection` antes de rodar, para
                      forçar o processamento de verdade

    ⚠️ É SÍNCRONA de propósito: você vê o resultado direto no navegador.
       Para produção use POST /jobs, que é assíncrono e serializado.

    EXEMPLO
        GET /teste/construct?video=cena_001.mp4
    """
    import json
    import shutil
    import time

    if ConfigServico.carregar_no_startup and not modelos.pronto:
        raise HTTPException(503, "modelos ainda não carregados")

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
    if limpar_cache:
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
    caminho_props = os.path.join(cfg.exp_dir, cfg.proposals_file)
    if os.path.isfile(caminho_props):
        with open(caminho_props, encoding="utf-8") as f:
            props = json.load(f)
        dados = props.get(nome_base, {})
        if dados.get("proposals"):
            p0 = dados["proposals"][0]
            ranking = {
                "rank_by": p0.get("rank_by"),
                "n_raw": p0.get("n_raw"),
                "n_distinct": p0.get("n_distinct"),
                "ranking": p0.get("ranking"),
                "warning": p0.get("warning"),
            }

    return {
        "ok": True,
        "video": video,
        "segundos": round(time.perf_counter() - t_inicio, 2),
        "passos": passos,
        "exp_dir": cfg.exp_dir,
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
