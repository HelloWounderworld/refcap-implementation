#!/usr/bin/env bash
# =============================================================================
# diagnostico_mount.sh — por que o diretório montado "não é encontrado"
#
# ★ A PERGUNTA CENTRAL
#   Não é "o diretório existe?" — é "existe PARA QUEM?".
#
#   O shell roda como VOCÊ. O serviço roda como o usuário do supervisord
#   (ou do systemd). Uma montagem CIFS/SMB feita por um usuário costuma ser
#   INVISÍVEL para os outros, a menos que tenha sido montada com as opções
#   certas. Daí o sintoma: você faz `ls` e vê tudo, o serviço diz 404.
#
#   Este script checa os dois lados e compara.
#
# USO
#     bash diagnostico_mount.sh                    # lê o teste_config.sh
#     bash diagnostico_mount.sh /caminho/montado
#     API=http://host:8000 bash diagnostico_mount.sh /caminho
# =============================================================================

AQUI="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${CONFIG:-$AQUI/teste_config.sh}"

cV='\033[0;32m'; cR='\033[0;31m'; cA='\033[0;33m'; cC='\033[0;36m'; cF='\033[0m'
t() { echo; echo "═══════════════════════════════════════════════════════════════════"; echo " $1"; echo "═══════════════════════════════════════════════════════════════════"; }
ok()  { printf "  ${cV}✓${cF} %s\n" "$1"; }
mal() { printf "  ${cR}✗${cF} %s\n" "$1"; }
av()  { printf "  ${cA}⚠️${cF}  %s\n" "$1"; }
det() { printf "     ${cC}%s${cF}\n" "$1"; }

# --------------------------------------------------------------------------- #
if [ -n "$1" ]; then
    BASE="$1"
elif [ -f "$CONFIG" ]; then
    . "$CONFIG"
    API="${API:-${API_SCHEME:-http}://${API_HOST:-localhost}:${API_PORT:-8000}}"
else
    echo "Uso: bash diagnostico_mount.sh /caminho/montado"; exit 1
fi
API="${API:-http://localhost:8000}"

t "O QUE ESTAMOS INVESTIGANDO"
printf "  %-14s %s\n" "BASE"        "$BASE"
printf "  %-14s %s\n" "PROGRAM_ID"  "${PROGRAM_ID:-—}"
printf "  %-14s %s\n" "API"         "$API"
printf "  %-14s %s (uid=%s)\n" "seu usuário" "$(id -un)" "$(id -u)"

# =============================================================================
t "0. ★ A API RODA EM CONTAINER?"

EM_DOCKER=0
if command -v docker >/dev/null 2>&1; then
    CTR=$(docker ps --format '{{.Names}}\t{{.Ports}}' 2>/dev/null | grep -iE 'caption|refcap|api' | head -1)
    if [ -n "$CTR" ]; then
        EM_DOCKER=1
        NOME=$(echo "$CTR" | cut -f1)
        ok "container encontrado: $NOME"
        det "portas: $(echo "$CTR" | cut -f2)"
        echo
        printf "  ${cA}★ ISTO MUDA TUDO${cF}\n"
        echo "    O container tem o PRÓPRIO filesystem. Uma montagem SMB feita no"
        echo "    host NÃO existe dentro dele, a menos que seja bind-montada."
        echo
        echo "    E os valores seguem regras OPOSTAS:"
        echo "      a URL da API      -> porta do HOST"
        echo "      o scene_video_path -> caminho do CONTAINER"
        echo
        echo "  Os bind-mounts deste container:"
        docker inspect "$NOME" --format '{{range .Mounts}}     {{.Source}} -> {{.Destination}} ({{if .RW}}rw{{else}}ro{{end}}){{"\n"}}{{end}}' 2>/dev/null
        echo
        echo "  ★ O container enxerga a BASE?"
        if docker exec "$NOME" test -d "$BASE" 2>/dev/null; then
            ok "SIM — $BASE existe DENTRO do container"
            det "$(docker exec "$NOME" ls "$BASE" 2>/dev/null | head -5 | tr '\n' ' ')"
        else
            mal "NÃO — $BASE não existe dentro do container"
            echo
            echo "     ★ ESTA É A CAUSA. Acrescente ao docker-compose.yml:"
            echo
            echo "         volumes:"
            echo "           - $BASE:$BASE:ro"
            echo
            echo "     Usar o MESMO caminho dos dois lados evita ter de traduzir"
            echo "     entre host e container. Depois:  docker compose up -d"
        fi
    else
        det "nenhum container com nome caption/refcap/api rodando"
        det "(se a API roda direto no host, ignore este bloco)"
    fi
