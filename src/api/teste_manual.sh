#!/usr/bin/env bash
# =============================================================================
# teste_manual.sh — 18 casos contra a API rodando, usando as SUAS cenas
#
# PRÉ-REQUISITOS
#   1. bash preparar_teste.sh [/caminho/das/suas/cenas]
#      → gera o teste_config.sh, que você pode EDITAR
#   2. o serviço no ar, COM os modelos:
#          cd api && python app.py
#
# USO
#   bash teste_manual.sh                     # a bateria inteira
#   bash teste_manual.sh 10                  # só o caso 10
#   API=http://outro:8000 bash teste_manual.sh
#   CONFIG=/outro/config.sh bash teste_manual.sh
#
# ★ AS CENAS VÊM DO teste_config.sh — nada é hardcoded aqui.
#   Um papel vazio no config faz seus testes serem PULADOS, não falharem.
#
# ★ O CASO 3 (assíncrono) precisa de REFCAP_LIMIAR_ASSINCRONO=2 no serviço.
#   Com o default (30), ele é pulado — reinicie com o limiar baixo para
#   exercitá-lo sem precisar de 31 cenas.
# =============================================================================

CONFIG="${CONFIG:-$(cd "$(dirname "$0")" && pwd)/teste_config.sh}"
SO_ESTE="${1:-}"

VERDE='\033[0;32m'; VERM='\033[0;31m'; AMAR='\033[0;33m'; AZUL='\033[0;36m'; FIM='\033[0m'
PASSOU=0; FALHOU=0; PULADO=0

[ -f "$CONFIG" ] || {
    printf "${VERM}✗ configuração não encontrada: %s${FIM}\n" "$CONFIG"
    echo "  Rode primeiro:  bash preparar_teste.sh [/caminho/das/suas/cenas]"
    exit 1
}
# shellcheck disable=SC1090
. "$CONFIG"
API="${API:-http://localhost:8000}"

# --------------------------------------------------------------------------- #
titulo() { echo; echo "═══════════════════════════════════════════════════════════════════"; echo " $1"; echo "═══════════════════════════════════════════════════════════════════"; }
pula()  { [ -n "$SO_ESTE" ] && [ "$SO_ESTE" != "$1" ]; }
ok()    { PASSOU=$((PASSOU+1)); printf "  ${VERDE}✓${FIM} %s\n" "$1"; }
nok()   { FALHOU=$((FALHOU+1)); printf "  ${VERM}✗${FIM} %s\n       %s\n" "$1" "$2"; }
skip()  { PULADO=$((PULADO+1)); printf "  ${AMAR}○${FIM} %s\n       pulado: %s\n" "$1" "$2"; }
det()   { printf "       ${AZUL}%s${FIM}\n" "$1"; }

post() {
    local r; r=$(curl -s -w '\n%{http_code}' -X POST "$API/caption$2" \
                 -H 'Content-Type: application/json' -d "$1")
    HTTP=$(echo "$r" | tail -1); echo "$r" | sed '$d'
}
get() {
    local r; r=$(curl -s -w '\n%{http_code}' "$API$1")
    HTTP=$(echo "$r" | tail -1); echo "$r" | sed '$d'
}
jqp() { echo "$1" | python3 -c "import sys,json;d=json.load(sys.stdin);print($2)" 2>/dev/null; }

# item <ID> <VID> <PATH> [extras json]
item() {
    printf '{"scene_id":"%s","video_id":"%s","program_id":"%s","scene_video_path":"%s"%s}' \
           "$1" "$2" "${5:-$PROG}" "$3" "${4:+,$4}"
}

