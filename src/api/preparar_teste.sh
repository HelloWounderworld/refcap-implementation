#!/usr/bin/env bash
# =============================================================================
# preparar_teste.sh — encontra as suas cenas e as divide nos papéis do teste
#
# ★ NÃO CRIA NADA. Só lê o que já existe e monta o mapa.
#   (Se o diretório estiver vazio e houver ffmpeg, oferece gerar cenas.)
#
# USO
#     bash preparar_teste.sh              # lê o teste_config.sh
#     bash preparar_teste.sh --gerar      # gera cenas sintéticas, se vazio
#
# O QUE ELE PRODUZ
#     teste_papeis.sh — o mapa, consumido pelo teste_manual.sh
# =============================================================================

AQUI="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${CONFIG:-$AQUI/teste_config.sh}"
PAPEIS="${PAPEIS:-$AQUI/teste_papeis.sh}"

V='\033[0;32m'; A='\033[0;33m'; R='\033[0;31m'; C='\033[0;36m'; F='\033[0m'
t() { echo; echo "═══════════════════════════════════════════════════════════════════"; echo " $1"; echo "═══════════════════════════════════════════════════════════════════"; }

[ -f "$CONFIG" ] || { printf "${R}✗ falta o %s${F}\n" "$CONFIG"; exit 1; }
# shellcheck disable=SC1090
. "$CONFIG"

API="${API_SCHEME}://${API_HOST}:${API_PORT}"

# ★ DOIS CAMINHOS
#   BASE_HOST  onde ESTE script procura os .mp4
#   BASE_API   o prefixo que vai no scene_video_path da requisição
#
# Aceita o `BASE` antigo, para configs de antes do Docker.
EXT="${EXT:-.mp4}"
BASE_HOST="${BASE_HOST:-$BASE}"
BASE_API="${BASE_API:-$BASE_HOST}"
CONTAINER="${CONTAINER:-}"

# traduz_para_api <caminho-no-host>
# Troca o prefixo do host pelo do container. Sem tradução configurada,
# devolve o caminho como está.
traduz_para_api() {
    case "$1" in
        "$BASE_HOST"*) echo "$BASE_API${1#$BASE_HOST}" ;;
        *)             echo "$1" ;;
    esac
}

