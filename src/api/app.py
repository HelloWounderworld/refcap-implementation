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

from fastapi import BackgroundTasks, FastAPI, HTTPException
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
