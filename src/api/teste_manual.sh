#!/usr/bin/env bash
# =============================================================================
# teste_manual.sh — as combinações de POST /caption e POST /caption/batch
#
# PRÉ-REQUISITOS
#   1. preencher o teste_config.sh
#   2. bash preparar_teste.sh
#   3. o serviço no ar, COM os modelos
#
# USO
#     bash teste_manual.sh          # tudo, em série
#     bash teste_manual.sh 7        # só o caso 7
#
# ★ NATUREZA EM SÉRIE
#   Cada requisição só é disparada depois que a anterior devolveu resposta.
#   Não há paralelismo: o `curl` é bloqueante e os casos rodam em sequência.
#   Vários casos DEPENDEM do anterior (o cache do 6 vem do 5; o force do 7
#   precisa do 6). Por isso, rodar um caso isolado pode dar resultado
#   diferente de rodá-lo na sequência.
#
# ★ SÓ OS DOIS FORMATOS ESSENCIAIS
#     POST /caption        { scene_id, video_id, program_id, scene_video_path }
#     POST /caption/batch  { items: [ {...}, ... ] }
#   Campos extras (force, assincrono, callback_url) só onde o teste exige.
# =============================================================================

AQUI="$(cd "$(dirname "$0")" && pwd)"
PAPEIS="${PAPEIS:-$AQUI/teste_papeis.sh}"
SO="${1:-}"

# ⚠️ nomes de cor com 2 letras: R/A/V colidiriam com $R (corpo da resposta),
# $A e $V usados no script. Foi o que embaralhou o resumo final.
cV='\033[0;32m'; cR='\033[0;31m'; cA='\033[0;33m'; cC='\033[0;36m'; cF='\033[0m'
OK=0; ERRO=0; PULO=0

[ -f "$PAPEIS" ] || { printf "${cR}✗ falta o %s${cF}\n  Rode: bash preparar_teste.sh\n" "$PAPEIS"; exit 1; }
# shellcheck disable=SC1090
. "$PAPEIS"

t()    { echo; echo "═══════════════════════════════════════════════════════════════════"; echo " $1"; echo "═══════════════════════════════════════════════════════════════════"; }
pula() { [ -n "$SO" ] && [ "$SO" != "$1" ]; }
ok()   { OK=$((OK+1));     printf "  ${cV}✓${cF} %s\n" "$1"; }
nok()  { ERRO=$((ERRO+1)); printf "  ${cR}✗${cF} %s\n       %s\n" "$1" "$2"; }
skip() { PULO=$((PULO+1)); printf "  ${cA}○${cF} %s\n       pulado: %s\n" "$1" "$2"; }
det()  { printf "       ${cC}%s${cF}\n" "$1"; }

# ⚠️ As funções definem $HTTP e $R e são chamadas SEM $( ) — dentro de uma
# substituição de comando elas rodariam num subshell e as variáveis não
# propagariam para cá.
_B=$(mktemp); trap 'rm -f "$_B"' EXIT

POST() {  # POST <rota> <json>
    HTTP=$(curl -s -o "$_B" -w '%{http_code}' --max-time "$TIMEOUT" \
           -X POST "$API$1" -H 'Content-Type: application/json' -d "$2" 2>/dev/null)
    R=$(cat "$_B")
}
GET() {
    HTTP=$(curl -s -o "$_B" -w '%{http_code}' --max-time "$TIMEOUT" "$API$1" 2>/dev/null)
    R=$(cat "$_B")
}
J() { echo "$1" | python3 -c "import sys,json;d=json.load(sys.stdin);print($2)" 2>/dev/null; }

# item <sid> <vid> <path> [program_id]
item() {
    printf '{"scene_id":"%s","video_id":"%s","program_id":"%s","scene_video_path":"%s"}' \
           "$1" "$2" "${4:-$PROGRAM_ID}" "$3"
}

