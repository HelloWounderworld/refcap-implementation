#!/usr/bin/env python3
"""
diagnostico_gpu.py — descobre por que o modelo não ficou residente na GPU.

USO (no ambiente do serviço, com o .venv ativo):

    # 1. checagem do ambiente, sem carregar nada
    python diagnostico_gpu.py

    # 2. carrega UM modelo de verdade e mede a GPU antes/depois
    python diagnostico_gpu.py --carregar

    # 3. carrega e FICA VIVO, para você olhar o nvidia-smi com calma
    python diagnostico_gpu.py --carregar --manter

O QUE ELE INVESTIGA, EM ORDEM
-----------------------------
    A. O torch enxerga a GPU?
    B. As variáveis de ambiente estão como você espera?
    C. Carregar um modelo de fato ocupa memória de GPU?
    D. A memória PERMANECE ocupada enquanto o processo vive?

AS TRÊS CAUSAS MAIS COMUNS DE "carregou mas não ficou"
------------------------------------------------------
    1. O PROCESSO TERMINOU.
       Um script com `with TestClient(app):` carrega ao ENTRAR e LIBERA ao
       SAIR do bloco. `python app.py` sem bloco __main__ nem sobe servidor.
       O nvidia-smi só mostra memória de processos VIVOS.

    2. O MODELO FOI PARA A CPU.
       Se `device="cpu"` (ou REFCAP_DEVICE=cpu), tudo funciona — mas sem GPU.

    3. VOCÊ ESTÁ OLHANDO A GPU ERRADA.
       Com CUDA_VISIBLE_DEVICES=1, o "device 0" do processo é a GPU FÍSICA 1.
       O nvidia-smi numera pelas físicas.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

LARG = 74


def titulo(txt: str) -> None:
    print("\n" + "=" * LARG)
    print(f" {txt}")
    print("=" * LARG)


def item(rotulo: str, valor, nota: str = "") -> None:
    print(f"  {rotulo:<34} {valor}" + (f"   {nota}" if nota else ""))


# --------------------------------------------------------------------------- #
def bloco_a_torch() -> dict:
    titulo("A. O torch enxerga a GPU?")
    try:
        import torch
    except ImportError:
        item("torch", "NÃO INSTALADO", "<- instale no .venv do serviço")
        return {"ok": False}

    item("torch", torch.__version__)
    item("compilado com CUDA", torch.version.cuda or "NÃO (build CPU-only)")
    disponivel = torch.cuda.is_available()
    item("torch.cuda.is_available()", disponivel,
         "" if disponivel else "<- ★ AQUI ESTÁ O PROBLEMA")

    if not disponivel:
        print("""
  CAUSAS POSSÍVEIS:
    - o torch instalado é o build CPU-only  (pip install torch  sem índice CUDA)
    - CUDA_VISIBLE_DEVICES=""  (string vazia esconde todas as GPUs)
    - driver NVIDIA ausente ou incompatível com a versão do CUDA do torch
""")
        return {"ok": False}

    n = torch.cuda.device_count()
    item("dispositivos visíveis", n)
    for i in range(n):
        props = torch.cuda.get_device_properties(i)
        item(f"  device {i}", f"{props.name}  ({props.total_memory/1024**3:.1f} GB)")
    return {"ok": True, "torch": torch}


def bloco_b_ambiente() -> None:
    titulo("B. As variáveis de ambiente")
    esperadas = [
        ("CUDA_VISIBLE_DEVICES", "quais GPUs o processo enxerga"),
        ("REFCAP_DEVICE", "para onde os modelos vão (cuda/cpu)"),
        ("REFCAP_CARREGAR_MODELOS", "1 carrega no startup; 0 sobe SEM modelos"),
        ("REFCAP_ROOT", "raiz do RefCap (opcional)"),
        ("REFCAP_CAPTION_MODEL", ""),
        ("REFCAP_BLIP_ITM_MODEL", ""),
        ("REFCAP_SENTENCE_TRANSFORMER", ""),
    ]
    for nome, desc in esperadas:
        valor = os.environ.get(nome)
        if valor is None:
            item(nome, "(não definida)", f"<- {desc}" if desc else "")
        else:
            item(nome, repr(valor))

    print()
    cvd = os.environ.get("CUDA_VISIBLE_DEVICES")
    if cvd == "":
        print("  ⚠️ CUDA_VISIBLE_DEVICES está VAZIA — isso ESCONDE todas as GPUs.")
    elif cvd and cvd != "0":
        print(f"  ⚠️ CUDA_VISIBLE_DEVICES={cvd!r}: o 'device 0' deste processo é a")
        print(f"     GPU FÍSICA {cvd.split(',')[0]}. Confira essa linha no nvidia-smi.")

    if os.environ.get("REFCAP_CARREGAR_MODELOS") == "0":
        print("  ⚠️ REFCAP_CARREGAR_MODELOS=0 — o serviço sobe SEM carregar modelos.")
    if os.environ.get("REFCAP_DEVICE") == "cpu":
        print("  ⚠️ REFCAP_DEVICE=cpu — os modelos vão para a CPU, não para a GPU.")


def mb(torch, i: int = 0) -> tuple[float, float]:
    return (
        torch.cuda.memory_allocated(i) / 1024**2,
        torch.cuda.memory_reserved(i) / 1024**2,
    )


def bloco_c_carregar(torch, modelo: str, device: str) -> bool:
    titulo("C. Carregar um modelo ocupa GPU de fato?")
    if device != "cuda":
        item("device pedido", device, "<- não é cuda; nada a medir na GPU")
        return False

    aloc0, res0 = mb(torch)
    item("antes — alocado / reservado", f"{aloc0:.1f} MB / {res0:.1f} MB")

    print(f"\n  carregando {modelo} ...")
    t0 = time.perf_counter()
    try:
        from transformers import BlipForConditionalGeneration

        m = BlipForConditionalGeneration.from_pretrained(modelo).to(device)
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ FALHOU: {type(exc).__name__}: {exc}")
        return False
    dt = time.perf_counter() - t0

    aloc1, res1 = mb(torch)
    item("depois — alocado / reservado", f"{aloc1:.1f} MB / {res1:.1f} MB")
    item("tempo de carga", f"{dt:.1f}s")
    item("delta alocado", f"+{aloc1 - aloc0:.1f} MB")

    if aloc1 - aloc0 < 1:
        print("""
  ✗ A memória NÃO subiu. O modelo não foi para a GPU.
    Confira o device e o CUDA_VISIBLE_DEVICES (bloco B).