# ═══════════════════════════════════════════════════════════════════════════
# MODO A — DECLARATIVO
#
# ★ Se CENAS_A estiver preenchido, montamos os caminhos direto do que você
#   declarou. NENHUM acesso ao filesystem — nem do host, nem do container.
#
#   É o modo que sempre funciona: o mesmo que você faria montando o curl à
#   mão. A descoberta (modo B) só existe para quando você NÃO sabe as cenas,
#   e ela depende de conseguir ler o diretório — o que em Docker com SMB
#   costuma falhar.
# ═══════════════════════════════════════════════════════════════════════════
if [ -n "$CENAS_A" ]; then
    t "MODO DECLARATIVO — usando as cenas que você informou"
    printf "  %-14s %s\n" "API"        "$API"
    printf "  %-14s %s\n" "BASE_API"   "$BASE_API"
    printf "  %-14s %s\n" "PROGRAM_ID" "$PROGRAM_ID"
    echo
    EXT="${EXT:-.mp4}"

    cam() { echo "$BASE_API/$PROGRAM_ID/$1/$2$EXT"; }

    # --- diretório A ---
    set -- $CENAS_A
    A1="$1"; A2="${2:-}"; A3="${3:-}"
    printf "  %-10s %-12s %s\n" "$VIDEO_A" "$A1" "$(cam "$VIDEO_A" "$A1")"
    [ -n "$A2" ] && printf "  %-10s %-12s %s\n" "" "$A2" "$(cam "$VIDEO_A" "$A2")"
    [ -n "$A3" ] && printf "  %-10s %-12s %s\n" "" "$A3" "$(cam "$VIDEO_A" "$A3")"

    # --- diretório B (opcional) ---
    B1=""
    if [ -n "$VIDEO_B" ] && [ -n "$CENAS_B" ]; then
        set -- $CENAS_B; B1="$1"
        echo
        printf "  %-10s %-12s %s\n" "$VIDEO_B" "$B1" "$(cam "$VIDEO_B" "$B1")"
    fi

    # --- monta os papéis ---
    UNICA_SID="$A1";  UNICA_VID="$VIDEO_A";  UNICA_PATH="$(cam "$VIDEO_A" "$A1")"
    LOTE_A1_SID="${A2:-$A1}"; LOTE_A1_VID="$VIDEO_A"; LOTE_A1_PATH="$(cam "$VIDEO_A" "${A2:-$A1}")"
    LOTE_A2_SID="${A3:-${A2:-$A1}}"; LOTE_A2_VID="$VIDEO_A"; LOTE_A2_PATH="$(cam "$VIDEO_A" "${A3:-${A2:-$A1}}")"
    if [ -n "$B1" ]; then
        LOTE_B1_SID="$B1"; LOTE_B1_VID="$VIDEO_B"; LOTE_B1_PATH="$(cam "$VIDEO_B" "$B1")"
    else
        LOTE_B1_SID=""; LOTE_B1_VID=""; LOTE_B1_PATH=""
    fi
    if [ -n "$CENA_CURTA" ]; then
        CURTA_SID="$CENA_CURTA"; CURTA_VID="${CENA_CURTA_VIDEO:-$VIDEO_A}"
        CURTA_PATH="$(cam "${CENA_CURTA_VIDEO:-$VIDEO_A}" "$CENA_CURTA")"; CURTA_DUR="<1"
    else
        CURTA_SID=""; CURTA_VID=""; CURTA_PATH=""; CURTA_DUR=""
    fi

    # todas, para o lote completo
    TODAS=""
    for c in $CENAS_A; do TODAS="$TODAS $VIDEO_A:$c:$(cam "$VIDEO_A" "$c")"; done
    for c in $CENAS_B; do TODAS="$TODAS $VIDEO_B:$c:$(cam "$VIDEO_B" "$c")"; done
    TODAS="${TODAS# }"
    N_CENAS=$(echo "$TODAS" | wc -w)
    N_DIRS=$([ -n "$B1" ] && echo 2 || echo 1)

    # segundo programa, para o isolamento
    ISO_SID=""; ISO_VID=""; ISO_PATH=""; MESMO=0
    if [ -n "$PROGRAM_ID_2" ]; then
        ISO_VID="${VIDEO_ID_2:-$VIDEO_A}"
        ISO_SID="${CENA_ISO:-$A1}"
        ISO_PATH="$BASE_API/$PROGRAM_ID_2/$ISO_VID/$ISO_SID$EXT"
        [ "$ISO_SID" = "$A1" ] && MESMO=1
    fi

    t "PAPÉIS"
    pp() { if [ -n "$2" ]; then printf "  ${cV}✓${cF} %-11s %-16s %s\n" "$1" "$2" "$3"
           else printf "  ${cA}○${cF} %-11s %-16s %s\n" "$1" "(ausente)" "$3"; fi; }
    pp "UNICA"   "$UNICA_SID"   "POST /caption + cache"
    pp "LOTE_A1" "$LOTE_A1_SID" "lote — mesmo diretório"
    pp "LOTE_A2" "$LOTE_A2_SID" "lote — mesmo diretório"
    pp "LOTE_B1" "$LOTE_B1_SID" "★ outro diretório — agrupamento"
    pp "CURTA"   "$CURTA_SID"   "★ < 1s — patch do viddataset"
    pp "ISOLAM." "$ISO_SID"     "★ outro program_id"

    DIR_VAZIO="/tmp/refcap_teste_dir_vazio"; mkdir -p "$DIR_VAZIO" 2>/dev/null
    DIR_COM_VIDEO="$BASE_API/$PROGRAM_ID/$VIDEO_A"
    DECLARADO=1
fi

if [ -z "$DECLARADO" ]; then

t "CONFIGURAÇÃO LIDA"
printf "  %-14s %s\n" "API"        "$API"
printf "  %-14s %s\n" "BASE_HOST"  "$BASE_HOST"
printf "  %-14s %s%s\n" "BASE_API"   "$BASE_API" \
    "$([ "$BASE_API" != "$BASE_HOST" ] && echo '   ← o caminho que vai na requisição')"
[ -n "$CONTAINER" ] && printf "  %-14s %s\n" "CONTAINER" "$CONTAINER   ← listagem via docker exec"
printf "  %-14s %s\n" "PROGRAM_ID" "$PROGRAM_ID"
printf "  %-14s %s\n" "VIDEO_IDS"  "${VIDEO_IDS:-(descobrir automaticamente)}"
printf "  %-14s %s\n" "PROGRAM_ID_2" "${PROGRAM_ID_2:-(sem teste de isolamento)}"
printf "  %-14s %s\n" "MAX_CENAS"  "$MAX_CENAS"