else
    det "docker não encontrado — assumindo que a API roda no host"
fi

t "1. O CAMINHO, VISTO DAQUI (o seu shell$([ "$EM_DOCKER" = "1" ] && echo ", no HOST"))"

if [ -d "$BASE" ]; then
    ok "o diretório EXISTE para o usuário $(id -un)"
else
    mal "o diretório NÃO existe para o usuário $(id -un)"
    det "confira digitação, e se a montagem está de pé"
fi

if [ -r "$BASE" ]; then ok "você tem permissão de LEITURA"
else mal "SEM permissão de leitura"; fi

if [ -x "$BASE" ]; then ok "você pode ATRAVESSAR o diretório (bit x)"
else mal "SEM bit de execução — não dá para entrar nele"; fi

echo
echo "  Permissões e dono:"
ls -ld "$BASE" 2>/dev/null | sed 's/^/     /' || det "(não consegui ler)"

# =============================================================================
t "2. É UMA MONTAGEM? DE QUE TIPO?"

MONTAGEM=""
if command -v findmnt >/dev/null; then
    MONTAGEM=$(findmnt -T "$BASE" -o TARGET,SOURCE,FSTYPE,OPTIONS 2>/dev/null)
    [ -n "$MONTAGEM" ] && echo "$MONTAGEM" | sed 's/^/     /'
else
    MONTAGEM=$(mount 2>/dev/null | grep -F "$BASE")
    [ -n "$MONTAGEM" ] && echo "$MONTAGEM" | sed 's/^/     /'
fi

FSTYPE=$(findmnt -T "$BASE" -no FSTYPE 2>/dev/null)
OPCOES=$(findmnt -T "$BASE" -no OPTIONS 2>/dev/null)

echo
case "$FSTYPE" in
    cifs|smb3|smbfs)
        ok "é uma montagem CIFS/SMB"
        echo
        echo "  ★ AS OPÇÕES QUE DECIDEM QUEM ENXERGA:"
        for opt in uid gid file_mode dir_mode noperm multiuser; do
            valor=$(echo "$OPCOES" | tr ',' '\n' | grep "^${opt}" | head -1)
            if [ -n "$valor" ]; then printf "     ${cV}✓${cF} %s\n" "$valor"
            else printf "     ${cA}○${cF} %s (ausente)\n" "$opt"; fi
        done
        echo
        if ! echo "$OPCOES" | grep -q "uid="; then
            av "SEM uid= na montagem"
            det "Sem ele, os arquivos pertencem a quem montou — e o usuário do"
            det "serviço pode não conseguir ler, mesmo o caminho existindo."
        fi
        ;;
    nfs|nfs4)  ok "é NFS — as observações sobre uid/gid valem igual" ;;
    "")        av "não identifiquei montagem — o caminho pode ser local" ;;
    *)         ok "sistema de arquivos: $FSTYPE" ;;
esac

# =============================================================================
t "3. A ESTRUTURA ESPERADA"

if [ -d "$BASE" ]; then
    echo "  Subdiretórios de BASE (seriam os program_id):"
    find "$BASE" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -10 | \
        while read -r d; do printf "     %s\n" "$(basename "$d")"; done
    N=$(find "$BASE" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
    [ "$N" -eq 0 ] && av "nenhum subdiretório — a BASE está no nível certo?"

    if [ -n "$PROGRAM_ID" ]; then
        echo
        D="$BASE/$PROGRAM_ID"
        if [ -d "$D" ]; then
            ok "$PROGRAM_ID existe"
            echo "     video_id lá dentro:"
            find "$D" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -8 | \
                while read -r v; do
                    n=$(find "$v" -maxdepth 1 -iname '*.mp4' 2>/dev/null | wc -l)
                    printf "       %-24s %s .mp4\n" "$(basename "$v")" "$n"
                done
        else
            mal "$PROGRAM_ID NÃO existe em $BASE"
            det "★ atenção à CAIXA: montagens SMB podem ser case-insensitive no"
            det "  Windows, mas o Linux compara byte a byte. 'Prog' ≠ 'prog'."
        fi
    fi
fi

# =============================================================================
t "4. ★ O QUE O SERVIÇO VÊ  (a comparação que importa)"

if ! command -v curl >/dev/null; then
    av "curl ausente — pulando esta parte"
elif ! curl -s -m 5 -o /dev/null "$API/health" 2>/dev/null; then
    av "a API não respondeu em $API — não dá para comparar"
    det "suba o serviço e rode este script de novo"
else
    # Um caminho que EXISTE aqui: pedimos ao serviço e vemos o que ele diz.
    ALVO=$(find "$BASE" -iname '*.mp4' 2>/dev/null | head -1)
    if [ -z "$ALVO" ]; then
        av "nenhum .mp4 encontrado aqui — sem alvo para comparar"
    else
        echo "  arquivo de teste (existe para VOCÊ):"
        det "$ALVO"
        echo
        RESP=$(curl -s -m 20 --get "$API/diagnostics/caption" \
               --data-urlencode "scene_video_path=$ALVO" 2>/dev/null)
        CODIGO=$(curl -s -m 20 -o /dev/null -w '%{http_code}' --get \
                 "$API/diagnostics/caption" \
                 --data-urlencode "scene_video_path=$ALVO" 2>/dev/null)

        if [ "$CODIGO" = "404" ]; then
            mal "o SERVIÇO não enxerga esse arquivo (HTTP 404)"
            echo
            echo "$RESP" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin).get('detail', {})