# --------------------------------------------------------------------------- #
titulo "CONFIGURAÇÃO EM USO"
printf "  %-14s %s\n" "config"   "$CONFIG"
printf "  %-14s %s\n" "API"      "$API"
printf "  %-14s %s\n" "BASE"     "$BASE"
# ★ As cenas podem estar em QUALQUER lugar: o caminho vai absoluto na
#   requisição, e a API deriva o video_root dele. Não precisam estar
#   perto do api/ nem sob o RefCap.
printf "  %-14s %s\n" "PROG"     "$PROG"
printf "  %-14s %s\n" "PROG2"    "${PROG2:-—}"
echo
printf "  %-14s %-22s %s\n" "papel" "scene_id" "video_id"
echo "  ──────────────────────────────────────────────────────"
printf "  %-14s %-22s %s\n" "CENA_A1"    "${CENA_A1_ID:-—}"    "${CENA_A1_VID:-—}"
printf "  %-14s %-22s %s\n" "CENA_A2"    "${CENA_A2_ID:-—}"    "${CENA_A2_VID:-—}"
printf "  %-14s %-22s %s\n" "CENA_B1"    "${CENA_B1_ID:-—}"    "${CENA_B1_VID:-—}"
printf "  %-14s %-22s %s\n" "CENA_CURTA" "${CENA_CURTA_ID:-—}" "${CENA_CURTA_DUR:+${CENA_CURTA_DUR}s}"
printf "  %-14s %-22s %s\n" "CENA_P2"    "${CENA_P2_ID:-—}"    "${CENA_P2_VID:-—}"

# --------------------------------------------------------------------------- #
titulo "PRÉ-VOO"

command -v curl >/dev/null || {
    printf "  ${VERM}✗ curl não encontrado${FIM}\n"
    echo "    Instale o curl, ou rode os testes pelo TESTES_CURL.md com outra ferramenta."
    exit 1
}

R=$(get /health)
if [ "$HTTP" != "200" ]; then
    printf "  ${VERM}✗ o serviço não respondeu em %s${FIM}\n" "$API"
    echo
    echo "  ⚠️ ISTO NÃO TEM RELAÇÃO COM O CAMINHO DAS CENAS."
    echo "     O pré-voo só chama GET /health — as cenas nem foram consultadas."
    echo

    # --- diagnóstico: por que falhou? ---
    CODIGO=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$API/health" 2>/dev/null)
    ERRO=$(curl -s -o /dev/null --max-time 5 "$API/health" 2>&1)
    case "$CODIGO" in
        000) echo "  CAUSA: não houve conexão (código 000)."
             echo "         $ERRO"
             echo
             echo "  Verifique, nesta ordem:"
             echo "    1. o serviço está no ar?"
             echo "         cd api && python app.py"
             echo "         (ou: supervisorctl status refcap-api)"
             echo
             echo "    2. é esta a porta? o default do app.py é 8000."
             echo "         API=http://localhost:8080 bash teste_manual.sh"
             echo
             echo "    3. o serviço está noutra máquina ou container?"
             echo "         API=http://IP_OU_HOST:8000 bash teste_manual.sh"
             echo
             echo "    4. teste à mão:"
             echo "         curl -v $API/health"
             ;;
        404) echo "  CAUSA: o servidor respondeu, mas não tem a rota /health (404)."
             echo "         Há algo escutando em $API, mas não é a Caption API."
             echo "         Confira a porta."
             ;;
        *)   echo "  CAUSA: o servidor respondeu com HTTP $CODIGO."
             echo "         Veja o log do serviço."
             ;;
    esac
    exit 1
fi
PRONTO=$(jqp "$R" "d['models']['ready']")
GPU_INI=$(jqp "$R" "d['models']['gpu'].get('allocated_mb','—')")
echo "  serviço          : ok"
echo "  models.ready     : $PRONTO"
echo "  gpu.allocated_mb : $GPU_INI"
[ "$PRONTO" = "True" ] || {
    printf "\n  ${VERM}✗ modelos NÃO carregados${FIM} — suba sem REFCAP_CARREGAR_MODELOS=0\n"; exit 1
}

# =============================================================================
titulo "PARTE 1 — CAMINHO FELIZ"