# --------------------------------------------------------------------------- #
DIR_PROG="$BASE_HOST/$PROGRAM_ID"

# ★ Descobre COMO executar dentro do container.
#
# `docker exec` quer o NOME DO CONTAINER (ex.: projeto-caption-api-1).
# `docker compose exec` quer o NOME DO SERVIÇO (ex.: caption-api).
#
# Como não dá para adivinhar qual você informou, testamos os dois e usamos o
# que funcionar. Define $DEXEC com o comando certo.
descobrir_exec() {
    if docker exec "$CONTAINER" true 2>/dev/null; then
        DEXEC="docker exec $CONTAINER"
        det "usando: docker exec $CONTAINER   (nome do container)"
        return 0
    fi
    if docker compose exec -T "$CONTAINER" true 2>/dev/null; then
        DEXEC="docker compose exec -T $CONTAINER"
        det "usando: docker compose exec -T $CONTAINER   (nome do serviço)"
        return 0
    fi
    return 1
}

# ★ MODO CONTAINER: quando o HOST não enxerga os arquivos (a montagem só
#   existe dentro do container), listamos com `docker exec`. Aí o BASE_HOST
#   é irrelevante — tudo é resolvido no BASE_API.
if [ -n "$CONTAINER" ]; then
    if ! command -v docker >/dev/null; then
        printf "\n${cR}✗ CONTAINER definido mas o docker não está no PATH${cF}\n"; exit 1
    fi
    if ! descobrir_exec; then
        printf "\n${cR}✗ não consegui executar em '%s'${cF}\n" "$CONTAINER"
        echo
        echo "  Tentei das duas formas:"
        echo "      docker exec $CONTAINER ...            (nome do CONTAINER)"
        echo "      docker compose exec -T $CONTAINER ... (nome do SERVIÇO)"
        echo
        echo "  Descubra o nome certo:"
        echo "      docker compose ps"
        echo "          NAME                  SERVICE       STATUS"
        echo "          projeto-api-1         caption-api   running"
        echo "               ↑ container           ↑ serviço"
        echo
        echo "  Qualquer um dos dois serve — o script detecta qual é."
        exit 1
    fi
    DIR_PROG_API="$BASE_API/$PROGRAM_ID"
    if ! $DEXEC test -d "$DIR_PROG_API" 2>/dev/null; then
        printf "\n${cR}✗ %s não existe DENTRO do container${cF}\n" "$DIR_PROG_API"
        echo "  O que há em $BASE_API:"
        docker exec "$CONTAINER" ls "$BASE_API" 2>/dev/null | head -10 | sed 's/^/     /'
        echo
        echo "  Confira BASE_API e PROGRAM_ID no teste_config.sh."
        exit 1
    fi
elif [ ! -d "$DIR_PROG" ]; then
    if [ "$1" = "--gerar" ] && command -v ffmpeg >/dev/null; then
        t "GERANDO CENAS SINTÉTICAS"
        mkdir -p "$DIR_PROG/vidA" "$DIR_PROG/vidB"
        g() { ffmpeg -f lavfi -i "testsrc=duration=$2:size=320x240:rate=25" \
                     -y "$1" -loglevel error 2>/dev/null; echo "  ${1#$BASE_HOST/}  ${2}s"; }
        g "$DIR_PROG/vidA/cena_01.mp4" 3
        g "$DIR_PROG/vidA/cena_02.mp4" 2
        g "$DIR_PROG/vidA/cena_03.mp4" 0.5
        g "$DIR_PROG/vidB/cena_04.mp4" 3
        g "$DIR_PROG/vidB/cena_05.mp4" 2
        if [ -n "$PROGRAM_ID_2" ]; then
            mkdir -p "$BASE_HOST/$PROGRAM_ID_2/${VIDEO_ID_2:-vidX}"
            g "$BASE_HOST/$PROGRAM_ID_2/${VIDEO_ID_2:-vidX}/cena_01.mp4" 2
        fi
    else
        printf "\n${cR}✗ diretório não encontrado no HOST: %s${cF}\n" "$DIR_PROG"
        echo
        echo "  Três saídas:"
        echo "    1. ajuste BASE_HOST e PROGRAM_ID no teste_config.sh"
        echo "    2. se os arquivos só existem DENTRO do container, informe"
        echo "       CONTAINER=\"nome-do-container\" e BASE_API no config"
        echo "    3. gere cenas de teste:  bash preparar_teste.sh --gerar"
        exit 1
    fi
