"""Contratos da API: os modelos Pydantic e os códigos de erro.

Separado do pipeline de propósito: quem consome a API precisa entender ESTE
arquivo, e mais nada. As duas formas de requisição (cena única e lote) são
normalizadas numa lista só pelo `como_itens()`, de modo que o processamento
não tem dois caminhos para manter em sincronia.
"""
from __future__ import annotations

import os

from pydantic import BaseModel, Field

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
