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

t "CONFIGURAÇÃO LIDA"
printf "  %-14s %s\n" "API"        "$API"
printf "  %-14s %s\n" "BASE"       "$BASE"
printf "  %-14s %s\n" "PROGRAM_ID" "$PROGRAM_ID"
printf "  %-14s %s\n" "VIDEO_IDS"  "${VIDEO_IDS:-(descobrir automaticamente)}"
printf "  %-14s %s\n" "PROGRAM_ID_2" "${PROGRAM_ID_2:-(sem teste de isolamento)}"
printf "  %-14s %s\n" "MAX_CENAS"  "$MAX_CENAS"

# --------------------------------------------------------------------------- #
DIR_PROG="$BASE/$PROGRAM_ID"

if [ ! -d "$DIR_PROG" ]; then
    if [ "$1" = "--gerar" ] && command -v ffmpeg >/dev/null; then
        t "GERANDO CENAS SINTÉTICAS"
        mkdir -p "$DIR_PROG/vidA" "$DIR_PROG/vidB"
        g() { ffmpeg -f lavfi -i "testsrc=duration=$2:size=320x240:rate=25" \
                     -y "$1" -loglevel error 2>/dev/null; echo "  ${1#$BASE/}  ${2}s"; }
        g "$DIR_PROG/vidA/cena_01.mp4" 3
        g "$DIR_PROG/vidA/cena_02.mp4" 2
        g "$DIR_PROG/vidA/cena_03.mp4" 0.5
        g "$DIR_PROG/vidB/cena_04.mp4" 3
        g "$DIR_PROG/vidB/cena_05.mp4" 2
        if [ -n "$PROGRAM_ID_2" ]; then
            mkdir -p "$BASE/$PROGRAM_ID_2/${VIDEO_ID_2:-vidX}"
            g "$BASE/$PROGRAM_ID_2/${VIDEO_ID_2:-vidX}/cena_01.mp4" 2
        fi
    else
        printf "\n${R}✗ diretório não encontrado: %s${F}\n" "$DIR_PROG"
        echo "  Ajuste BASE e PROGRAM_ID no teste_config.sh,"
        echo "  ou rode:  bash preparar_teste.sh --gerar"
        exit 1
    fi
fi

# --------------------------------------------------------------------------- #
t "CENAS ENCONTRADAS"

MAPA=$(python3 - "$DIR_PROG" "$VIDEO_IDS" "$MAX_CENAS" <<'PYEOF'
import pathlib, subprocess, sys
raiz = pathlib.Path(sys.argv[1])
filtro = [v for v in sys.argv[2].split() if v]
limite = int(sys.argv[3] or 0)

def dur(p):
    """Duração do STREAM — é o que o RefCap lê, e difere do player."""
    try:
        r = subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
                            "-show_entries","stream=duration","-of","csv=p=0",str(p)],
                           capture_output=True, text=True, timeout=20)
        return float(r.stdout.strip())
    except Exception:
        return -1.0

dirs = sorted(d for d in raiz.iterdir() if d.is_dir())
if filtro:
    dirs = [d for d in dirs if d.name in filtro]

linhas = []
for d in dirs:
    for f in sorted(d.glob("*.mp4")):
        linhas.append((d.name, f.stem, str(f), dur(f)))

if limite > 0:
    # ★ Distribui o limite ENTRE os diretórios, em vez de cortar no primeiro.
    # Cortar direto deixaria o segundo diretório de fora — e sem ele não há
    # como testar o agrupamento.
    por_dir = {}
    for v, s, c, du in linhas:
        por_dir.setdefault(v, []).append((v, s, c, du))
    saida, i = [], 0
    while len(saida) < limite:
        avancou = False
        for v in por_dir:
            if i < len(por_dir[v]) and len(saida) < limite:
                saida.append(por_dir[v][i]); avancou = True
        if not avancou: break
        i += 1
    linhas = saida

for v, s, c, du in linhas:
    print(f"{v}|{s}|{c}|{du:.3f}")
PYEOF
)

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
    D2="$BASE/$PROGRAM_ID_2/${VIDEO_ID_2}"
    [ -z "$VIDEO_ID_2" ] && D2=$(find "$BASE/$PROGRAM_ID_2" -mindepth 1 -maxdepth 1 -type d | head -1)
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