fi

# --------------------------------------------------------------------------- #
t "CENAS ENCONTRADAS"

# A listagem: no HOST, ou dentro do container.
# ★ O 3o campo do MAPA e' SEMPRE o caminho que vai na REQUISICAO (o do
#   container, se houver traducao) — nunca o caminho do host.
if [ -n "$CONTAINER" ]; then
    # ★ O stderr NÃO é descartado: se o comando falhar dentro do container,
    # queremos ver o motivo. A versão anterior mandava tudo para /dev/null e
    # o sintoma virava um enigmático "nenhum .mp4 encontrado".
    ERRO_CTR=$(mktemp)
    BRUTO=$($DEXEC python3 -c "
import pathlib, subprocess
raiz = pathlib.Path('$BASE_API/$PROGRAM_ID')
def dur(p):
    try:
        r = subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
                            '-show_entries','stream=duration','-of','csv=p=0',str(p)],
                           capture_output=True, text=True, timeout=20)
        return float(r.stdout.strip())
    except Exception:
        return -1.0
for d in sorted(x for x in raiz.iterdir() if x.is_dir()):
    for f in sorted(d.glob('*$EXT')):
        print('%s|%s|%s|%.3f' % (d.name, f.stem, f, dur(f)))
" 2>"$ERRO_CTR")
    if [ -z "$BRUTO" ]; then
        printf "\n${cR}✗ o container não listou nenhum %s em %s${cF}\n" "$EXT" "$BASE_API/$PROGRAM_ID"
        if [ -s "$ERRO_CTR" ]; then
            echo
            echo "  O erro DENTRO do container:"
            sed 's/^/     /' "$ERRO_CTR" | head -12
            echo
            grep -q "No module named\|python3: not found\|executable file not found" "$ERRO_CTR" && {
                echo "  ★ parece que o python3 não está no PATH do container."
                echo "    Use o MODO DECLARATIVO no teste_config.sh — ele não"
                echo "    precisa executar nada lá dentro."
            }
        else
            echo
            echo "  O diretório existe, mas está vazio para o container. Confira:"
            echo "      $DEXEC ls -la $BASE_API/$PROGRAM_ID"
            echo
            echo "  Se lá tiver subdiretórios com .mp4 e mesmo assim vier vazio,"
            echo "  use o MODO DECLARATIVO — é mais simples e sempre funciona."
        fi
        rm -f "$ERRO_CTR"; exit 1
    fi
    rm -f "$ERRO_CTR"
else
    BRUTO=$(python3 -c "
import pathlib, subprocess
raiz = pathlib.Path('$DIR_PROG')
def dur(p):
    try:
        r = subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
                            '-show_entries','stream=duration','-of','csv=p=0',str(p)],
                           capture_output=True, text=True, timeout=20)
        return float(r.stdout.strip())
    except Exception:
        return -1.0
for d in sorted(x for x in raiz.iterdir() if x.is_dir()):
    for f in sorted(d.glob('*$EXT')):
        print('%s|%s|%s|%.3f' % (d.name, f.stem, f, dur(f)))
")
fi