""")
        return False

    print(f"""
  ✓ O modelo OCUPA a GPU: +{aloc1 - aloc0:.0f} MB alocados.
    Rode `nvidia-smi` AGORA, em outro terminal, e você deve ver este
    processo (PID {os.getpid()}) na lista.
""")
    globals()["_modelo_vivo"] = m          # mantém a referência viva
    return True


def bloco_d_manter(torch) -> None:
    titulo("D. Mantendo o processo VIVO")
    print(f"""
  PID deste processo: {os.getpid()}

  Em OUTRO terminal, rode:
      nvidia-smi
      nvidia-smi --query-compute-apps=pid,used_memory --format=csv

  Você deve ver o PID {os.getpid()} ocupando memória. Enquanto este processo
  viver, a memória permanece. Ctrl+C encerra e a memória é liberada — é
  exatamente esse o comportamento de "residente".
""")
    try:
        i = 0
        while True:
            time.sleep(5)
            i += 1
            aloc, res = mb(torch)
            print(f"  [{i*5:>4}s] alocado={aloc:8.1f} MB   reservado={res:8.1f} MB")
    except KeyboardInterrupt:
        print("\n  encerrado pelo usuário — a memória será liberada agora.")


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--carregar", action="store_true",
                    help="carrega um modelo de verdade e mede a GPU")
    ap.add_argument("--manter", action="store_true",
                    help="após carregar, fica vivo para você olhar o nvidia-smi")
    ap.add_argument("--modelo",
                    default=os.environ.get("REFCAP_CAPTION_MODEL",
                                           "Salesforce/blip-image-captioning-large"))
    ap.add_argument("--device", default=os.environ.get("REFCAP_DEVICE", "cuda"))
    args = ap.parse_args()

    print("=" * LARG)
    print(" DIAGNÓSTICO — por que o modelo não ficou residente na GPU")
    print("=" * LARG)
    item("python", sys.version.split()[0])
    item("executável", sys.executable)
    item("PID", os.getpid())

    resultado = bloco_a_torch()
    bloco_b_ambiente()

    if not resultado["ok"]:
        titulo("CONCLUSÃO")
        print("  O torch não enxerga a GPU. Resolva o bloco A antes de seguir.")
        return 1

    if not args.carregar:
        titulo("PRÓXIMO PASSO")
        print("""
  O ambiente parece OK. Para confirmar que o carregamento ocupa GPU:

      python diagnostico_gpu.py --carregar --manter

  E, com o serviço rodando, compare com:

      curl -s localhost:8000/health | python -m json.tool

  No /health, olhe `modelos.gpu.alocado_mb`:
      > 0 e estável entre requisições  -> residente ✓
      = 0 com `pronto: true`           -> os modelos estão na CPU
""")
        return 0

    ok = bloco_c_carregar(resultado["torch"], args.modelo, args.device)
    if ok and args.manter:
        bloco_d_manter(resultado["torch"])
    elif ok:
        titulo("ATENÇÃO")
        print("""
  O modelo carregou e ocupou a GPU — mas este processo vai TERMINAR agora,
  e a memória será liberada. É exatamente isso que acontece quando você roda
  um script pontual em vez de um servidor.

  Para ver a memória PERMANECER, use --manter.
""")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
