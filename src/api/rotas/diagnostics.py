"""GET /diagnostics/* — o MESMO pipeline da produção, com diagnóstico junto.

★ O QUE MUDOU (correção)
    A versão anterior tinha um contrato PRÓPRIO — recebia `video` como o NOME
    de um arquivo dentro do `video_root` do cfg.py. Isso vinha do desenho
    antigo, de antes do contrato `scene_video_path`, e dava 404 sempre que o
    vídeo não estivesse naquele diretório configurado.

    Agora estas rotas recebem o MESMO tipo de caminho da produção, e derivam
    o resto da estrutura:

        scene_video_path = <prefixo>/{program_id}/{video_id}/{scene_id}.mp4
                                      └─ derivado ─┘ └ derivado ┘ └ derivado ┘

★ E A DEDUPLICAÇÃO
    Elas montam um `CaptionRequest` e chamam `pipeline.processar_pedido` — a
    MESMA função da produção. O que muda é só o que devolvem:

        produção    -> o contrato
        diagnóstico -> o contrato MAIS gpu antes/depois, passos, exp_dir

    A versão anterior repetia ~500 linhas da lógica do pipeline. Qualquer
    correção precisava ser feita em dois lugares — e o diagnóstico ficou para
    trás justamente por isso.

★ O `collection` PRÓPRIO
    Por padrão usam `COLLECTION_DIAGNOSTICO` ("diagnostics"), nunca o
    program_id derivado. Assim você testa sem contaminar cache, annos e
    resultados de dados reais. Para diagnosticar sobre os dados REAIS, passe
    `usar_program_id=true`.
"""
from __future__ import annotations

import logging
import os
import pathlib

from fastapi import APIRouter, HTTPException

from carregador import ModelosResidentes
from contratos import CaptionRequest, ErrorCode, SceneItem
from estado import COLLECTION_DIAGNOSTICO, ConfigServico, modelos
from ponte_refcap import montar_cfg
import pipeline

log = logging.getLogger("refcap.api.diagnostics")

router = APIRouter(tags=["diagnostics"])

EXTENSOES = (".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v")


# --------------------------------------------------------------------------- #
def derivar_do_caminho(caminho: str) -> dict:
    """Extrai program_id, video_id e scene_id de um caminho de cena.

        /qualquer/prefixo/{program_id}/{video_id}/{scene_id}.mp4
                            └─ [-3] ─┘  └─ [-2] ─┘  └─ stem ─┘

    Com menos níveis, o que faltar volta como None — e quem chama decide.
    """
    p = pathlib.Path(caminho)
    partes = p.parts
    return {
        "scene_id": p.stem,
        "video_id": partes[-2] if len(partes) >= 2 else None,
        "program_id": partes[-3] if len(partes) >= 3 else None,
    }


def _cenas_do_diretorio(diretorio: str, extensoes: str, limite: int) -> list[dict]:
    """Lista as cenas de um diretório, derivando os ids de cada caminho."""
    sufixos = tuple(e.strip().lower() for e in extensoes.split(",") if e.strip())
    d = pathlib.Path(diretorio)
    arquivos = sorted(
        f for f in d.iterdir()
        if f.is_file() and f.suffix.lower() in sufixos
    )
    if limite > 0:
        arquivos = arquivos[:limite]
    return [{**derivar_do_caminho(str(f)), "scene_video_path": str(f)}
            for f in arquivos]


def _executar_com_diagnostico(itens: list[dict], collection: str | None,
                              proposal_generator: str, force: bool) -> dict:
    """O núcleo: monta o pedido, chama o pipeline, e junta o diagnóstico.

    É AQUI que a deduplicação acontece — `pipeline.processar_pedido` é a mesma
    função que o POST /caption usa.
    """
    if not modelos.pronto:
        raise HTTPException(503, {
            "error_code": ErrorCode.INTERNAL_ERROR,
            "message": "models not loaded",
            "hint": "start the service without REFCAP_CARREGAR_MODELOS=0",
        })

    # Se pedimos um collection próprio, sobrescrevemos o program_id derivado:
    # é ele que vira o collection no pipeline.
    if collection:
        itens = [{**i, "program_id": collection} for i in itens]

    pedido = CaptionRequest(
        items=[SceneItem(**i) for i in itens],
        proposal_generator=proposal_generator,
        force=force,
    )

    gpu_antes = ModelosResidentes.estado_da_gpu()
    resultado = pipeline.processar_pedido(
        pedido=pedido,
        job_id="diagnostics",
        montar_cfg=montar_cfg,
        modelos=modelos,
        config_servico=ConfigServico,
    )
    gpu_depois = ModelosResidentes.estado_da_gpu()

    return {
        **resultado,
        "diagnostics": {
            "collection_usado": collection or "(o program_id derivado)",
            "cenas_enviadas": [
                {"scene_id": i["scene_id"], "video_id": i.get("video_id"),
                 "program_id": i.get("program_id"),
                 "path": i["scene_video_path"]}
                for i in itens
            ],
            "modelos_reaproveitados": {
                "gpu_allocated_mb_antes": gpu_antes.get("allocated_mb"),
                "gpu_allocated_mb_depois": gpu_depois.get("allocated_mb"),
                "nota": ("valores próximos e > 0 = os modelos continuam "
                         "residentes; o build NÃO recarregou nada"),
            },
        },
    }