# filtra por VIDEO_IDS, aplica MAX_CENAS e TRADUZ os caminhos
MAPA=$(printf '%s' "$BRUTO" | python3 -c "
import sys
filtro = [v for v in '''$VIDEO_IDS'''.split() if v]
limite = int('''$MAX_CENAS''' or 0)
b_host, b_api = '''$BASE_HOST''', '''$BASE_API'''

linhas = []
for l in sys.stdin.read().strip().splitlines():
    if not l.strip(): continue
    v, s, c, d = l.split('|')
    if filtro and v not in filtro: continue
    # ★ TRADUCAO: o caminho da requisicao e' o do container
    if b_api != b_host and c.startswith(b_host):
        c = b_api + c[len(b_host):]
    try: d = float(d)
    except ValueError: d = -1.0
    linhas.append((v, s, c, d))

if limite > 0:
    # ★ Distribui o limite ENTRE os diretorios, em vez de cortar no primeiro.
    # Cortando direto, o segundo diretorio ficaria de fora — e sem ele nao ha
    # como testar o agrupamento.
    por_dir = {}
    for t in linhas: por_dir.setdefault(t[0], []).append(t)
    saida, i = [], 0
    while len(saida) < limite:
        avancou = False
        for v in por_dir:
            if i < len(por_dir[v]) and len(saida) < limite:
                saida.append(por_dir[v][i]); avancou = True
        if not avancou: break
        i += 1
    linhas = saida

for v, s, c, d in linhas:
    print('%s|%s|%s|%.3f' % (v, s, c, d))
")

[ -z "$MAPA" ] && { printf "${R}✗ nenhum .mp4 em %s${F}\n" "$DIR_PROG"; exit 1; }

printf "  %-14s %-22s %9s %7s\n" "video_id" "scene_id" "duração" "frames"
echo "  ─────────────────────────────────────────────────────────"
echo "$MAPA" | while IFS='|' read -r v s c d; do
    fr=$(python3 -c "print(max(1,int($d)) if $d>0 else '?')" 2>/dev/null)
    av=$(python3 -c "print(' <-- <1s' if 0<$d<1 else '')" 2>/dev/null)
    printf "  %-14s %-22s %8.3fs %6s%s\n" "$v" "$s" "$d" "$fr" "$av"
done

N_TOTAL=$(echo "$MAPA" | wc -l)
N_DIRS=$(echo "$MAPA" | cut -d'|' -f1 | sort -u | wc -l)

# --------------------------------------------------------------------------- #
t "PAPÉIS — como as cenas foram divididas"

eval "$(python3 - <<PYEOF
linhas = [l.split("|") for l in """$MAPA""".strip().splitlines() if l.strip()]
por_dir = {}
for v, s, c, d in linhas:
    por_dir.setdefault(v, []).append((s, c, float(d)))

dirs = sorted(por_dir)
dA = dirs[0]
dB = dirs[1] if len(dirs) > 1 else ""

A = por_dir[dA]
B = por_dir[dB] if dB else []

def emit(nome, t, vid):
    if t:
        s, c, d = t
        print(f'{nome}_SID="{s}"; {nome}_VID="{vid}"; {nome}_PATH="{c}"; {nome}_DUR="{d:.3f}"')
    else:
        print(f'{nome}_SID=""; {nome}_VID=""; {nome}_PATH=""; {nome}_DUR=""')

# UNICA: a cena do POST /caption e dos testes de cache
emit("UNICA",  A[0] if len(A) > 0 else None, dA)
# LOTE_A1/A2: duas do MESMO diretório
emit("LOTE_A1", A[1] if len(A) > 1 else (A[0] if A else None), dA)
emit("LOTE_A2", A[2] if len(A) > 2 else (A[1] if len(A) > 1 else None), dA)
# LOTE_B1: de OUTRO diretório -> agrupamento
emit("LOTE_B1", B[0] if B else None, dB)

# a cena curta, se houver
curtas = [(s, c, d, v) for v in por_dir for s, c, d in por_dir[v] if 0 < d < 1.0]
if curtas:
    s, c, d, v = min(curtas, key=lambda x: x[2])
    print(f'CURTA_SID="{s}"; CURTA_VID="{v}"; CURTA_PATH="{c}"; CURTA_DUR="{d:.3f}"')
else:
    print('CURTA_SID=""; CURTA_VID=""; CURTA_PATH=""; CURTA_DUR=""')

# TODAS: para o lote grande e o assíncrono
todas = [f"{v}:{s}:{c}" for v in dirs for s, c, _ in por_dir[v]]
print(f'TODAS="{chr(32).join(todas)}"')
print(f'N_CENAS={len(todas)}; N_DIRS={len(dirs)}; DIR_A="{dA}"; DIR_B="{dB}"')
PYEOF
)"

p() {  # p <papel> <valor> <descrição>
    if [ -n "$2" ]; then printf "  ${V}✓${F} %-11s %-24s %s\n" "$1" "$2" "$3"
    else printf "  ${A}○${F} %-11s %-24s %s\n" "$1" "(ausente)" "$3"; fi
}
p "UNICA"   "$UNICA_SID"   "POST /caption + testes de cache"
p "LOTE_A1" "$LOTE_A1_SID" "lote — mesmo diretório"
p "LOTE_A2" "$LOTE_A2_SID" "lote — mesmo diretório"
p "LOTE_B1" "$LOTE_B1_SID" "★ OUTRO diretório — agrupamento"
p "CURTA"   "$CURTA_SID"   "★ < 1s — patch do viddataset"
echo
printf "  %-13s %s cena(s) em %s diretório(s)\n" "total:" "$N_CENAS" "$N_DIRS"