# =============================================================================
t "CONFIGURAÇÃO"
printf "  %-16s %s\n" "API"        "$API"
printf "  %-16s %s\n" "program_id" "$PROGRAM_ID"
printf "  %-16s %s cena(s) em %s diretório(s)\n" "cenas" "$N_CENAS" "$N_DIRS"
echo
printf "  %-11s %-20s %s\n" "papel" "scene_id" "video_id"
echo "  ────────────────────────────────────────────────"
printf "  %-11s %-20s %s\n" "UNICA"   "${UNICA_SID:-—}"   "${UNICA_VID:-—}"
printf "  %-11s %-20s %s\n" "LOTE_A1" "${LOTE_A1_SID:-—}" "${LOTE_A1_VID:-—}"
printf "  %-11s %-20s %s\n" "LOTE_A2" "${LOTE_A2_SID:-—}" "${LOTE_A2_VID:-—}"
printf "  %-11s %-20s %s\n" "LOTE_B1" "${LOTE_B1_SID:-—}" "${LOTE_B1_VID:-—}"
printf "  %-11s %-20s %s\n" "CURTA"   "${CURTA_SID:-—}"   "${CURTA_DUR:+${CURTA_DUR}s}"
printf "  %-11s %-20s %s\n" "ISOLAM." "${ISO_SID:-—}"     "${PROGRAM_ID_2:-—}"

# =============================================================================
t "PRÉ-VOO"
command -v curl >/dev/null || { printf "  ${cR}✗ curl não encontrado${cF}\n"; exit 1; }
GET /health
if [ "$HTTP" != "200" ]; then
    printf "  ${cR}✗ a API não respondeu em %s (HTTP %s)${cF}\n" "$API" "$HTTP"
    echo "    Isto NÃO tem relação com as cenas — é só o GET /health."
    echo "    Confira: o serviço está no ar? é esta a porta? (teste_config.sh)"
    exit 1
fi
PRONTO=$(J "$R" "d['models']['ready']")
GPU0=$(J "$R" "d['models']['gpu'].get('allocated_mb','—')")
echo "  API              : ok"
echo "  models.ready     : $PRONTO"
echo "  gpu.allocated_mb : $GPU0"
[ "$PRONTO" = "True" ] || { printf "\n  ${cR}✗ modelos não carregados${cF} — suba sem REFCAP_CARREGAR_MODELOS=0\n"; exit 1; }

# =============================================================================
t "BLOCO 1 — POST /caption  (formato de cena única)"

# --- 1. o caso base ---
if ! pula 1; then
    if [ -z "$UNICA_SID" ]; then skip "1. cena única" "sem cenas"
    else
        POST /caption "$(item "$UNICA_SID" "$UNICA_VID" "$UNICA_PATH")"
        S=$(J "$R" "d['items'][0]['status']"); CAP=$(J "$R" "d['items'][0]['scene_caption_en']")
        if [ "$HTTP" = "200" ] && [ "$S" = "success" ] && [ -n "$CAP" ]; then
            ok "1. POST /caption — $UNICA_SID"
            det "state   : $(J "$R" "d['state']")"
            det "summary : $(J "$R" "json.dumps(d['summary'])")"
            det "legenda : $CAP"
            det "keywords: $(J "$R" "', '.join(k['token'] for k in d['items'][0]['keywords_en'])")"
        else nok "1. POST /caption" "HTTP=$HTTP status=$S"; fi
    fi
fi

# --- 2. cena < 1s (o patch do viddataset) ---
if ! pula 2; then
    if [ -z "$CURTA_SID" ]; then skip "2. ★ cena com menos de 1s" "nenhuma no conjunto"
    else
        POST /caption "$(item "$CURTA_SID" "$CURTA_VID" "$CURTA_PATH")"
        S=$(J "$R" "d['items'][0]['status']")
        if [ "$HTTP" = "200" ] && [ "$S" = "success" ]; then
            ok "2. ★ cena de ${CURTA_DUR}s — o patch max(1,int(duration))"
            det "legenda: $(J "$R" "d['items'][0]['scene_caption_en']")"
        else nok "2. cena curta" "HTTP=$HTTP status=$S — o patch foi aplicado?"; fi
    fi
