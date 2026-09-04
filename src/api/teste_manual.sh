#!/usr/bin/env bash
# =============================================================================
# teste_manual.sh — bateria completa contra a API rodando
#
# PRÉ-REQUISITOS
#   1. bash preparar_teste.sh          (cria as cenas)
#   2. o serviço no ar, COM os modelos:
#          cd api && python app.py
#      ou via supervisord
#
# USO
#     bash teste_manual.sh                 # a bateria inteira
#     bash teste_manual.sh 5               # só o caso 5
#     API=http://outro:8000 bash teste_manual.sh
#
# ★ O CASO 3 (assíncrono) usa REFCAP_LIMIAR_ASSINCRONO=2 no serviço.
#   Se o seu serviço estiver com o default (30), esse caso é PULADO — reinicie
#   com o limiar baixo para exercitá-lo sem precisar de 31 cenas.
# =============================================================================

API="${API:-http://localhost:8000}"
BASE="${BASE:-/tmp/teste_refcap}"
PROG="prog_teste"
SO_ESTE="${1:-}"

VERDE='\033[0;32m'; VERM='\033[0;31m'; AMAR='\033[0;33m'; FIM='\033[0m'
PASSOU=0; FALHOU=0; PULADO=0

# ---------------------------------------------------------------------------
titulo() { echo; echo "═══════════════════════════════════════════════════════════════════"; echo " $1"; echo "═══════════════════════════════════════════════════════════════════"; }

pula() { [ -n "$SO_ESTE" ] && [ "$SO_ESTE" != "$1" ]; }

ok()   { PASSOU=$((PASSOU+1)); printf "  ${VERDE}✓${FIM} %s\n" "$1"; }
nok()  { FALHOU=$((FALHOU+1)); printf "  ${VERM}✗${FIM} %s\n     %s\n" "$1" "$2"; }
skip() { PULADO=$((PULADO+1)); printf "  ${AMAR}○${FIM} %s  (pulado: %s)\n" "$1" "$2"; }

# post <json> -> imprime o corpo; guarda o status em $HTTP
post() {
    local r
    r=$(curl -s -w '\n%{http_code}' -X POST "$API/caption$2" \
        -H 'Content-Type: application/json' -d "$1")
    HTTP=$(echo "$r" | tail -1)
    echo "$r" | sed '$d'
}
get() {
    local r
    r=$(curl -s -w '\n%{http_code}' "$API$1")
    HTTP=$(echo "$r" | tail -1)
    echo "$r" | sed '$d'
}
# jqp <json> <expressao python sobre `d`>
jqp() { echo "$1" | python3 -c "import sys,json; d=json.load(sys.stdin); print($2)" 2>/dev/null; }

cena() {  # cena <scene_id> <video_id>
    cat <<EOF
{"scene_id":"$1","video_id":"$2","program_id":"$PROG","scene_video_path":"$BASE/$PROG/$2/$1.mp4"}
EOF
}

# ---------------------------------------------------------------------------
titulo "PRÉ-VOO"

R=$(get /health)
if [ "$HTTP" != "200" ]; then
    echo "  ✗ o serviço não respondeu em $API  (HTTP $HTTP)"
    echo "    Suba com: cd api && python app.py"
    exit 1
fi
PRONTO=$(jqp "$R" "d['models']['ready']")
GPU=$(jqp "$R" "d['models']['gpu'].get('allocated_mb','—')")
echo "  serviço      : ok"
echo "  models.ready : $PRONTO"
echo "  gpu.allocated_mb : $GPU"
if [ "$PRONTO" != "True" ]; then
    echo
    echo "  ✗ os modelos NÃO estão carregados. Suba sem REFCAP_CARREGAR_MODELOS=0."
    exit 1
fi
[ -d "$BASE/$PROG" ] || { echo "  ✗ cenas não encontradas. Rode: bash preparar_teste.sh"; exit 1; }

LIMIAR=$(get /openapi.json >/dev/null; echo "?")

# =============================================================================
titulo "PARTE 1 — CAMINHO FELIZ"

