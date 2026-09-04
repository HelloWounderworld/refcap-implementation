"""Carregamento seletivo dos modelos do RefCap.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
O RefCap tem um único ponto de carregamento — `utils/model_utils.py:load_pretrained_models`
— e ele é tudo-ou-nada: carrega QUATRO modelos, incluindo o GloVe.

O GloVe tem um único consumidor: `pipeline/treebuilder/capTree.py:23`. E o `CapTree`
só é instanciado em `retrieve.py:269`. Como esta API não faz retrieval, carregá-lo
seria pagar o parse de um arquivo de texto grande para nada.

Este módulo carrega os TRÊS modelos que o `construct` precisa, e devolve um
dicionário com o MESMO formato que `load_pretrained_models` — para que o
`build(cfg, pretrained_models)` do RefCap o aceite sem qualquer adaptação.

O QUE CADA MODELO ATENDE (verificado no código do RefCap)
--------------------------------------------------------
    cap_gen_model / cap_gen_processor
        BlipCapGener.py:14-15  -> a legendagem (etapa 1)

    blip_itrtv_model / blip_itrtv_processor
        constructpipe/base.py:50-51  -> features de frame e scores (etapas 2,3,5)
        denoiser/base.py:26-27       -> denoising (etapa 4)
        WholePropGener.py            -> scene_score / self_score (etapa 6)

    sentence_transformer
        WholePropGener.py  -> o sinal de consenso (etapa 6)
        QMPropGener.py:22  -> a matriz de auto-similaridade

    glove_model = None
        NÃO carregado. Só o CapTree o usa, e o CapTree é do retrieve.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class InfoDeCarga:
    """Diagnóstico do carregamento — útil no /health e nos logs."""
    nome: str
    identificador: str
    segundos: float


class ModelosResidentes:
    """Guarda os modelos carregados uma única vez, para toda a vida do processo.

    Uso:
        residentes = ModelosResidentes()
        residentes.carregar(caption_model=..., blip_itm_model=..., ...)
        ...
        build(cfg, residentes.como_dict())
    """

    def __init__(self) -> None:
        self.cap_gen_model = None
        self.cap_gen_processor = None
        self.blip_itrtv_model = None
        self.blip_itrtv_processor = None
        self.sentence_transformer = None
        self.spacy_nlp = None
        self.device: str | None = None
        self.cargas: list[InfoDeCarga] = []

    # ------------------------------------------------------------------ #
    @property
    def pronto(self) -> bool:
        return all([
            self.cap_gen_model is not None,
            self.cap_gen_processor is not None,
            self.blip_itrtv_model is not None,
            self.blip_itrtv_processor is not None,
            self.sentence_transformer is not None,
            self.spacy_nlp is not None,
        ])

    def carregar(
        self,
        *,
        caption_model: str,
        blip_itm_model: str,
        sentence_transformer: str,
        device: str = "cuda",
        spacy_model: str = "en_core_web_sm",
    ) -> None:
        """Carrega os três modelos. Chamado UMA vez, no startup do serviço.

        Os imports ficam aqui dentro (e não no topo do arquivo) por dois motivos:
        1. o módulo pode ser importado para inspeção sem puxar torch;
        2. deixa explícito que o custo pesado acontece nesta chamada.
        """
        # Import tardio: só quando de fato vamos carregar.
        from transformers import (
            BlipForConditionalGeneration,
            BlipForImageTextRetrieval,
            BlipProcessor,
        )
        from sentence_transformers import SentenceTransformer
        import spacy

        self.device = device
        self.cargas = []

        # --- 1. BLIP captioning (a etapa 1) ---------------------------- #
        # Espelha utils/model_utils.py:12-13
        t0 = time.perf_counter()
        log.info("carregando cap_gen_model=%s ...", caption_model)
        self.cap_gen_model = BlipForConditionalGeneration.from_pretrained(
            caption_model
        ).to(device)
        self.cap_gen_processor = BlipProcessor.from_pretrained(caption_model)
        self._registrar("cap_gen", caption_model, t0)

        # --- 2. BLIP-ITM (etapas 2,3,4,5,6) ---------------------------- #
        # Espelha utils/model_utils.py:30-31
        t0 = time.perf_counter()
        log.info("carregando blip_itrtv_model=%s ...", blip_itm_model)
        self.blip_itrtv_model = BlipForImageTextRetrieval.from_pretrained(
            blip_itm_model
        ).to(device)
        self.blip_itrtv_processor = BlipProcessor.from_pretrained(blip_itm_model)
        self._registrar("blip_itm", blip_itm_model, t0)

        # --- 3. sentence-transformer (etapa 6) ------------------------- #
        # Espelha utils/model_utils.py:35
        t0 = time.perf_counter()
        log.info("carregando sentence_transformer=%s ...", sentence_transformer)
        self.sentence_transformer = SentenceTransformer(sentence_transformer).to(device)
        self._registrar("sentence_transformer", sentence_transformer, t0)

        # --- 4. spaCy (etapa 6: extração de keywords) ------------------ #
        # Sem isto, o propgenerator faria spacy.load() a CADA requisição:
        # o __init__ do propgen roda dentro de build(), não no startup.
        t0 = time.perf_counter()
        log.info("carregando spacy=%s ...", spacy_model)
        self.spacy_nlp = spacy.load(spacy_model)
        self._registrar("spacy", spacy_model, t0)

        total = sum(c.segundos for c in self.cargas)
        log.info("modelos residentes prontos em %.1fs (device=%s)", total, device)

    def _registrar(self, nome: str, identificador: str, t0: float) -> None:
        info = InfoDeCarga(nome, identificador, time.perf_counter() - t0)
        self.cargas.append(info)
        log.info("  %s carregado em %.1fs", nome, info.segundos)

    # ------------------------------------------------------------------ #
    def como_dict(self) -> dict:
        """O dicionário no formato EXATO que o RefCap espera.

        As seis chaves são as mesmas de `load_pretrained_models`. O `glove_model`
        vai como None de propósito: nenhum componente do `construct` o consulta
        (só o CapTree, que é do retrieve). Manter a chave presente evita KeyError
        se algum código futuro fizer `models.get("glove_model")`.
        """
        if not self.pronto:
            raise RuntimeError(
                "modelos não carregados — chame carregar() no startup do serviço"
            )
        return {
            "cap_gen_model": self.cap_gen_model,
            "cap_gen_processor": self.cap_gen_processor,
            "blip_itrtv_model": self.blip_itrtv_model,
            "blip_itrtv_processor": self.blip_itrtv_processor,
            "sentence_transformer": self.sentence_transformer,
            # ★ chave EXTRA (não existe em load_pretrained_models). O
            # WholePropGenerator a consulta com .get(); o QMPropGenerator a
            # ignora e carrega o seu próprio. Nenhum componente quebra por ela.
            "spacy_nlp": self.spacy_nlp,
            "glove_model": None,
        }

    def liberar(self) -> None:
        """Solta as referências e limpa o cache da GPU. Chamado no shutdown."""
        self.cap_gen_model = None
        self.cap_gen_processor = None
        self.blip_itrtv_model = None
        self.blip_itrtv_processor = None
        self.sentence_transformer = None
        self.spacy_nlp = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 — no shutdown, não vale derrubar por isto
            pass
        log.info("modelos liberados")

    def diagnostico(self) -> dict:
        """Resumo para o endpoint /health.

        Inclui o estado REAL da GPU — é isto que responde à pergunta "o modelo
        está mesmo residente?". Sem isso, `pronto: true` só diz que os objetos
        existem, não que ocupam memória de GPU.
        """
        return {
            "ready": self.pronto,
            "device": self.device,
            "models": [
                {"name": c.nome, "id": c.identificador,
                 "load_seconds": round(c.segundos, 2)}
                for c in self.cargas
            ],
            "glove_loaded": False,
            "gpu": self.estado_da_gpu(),
        }

    @staticmethod
    def estado_da_gpu() -> dict:
        """Memória de GPU de fato ocupada por ESTE processo.

        `alocado_mb` é o que os tensores deste processo ocupam. Se os modelos
        estiverem residentes na GPU, este número é grande e ESTÁVEL entre
        requisições. Se for 0 com `pronto: true`, os modelos estão na CPU.
        """
        try:
            import torch
        except ImportError:
            return {"available": False, "reason": "torch not installed"}

        if not torch.cuda.is_available():
            return {
                "available": False,
                "reason": "torch.cuda.is_available() == False",
                "hint": "CPU-only torch build, or empty CUDA_VISIBLE_DEVICES",
            }

        try:
            indice = torch.cuda.current_device()
            return {
                "available": True,
                "device_count": torch.cuda.device_count(),
                "current_index": indice,
                "name": torch.cuda.get_device_name(indice),
                # ★ allocated_mb > 0 e ESTÁVEL entre chamadas = modelos
                #   residentes na GPU. Se for 0 com ready:true, estão na CPU.
                "allocated_mb": round(torch.cuda.memory_allocated(indice) / 1024**2, 1),
                "reserved_mb": round(torch.cuda.memory_reserved(indice) / 1024**2, 1),
                "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            }
        except Exception as exc:  # noqa: BLE001 — diagnóstico não pode derrubar
            return {"available": True, "error": f"{type(exc).__name__}: {exc}"}