fi

# --- 3. caminho inexistente ---
if ! pula 3; then
    POST /caption "$(item "cena_fantasma" "vidX" "/caminho/que/nao/existe/x.mp4")"
    E=$(J "$R" "d['items'][0]['error_code']")
    if [ "$HTTP" = "200" ] && [ "$E" = "FILE_NOT_FOUND" ]; then
        ok "3. caminho inexistente → FILE_NOT_FOUND"
        det "HTTP 200 com o erro DENTRO do item — não 4xx"
    else nok "3. FILE_NOT_FOUND" "HTTP=$HTTP error_code=$E"; fi
fi

# --- 4. diretório sem a cena ---
if ! pula 4; then
    POST /caption "$(item "cena_ausente" "vidX" "$DIR_VAZIO")"
    E=$(J "$R" "d['items'][0]['error_code']")
    [ "$E" = "SCENE_NOT_FOUND" ] && ok "4. diretório vazio → SCENE_NOT_FOUND" \
        || nok "4. SCENE_NOT_FOUND" "error_code=$E"
fi

# --- 5. ★ o fallback removido ---
if ! pula 5; then
    if [ -z "$DIR_COM_VIDEO" ]; then skip "5. ★ fallback removido" "sem diretório de referência"
    else
        POST /caption "$(item "id_inexistente_ali" "vidX" "$DIR_COM_VIDEO")"
        E=$(J "$R" "d['items'][0]['error_code']")
        if [ "$E" = "SCENE_NOT_FOUND" ]; then
            ok "5. ★ fallback removido — não legenda o vídeo errado"
            det "pedi um scene_id inexistente num diretório que TEM vídeos"
        else nok "5. fallback removido" "error_code=$E — deveria recusar"; fi
    fi
fi

# =============================================================================
t "BLOCO 2 — CACHE  (em série: 6 depende de 1; 7 depende de 6)"

# --- 6. reprocessar: deve PULAR ---
if ! pula 6; then
    if [ -z "$UNICA_SID" ]; then skip "6. reprocessar (cache)" "sem cenas"
    else
        T0=$(date +%s%N)
        POST /caption "$(item "$UNICA_SID" "$UNICA_VID" "$UNICA_PATH")"
        T1=$(date +%s%N); MS_CACHE=$(( (T1-T0)/1000000 ))
        S=$(J "$R" "d['items'][0]['status']")
        EM=$(J "$R" "d['groups'][0].get('estavam_em_cache','?')")
        if [ "$S" = "success" ]; then
            ok "6. reprocessar SEM force — ${MS_CACHE}ms"
            det "estavam_em_cache: $EM   ← 1 = o BLIP não rodou de novo"
        else nok "6. reprocessar" "status=$S"; fi
    fi
fi

