#!/usr/bin/env bash
# =============================================================================
# verificar_contrato.sh — o contrato da resposta está íntegro?
#
# ★ POR QUE ESTE SCRIPT EXISTE
#   O teste_manual.sh usa `.get(chave, '?')` ao ler campos de diagnóstico.
#   Isso é robusto contra ausência — mas silencioso: se uma chave for
#   renomeada, o teste PASSA mostrando '?', e ninguém percebe que a
#   informação sumiu.
#
#   Aqui é o contrário: cada chave esperada é verificada EXPLICITAMENTE, e
#   a ausência de qualquer uma FALHA o script.
#
# USO
#     bash verificar_contrato.sh                 # lê o teste_papeis.sh
#     API=http://host:8000 CENA=/path/x.mp4 bash verificar_contrato.sh
# =============================================================================

AQUI="$(cd "$(dirname "$0")" && pwd)"
PAPEIS="${PAPEIS:-$AQUI/teste_papeis.sh}"

cV='\033[0;32m'; cR='\033[0;31m'; cF='\033[0m'
OK=0; ERRO=0

if [ -f "$PAPEIS" ]; then
    # shellcheck disable=SC1090
    . "$PAPEIS"
    CENA="${CENA:-$UNICA_PATH}"
    SID="${SID:-$UNICA_SID}"
    VID="${VID:-$UNICA_VID}"
    PID="${PID:-$PROGRAM_ID}"
fi
API="${API:-http://localhost:8000}"
[ -n "$CENA" ] || { echo "✗ informe CENA=/caminho/da/cena.mp4"; exit 1; }

echo "═══════════════════════════════════════════════════════════════════"
echo " VERIFICAÇÃO DO CONTRATO — $API"
echo "═══════════════════════════════════════════════════════════════════"

RESP=$(curl -s --max-time 900 -X POST "$API/caption" \
       -H 'Content-Type: application/json' \
       -d "{\"scene_id\":\"$SID\",\"video_id\":\"$VID\",\"program_id\":\"$PID\",\"scene_video_path\":\"$CENA\"}" 2>/dev/null)

[ -n "$RESP" ] || { printf "${cR}✗ a API não respondeu${cF}\n"; exit 1; }

verificar() {  # verificar <rótulo> <expressão python sobre d>
    local r
    r=$(echo "$RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
try:
    v = $2
    print('OK' if v is not None else 'AUSENTE')
except (KeyError, IndexError, TypeError):
    print('AUSENTE')
" 2>/dev/null)
    if [ "$r" = "OK" ]; then OK=$((OK+1)); printf "  ${cV}✓${cF} %s\n" "$1"
    else ERRO=$((ERRO+1)); printf "  ${cR}✗ %s — AUSENTE ou renomeado${cF}\n" "$1"; fi
}

echo
echo "  --- envelope ---"
for c in state program_id summary items groups persisted seconds; do
    verificar "$c" "d['$c']"
done

echo
echo "  --- summary ---"
for c in total ok errors; do verificar "summary.$c" "d['summary']['$c']"; done

echo
echo "  --- items[0] ---"
for c in scene_id scene_caption_en keywords_en model_name model_version status; do
    verificar "items[0].$c" "d['items'][0]['$c']"
done
verificar "items[0].keywords_en[0].token"  "d['items'][0]['keywords_en'][0]['token']"
verificar "items[0].keywords_en[0].weight" "d['items'][0]['keywords_en'][0]['weight']"

echo
echo "  --- groups[0] ---"
for c in directory collection scenes from_cache cache_cleared annos exp_dir merge; do
    verificar "groups[0].$c" "d['groups'][0]['$c']"
done
verificar "groups[0].merge.merged" "d['groups'][0]['merge']['merged']"
verificar "groups[0].merge.total"  "d['groups'][0]['merge']['total']"

echo
echo "  --- persisted ---"
for c in written replaced total_in_program jsonl scenes_dir; do
    verificar "persisted.$c" "d['persisted']['$c']"
done

echo
echo "  --- as chaves ANTIGAS não podem voltar ---"
antiga() {
    local r
    r=$(echo "$RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('PRESENTE' if '$2' in json.dumps(d) else 'ausente')
" 2>/dev/null)
    if [ "$r" = "ausente" ]; then OK=$((OK+1)); printf "  ${cV}✓${cF} '%s' não aparece\n" "$2"
    else ERRO=$((ERRO+1)); printf "  ${cR}✗ '%s' VOLTOU — o contrato regrediu${cF}\n" "$2"; fi
}
for k in '"diretorio"' '"estavam_em_cache"' '"cache_limpo"' '"fundidas"' '"gravadas"' '"job_id"' '"resumo"' '"erros"' '"segundos"'; do
    antiga "" "$(echo "$k" | tr -d '"')"
done

echo
echo "═══════════════════════════════════════════════════════════════════"
printf "  ${cV}%d ok${cF}   ${cR}%d problema(s)${cF}\n" "$OK" "$ERRO"
[ "$ERRO" -eq 0 ] && echo "  ✓ contrato íntegro" || echo "  ✗ o contrato mudou — atualize quem o consome"
exit $([ "$ERRO" -eq 0 ] && echo 0 || echo 1)
