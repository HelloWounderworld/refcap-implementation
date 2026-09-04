"""Serviço FastAPI do RefCap — ciclo de vida e registro das rotas.

    supervisord -> uvicorn -> FastAPI
                              |
                              +-- startup: carrega os 4 modelos UMA vez
                              |            (estado permanente na GPU)
                              |
                              +-- POST /caption              uma cena
                              +-- POST /caption/batch        lote
                              +-- GET  /caption/{program_id} lê o persistido
                              +-- GET  /health               status
                              +-- GET  /diagnostics/*        pipeline + diagnóstico
                              |
                              +-- shutdown: libera os modelos

ORGANIZAÇÃO
    app.py          este arquivo: ciclo de vida e registro
    estado.py       modelos, fila e config — o que as rotas compartilham
    contratos.py    os modelos Pydantic e os códigos de erro
    pipeline.py     o processamento, da requisição à resposta
    persistencia.py o histórico durável e a fusão do proposals
    rotas/          um router por área

    As rotas importam de `estado.py`, nunca deste arquivo — é isso que evita
    o import circular.

RODAR EM DESENVOLVIMENTO
    uvicorn app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from estado import ConfigServico, modelos
from ponte_refcap import RAIZ_REFCAP, preparar_sys_path
from rotas import caption, diagnostics, health

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
log = logging.getLogger("refcap.api")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    """Startup e shutdown.

    ★ É AQUI que o carregamento acontece — UMA vez, quando o supervisord sobe
    o processo. A partir daí os modelos ficam residentes e cada requisição os
    usa sem recarregar.
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
        # Modo de desenvolvimento: sobe sem GPU/modelos para testar rotas.
        log.warning("REFCAP_CARREGAR_MODELOS=0 — subindo SEM os modelos")

    yield

    log.info("encerrando serviço")
    modelos.liberar()


app = FastAPI(
    title="RefCap Caption API",
    description=(
        "Legendagem de cenas com os modelos do RefCap residentes em memória."
    ),
    version="1.0.0",
    lifespan=ciclo_de_vida,
)

app.include_router(health.router)
app.include_router(caption.router)
app.include_router(diagnostics.router)


if __name__ == "__main__":
    # ⚠️ SEM este bloco, `python app.py` não sobe servidor nenhum: o módulo é
    # importado, o objeto `app` é criado, e o processo termina. O lifespan
    # NUNCA roda — e portanto os modelos nunca são carregados.
    #
    # Em produção quem sobe é o supervisord chamando o uvicorn direto:
    #     uvicorn app:app --host 0.0.0.0 --port 8000
    import uvicorn

    uvicorn.run(
        "app:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        # reload=False de propósito: com reload, o uvicorn recria o processo a
        # cada mudança de arquivo — os modelos seriam recarregados junto, o que
        # anula o estado permanente.
        reload=False,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )
