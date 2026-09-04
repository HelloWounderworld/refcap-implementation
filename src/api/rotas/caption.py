"""POST /caption, POST /caption/batch e GET /caption/{program_id}.

As duas rotas de POST compartilham o corpo (`_executar`): existem separadas
para deixar a intenção explícita no contrato, mas o `como_itens()` já
normaliza cena única e lote numa lista só — não há dois caminhos a manter.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import JSONResponse

import persistencia
import pipeline
from contratos import CaptionRequest, ErrorCode
from estado import LIMIAR_ASSINCRONO, ConfigServico, modelos, registro
from jobs import EstadoJob, Job
from ponte_refcap import montar_cfg

log = logging.getLogger("refcap.api.caption")

router = APIRouter(tags=["caption"])


def processar_job(job: Job) -> dict:
    """Executa um job: pipeline + captioning + resposta.

    O pipeline (annos, agrupamento por diretório, collection, cache) e a
    transformação da saída vivem em `pipeline.py` — aqui só ligamos as peças
    do serviço.

    Os modelos JÁ ESTÃO CARREGADOS: `modelos.como_dict()` devolve o dicionário
    no formato que o `build()` do RefCap espera, e ele NÃO recarrega nada.
    """
    pedido = CaptionRequest(**job.entrada)
    return pipeline.processar_pedido(
        pedido=pedido,
        job_id=job.id,
        montar_cfg=montar_cfg,
        modelos=modelos,
        config_servico=ConfigServico,
    )


def _programa_do_pedido(pedido: CaptionRequest) -> str | None:
    """O `program_id` da requisição — governa collection, caches e response."""
    for item in pedido.como_itens():
        if item.program_id:
            return item.program_id
    return None


async def _executar(pedido: CaptionRequest, tarefas: BackgroundTasks):
    """Corpo comum de POST /caption e POST /caption/batch.

    As duas rotas existem para deixar a intenção explícita no contrato, mas o
    processamento é o mesmo: `como_itens()` normaliza cena única e lote numa
    lista, e daí para frente não há dois caminhos.
    """
    if not modelos.pronto:
        raise HTTPException(503, {
            "error_code": ErrorCode.INTERNAL_ERROR,
            "message": "models not loaded",
            "hint": ("start the service without REFCAP_CARREGAR_MODELOS=0 "
                     "so the models load at startup"),
        })

    itens = pedido.como_itens()
    if not itens:
        raise HTTPException(400, {
            "error_code": ErrorCode.INVALID_REQUEST,
            "message": ("empty request: provide `scene_id` + `scene_video_path`, "
                        "or `items`"),
        })

    program_id = _programa_do_pedido(pedido)
    job = registro.criar(entrada=pedido.model_dump(), callback_url=pedido.callback_url)

    # --- assíncrono: automático acima do limiar, ou forçado --------------- #
    if len(itens) > LIMIAR_ASSINCRONO or pedido.assincrono:
        tarefas.add_task(registro.executar, job, processar_job)
        return JSONResponse(status_code=202, content={
            "state": "accepted",
            "program_id": program_id,
            "scenes": [i.scene_id for i in itens],
            "total": len(itens),
            "check_at": f"/caption/{program_id}" if program_id else None,
            "reason": ("above the synchronous threshold"
                       if len(itens) > LIMIAR_ASSINCRONO else "requested"),
        })

    # --- síncrono: aguarda e devolve o resultado -------------------------- #
    # `executar` roda a tarefa em asyncio.to_thread, sob a trava da fila —
    # aguardar aqui NÃO bloqueia o loop: /health e GET /caption continuam
    # respondendo durante o processamento.
    await registro.executar(job, processar_job)

    resultado = job.resultado or {}
    corpo = {
        "state": job.estado.value,
        "program_id": program_id,
        **(resultado if isinstance(resultado, dict) else {"result": resultado}),
    }
    if job.erro:
        corpo["error_code"] = ErrorCode.INTERNAL_ERROR
        corpo["message"] = job.erro
    return JSONResponse(
        status_code=200 if job.estado == EstadoJob.CONCLUIDO else 500,
        content=corpo,
    )


@router.post("/caption", summary="Caption a single scene")
async def caption(pedido: CaptionRequest, tarefas: BackgroundTasks):
    """Legenda UMA cena e devolve o resultado.

        {"scene_id": "...", "video_id": "...", "program_id": "...",
         "scene_video_path": "/path/{program_id}/{video_id}/{scene_id}.mp4"}

    Devolve o contrato com `scene_caption_en`, `keywords_en` e `status`.
    O resultado também fica persistido — consulte por GET /caption/{program_id}.
    """
    return await _executar(pedido, tarefas)


@router.post("/caption/batch", summary="Caption a batch of scenes")
async def caption_batch(pedido: CaptionRequest, tarefas: BackgroundTasks):
    """Legenda VÁRIAS cenas.

        {"items": [ {scene_id, video_id, program_id, scene_video_path}, ... ]}

    Cenas de `video_id` diferentes ficam em diretórios diferentes — a API
    agrupa por diretório e roda um `build()` por grupo.

    ★ Acima de LIMIAR_ASSINCRONO cenas, devolve 202 e processa em segundo
      plano; nada se perde, o resultado fica persistido.
    """
    return await _executar(pedido, tarefas)


@router.get("/caption/{program_id}", summary="Read persisted captions of a program")
async def caption_do_programa(
    program_id: str,
    scene_id: list[str] | None = Query(
        default=None,
        description="Filtra por uma ou várias cenas. Omitido, devolve todas.",
    ),
) -> dict:
    """Lê o que foi persistido, sem reprocessar nada.

        GET /caption/prog1                              todas
        GET /caption/prog1?scene_id=a                   uma
        GET /caption/prog1?scene_id=a&scene_id=b        várias

    Programa nunca processado devolve 200 com lista vazia — não 404. Assim o
    cliente trata um caso só, em vez de distinguir "não existe" de "vazio".
    """
    cfg = montar_cfg()
    itens = persistencia.ler_respostas(cfg.res_dir, program_id, scene_id)
    ok = sum(1 for i in itens if i.get("status") == "success")
    return {
        "program_id": program_id,
        "items": itens,
        "summary": {"total": len(itens), "ok": ok, "errors": len(itens) - ok},
    }