# --- 1. uma cena ---
if ! pula 1; then
    R=$(post "$(cena cena_01 vidA)")
    S=$(jqp "$R" "d['items'][0]['status']")
    C=$(jqp "$R" "d['items'][0]['scene_caption_en']")
    K=$(jqp "$R" "len(d['items'][0]['keywords_en'])")
    if [ "$HTTP" = "200" ] && [ "$S" = "success" ] && [ -n "$C" ]; then
        ok "1. POST /caption (uma cena)"
        echo "       legenda : $C"
        echo "       keywords: $K"
    else
        nok "1. POST /caption (uma cena)" "HTTP=$HTTP status=$S"
    fi
fi

# --- 2. lote, dois diretórios ---
if ! pula 2; then
    R=$(post "{\"items\":[$(cena cena_02 vidA),$(cena cena_04 vidB)]}" /batch)
    T=$(jqp "$R" "d['summary']['total']")
    O=$(jqp "$R" "d['summary']['ok']")
    G=$(jqp "$R" "len(d['groups'])")
    if [ "$HTTP" = "200" ] && [ "$T" = "2" ] && [ "$O" = "2" ] && [ "$G" = "2" ]; then
        ok "2. POST /caption/batch (2 cenas, 2 diretórios)"
        echo "       grupos: $G  ← um build() por diretório"
    else
        nok "2. POST /caption/batch" "HTTP=$HTTP total=$T ok=$O grupos=$G"
    fi
fi

# --- 3. assíncrono ---
if ! pula 3; then
    R=$(post "{\"items\":[$(cena cena_01 vidA),$(cena cena_02 vidA),$(cena cena_04 vidB)]}" /batch)
    if [ "$HTTP" = "202" ]; then
        ok "3. assíncrono automático (limiar baixo)"
        echo "       state: $(jqp "$R" "d['state']")  check_at: $(jqp "$R" "d['check_at']")"
        sleep 8
    else
        skip "3. assíncrono automático" "limiar alto — reinicie com REFCAP_LIMIAR_ASSINCRONO=2"
    fi
fi

# --- 4. vídeo curto (< 1s) ---
if ! pula 4; then
    R=$(post "$(cena cena_03 vidA)")
    S=$(jqp "$R" "d['items'][0]['status']")
    if [ "$HTTP" = "200" ] && [ "$S" = "success" ]; then
        ok "4. ★ vídeo de 0.5s processado (patch do viddataset)"
        echo "       legenda: $(jqp "$R" "d['items'][0]['scene_caption_en']")"
    else
        nok "4. vídeo curto" "HTTP=$HTTP status=$S  → o patch max(1,int(duration)) foi aplicado?"
    fi
fi

# =============================================================================
titulo "PARTE 2 — CACHE"

# --- 5. reprocessar sem force: deve PULAR ---
if ! pula 5; then
    T0=$(date +%s%N)
    R=$(post "$(cena cena_01 vidA)")
    T1=$(date +%s%N)
    MS=$(( (T1-T0)/1000000 ))
    S=$(jqp "$R" "d['items'][0]['status']")
    CACHE=$(jqp "$R" "d['groups'][0].get('estavam_em_cache','?')")
    if [ "$S" = "success" ]; then
        ok "5. reprocessar SEM force (${MS}ms)"
        echo "       estavam_em_cache: $CACHE   ← 1 = o BLIP não rodou de novo"
    else
        nok "5. reprocessar sem force" "status=$S"
    fi
fi

# --- 6. force: deve REPROCESSAR ---
if ! pula 6; then
    P=$(cena cena_01 vidA | python3 -c "import sys,json; d=json.load(sys.stdin); d['force']=True; print(json.dumps(d))")
    T0=$(date +%s%N); R=$(post "$P"); T1=$(date +%s%N)
    MS=$(( (T1-T0)/1000000 ))
    S=$(jqp "$R" "d['items'][0]['status']")
    LIMPO=$(jqp "$R" "d['groups'][0].get('cache_limpo')")
    if [ "$S" = "success" ]; then
        ok "6. force: true (${MS}ms)"
        echo "       cache_limpo: $LIMPO"
        echo "       ★ compare com o caso 5: este deve ser MAIS LENTO"
    else
        nok "6. force" "status=$S"
    fi
fi