except Exception:
    print('     (resposta ilegível)'); raise SystemExit
print(f\"     o diretório pai existe para o serviço? {d.get('existe_o_diretorio')}\")
viz = d.get('primeiros_arquivos_la') or []
print(f\"     o que o serviço lista lá: {viz if viz else '(nada)'}\")
" 2>/dev/null
            echo
            printf "  ${cA}★ ESTE É O DIAGNÓSTICO:${cF} o caminho existe para você e não para\n"
            echo "    o serviço. Quase sempre é uma destas três coisas:"
            echo
            echo "    a) USUÁRIOS DIFERENTES"
            echo "       Você roda como $(id -un); o serviço roda como o 'user=' do"
            echo "       supervisord. Confira:"
            echo "           grep -E '^user=' /etc/supervisor/conf.d/*.conf"
            echo "           sudo -u <usuario_do_servico> ls '$BASE'"
            echo
            echo "    b) A MONTAGEM NÃO É COMPARTILHADA"
            echo "       Montagem feita por um usuário não aparece para outros."
            echo "       Remonte com uid/gid do usuário do serviço:"
            echo "           sudo mount -t cifs //servidor/share '$BASE' \\"
            echo "             -o username=USER,uid=\$(id -u SERVICO),gid=\$(id -g SERVICO),\\"
            echo "                file_mode=0644,dir_mode=0755"
            echo
            echo "    c) NAMESPACE DE MONTAGEM ISOLADO"
            echo "       Se o supervisord/systemd sobe com namespace próprio, ele"
            echo "       não vê montagens feitas depois. Reinicie o serviço:"
            echo "           sudo supervisorctl restart refcap-api"
        elif [ -n "$CODIGO" ]; then
            ok "o serviço TAMBÉM enxerga o arquivo (HTTP $CODIGO)"
            det "o problema não é de montagem — confira BASE/PROGRAM_ID no teste_config.sh"
        fi
    fi
fi

# =============================================================================
t "5. CHECAGENS EXTRAS QUE COSTUMAM PEGAR"

# espaços ou caracteres invisíveis
if [ "$BASE" != "$(echo "$BASE" | tr -d '[:space:]' | sed 's|/*$||')" ]; then
    LIMPO=$(echo "$BASE" | xargs)
    [ "$BASE" != "$LIMPO" ] && av "a BASE tem espaço no início ou fim — remova as aspas soltas"
fi
case "$BASE" in
    */) av "a BASE termina com '/' — funciona, mas evite para os caminhos não ficarem com '//'" ;;
esac
case "$BASE" in
    ~*) mal "a BASE usa '~' — dentro de aspas ele NÃO é expandido. Use o caminho absoluto." ;;
esac

# a montagem caiu?
if [ -d "$BASE" ] && [ -z "$(ls -A "$BASE" 2>/dev/null)" ]; then
    av "o diretório existe mas está VAZIO"
    det "montagem SMB que caiu costuma deixar o ponto de montagem vazio"
    det "confira:  mount | grep -i cifs   e   dmesg | tail"
fi

t "RESUMO"
cat <<'FIM'
  A ordem para resolver:

    1. `ls -l` funciona para VOCÊ?            (bloco 1)
    2. é montagem CIFS e tem uid=/gid=?       (bloco 2)
    3. a estrutura program_id/video_id bate?  (bloco 3)
    4. ★ o SERVIÇO enxerga o mesmo arquivo?   (bloco 4)

  Se 1-3 passam e o 4 falha, é permissão ou namespace — não caminho.

  ★ EM DOCKER, a causa quase sempre é o bloco 0: a montagem do host não
    foi bind-montada para dentro do container. Veja DOCKER.md.
FIM
