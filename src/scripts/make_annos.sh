#!/bin/bash
# =============================================================================
# make_annos.sh — Shellscript MÍNIMO para testar o adapter make_annos.py
# =============================================================================
# Roda SÓ o adapter (não o construct.py), para verificar que o vcmr.jsonl é
# criado corretamente dentro de annos/{collection}/.
#
# COMO ISTO SE ENCAIXA NO construct.sh:
#   Você define `collection` UMA vez (fonte única de verdade) e o passa tanto
#   para o make_annos.py quanto, depois, para o construct.py. No construct.sh
#   real, a linha do make_annos.py entraria ANTES da linha "python construct.py",
#   usando a MESMA variável $collection.
# =============================================================================

set -u  # aborta se usar variável não definida

# --- Fonte única de verdade: você define o collection aqui --------------------
collection=meu_corpus                 # <- nome FIXO, definido por você
video_root=/dir/to/videos             # <- ajuste para o seu diretório de vídeos
annos_dir=annos                       # raiz das anotações (padrão do RefCap)

# --- Roda o adapter -----------------------------------------------------------
# Nota: stdout do make_annos.py = o caminho do arquivo gerado (dado);
#       stderr = todos os logs. Aqui NÃO capturamos o stdout (você já tem o
#       collection). A checagem de erro (|| exit 1) é o que importa.
echo "== Rodando adapter para collection='${collection}' ==" >&2
python make_annos.py \
    --collection "${collection}" \
    --video_root "${video_root}" \
    --annos_dir "${annos_dir}" \
  || { echo "make_annos.py FALHOU — abortando." >&2; exit 1; }

echo "== Adapter concluído. vcmr.jsonl em: ${annos_dir}/${collection}/vcmr.jsonl ==" >&2

# --- (No construct.sh real, aqui viria, com o MESMO $collection:) -------------
# python construct.py --collection "${collection}" --video_root "${video_root}" ... (resto igual)