if ! pula 1; then
    if [ -z "$CENA_A1_ID" ]; then skip "1. POST /caption (uma cena)" "CENA_A1 não configurada"
    else
        R=$(post "$(item "$CENA_A1_ID" "$CENA_A1_VID" "$CENA_A1_PATH")")
        S=$(jqp "$R" "d['items'][0]['status']"); C=$(jqp "$R" "d['items'][0]['scene_caption_en']")
        if [ "$HTTP" = "200" ] && [ "$S" = "success" ] && [ -n "$C" ]; then
            ok "1. POST /caption ($CENA_A1_ID)"
            det "legenda : $C"
            det "keywords: $(jqp "$R" "', '.join(k['token'] for k in d['items'][0]['keywords_en'])")"
        else nok "1. POST /caption" "HTTP=$HTTP status=$S"; fi
    fi
fi

if ! pula 2; then
    if [ -z "$CENA_A2_ID" ] || [ -z "$CENA_B1_ID" ]; then
        skip "2. POST /caption/batch (2 diretórios)" "faltam CENA_A2 ou CENA_B1"
    else
        R=$(post "{\"items\":[$(item "$CENA_A2_ID" "$CENA_A2_VID" "$CENA_A2_PATH"),$(item "$CENA_B1_ID" "$CENA_B1_VID" "$CENA_B1_PATH")]}" /batch)
        T=$(jqp "$R" "d['summary']['total']"); O=$(jqp "$R" "d['summary']['ok']"); G=$(jqp "$R" "len(d['groups'])")
        if [ "$HTTP" = "200" ] && [ "$O" = "2" ] && [ "$G" = "2" ]; then
            ok "2. POST /caption/batch — 2 cenas, 2 diretórios"
            det "grupos: $G  ← um build() por diretório"
        else nok "2. POST /caption/batch" "HTTP=$HTTP total=$T ok=$O grupos=$G (esperava 2 grupos)"; fi
    fi
fi

if ! pula 3; then
    if [ -z "$CENA_A1_ID" ]; then skip "3. assíncrono automático" "CENA_A1 não configurada"
    else
        R=$(post "{\"items\":[$(item "$CENA_A1_ID" "$CENA_A1_VID" "$CENA_A1_PATH"),$(item "${CENA_A2_ID:-$CENA_A1_ID}" "${CENA_A2_VID:-$CENA_A1_VID}" "${CENA_A2_PATH:-$CENA_A1_PATH}"),$(item "${CENA_B1_ID:-$CENA_A1_ID}" "${CENA_B1_VID:-$CENA_A1_VID}" "${CENA_B1_PATH:-$CENA_A1_PATH}")]}" /batch)
        if [ "$HTTP" = "202" ]; then
            ok "3. assíncrono automático"
            det "state=$(jqp "$R" "d['state']")  check_at=$(jqp "$R" "d['check_at']")"
            sleep 8
        else skip "3. assíncrono automático" "limiar alto — reinicie com REFCAP_LIMIAR_ASSINCRONO=2"; fi
    fi
fi

if ! pula 4; then
    if [ -z "$CENA_CURTA_ID" ]; then
        skip "4. ★ vídeo curto (< 1s)" "nenhuma cena com menos de 1s no seu conjunto"
    else
        R=$(post "$(item "$CENA_CURTA_ID" "$CENA_CURTA_VID" "$CENA_CURTA_PATH")")
        S=$(jqp "$R" "d['items'][0]['status']")
        if [ "$HTTP" = "200" ] && [ "$S" = "success" ]; then
            ok "4. ★ vídeo de ${CENA_CURTA_DUR}s processado (patch do viddataset)"
            det "legenda: $(jqp "$R" "d['items'][0]['scene_caption_en']")"
        else nok "4. vídeo curto" "HTTP=$HTTP status=$S → o patch max(1,int(duration)) foi aplicado?"; fi
    fi
fi

# =============================================================================
titulo "PARTE 2 — CACHE"