# --------------------------------------------------------------------------- #
# Segundo programa, para o isolamento
ISO_SID=""; ISO_VID=""; ISO_PATH=""
if [ -n "$PROGRAM_ID_2" ]; then
    D2="$BASE_HOST/$PROGRAM_ID_2/${VIDEO_ID_2}"
    [ -z "$VIDEO_ID_2" ] && D2=$(find "$BASE_HOST/$PROGRAM_ID_2" -mindepth 1 -maxdepth 1 -type d | head -1)
    if [ -d "$D2" ]; then
        # de preferência uma cena com o MESMO scene_id da UNICA — é o caso que
        # provaria o vazamento de cache, se houvesse
        CAND="$D2/$UNICA_SID.mp4"
        [ -f "$CAND" ] || CAND=$(find "$D2" -maxdepth 1 -name '*.mp4' | head -1)
        if [ -f "$CAND" ]; then
            ISO_PATH="$CAND"; ISO_SID=$(basename "$CAND" .mp4); ISO_VID=$(basename "$D2")
        fi
    fi
fi
if [ -n "$ISO_SID" ]; then
    MESMO=$([ "$ISO_SID" = "$UNICA_SID" ] && echo "1" || echo "0")
    printf "  ${V}✓${F} %-11s %-24s %s\n" "ISOLAMENTO" "$PROGRAM_ID_2/$ISO_SID" \
        "$([ "$MESMO" = "1" ] && echo '★ MESMO scene_id — teste completo' || echo 'scene_id diferente')"
else
    MESMO=0
    printf "  ${A}○${F} %-11s %-24s %s\n" "ISOLAMENTO" "(ausente)" "sem PROGRAM_ID_2"
fi

# diretório vazio, em /tmp — nunca dentro das suas cenas
DIR_VAZIO="/tmp/refcap_teste_dir_vazio"; mkdir -p "$DIR_VAZIO"

fi   # fim do bloco de DESCOBERTA (modo B)

# --------------------------------------------------------------------------- #
cat > "$PAPEIS" <<CFG
#!/usr/bin/env bash
# GERADO por preparar_teste.sh em $(date '+%Y-%m-%d %H:%M') — não edite à mão.
# Para mudar as cenas, ajuste o teste_config.sh e rode o preparador de novo.

API="$API"
TIMEOUT="$TIMEOUT"
LIMIAR_ASSINCRONO="$LIMIAR_ASSINCRONO"
PROGRAM_ID="$PROGRAM_ID"
PROGRAM_ID_2="$PROGRAM_ID_2"

# a cena do POST /caption e dos testes de cache
UNICA_SID="$UNICA_SID"; UNICA_VID="$UNICA_VID"; UNICA_PATH="$UNICA_PATH"

# duas do MESMO diretório
LOTE_A1_SID="$LOTE_A1_SID"; LOTE_A1_VID="$LOTE_A1_VID"; LOTE_A1_PATH="$LOTE_A1_PATH"
LOTE_A2_SID="$LOTE_A2_SID"; LOTE_A2_VID="$LOTE_A2_VID"; LOTE_A2_PATH="$LOTE_A2_PATH"

# de OUTRO diretório — o agrupamento
LOTE_B1_SID="$LOTE_B1_SID"; LOTE_B1_VID="$LOTE_B1_VID"; LOTE_B1_PATH="$LOTE_B1_PATH"

# menos de 1s — o patch do viddataset
CURTA_SID="$CURTA_SID"; CURTA_VID="$CURTA_VID"; CURTA_PATH="$CURTA_PATH"; CURTA_DUR="$CURTA_DUR"

# outro programa — o isolamento de cache
ISO_SID="$ISO_SID"; ISO_VID="$ISO_VID"; ISO_PATH="$ISO_PATH"; ISO_MESMO_SID="$MESMO"

# todas as cenas, no formato video:scene:path
TODAS="$TODAS"
N_CENAS=$N_CENAS
N_DIRS=$N_DIRS

DIR_VAZIO="$DIR_VAZIO"
DIR_COM_VIDEO="\$(dirname "$UNICA_PATH")"
CFG

t "PRONTO"
echo "  mapa gravado em: $PAPEIS"
echo
[ "$N_DIRS" -lt 2 ] && printf "  ${A}⚠️  só 1 diretório — o teste de AGRUPAMENTO será pulado.${F}\n     Informe dois VIDEO_IDS no teste_config.sh para exercitá-lo.\n\n"
[ -z "$CURTA_SID" ] && printf "  ${A}⚠️  nenhuma cena com menos de 1s — esse teste será pulado.${F}\n\n"
echo "  Agora:  bash teste_manual.sh"
