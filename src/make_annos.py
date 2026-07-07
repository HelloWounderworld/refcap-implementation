#!/usr/bin/env python3
"""
make_annos.py — Adaptador não-invasivo para o RefCap
================================================================================
PROPÓSITO
    Gerar o arquivo `annos/{collection}/vcmr.jsonl` que o `construct.py` espera,
    a partir de um diretório de vídeos brutos — SEM tocar em nenhuma linha do
    código-núcleo do RefCap. É um "adapter" (anti-corruption layer): traduz a
    sua realidade (uma pasta de vídeos) para o formato que o sistema já consome.

DECISÕES DE DESIGN (alinhadas e verificadas contra o código do RefCap)
    - Opção A (regenerar do zero): a cada execução, relista o diretório e
      REESCREVE o vcmr.jsonl por completo. É barato (só lista nomes) e sempre
      correto. A incrementalidade cara (legendas/features) vive no cache do
      pipeline (meta/, chaveado por video_name), NÃO neste arquivo.
    - Campos placeholder: só `vid_name` é lido na construção (verificado por
      instrumentação). `duration`/`ts`/`desc`/`desc_name` são INERTES na
      construção; preenchemos com placeholders para o arquivo nascer no formato
      pleno e ser forward-compatible com a recuperação futura.
    - `collection` é FORNECIDO por você (via --collection), não gerado. Isso
      mantém o cache do meta/ estável (chaveado por collection) e evita a
      captura-de-retorno frágil no shell.

GARGALO RESIDUAL (documentado — leia com atenção)
    O cache do RefCap identifica vídeos por NOME DE ARQUIVO, não por conteúdo.
    => REGRA INVARIÁVEL: nomes de vídeo são ÚNICOS e IMUTÁVEIS por conteúdo.
       Se o conteúdo mudar, o nome DEVE mudar (ex.: vidA_v2.mp4). Reutilizar ou
       modificar um nome faz o pipeline servir legendas OBSOLETAS silenciosamente
       (sem erro). Este script NÃO detecta isso (nem poderia, sem hash de
       conteúdo, o que exigiria modificar o núcleo). Ver o relatório de proposta.

DISCIPLINA DE I/O (importante para o shell)
    - stdout: reservado para saída "de dados" (o caminho do arquivo gerado).
    - stderr: TODO log/progresso/aviso. Assim, se um dia você quiser capturar a
      saída no shell, ela fica limpa. (Nesta versão o .sh NÃO captura — você
      fornece o collection — mas mantemos a higiene por robustez.)

USO
    python make_annos.py --collection meu_corpus --video_root /dir/para/videos
    python make_annos.py --collection meu_corpus --video_root /dir --annos_dir annos
================================================================================
"""

import argparse
import json
import os
import sys


# Extensões de vídeo reconhecidas (ajuste se seu corpus usar outras).
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".mpg", ".mpeg", ".wmv", ".flv"}


def log(msg):
    """Todo log vai para stderr, mantendo o stdout limpo."""
    print(msg, file=sys.stderr)


def list_videos(video_root):
    """
    Lista os arquivos de vídeo no diretório (não-recursivo), ordenados para
    determinismo. Retorna a lista de nomes de arquivo (com extensão).
    """
    if not os.path.isdir(video_root):
        raise NotADirectoryError(f"video_root não é um diretório: {video_root}")

    files = []
    for name in sorted(os.listdir(video_root)):
        full = os.path.join(video_root, name)
        if not os.path.isfile(full):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in VIDEO_EXTS:
            files.append(name)
    return files


def check_duplicate_stems(video_files):
    """
    GARGALO RESIDUAL — detecção defensiva de colisão de NOME-BASE.
    O RefCap deriva `vid_name` de `arquivo.split('.')[0]` (o nome sem extensão).
    Se dois arquivos tiverem o mesmo nome-base (ex.: vidA.mp4 e vidA.mkv), eles
    colapsam no mesmo `vid_name` e o cache os confunde. Este script ABORTA nesse
    caso, em vez de gerar um catálogo ambíguo silenciosamente.
    """
    stems = {}
    for f in video_files:
        stem = f.split(".")[0]   # mesma regra do RefCap (base.py:41)
        stems.setdefault(stem, []).append(f)
    collisions = {s: fs for s, fs in stems.items() if len(fs) > 1}
    if collisions:
        log("ERRO: nomes-base duplicados detectados (o RefCap os confundiria):")
        for s, fs in collisions.items():
            log(f"  '{s}' <- {fs}")
        raise ValueError("Nomes de vídeo devem ser únicos por nome-base. Renomeie os conflitantes.")


def build_records(video_files):
    """
    Constrói os registros do vcmr.jsonl. Só `vid_name` é real; o resto é
    placeholder inerte na construção (verificado no código do RefCap).
    """
    records = []
    for f in video_files:
        vid_name = f.split(".")[0]              # regra do RefCap (base.py:41)
        records.append({
            "vid_name": vid_name,               # REAL — o único campo lido na construção
            "desc_name": f"{vid_name}#enc#0",   # placeholder (formato pleno)
            "duration": 0,                       # placeholder — inerte na construção
            "ts": [0, 0],                        # placeholder — inerte na construção
            "desc": "",                          # placeholder — inerte na construção
        })
    return records


def write_jsonl(records, out_path):
    """Escreve os registros (um JSON por linha). Opção A: reescreve do zero."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def make_annos(collection, video_root, annos_dir="annos"):
    """
    Orquestra a geração. Retorna o caminho do vcmr.jsonl criado.
    """
    log(f"[make_annos] collection = {collection}")
    log(f"[make_annos] video_root = {video_root}")

    video_files = list_videos(video_root)
    log(f"[make_annos] {len(video_files)} vídeo(s) encontrado(s).")
    if len(video_files) == 0:
        raise RuntimeError(f"Nenhum vídeo encontrado em {video_root} (exts: {sorted(VIDEO_EXTS)}).")

    check_duplicate_stems(video_files)          # aborta em colisão de nome-base
    records = build_records(video_files)

    out_dir = os.path.join(annos_dir, collection)
    out_path = os.path.join(out_dir, "vcmr.jsonl")

    # Opção A: se já existir, será sobrescrito (regeneração do zero).
    if os.path.exists(out_path):
        log(f"[make_annos] vcmr.jsonl existente será REESCRITO (Opção A): {out_path}")

    write_jsonl(records, out_path)
    log(f"[make_annos] OK — {len(records)} registro(s) escrito(s) em: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="Gera annos/{collection}/vcmr.jsonl a partir de um diretório de vídeos brutos."
    )
    parser.add_argument("--collection", required=True,
                        help="Nome (fixo, definido por você) do diretório dentro de annos/.")
    parser.add_argument("--video_root", required=True,
                        help="Diretório com os vídeos brutos.")
    parser.add_argument("--annos_dir", default="annos",
                        help="Diretório raiz das anotações (default: annos).")
    args = parser.parse_args()

    try:
        out_path = make_annos(args.collection, args.video_root, args.annos_dir)
    except Exception as e:
        log(f"[make_annos] FALHOU: {e}")
        sys.exit(1)                              # código != 0 → o .sh pode abortar

    # stdout: SÓ o caminho de dados (única linha), para eventual captura futura.
    print(out_path)


if __name__ == "__main__":
    main()
