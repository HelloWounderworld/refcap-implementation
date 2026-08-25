#!/usr/bin/env python3
"""
diagnostico_supervisord.py — investiga por que o serviço não fica permanente.

Complementa o `diagnostico_gpu.py`. Enquanto aquele olha para o torch e a GPU,
este olha para o SUPERVISORD: o processo está mesmo vivo, ou está reiniciando
em loop?

USO
    python diagnostico_supervisord.py --logs /var/log/refcap-api
    python diagnostico_supervisord.py --logs ./logs --programa refcap-api

A ASSINATURA DO LOOP DE REINÍCIO
--------------------------------
Quando o processo carrega e morre, o supervisord reinicia. No stdout você vê a
MESMA sequência de carregamento repetida, com PIDs DIFERENTES:

    [PID 493] carregando cap_gen_model ...
    [PID 494] carregando cap_gen_model ...      <- PID diferente!
    [PID 497] carregando cap_gen_model ...

E o `supervisorctl status` mostra BACKOFF ou FATAL em vez de RUNNING.
Foi assim que reproduzi o cenário: 3 tentativas e depois
"gave up: entered FATAL state, too many start retries too quickly".

O QUE OLHAR, EM ORDEM
---------------------
    1. supervisorctl status        -> RUNNING com uptime crescente?
    2. stderr do programa          -> a CAUSA real da morte
    3. log do supervisord          -> spawned / exited / gave up
    4. contagem de PIDs no stdout  -> quantas vezes carregou?
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
from collections import Counter

LARG = 74


def titulo(t: str) -> None:
    print("\n" + "=" * LARG)
    print(f" {t}")
    print("=" * LARG)


# --------------------------------------------------------------------------- #
def bloco_status(programa: str, conf: str | None) -> None:
    titulo("1. supervisorctl status")
    cmd = ["supervisorctl"]
    if conf:
        cmd += ["-c", conf]
    cmd += ["status", programa]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        saida = (r.stdout + r.stderr).strip()
        print(f"  {saida or '(sem saída)'}")
    except FileNotFoundError:
        print("  supervisorctl não encontrado no PATH — rode manualmente:")
        print(f"      supervisorctl status {programa}")
        return
    except Exception as exc:  # noqa: BLE001
        print(f"  não consegui executar: {type(exc).__name__}: {exc}")
        return

    print("""
  COMO LER:
    RUNNING  pid 1234, uptime 0:15:32   -> ✓ vivo há 15 min; se o uptime CRESCE
                                            entre duas consultas, está estável
    RUNNING  pid 5678, uptime 0:00:03   -> ⚠️ acabou de subir; consulte de novo
                                            em 30s: se o PID MUDAR, é loop
    BACKOFF  Exited too quickly          -> ✗ morrendo logo após subir
    FATAL    too many start retries      -> ✗ desistiu; veja o stderr
    STOPPED                              -> não está rodando