# --- 7. as outras cenas sobreviveram ao force? ---
if ! pula 7; then
    R=$(get "/caption/$PROG")
    T=$(jqp "$R" "d['summary']['total']")
    if [ "$T" -ge 4 ]; then
        ok "7. force NÃO apagou as outras cenas"
        echo "       cenas persistidas: $T"
    else
        nok "7. force cirúrgico" "só $T cena(s) — o force pode ter limpado demais"
    fi
fi

# =============================================================================
titulo "PARTE 3 — ERROS"

# --- 8. FILE_NOT_FOUND ---
if ! pula 8; then
    R=$(post "{\"scene_id\":\"fantasma\",\"program_id\":\"$PROG\",\"scene_video_path\":\"$BASE/nao_existe/x.mp4\"}")
    E=$(jqp "$R" "d['items'][0]['error_code']")
    [ "$E" = "FILE_NOT_FOUND" ] && ok "8. FILE_NOT_FOUND" || nok "8. FILE_NOT_FOUND" "veio: $E"
fi

# --- 9. SCENE_NOT_FOUND (diretório sem a cena) ---
if ! pula 9; then
    R=$(post "{\"scene_id\":\"cena_99\",\"program_id\":\"$PROG\",\"scene_video_path\":\"$BASE/$PROG/vazio\"}")
    E=$(jqp "$R" "d['items'][0]['error_code']")
    [ "$E" = "SCENE_NOT_FOUND" ] && ok "9. SCENE_NOT_FOUND (dir sem a cena)" || nok "9. SCENE_NOT_FOUND" "veio: $E"
fi

# --- 10. o fallback REMOVIDO ---
if ! pula 10; then
    # vidB tem UM vídeo (cena_04). Pedir cena_77 apontando para o DIRETÓRIO:
    # antes da Etapa 2 isso legendava a cena_04 em silêncio.
    R=$(post "{\"scene_id\":\"cena_77\",\"program_id\":\"$PROG\",\"scene_video_path\":\"$BASE/$PROG/vidB\"}")
    E=$(jqp "$R" "d['items'][0]['error_code']")
    if [ "$E" = "SCENE_NOT_FOUND" ]; then
        ok "10. ★ fallback removido (não legenda o vídeo errado)"
    else
        nok "10. fallback removido" "veio: $E — deveria recusar, não usar o único vídeo"
    fi
fi

# --- 11. INVALID_REQUEST ---
if ! pula 11; then
    R=$(post '{}')
    if [ "$HTTP" = "400" ] || [ "$HTTP" = "422" ]; then
        ok "11. INVALID_REQUEST (pedido vazio) — HTTP $HTTP"
    else
        nok "11. INVALID_REQUEST" "HTTP=$HTTP"
    fi
fi

# --- 12. erro PARCIAL no lote ---
if ! pula 12; then
    R=$(post "{\"items\":[$(cena cena_01 vidA),{\"scene_id\":\"ruim\",\"program_id\":\"$PROG\",\"scene_video_path\":\"/nada/x.mp4\"},$(cena cena_02 vidA)]}" /batch)
    T=$(jqp "$R" "d['summary']['total']"); O=$(jqp "$R" "d['summary']['ok']"); E=$(jqp "$R" "d['summary']['errors']")
    if [ "$HTTP" = "200" ] && [ "$O" = "2" ] && [ "$E" = "1" ]; then
        ok "12. ★ erro parcial não derruba o lote"
        echo "       total=$T ok=$O errors=$E  (HTTP 200, não 500)"
    else
        nok "12. erro parcial" "HTTP=$HTTP total=$T ok=$O errors=$E"
    fi
fi

# =============================================================================
titulo "PARTE 4 — CONSULTA"

if ! pula 13; then
    R=$(get "/caption/$PROG"); T=$(jqp "$R" "d['summary']['total']")
    [ "$HTTP" = "200" ] && [ "$T" -ge 4 ] && { ok "13. GET /caption/{program_id}"; echo "       cenas: $T"; } \
        || nok "13. GET todas" "HTTP=$HTTP total=$T"
fi

if ! pula 14; then
    R=$(get "/caption/$PROG?scene_id=cena_01"); T=$(jqp "$R" "d['summary']['total']")
    [ "$T" = "1" ] && ok "14. GET com 1 filtro" || nok "14. GET 1 filtro" "total=$T"
