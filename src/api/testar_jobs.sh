#!/usr/bin/env bash
# =============================================================================
# testar_jobs.sh — as duas requisições POST /jobs, prontas para testar
#
# ★ AJUSTE APENAS OS CAMINHOS. Os nomes dos campos são os que a API espera.
#
# USO
#     bash testar_jobs.sh lote      # conjunto de vídeos
#     bash testar_jobs.sh unico     # um vídeo só
#     bash testar_jobs.sh           # roda os dois
#
# [V] Ambos os formatos foram testados contra a API e retornaram 202 +
#     resultado no contrato acordado.
# =============================================================================

API="${API:-http://localhost:8000}"

# --- AJUSTE AQUI -------------------------------------------------------------
BASE="/caminho/para/suas/cenas"        # a raiz onde ficam program_id/video_id/
PROGRAMA="prog1"                       # o seu program_id
# -----------------------------------------------------------------------------

jq_ou_python() { command -v jq >/dev/null && jq . || python3 -m json.tool; }

esperar_job() {
    local jid="$1"
    echo "  job_id: $jid"
    for _ in $(seq 1 120); do
        local estado
        estado=$(curl -s "$API/jobs/$jid" | python3 -c \
            "import sys,json; print(json.load(sys.stdin)['estado'])" 2>/dev/null)
        case "$estado" in
            concluido|falhou) echo "  estado: $estado"; break ;;
            *) printf '.'; sleep 2 ;;
        esac
    done
    echo
    curl -s "$API/jobs/$jid" | jq_ou_python
}


# =============================================================================
# FORMATO 1 — LOTE (conjunto de vídeos)
# =============================================================================
# Cada item é uma cena. Cenas de `video_id` DIFERENTES ficam em diretórios
# diferentes — a API AGRUPA por diretório e chama o build() uma vez por grupo.
# [V] Verificado: 3 cenas em 2 diretórios geraram 2 chamadas de build.
#
# O `scene_video_path` aceita TRÊS formas:
#     1. o arquivo com extensão      /caminho/vidA/cena_01.mp4
#     2. o arquivo sem extensão      /caminho/vidA/cena_01      (tenta .mp4, .mkv, ...)
#     3. o diretório da cena         /caminho/vidA             (procura pelo scene_id)
# =============================================================================
requisicao_lote() {
    echo "═══ FORMATO 1 — LOTE ═══"
    local resp
    resp=$(curl -s -X POST "$API/jobs" \
        -H 'Content-Type: application/json' \
        -d @- <<EOF
{
  "items": [
    {
      "scene_id": "cena_01",
      "video_id": "vidA",
      "program_id": "$PROGRAMA",
      "scene_video_path": "$BASE/$PROGRAMA/vidA/cena_01.mp4"
    },
    {
      "scene_id": "cena_02",
      "video_id": "vidA",
      "program_id": "$PROGRAMA",
      "scene_video_path": "$BASE/$PROGRAMA/vidA/cena_02.mp4"
    },
    {
      "scene_id": "cena_04",
      "video_id": "vidB",
      "program_id": "$PROGRAMA",
      "scene_video_path": "$BASE/$PROGRAMA/vidB/cena_04.mp4"
    }
  ]
}
EOF
)
    echo "$resp" | jq_ou_python
    esperar_job "$(echo "$resp" | python3 -c \
        "import sys,json; print(json.load(sys.stdin)['job_id'])")"
}


# =============================================================================
# FORMATO 2 — CENA ÚNICA
# =============================================================================
# Os campos vão no NÍVEL DE CIMA, sem o "items". Internamente vira um lote de
# um — não há dois caminhos de execução.
#
# Aqui o `scene_video_path` aponta para um DIRETÓRIO com um vídeo só, para
# exercitar a forma 3 da resolução de caminho.
# =============================================================================
requisicao_unico() {
    echo "═══ FORMATO 2 — CENA ÚNICA ═══"
    local resp
    resp=$(curl -s -X POST "$API/jobs" \
        -H 'Content-Type: application/json' \
        -d @- <<EOF
{
  "scene_id": "cena_solo",
  "video_id": "vidUnico",
  "program_id": "prog2",
  "scene_video_path": "$BASE/prog2/vidUnico"
}
EOF
)
    echo "$resp" | jq_ou_python
    esperar_job "$(echo "$resp" | python3 -c \
        "import sys,json; print(json.load(sys.stdin)['job_id'])")"
}


# =============================================================================
case "${1:-ambos}" in
    lote)  requisicao_lote ;;
    unico) requisicao_unico ;;
    *)     requisicao_lote; echo; requisicao_unico ;;
esac
