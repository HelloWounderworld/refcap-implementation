"""Registro de jobs assíncronos: fila serializada, estado consultável, webhook.

POR QUE FILA SERIALIZADA (e não vários workers)
------------------------------------------------
Cada worker adicional carrega SEU PRÓPRIO conjunto de modelos na GPU — dois
workers com BLIP-large são dois BLIP-large residentes. E inferência simultânea
no mesmo modelo não traz ganho real, porque a GPU já serializa internamente.

Portanto: UM processo, UM conjunto de modelos, requisições executadas uma de
cada vez. Se precisar de throughput, o caminho é batch (juntar frames de várias
requisições numa chamada), não mais processos.

JOB_ID + GET E WEBHOOK — os dois
--------------------------------
    job_id + GET : simples, funciona com qualquer cliente, permite RECONSULTAR
                   um resultado e diagnosticar um job que falhou.
    webhook      : evita polling quando o cliente é outro sistema.

Um não substitui o outro: o GET continua indispensável mesmo com webhook, para
reconsulta e para quando a entrega do callback falhar.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

log = logging.getLogger(__name__)


class EstadoJob(str, Enum):
    NA_FILA = "na_fila"
    EXECUTANDO = "executando"
    CONCLUIDO = "concluido"
    FALHOU = "falhou"


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    estado: EstadoJob = EstadoJob.NA_FILA
    criado_em: str = field(default_factory=_agora)
    iniciado_em: str | None = None
    terminado_em: str | None = None
    resultado: Any = None
    erro: str | None = None
    callback_url: str | None = None
    callback_entregue: bool | None = None
    entrada: dict = field(default_factory=dict)

    def como_dict(self, incluir_resultado: bool = True) -> dict:
        d = {
            "job_id": self.id,
            "estado": self.estado.value,
            "criado_em": self.criado_em,
            "iniciado_em": self.iniciado_em,
            "terminado_em": self.terminado_em,
            "erro": self.erro,
            "callback_url": self.callback_url,
            "callback_entregue": self.callback_entregue,
            "entrada": self.entrada,
        }
        if incluir_resultado:
            d["resultado"] = self.resultado
        return d


class RegistroDeJobs:
    """Guarda os jobs e executa um de cada vez.

    ⚠️ O armazenamento é EM MEMÓRIA: reiniciar o processo perde o histórico.
    Para persistência, troque `self._jobs` por SQLite/Redis — a interface
    pública deste objeto não muda.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        # Serializa a execução: só um job usa os modelos por vez.
        self._trava = asyncio.Lock()

    # ------------------------------------------------------------------ #
    def criar(self, entrada: dict, callback_url: str | None = None) -> Job:
        job = Job(id=uuid.uuid4().hex, entrada=entrada, callback_url=callback_url)
        self._jobs[job.id] = job
        log.info("job %s criado", job.id)
        return job

    def obter(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def listar(self, limite: int = 50) -> list[dict]:
        jobs = sorted(self._jobs.values(), key=lambda j: j.criado_em, reverse=True)
        return [j.como_dict(incluir_resultado=False) for j in jobs[:limite]]

    def quantos_na_fila(self) -> int:
        return sum(1 for j in self._jobs.values() if j.estado == EstadoJob.NA_FILA)

    # ------------------------------------------------------------------ #
    async def executar(self, job: Job, tarefa: Callable[[Job], Any]) -> None:
        """Executa `tarefa(job)` numa thread, sob a trava.

        `tarefa` é SÍNCRONA e pesada (decodificação de vídeo + inferência). Roda
        em `asyncio.to_thread` para não travar o loop de eventos — assim o
        servidor continua respondendo /health e GET /jobs enquanto processa.
        """
        async with self._trava:                      # <- um job por vez
            job.estado = EstadoJob.EXECUTANDO
            job.iniciado_em = _agora()
            log.info("job %s iniciado", job.id)
            try:
                job.resultado = await asyncio.to_thread(tarefa, job)
                job.estado = EstadoJob.CONCLUIDO
                log.info("job %s concluido", job.id)
            except Exception as exc:  # noqa: BLE001 — a falha vai para o job
                job.estado = EstadoJob.FALHOU
                job.erro = f"{type(exc).__name__}: {exc}"
                log.exception("job %s falhou", job.id)
                job.resultado = {"traceback": traceback.format_exc()}
            finally:
                job.terminado_em = _agora()

        # Fora da trava: a entrega do callback não deve bloquear a fila.
        if job.callback_url:
            await self._entregar_callback(job)

    async def _entregar_callback(self, job: Job) -> None:
        """POST no callback_url com o estado final do job.

        Falha de entrega NÃO derruba o job — fica registrada em
        `callback_entregue=False`, e o cliente ainda pode consultar via GET.
        """
        import httpx  # noqa: PLC0415 — import tardio, só quando há callback

        try:
            async with httpx.AsyncClient(timeout=10.0) as cliente:
                r = await cliente.post(job.callback_url, json=job.como_dict())
                r.raise_for_status()
            job.callback_entregue = True
            log.info("callback do job %s entregue em %s", job.id, job.callback_url)
        except Exception as exc:  # noqa: BLE001
            job.callback_entregue = False
            log.warning(
                "callback do job %s falhou (%s): %s — consulte via GET /jobs/%s",
                job.id, job.callback_url, exc, job.id,
            )