# --- 7. force: deve REPROCESSAR ---
if ! pula 7; then
    if [ -z "$UNICA_SID" ]; then skip "7. force" "sem cenas"
    else
        P=$(python3 -c "
import json
d = json.loads('''$(item "$UNICA_SID" "$UNICA_VID" "$UNICA_PATH")''')
d['force'] = True
print(json.dumps(d))")
        T0=$(date +%s%N); POST /caption "$P"; T1=$(date +%s%N)
        MS_FORCE=$(( (T1-T0)/1000000 ))
        S=$(J "$R" "d['items'][0]['status']")
        if [ "$S" = "success" ]; then
            ok "7. force: true — ${MS_FORCE}ms"
            det "cache_limpo: $(J "$R" "d['groups'][0].get('cache_limpo')")"
            if [ -n "$MS_CACHE" ] && [ "$MS_FORCE" -gt "$MS_CACHE" ]; then
                det "★ ${MS_FORCE}ms > ${MS_CACHE}ms — reprocessou de verdade"
            elif [ -n "$MS_CACHE" ]; then
                printf "       ${cA}⚠️  %sms não é maior que %sms — o cache foi limpo mesmo?${cF}\n" "$MS_FORCE" "$MS_CACHE"
            fi
        else nok "7. force" "status=$S"; fi
    fi
fi

# =============================================================================
t "BLOCO 3 — POST /caption/batch  (formato items)"

# --- 8. lote no MESMO diretório: 1 grupo ---
if ! pula 8; then
    if [ -z "$LOTE_A1_SID" ] || [ -z "$LOTE_A2_SID" ]; then
        skip "8. lote — mesmo diretório" "precisa de 2 cenas no mesmo video_id"
    else
        POST /caption/batch "{\"items\":[$(item "$LOTE_A1_SID" "$LOTE_A1_VID" "$LOTE_A1_PATH"),$(item "$LOTE_A2_SID" "$LOTE_A2_VID" "$LOTE_A2_PATH")]}"
        T=$(J "$R" "d['summary']['total']"); O=$(J "$R" "d['summary']['ok']"); G=$(J "$R" "len(d['groups'])")
        if [ "$HTTP" = "200" ] && [ "$O" = "2" ] && [ "$G" = "1" ]; then
            ok "8. lote de 2 no MESMO diretório"
            det "grupos: $G  ← um só build(), como esperado"
        else nok "8. lote mesmo diretório" "HTTP=$HTTP total=$T ok=$O grupos=$G (esperava 1 grupo)"; fi
    fi
fi

# --- 9. ★ lote em diretórios DIFERENTES: N grupos ---
if ! pula 9; then
    if [ -z "$LOTE_B1_SID" ]; then
        skip "9. ★ lote — diretórios diferentes" "só 1 diretório (informe 2 VIDEO_IDS)"
    else
        POST /caption/batch "{\"items\":[$(item "$LOTE_A1_SID" "$LOTE_A1_VID" "$LOTE_A1_PATH"),$(item "$LOTE_B1_SID" "$LOTE_B1_VID" "$LOTE_B1_PATH")]}"
        O=$(J "$R" "d['summary']['ok']"); G=$(J "$R" "len(d['groups'])")
        if [ "$HTTP" = "200" ] && [ "$O" = "2" ] && [ "$G" = "2" ]; then
            ok "9. ★ lote em 2 diretórios → 2 builds"
            det "$(J "$R" "chr(10).join('       %s cena(s) em %s' % (g['cenas'], g['diretorio']) for g in d['groups'])")"
        else nok "9. agrupamento" "HTTP=$HTTP ok=$O grupos=$G (esperava 2)"; fi
    fi
fi

# --- 10. lote de UMA cena só ---
if ! pula 10; then
    if [ -z "$UNICA_SID" ]; then skip "10. lote de 1" "sem cenas"
    else
        POST /caption/batch "{\"items\":[$(item "$UNICA_SID" "$UNICA_VID" "$UNICA_PATH")]}"
        O=$(J "$R" "d['summary']['ok']")
        [ "$HTTP" = "200" ] && [ "$O" = "1" ] && ok "10. lote com UMA cena (borda)" \
            || nok "10. lote de 1" "HTTP=$HTTP ok=$O"
    fi
fi

# --- 11. ★ erro parcial: uma ruim não derruba as outras ---
if ! pula 11; then
    if [ -z "$LOTE_A1_SID" ]; then skip "11. ★ erro parcial" "sem cenas"
    else
        POST /caption/batch "{\"items\":[$(item "$LOTE_A1_SID" "$LOTE_A1_VID" "$LOTE_A1_PATH"),$(item "ruim" "vidX" "/nada/x.mp4"),$(item "$UNICA_SID" "$UNICA_VID" "$UNICA_PATH")]}"
        O=$(J "$R" "d['summary']['ok']"); E=$(J "$R" "d['summary']['errors']")
        if [ "$HTTP" = "200" ] && [ "$O" = "2" ] && [ "$E" = "1" ]; then
            ok "11. ★ erro parcial não derruba o lote"
            det "ok=$O errors=$E, e HTTP 200 — não 500"
            det "o item ruim: $(J "$R" "[i['error_code'] for i in d['items'] if i['status']=='error'][0]")"
        else nok "11. erro parcial" "HTTP=$HTTP ok=$O errors=$E"; fi
    fi
fi

# --- 12. ★ cenas REPETIDAS no mesmo lote ---
if ! pula 12; then
    if [ -z "$UNICA_SID" ]; then skip "12. cena repetida no lote" "sem cenas"
    else
        POST /caption/batch "{\"items\":[$(item "$UNICA_SID" "$UNICA_VID" "$UNICA_PATH"),$(item "$UNICA_SID" "$UNICA_VID" "$UNICA_PATH")]}"
        T=$(J "$R" "d['summary']['total']")
        if [ "$HTTP" = "200" ]; then
            ok "12. mesma cena repetida no lote (borda)"
            det "total=$T — o pipeline não quebra com duplicatas"
        else nok "12. cena repetida" "HTTP=$HTTP"; fi
    fi
fi

# --- 13. TODAS as cenas de uma vez ---
if ! pula 13; then
    ITENS=$(python3 - <<PYEOF
import json
todas = "$TODAS".split()
out = []
for t in todas:
    v, s, c = t.split(":", 2)
    out.append({"scene_id": s, "video_id": v,
                "program_id": "$PROGRAM_ID", "scene_video_path": c})
print(json.dumps({"items": out}))
PYEOF
)
    POST /caption/batch "$ITENS"
    T=$(J "$R" "d['summary']['total']"); O=$(J "$R" "d['summary']['ok']"); G=$(J "$R" "len(d['groups'])")
    if [ "$HTTP" = "200" ] && [ "$O" = "$T" ]; then
        ok "13. TODAS as $N_CENAS cenas num lote"
        det "total=$T ok=$O grupos=$G"
    elif [ "$HTTP" = "202" ]; then
        skip "13. todas as cenas" "passou do limiar → virou assíncrono (veja o caso 14)"
    else nok "13. lote completo" "HTTP=$HTTP total=$T ok=$O"; fi
fi

# --- 14. assíncrono acima do limiar ---
if ! pula 14; then
    if [ "$N_CENAS" -le "$LIMIAR_ASSINCRONO" ]; then
        skip "14. assíncrono automático" "$N_CENAS cenas ≤ limiar $LIMIAR_ASSINCRONO — reinicie o serviço com REFCAP_LIMIAR_ASSINCRONO=2"
    else
        POST /caption/batch "$ITENS"
        if [ "$HTTP" = "202" ]; then
            ok "14. ★ acima do limiar → 202 assíncrono"
            det "state=$(J "$R" "d['state']")  check_at=$(J "$R" "d['check_at']")"
            sleep 10
        else nok "14. assíncrono" "HTTP=$HTTP (esperava 202)"; fi
    fi
fi

# =============================================================================
t "BLOCO 4 — CONSULTA E PERSISTÊNCIA"

if ! pula 15; then
    GET "/caption/$PROGRAM_ID"
    T=$(J "$R" "d['summary']['total']")
    if [ "$HTTP" = "200" ] && [ -n "$T" ] && [ "$T" -ge 1 ]; then
        ok "15. GET /caption/$PROGRAM_ID — o persistido"
        det "cenas gravadas: $T"
    else nok "15. GET todas" "HTTP=$HTTP total=$T"; fi
fi

if ! pula 16; then
    GET "/caption/$PROGRAM_ID?scene_id=$UNICA_SID"
    T=$(J "$R" "d['summary']['total']")
    [ "$T" = "1" ] && ok "16. GET com filtro de 1 cena" || nok "16. filtro 1" "total=$T"
fi

if ! pula 17; then
    if [ -z "$LOTE_A1_SID" ]; then skip "17. GET com 2 filtros" "sem segunda cena"
    else
        GET "/caption/$PROGRAM_ID?scene_id=$UNICA_SID&scene_id=$LOTE_A1_SID"
        T=$(J "$R" "d['summary']['total']")
        [ "$T" = "2" ] && ok "17. GET com filtro de 2 cenas" || nok "17. filtro 2" "total=$T"
    fi
fi

if ! pula 18; then
    GET "/caption/programa_que_nunca_existiu"
    T=$(J "$R" "d['summary']['total']")
    { [ "$HTTP" = "200" ] && [ "$T" = "0" ]; } \
        && ok "18. GET de programa inexistente → 200 + vazio" \
        || nok "18. GET inexistente" "HTTP=$HTTP total=$T"
fi

# =============================================================================
t "BLOCO 5 — ISOLAMENTO ENTRE PROGRAMAS"

if ! pula 19; then
    if [ -z "$ISO_SID" ]; then skip "19. ★ isolamento" "sem PROGRAM_ID_2 no teste_config.sh"
    else
        POST /caption "$(item "$ISO_SID" "$ISO_VID" "$ISO_PATH" "$PROGRAM_ID_2")"
        S=$(J "$R" "d['items'][0]['status']")
        if [ "$HTTP" = "200" ] && [ "$S" = "success" ]; then
            C2=$(J "$R" "d['items'][0]['scene_caption_en']")
            ok "19. cena no segundo programa ($PROGRAM_ID_2)"
            det "legenda: $C2"
            if [ "$ISO_MESMO_SID" = "1" ]; then
                GET "/caption/$PROGRAM_ID?scene_id=$ISO_SID"
                C1=$(J "$R" "d['items'][0]['scene_caption_en']")
                det "$PROGRAM_ID/$ISO_SID  : ${C1:-—}"
                det "$PROGRAM_ID_2/$ISO_SID: $C2"
                if [ -n "$C1" ] && [ "$C1" = "$C2" ]; then
                    printf "       ${cA}⚠️  legendas IGUAIS — se os vídeos diferem, o cache VAZOU${cF}\n"
                elif [ -n "$C1" ]; then
                    det "★ legendas DIFERENTES — caches isolados por program_id"
                fi
            fi
        else nok "19. isolamento" "HTTP=$HTTP status=$S"; fi
    fi
fi

if ! pula 20; then
    if [ -z "$PROGRAM_ID_2" ]; then skip "20. GET do segundo programa" "sem PROGRAM_ID_2"
    else
        GET "/caption/$PROGRAM_ID_2"
        T=$(J "$R" "d['summary']['total']")
        [ "$HTTP" = "200" ] && [ -n "$T" ] && [ "$T" -ge 1 ] \
            && { ok "20. GET /caption/$PROGRAM_ID_2 — persistido separado"; det "cenas: $T"; } \
            || nok "20. GET programa 2" "HTTP=$HTTP total=$T"
    fi
fi

# =============================================================================
t "FECHAMENTO — os modelos ficaram residentes?"
GET /health; GPU1=$(J "$R" "d['models']['gpu'].get('allocated_mb','—')")
echo "  allocated_mb no início : $GPU0"
echo "  allocated_mb no fim    : $GPU1"
if [ "$GPU0" = "$GPU1" ]; then
    printf "  ${cV}✓ IGUAL — nenhuma requisição recarregou modelo${cF}\n"
else
    printf "  ${cA}⚠️  mudou — investigue se algo está recarregando${cF}\n"
fi

t "RESULTADO"
printf "  ${cV}%d passou${cF}   ${cR}%d falhou${cF}   ${cA}%d pulado${cF}\n" "$OK" "$ERRO" "$PULO"
echo
if [ "$ERRO" -eq 0 ]; then
    echo "  ✓ Todos os casos executados passaram."
    [ "$PULO" -gt 0 ] && echo "    Os pulados precisam de cenas que o conjunto não tem —"
    [ "$PULO" -gt 0 ] && echo "    ajuste o teste_config.sh (VIDEO_IDS, PROGRAM_ID_2) para cobri-los."
else
    echo "  ✗ Há falhas acima."
fi
exit $([ "$ERRO" -eq 0 ] && echo 0 || echo 1)