if ! pula 5; then
    if [ -z "$CENA_A1_ID" ]; then skip "5. reprocessar sem force" "CENA_A1 não configurada"
    else
        T0=$(date +%s%N); R=$(post "$(item "$CENA_A1_ID" "$CENA_A1_VID" "$CENA_A1_PATH")"); T1=$(date +%s%N)
        MS_SEM=$(( (T1-T0)/1000000 ))
        S=$(jqp "$R" "d['items'][0]['status']"); CACHE=$(jqp "$R" "d['groups'][0].get('estavam_em_cache','?')")
        if [ "$S" = "success" ]; then
            ok "5. reprocessar SEM force — ${MS_SEM}ms"
            det "estavam_em_cache: $CACHE   ← ≥1 significa que o BLIP não rodou"
        else nok "5. reprocessar sem force" "status=$S"; fi
    fi
fi

if ! pula 6; then
    if [ -z "$CENA_A1_ID" ]; then skip "6. force: true" "CENA_A1 não configurada"
    else
        T0=$(date +%s%N)
        R=$(post "$(item "$CENA_A1_ID" "$CENA_A1_VID" "$CENA_A1_PATH" '"force":true')")
        T1=$(date +%s%N); MS_COM=$(( (T1-T0)/1000000 ))
        S=$(jqp "$R" "d['items'][0]['status']")
        if [ "$S" = "success" ]; then
            ok "6. force: true — ${MS_COM}ms"
            det "cache_limpo: $(jqp "$R" "d['groups'][0].get('cache_limpo')")"
            if [ -n "$MS_SEM" ] && [ "$MS_COM" -gt "$MS_SEM" ]; then
                det "★ ${MS_COM}ms > ${MS_SEM}ms — reprocessou de verdade"
            elif [ -n "$MS_SEM" ]; then
                printf "       ${AMAR}⚠️  %sms NÃO é maior que %sms — o cache foi mesmo limpo?${FIM}\n" "$MS_COM" "$MS_SEM"
            fi
        else nok "6. force" "status=$S"; fi
    fi
fi

if ! pula 7; then
    R=$(get "/caption/$PROG"); T=$(jqp "$R" "d['summary']['total']")
    if [ -n "$T" ] && [ "$T" -ge 2 ]; then
        ok "7. o force NÃO apagou as outras cenas"
        det "cenas persistidas no $PROG: $T"
    else nok "7. force cirúrgico" "só $T cena(s) — o force pode ter limpado demais"; fi
fi

# =============================================================================
titulo "PARTE 3 — ERROS"

if ! pula 8; then
    R=$(post "$(item "cena_que_nao_existe" "vid" "$BASE/__nao_existe__/x.mp4")")
    E=$(jqp "$R" "d['items'][0]['error_code']")
    [ "$E" = "FILE_NOT_FOUND" ] && ok "8. FILE_NOT_FOUND" || nok "8. FILE_NOT_FOUND" "veio: $E"
fi

if ! pula 9; then
    if [ -z "$DIR_VAZIO" ]; then skip "9. SCENE_NOT_FOUND" "DIR_VAZIO não configurado"
    else
        R=$(post "$(item "cena_inexistente" "vid" "$DIR_VAZIO")")
        E=$(jqp "$R" "d['items'][0]['error_code']")
        [ "$E" = "SCENE_NOT_FOUND" ] && ok "9. SCENE_NOT_FOUND (diretório vazio)" || nok "9. SCENE_NOT_FOUND" "veio: $E"
    fi
fi

if ! pula 10; then
    if [ -z "$DIR_COM_VIDEO" ]; then skip "10. ★ fallback removido" "DIR_COM_VIDEO não configurado"
    else
        R=$(post "$(item "id_que_nao_existe_ali" "vid" "$DIR_COM_VIDEO")")
        E=$(jqp "$R" "d['items'][0]['error_code']")
        if [ "$E" = "SCENE_NOT_FOUND" ]; then
            ok "10. ★ fallback removido — não legenda o vídeo errado"
            det "pedi um scene_id inexistente em $DIR_COM_VIDEO (que TEM vídeos)"
        else nok "10. fallback removido" "veio: $E — deveria recusar, não usar outro vídeo"; fi
    fi