""")


def _pids_no_log(texto: str) -> list[str]:
    """Extrai PIDs de linhas do uvicorn/supervisord."""
    padroes = [
        r"Started server process \[(\d+)\]",       # uvicorn
        r"spawned: '[^']+' with pid (\d+)",        # supervisord
        r"\[PID (\d+)\]",                          # formato próprio
    ]
    achados: list[str] = []
    for p in padroes:
        achados += re.findall(p, texto)
    return achados


def bloco_logs(pasta: pathlib.Path, programa: str) -> None:
    titulo("2. Os logs do programa")
    if not pasta.is_dir():
        print(f"  ✗ pasta não encontrada: {pasta}")
        return

    arquivos = sorted(p for p in pasta.iterdir() if p.is_file() and p.suffix in (".log", ""))
    if not arquivos:
        print(f"  ✗ nenhum arquivo de log em {pasta}")
        return

    for arq in arquivos:
        try:
            texto = arq.read_text(errors="replace")
        except Exception as exc:  # noqa: BLE001
            print(f"  {arq.name}: não consegui ler ({exc})")
            continue

        linhas = texto.splitlines()
        print(f"\n  --- {arq.name}  ({len(linhas)} linhas) ---")

        pids = _pids_no_log(texto)
        if pids:
            contagem = Counter(pids)
            print(f"      PIDs encontrados: {len(contagem)} distinto(s)")
            if len(contagem) > 1:
                print(f"      ⚠️ MÚLTIPLOS PIDs — assinatura de LOOP DE REINÍCIO")
                for pid, n in list(contagem.items())[:6]:
                    print(f"          PID {pid}: {n} ocorrência(s)")
            else:
                print(f"      ✓ um PID só ({list(contagem)[0]}) — sem reinício")

        # sinais de carregamento repetido
        marcas = [l for l in linhas if "carregando" in l.lower() or "carregado em" in l.lower()]
        if marcas:
            print(f"      linhas de carregamento: {len(marcas)}")
            if len(marcas) > 4:
                print("      ⚠️ carregou VÁRIAS vezes — reforça o loop")

        # erros
        erros = [l for l in linhas
                 if re.search(r"error|erro|Traceback|Exception|CUDA|out of memory",
                              l, re.IGNORECASE)]
        if erros:
            print(f"      ⚠️ {len(erros)} linha(s) com sinal de erro. Últimas:")
            for l in erros[-5:]:
                print(f"          {l.strip()[:110]}")
        elif "err" in arq.name:
            print("      ✓ sem erros registrados")


def bloco_log_supervisord(caminho: pathlib.Path | None) -> None:
    titulo("3. O log do próprio supervisord")
    candidatos = [caminho] if caminho else [
        pathlib.Path("/var/log/supervisor/supervisord.log"),
        pathlib.Path("/tmp/supervisord.log"),
    ]
    for c in candidatos:
        if c and c.is_file():
            texto = c.read_text(errors="replace")
            eventos = [l for l in texto.splitlines()
                       if re.search(r"spawned|exited|gave up|backoff|FATAL", l)]
            print(f"  {c}  ({len(eventos)} evento(s) relevante(s))")
            for l in eventos[-12:]:
                print(f"      {l.strip()[:110]}")
            spawns = len(re.findall(r"spawned:", texto))
            exits = len(re.findall(r"exited:", texto))
            print(f"\n      spawned: {spawns}   exited: {exits}")
            if exits >= 2:
                print("      ⚠️ o processo saiu mais de uma vez — LOOP confirmado")
            if "gave up" in texto:
                print("      ✗ o supervisord DESISTIU (FATAL). Veja o stderr acima.")
            return
    print("  não localizei o log do supervisord. Procure por:")
    print("      grep -E 'spawned|exited|gave up' /var/log/supervisor/supervisord.log")


def bloco_conclusao() -> None:
    titulo("O QUE FAZER COM O RESULTADO")
    print("""
  SE HÁ LOOP (múltiplos PIDs / vários "exited")
      A causa está no STDERR do programa. As mais comuns:
        - CUDA out of memory            -> outro processo já ocupa a GPU
        - modelo não encontrado         -> nome/caminho do modelo errado
        - ModuleNotFoundError           -> venv errado (use caminho ABSOLUTO
                                           do uvicorn no `command=`)
        - Permission denied             -> `user=` sem acesso a GPU/HF_HOME

  SE ESTÁ RUNNING COM UPTIME CRESCENTE
      O serviço ESTÁ permanente. Se mesmo assim o nvidia-smi não mostra nada:
        curl -s localhost:8000/health | python -m json.tool
      Olhe `modelos.gpu.alocado_mb`:
        > 0   -> está na GPU; confira se o nvidia-smi olha a MESMA GPU
                 (CUDA_VISIBLE_DEVICES remapeia os índices)
        = 0   -> os modelos foram para a CPU; veja REFCAP_DEVICE

  SE ESTÁ STOPPED
      supervisorctl start refcap-api
      e acompanhe:  supervisorctl tail -f refcap-api stderr
""")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs", default="/var/log/refcap-api",
                    help="pasta com stdout.log e stderr.log do programa")
    ap.add_argument("--programa", default="refcap-api")
    ap.add_argument("--conf", default=None, help="caminho do supervisord.conf")
    ap.add_argument("--log-supervisord", default=None)
    args = ap.parse_args()

    print("=" * LARG)
    print(" DIAGNÓSTICO — supervisord: o serviço está mesmo permanente?")
    print("=" * LARG)

    bloco_status(args.programa, args.conf)
    bloco_logs(pathlib.Path(args.logs), args.programa)
    bloco_log_supervisord(
        pathlib.Path(args.log_supervisord) if args.log_supervisord else None
    )
    bloco_conclusao()
    return 0


if __name__ == "__main__":
    sys.exit(main())