# --------------------------------------------------------------------------- #
@router.get("/diagnostics/caption",
            summary="[DIAGNOSTICS] pipeline on ONE scene, by path")
def diagnostics_caption(
    scene_video_path: str,
    usar_program_id: bool = False,
    proposal_generator: str = "whole",
    force: bool = False,
) -> dict:
    """Roda o pipeline completo numa cena, devolvendo o contrato + diagnóstico.

    PARÂMETROS
        scene_video_path  ★ o caminho COMPLETO do .mp4 — o mesmo que você
                          manda no POST /caption. `program_id`, `video_id` e
                          `scene_id` são derivados dele.
        usar_program_id   por padrão usa o collection "diagnostics", isolado.
                          Com `true`, usa o program_id derivado — ou seja,
                          mexe nos dados REAIS.
        proposal_generator  "whole" (o seu) ou "qm" (o original)
        force             reprocessa, limpando o cache daquela cena

    EXEMPLO
        GET /diagnostics/caption?scene_video_path=/dados/prog1/vidA/cena_01.mp4

    ⚠️ SÍNCRONA de propósito: você vê o resultado direto no navegador.
    """
    if not os.path.isfile(scene_video_path):
        # ★ Aqui checamos ARQUIVO porque o parâmetro é o caminho da cena.
        # A versão anterior checava um arquivo dentro do video_root
        # CONFIGURADO — o que dava 404 para qualquer cena fora dali.
        pai = os.path.dirname(scene_video_path)
        vizinhos = sorted(os.listdir(pai))[:20] if os.path.isdir(pai) else []
        raise HTTPException(404, {
            "error_code": ErrorCode.FILE_NOT_FOUND,
            "message": f"arquivo não encontrado: {scene_video_path}",
            "diretorio_pai": pai,
            "existe_o_diretorio": os.path.isdir(pai),
            "primeiros_arquivos_la": vizinhos,
        })

    item = {**derivar_do_caminho(scene_video_path),
            "scene_video_path": scene_video_path}
    collection = None if usar_program_id else COLLECTION_DIAGNOSTICO
    return _executar_com_diagnostico([item], collection, proposal_generator, force)


@router.get("/diagnostics/caption-batch",
            summary="[DIAGNOSTICS] pipeline on a DIRECTORY of scenes")
def diagnostics_caption_batch(
    diretorio: str,
    usar_program_id: bool = False,
    proposal_generator: str = "whole",
    force: bool = False,
    limite: int = 0,
    extensoes: str = ".mp4",
) -> dict:
    """Roda o pipeline em TODAS as cenas de um diretório.

    PARÂMETROS
        diretorio        ★ o caminho da pasta com os .mp4
        usar_program_id  ver acima
        limite           processa no máximo N cenas (0 = todas)
        extensoes        filtro, separado por vírgula

    ⚠️ SÍNCRONA. Um diretório grande estoura o timeout do HTTP — use `limite`
       para testar antes, e o POST /caption/batch para produção.
    """
    if not os.path.isdir(diretorio):
        # ★ Aqui checamos DIRETÓRIO, porque o parâmetro é uma pasta.
        raise HTTPException(404, {
            "error_code": ErrorCode.FILE_NOT_FOUND,
            "message": f"diretório não encontrado: {diretorio}",
        })

    itens = _cenas_do_diretorio(diretorio, extensoes, limite)
    if not itens:
        raise HTTPException(404, {
            "error_code": ErrorCode.SCENE_NOT_FOUND,
            "message": f"nenhum arquivo {extensoes} em {diretorio}",
            "primeiros_arquivos_la": sorted(os.listdir(diretorio))[:20],
        })

    collection = None if usar_program_id else COLLECTION_DIAGNOSTICO
    return _executar_com_diagnostico(itens, collection, proposal_generator, force)