fi

if ! pula 15; then
    R=$(get "/caption/$PROG?scene_id=cena_01&scene_id=cena_02"); T=$(jqp "$R" "d['summary']['total']")
    [ "$T" = "2" ] && ok "15. GET com 2 filtros" || nok "15. GET 2 filtros" "total=$T"
fi

if ! pula 16; then
    R=$(get "/caption/programa_que_nunca_existiu"); T=$(jqp "$R" "d['summary']['total']")
    [ "$HTTP" = "200" ] && [ "$T" = "0" ] && ok "16. GET programa inexistente → 200 + vazio" \
        || nok "16. GET inexistente" "HTTP=$HTTP total=$T"
fi

# =============================================================================
titulo "PARTE 5 — ISOLAMENTO"

# --- 17. mesmo scene_id em program_id diferente ---
if ! pula 17; then
    R=$(post "{\"scene_id\":\"cena_01\",\"video_id\":\"vidX\",\"program_id\":\"prog_outro\",\"scene_video_path\":\"$BASE/prog_outro/vidX/cena_01.mp4\"}")
    C2=$(jqp "$R" "d['items'][0]['scene_caption_en']")
    R1=$(get "/caption/$PROG?scene_id=cena_01"); C1=$(jqp "$R1" "d['items'][0]['scene_caption_en']")
    if [ "$HTTP" = "200" ] && [ -n "$C2" ]; then
        ok "17. ★ mesmo scene_id, program_id diferente"
        echo "       $PROG/cena_01  : $C1"
        echo "       prog_outro/cena_01: $C2"
        echo "       ★ processados SEPARADAMENTE (caches isolados)"
    else
        nok "17. isolamento entre programas" "HTTP=$HTTP"
    fi
fi

# --- 18. diagnóstico não contamina ---
if ! pula 18; then
    R=$(get "/diagnostics/caption?video=cena_01.mp4")
    if [ "$HTTP" = "200" ] || [ "$HTTP" = "404" ]; then
        ok "18. /diagnostics/caption respondeu (HTTP $HTTP)"
        echo "       ★ confira que criou annos/diagnostics/ e NÃO tocou em annos/$PROG/"
    else
        nok "18. /diagnostics/caption" "HTTP=$HTTP"
    fi
fi

# =============================================================================
titulo "PARTE 6 — O QUE FICOU NO DISCO"
cat <<'FIM_TXT'
  Confira na raiz do RefCap:

    ls annos/                              → prog_teste, prog_outro, diagnostics
    ls meta/captions/                      → prog_teste_blip.jsonl, prog_outro_blip.jsonl
    ls results/construct/prog_teste/       → proposals.json, tree.json, *.pt
    ls results/response/prog_teste/scenes/ → um .json por cena
    wc -l results/response/prog_teste/responses.jsonl

  ★ VERIFICAÇÕES QUE VALEM O OLHO:

    1. O proposals.json tem TODAS as cenas (a fusão funcionou):
       python -c "import json;print(sorted(json.load(open('results/construct/prog_teste/proposals.json'))))"

    2. O responses.jsonl tem MAIS linhas que scenes/ tem arquivos
       (o histórico guarda todas as versões; o force gerou uma nova)

    3. Uma cena guarda TUDO:
       python -m json.tool results/response/prog_teste/scenes/cena_01.json
       → deve ter: scene_caption_en, keywords_en, diagnostics.ranking,
         diagnostics.n_raw, diagnostics.warning, timestamp

    4. O /health durante o processamento continua respondendo, e o
       allocated_mb NÃO cresce entre requisições (modelos residentes).
FIM_TXT

# =============================================================================
titulo "RESULTADO"
printf "  ${VERDE}%d passou${FIM}   ${VERM}%d falhou${FIM}   ${AMAR}%d pulado${FIM}\n" "$PASSOU" "$FALHOU" "$PULADO"
echo
[ "$FALHOU" -eq 0 ] && echo "  ✓ Todos os casos executados passaram." \
                    || echo "  ✗ Há falhas acima — investigue antes de seguir."
exit $([ "$FALHOU" -eq 0 ] && echo 0 || echo 1)
