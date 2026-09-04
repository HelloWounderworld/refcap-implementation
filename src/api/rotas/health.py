"""GET /health — estado do serviço e dos modelos residentes."""
from __future__ import annotations

from fastapi import APIRouter

from estado import modelos, registro
from ponte_refcap import RAIZ_REFCAP

router = APIRouter(tags=["health"])


@router.get("/health", summary="Service and model status")
async def health() -> dict:
    """Estado do serviço e dos modelos residentes.

    ★ O campo que responde "os modelos estão MESMO na GPU?" é
      `models.gpu.allocated_mb`. `models.ready` só diz que os objetos existem;
      se `allocated_mb` for 0 com `ready: true`, eles estão na CPU.
    """
    return {
        "status": "ok",
        "service": "caption-api",
        "refcap_root": str(RAIZ_REFCAP),
        "models": modelos.diagnostico(),
        "queued_jobs": registro.quantos_na_fila(),
    }