fi

if ! pula 11; then
    R=$(post '{}')
    { [ "$HTTP" = "400" ] || [ "$HTTP" = "422" ]; } \
        && ok "11. INVALID_REQUEST (pedido vazio) — HTTP $HTTP" \
        || nok "11. INVALID_REQUEST" "HTTP=$HTTP (esperava 400 ou 422)"
fi

if ! pula 12; then
    if [ -z "$CENA_A1_ID" ]; then skip "12. erro parcial no lote" "CENA_A1 não configurada"
    else
        R=$(post "{\"items\":[$(item "$CENA_A1_ID" "$CENA_A1_VID" "$CENA_A1_PATH"),$(item "cena_ruim" "vid" "/nada/x.mp4"),$(item "${CENA_A2_ID:-$CENA_A1_ID}" "${CENA_A2_VID:-$CENA_A1_VID}" "${CENA_A2_PATH:-$CENA_A1_PATH}")]}" /batch)
        O=$(jqp "$R" "d['summary']['ok']"); E=$(jqp "$R" "d['summary']['errors']")
        if [ "$HTTP" = "200" ] && [ "$E" = "1" ]; then
            ok "12. ★ erro parcial NÃO derruba o lote"
            det "ok=$O errors=$E — e HTTP 200, não 500"
        else nok "12. erro parcial" "HTTP=$HTTP ok=$O errors=$E"; fi
    fi
fi

# =============================================================================
titulo "PARTE 4 — CONSULTA"

if ! pula 13; then
    R=$(get "/caption/$PROG"); T=$(jqp "$R" "d['summary']['total']")
    { [ "$HTTP" = "200" ] && [ -n "$T" ] && [ "$T" -ge 1 ]; } \
        && { ok "13. GET /caption/$PROG"; det "cenas: $T"; } \
        || nok "13. GET todas" "HTTP=$HTTP total=$T"
fi

if ! pula 14; then
    R=$(get "/caption/$PROG?scene_id=$CENA_A1_ID"); T=$(jqp "$R" "d['summary']['total']")
    [ "$T" = "1" ] && ok "14. GET com 1 filtro" || nok "14. GET 1 filtro" "total=$T"
fi

if ! pula 15; then
    if [ -z "$CENA_A2_ID" ]; then skip "15. GET com 2 filtros" "CENA_A2 não configurada"
    else
        R=$(get "/caption/$PROG?scene_id=$CENA_A1_ID&scene_id=$CENA_A2_ID")
        T=$(jqp "$R" "d['summary']['total']")
        [ "$T" = "2" ] && ok "15. GET com 2 filtros" || nok "15. GET 2 filtros" "total=$T"
    fi
fi

if ! pula 16; then
    R=$(get "/caption/programa_que_nunca_existiu"); T=$(jqp "$R" "d['summary']['total']")
    { [ "$HTTP" = "200" ] && [ "$T" = "0" ]; } \
        && ok "16. GET programa inexistente → 200 + lista vazia" \
        || nok "16. GET inexistente" "HTTP=$HTTP total=$T"
fi

# =============================================================================
titulo "PARTE 5 — ISOLAMENTO"

if ! pula 17; then
    if [ -z "$CENA_P2_ID" ]; then skip "17. ★ isolamento entre programas" "PROG2/CENA_P2 não configurados"
    else
        R=$(post "$(item "$CENA_P2_ID" "$CENA_P2_VID" "$CENA_P2_PATH" "" "$PROG2")")
        S=$(jqp "$R" "d['items'][0]['status']")
        if [ "$HTTP" = "200" ] && [ "$S" = "success" ]; then
            C2=$(jqp "$R" "d['items'][0]['scene_caption_en']")
            R1=$(get "/caption/$PROG?scene_id=$CENA_P2_ID"); C1=$(jqp "$R1" "d['items'][0]['scene_caption_en']")
            ok "17. ★ mesmo scene_id em program_id diferente"
            det "$PROG/$CENA_P2_ID  : ${C1:-—}"
            det "$PROG2/$CENA_P2_ID : $C2"
            if [ "$CENA_P2_REPETIDO" = "1" ] && [ -n "$C1" ]; then
                if [ "$C1" = "$C2" ]; then
                    printf "       ${AMAR}⚠️  legendas IGUAIS — se os vídeos são diferentes, o cache vazou${FIM}\n"
                else
                    det "★ legendas DIFERENTES — caches isolados por program_id"
                fi
            fi
        else nok "17. isolamento" "HTTP=$HTTP status=$S"; fi
    fi
fi

if ! pula 18; then
    R=$(get "/diagnostics/caption?video=$(basename "${CENA_A1_PATH:-x.mp4}")")
    if [ "$HTTP" = "200" ] || [ "$HTTP" = "404" ]; then
        ok "18. /diagnostics/caption respondeu — HTTP $HTTP"
        [ "$HTTP" = "404" ] && det "404 é esperado se o vídeo não está no video_root configurado"
        det "confira: annos/diagnostics/ criado, e annos/$PROG/ intacto"
    else nok "18. /diagnostics/caption" "HTTP=$HTTP"; fi
fi

# =============================================================================
titulo "FECHAMENTO — os modelos ficaram residentes?"
R=$(get /health); GPU_FIM=$(jqp "$R" "d['models']['gpu'].get('allocated_mb','—')")
echo "  allocated_mb no início : $GPU_INI"
echo "  allocated_mb no fim    : $GPU_FIM"
if [ "$GPU_INI" = "$GPU_FIM" ]; then
    printf "  ${VERDE}✓ IGUAL — nenhuma requisição recarregou modelo${FIM}\n"
else
    printf "  ${AMAR}⚠️  mudou — investigue se algo está recarregando modelo${FIM}\n"
fi

# =============================================================================
titulo "O QUE FICOU NO DISCO"
cat <<FIM_TXT
  Na raiz do RefCap:

    ls annos/                          → $PROG, ${PROG2:-...}, diagnostics
    ls meta/captions/                  → ${PROG}_blip.jsonl, ...
    ls results/construct/$PROG/
    ls results/response/$PROG/scenes/

  ★ AS QUATRO VERIFICAÇÕES QUE VALEM O OLHO:

    1. A fusão do proposals.json funcionou (tem TODAS as cenas):
       python3 -c "import json;print(sorted(json.load(open('results/construct/$PROG/proposals.json'))))"

    2. O histórico guarda todas as versões (o force gerou uma nova):
       wc -l results/response/$PROG/responses.jsonl
       ls results/response/$PROG/scenes/ | wc -l
       → o .jsonl deve ter MAIS linhas que scenes/ tem arquivos

    3. Uma cena guarda tudo:
       python3 -m json.tool results/response/$PROG/scenes/$CENA_A1_ID.json
       → scene_caption_en, keywords_en, timestamp, diagnostics.{ranking,n_raw,warning}

    4. Os caches são separados por programa:
       ls meta/captions/
       → ${PROG}_blip.jsonl e ${PROG2}_blip.jsonl, arquivos distintos
FIM_TXT

titulo "RESULTADO"
printf "  ${VERDE}%d passou${FIM}   ${VERM}%d falhou${FIM}   ${AMAR}%d pulado${FIM}\n" "$PASSOU" "$FALHOU" "$PULADO"
echo
if [ "$FALHOU" -eq 0 ]; then
    echo "  ✓ Todos os casos executados passaram."
    [ "$PULADO" -gt 0 ] && echo "    (os pulados precisam de cenas que o seu conjunto não tem —"
    [ "$PULADO" -gt 0 ] && echo "     edite o teste_config.sh para apontá-las)"
else
    echo "  ✗ Há falhas acima — investigue antes de seguir."
fi
exit $([ "$FALHOU" -eq 0 ] && echo 0 || echo 1)
