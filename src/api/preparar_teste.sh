#!/usr/bin/env bash
# =============================================================================
# preparar_teste.sh — descobre as SUAS cenas, ou cria cenas de teste
#
# COMO FUNCIONA
#   1. Olha o diretório indicado. Se JÁ HOUVER .mp4, usa os seus — não cria nada.
#   2. Só se estiver vazio, gera cenas sintéticas com ffmpeg.
#   3. Em ambos os casos, escreve `teste_config.sh` com os papéis mapeados.
#
#   O `teste_config.sh` é um arquivo comum: ABRA E EDITE se a descoberta
#   escolher cenas diferentes das que você quer testar.
#
# USO
#   bash preparar_teste.sh                        # usa /tmp/teste_refcap
#   bash preparar_teste.sh /dados/minhas_cenas    # usa as SUAS cenas
#   BASE=/dados/cenas bash preparar_teste.sh
#   bash preparar_teste.sh --limpar               # remove só as sintéticas
#
# ESTRUTURA ESPERADA (a do contrato da API)
#   <BASE>/{program_id}/{video_id}/{scene_id}.mp4
#
#   Se a sua for diferente, o script ainda descobre os .mp4 — mas confira o
#   `teste_config.sh` gerado, porque program_id e video_id podem sair errados.
# =============================================================================

if [ -n "$1" ] && [ "$1" != "--limpar" ]; then BASE="$1"; fi
BASE="${BASE:-/tmp/teste_refcap}"
CONFIG="${CONFIG:-$(cd "$(dirname "$0")" && pwd)/teste_config.sh}"

VERDE='\033[0;32m'; AMAR='\033[0;33m'; VERM='\033[0;31m'; FIM='\033[0m'
titulo() { echo; echo "═══════════════════════════════════════════════════════════════════"; echo " $1"; echo "═══════════════════════════════════════════════════════════════════"; }

# --------------------------------------------------------------------------- #
if [ "$1" = "--limpar" ]; then
    if [ "$BASE" = "/tmp/teste_refcap" ]; then
        rm -rf "$BASE"; rm -f "$CONFIG"
        echo "✓ $BASE e $CONFIG removidos"
    else
        printf "${VERM}✗ recusando apagar %s${FIM}\n" "$BASE"
        echo "  O --limpar só remove o diretório sintético (/tmp/teste_refcap)."
        echo "  Nunca apago cenas suas."
    fi
    exit 0
fi

# --------------------------------------------------------------------------- #
# 1. O diretório já tem vídeos?
# --------------------------------------------------------------------------- #
titulo "INVENTÁRIO — $BASE"

mkdir -p "$BASE"
N_VIDEOS=$(find "$BASE" -type f -iname '*.mp4' 2>/dev/null | wc -l)
SINTETICO=0

if [ "$N_VIDEOS" -gt 0 ]; then
    printf "  ${VERDE}✓ %d vídeo(s) encontrado(s) — usando os SEUS${FIM}\n" "$N_VIDEOS"
    echo "    (nada será criado nem modificado)"
else
    printf "  ${AMAR}○ nenhum .mp4 aqui${FIM}\n"
    command -v ffmpeg >/dev/null || {
        printf "  ${VERM}✗ ffmpeg não encontrado — não posso gerar cenas${FIM}\n"
        echo "    Aponte para um diretório com seus .mp4:"
        echo "        bash preparar_teste.sh /caminho/das/suas/cenas"
        exit 1
    }
    echo "  → gerando cenas sintéticas com ffmpeg"
    SINTETICO=1
    mkdir -p "$BASE/prog_teste/vidA" "$BASE/prog_teste/vidB" \
             "$BASE/prog_teste/vazio" "$BASE/prog_outro/vidX"
    criar() {
        ffmpeg -f lavfi -i "testsrc=duration=$2:size=320x240:rate=25" \
               -y "$1" -loglevel error 2>/dev/null
        printf "    %-44s %ss\n" "${1#$BASE/}" "$2"
    }
    echo
    criar "$BASE/prog_teste/vidA/cena_01.mp4" 3
    criar "$BASE/prog_teste/vidA/cena_02.mp4" 2
    criar "$BASE/prog_teste/vidA/cena_03.mp4" 0.5
    criar "$BASE/prog_teste/vidB/cena_04.mp4" 3
    criar "$BASE/prog_outro/vidX/cena_01.mp4" 2
fi

# --------------------------------------------------------------------------- #
# 2. Mapear <BASE>/{program}/{video}/{scene}.mp4
# --------------------------------------------------------------------------- #
titulo "ESTRUTURA DETECTADA"

MAPA=$(python3 - "$BASE" <<'PYEOF'
import pathlib, subprocess, sys
base = pathlib.Path(sys.argv[1]).resolve()

def duracao(p):
    """Duração do STREAM de vídeo — é o que o RefCap lê, e difere do player."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=duration", "-of", "csv=p=0", str(p)],
            capture_output=True, text=True, timeout=20)
        return float(r.stdout.strip())
    except Exception:
        return -1.0

for p in sorted(base.rglob("*.mp4")):
    rel = p.relative_to(base).parts
    if len(rel) >= 3:      # {program}/{video}/{scene}.mp4
        program, video = rel[-3], rel[-2]
    elif len(rel) == 2:    # {program}/{scene}.mp4
        program, video = rel[0], ""
    else:
        program, video = "", ""
    print(f"{program}|{video}|{p.stem}|{p}|{duracao(p):.3f}")
PYEOF
)

[ -z "$MAPA" ] && { printf "  ${VERM}✗ nenhum vídeo mapeado${FIM}\n"; exit 1; }

printf "  %-16s %-12s %-20s %9s %7s\n" "program_id" "video_id" "scene_id" "duração" "frames"
echo "  ──────────────────────────────────────────────────────────────────────"
echo "$MAPA" | head -25 | while IFS='|' read -r prog vid cena caminho dur; do
    info=$(python3 -c "
d=$dur
print(f\"{max(1,int(d)) if d>0 else '?'}|{' <-- < 1s' if 0<d<1 else ''}\")" 2>/dev/null)
    fr="${info%%|*}"; aviso="${info##*|}"
    printf "  %-16s %-12s %-20s %8.3fs %6s%s\n" "$prog" "$vid" "$cena" "$dur" "$fr" "$aviso"
done
TOT=$(echo "$MAPA" | wc -l)
[ "$TOT" -gt 25 ] && echo "  ... e mais $((TOT-25))"

# --------------------------------------------------------------------------- #
# 3. Escolher a cena de cada PAPEL
# --------------------------------------------------------------------------- #
titulo "PAPÉIS DO TESTE"

PAPEIS=$(python3 - <<PYEOF
from collections import defaultdict
linhas = [l.split("|") for l in """$MAPA""".strip().splitlines() if l.strip()]
por_prog = defaultdict(lambda: defaultdict(list))
for prog, vid, cena, cam, dur in linhas:
    por_prog[prog][vid].append((cena, cam, float(dur)))

# ★ O programa PRINCIPAL é o mais RICO — não o primeiro em ordem alfabética.
# Ele precisa preencher o máximo de papéis: várias cenas, vários diretórios,
# e de preferência uma cena curta. Ordenar por nome pegaria um programa com
# uma cena só e deixaria metade dos testes sem cenário.
def riqueza(prog):
    vids = por_prog[prog]
    n_cenas = sum(len(v) for v in vids.values())
    tem_curta = any(0 < d < 1.0 for v in vids.values() for _, _, d in v)
    return (len(vids), n_cenas, tem_curta)

progs = sorted(por_prog, key=riqueza, reverse=True)
prog1 = progs[0] if progs else ""
prog2 = progs[1] if len(progs) > 1 else ""

# vidA é o diretório com MAIS cenas (para ter A1 e A2); vidB é outro qualquer
vids = sorted(por_prog[prog1], key=lambda v: len(por_prog[prog1][v]), reverse=True) if prog1 else []
vidA  = vids[0] if vids else ""
vidB  = vids[1] if len(vids) > 1 else ""
cenasA = por_prog[prog1][vidA] if vidA else []
cenasB = por_prog[prog1][vidB] if vidB else []

def emitir(nome, t, vid):
    if t:
        c, cam, d = t
        print(f'{nome}_ID={c}\n{nome}_VID={vid}\n{nome}_PATH={cam}\n{nome}_DUR={d:.3f}')
    else:
        print(f'{nome}_ID=\n{nome}_VID=\n{nome}_PATH=\n{nome}_DUR=')

emitir("CENA_A1", cenasA[0] if len(cenasA) > 0 else None, vidA)
emitir("CENA_A2", cenasA[1] if len(cenasA) > 1 else None, vidA)
emitir("CENA_B1", cenasB[0] if len(cenasB) > 0 else None, vidB)

curtas = [(c, cam, d, v) for v in por_prog[prog1]
          for c, cam, d in por_prog[prog1][v] if 0 < d < 1.0]
if curtas:
    c, cam, d, v = min(curtas, key=lambda x: x[2])
    print(f'CENA_CURTA_ID={c}\nCENA_CURTA_VID={v}\nCENA_CURTA_PATH={cam}\nCENA_CURTA_DUR={d:.3f}')
else:
    print('CENA_CURTA_ID=\nCENA_CURTA_VID=\nCENA_CURTA_PATH=\nCENA_CURTA_DUR=')

ids1 = {c for v in por_prog[prog1] for c, _, _ in por_prog[prog1][v]}
achou = None
for v in sorted(por_prog.get(prog2, {})):
    for c, cam, d in por_prog[prog2][v]:
        if c in ids1:
            achou = (c, cam, v, "1"); break
    if achou: break
if not achou and prog2:
    v = sorted(por_prog[prog2])[0]
    c, cam, d = por_prog[prog2][v][0]
    achou = (c, cam, v, "0")
if achou:
    c, cam, v, rep = achou
    print(f'CENA_P2_ID={c}\nCENA_P2_VID={v}\nCENA_P2_PATH={cam}\nCENA_P2_REPETIDO={rep}')
else:
    print('CENA_P2_ID=\nCENA_P2_VID=\nCENA_P2_PATH=\nCENA_P2_REPETIDO=0')

print(f'PROG={prog1}\nPROG2={prog2}')
PYEOF
)

# carrega os papéis como variáveis
while IFS='=' read -r k v; do [ -n "$k" ] && eval "$k=\"\$v\""; done <<< "$PAPEIS"

# diretório vazio, para o SCENE_NOT_FOUND
DIR_VAZIO=""
for d in "$BASE/$PROG"/*/; do
    [ -d "$d" ] || continue
    [ "$(find "$d" -maxdepth 1 -iname '*.mp4' 2>/dev/null | wc -l)" -eq 0 ] && { DIR_VAZIO="${d%/}"; break; }
done
if [ -z "$DIR_VAZIO" ]; then
    # ★ Criado em /tmp, NUNCA dentro das suas cenas.
    # A versão anterior o criava em $BASE/$PROG/ — o que contradizia a
    # promessa de "nada será criado nem modificado" quando as cenas são suas.
    DIR_VAZIO="/tmp/refcap_dir_vazio_para_teste"
    mkdir -p "$DIR_VAZIO"; CRIEI_VAZIO=1
fi

papel() {
    if [ -n "$2" ]; then printf "  ${VERDE}✓${FIM} %-13s %-24s %s\n" "$1" "$2" "$3"
    else printf "  ${AMAR}○${FIM} %-13s %-24s %s\n" "$1" "(não encontrado)" "$3"; fi
}
papel "CENA_A1"    "$CENA_A1_ID"    "caminho feliz + testes de cache"
papel "CENA_A2"    "$CENA_A2_ID"    "lote no MESMO diretório"
papel "CENA_B1"    "$CENA_B1_ID"    "★ OUTRO diretório — agrupamento"
papel "CENA_CURTA" "$CENA_CURTA_ID" "★ < 1s — patch do viddataset"
papel "CENA_P2"    "$CENA_P2_ID"    "★ outro program_id — isolamento"
echo
printf "  ${VERDE}✓${FIM} %-13s %s\n" "DIR_VAZIO" "$DIR_VAZIO"
[ -n "$CRIEI_VAZIO" ] && echo "                (criado agora, vazio de propósito)"
[ "$CENA_P2_REPETIDO" = "1" ] && echo && printf "  ${VERDE}★${FIM} o scene_id '%s' existe nos DOIS programas — o teste de\n    isolamento fica completo.\n" "$CENA_P2_ID"

# --------------------------------------------------------------------------- #
# 4. Gravar a configuração
# --------------------------------------------------------------------------- #
DIR_UM_VIDEO=""
[ -n "$CENA_B1_PATH" ] && DIR_UM_VIDEO="$(dirname "$CENA_B1_PATH")"

cat > "$CONFIG" <<CFG
#!/usr/bin/env bash
# =============================================================================
# teste_config.sh — GERADO por preparar_teste.sh em $(date '+%Y-%m-%d %H:%M')
#
# ★ ESTE ARQUIVO É SEU PARA EDITAR.
#   Se a descoberta escolheu cenas diferentes das que você quer testar,
#   troque os valores abaixo. O teste_manual.sh lê daqui — não precisa rodar
#   o preparar_teste.sh de novo.
#
# Cada CENA_* tem três campos:
#     _ID    o scene_id que vai na requisição
#     _VID   o video_id
#     _PATH  o caminho completo do .mp4
#
# Deixar um _ID vazio faz os testes daquele papel serem PULADOS, não falharem.
# =============================================================================

BASE="$BASE"
API="\${API:-http://localhost:8000}"

# Os program_id (o collection do RefCap é derivado daqui)
PROG="$PROG"
PROG2="$PROG2"

# ── CENA_A1 — caminho feliz; usada também nos testes de cache ──
CENA_A1_ID="$CENA_A1_ID"
CENA_A1_VID="$CENA_A1_VID"
CENA_A1_PATH="$CENA_A1_PATH"

# ── CENA_A2 — outra cena no MESMO diretório de A1 ──
CENA_A2_ID="$CENA_A2_ID"
CENA_A2_VID="$CENA_A2_VID"
CENA_A2_PATH="$CENA_A2_PATH"

# ── CENA_B1 — ★ em OUTRO diretório: prova o agrupamento (2 builds) ──
CENA_B1_ID="$CENA_B1_ID"
CENA_B1_VID="$CENA_B1_VID"
CENA_B1_PATH="$CENA_B1_PATH"

# ── CENA_CURTA — ★ < 1s: prova o patch max(1,int(duration)) ──
#    Vazio = teste pulado. Para exercitá-lo, aponte para um clipe curto.
CENA_CURTA_ID="$CENA_CURTA_ID"
CENA_CURTA_VID="$CENA_CURTA_VID"
CENA_CURTA_PATH="$CENA_CURTA_PATH"
CENA_CURTA_DUR="$CENA_CURTA_DUR"

# ── CENA_P2 — ★ em OUTRO program_id: prova o isolamento de cache ──
#    Ideal: mesmo scene_id de alguma cena do PROG.  Repetido? $CENA_P2_REPETIDO
CENA_P2_ID="$CENA_P2_ID"
CENA_P2_VID="$CENA_P2_VID"
CENA_P2_PATH="$CENA_P2_PATH"
CENA_P2_REPETIDO="$CENA_P2_REPETIDO"

# ── DIR_VAZIO — diretório SEM vídeos: prova o SCENE_NOT_FOUND ──
DIR_VAZIO="$DIR_VAZIO"

# ── DIR_COM_VIDEO — ★ prova que o fallback perigoso foi removido ──
#    Um diretório COM vídeos, onde pediremos um scene_id INEXISTENTE.
#    Antes da Etapa 2, a API legendava o vídeo errado em silêncio.
DIR_COM_VIDEO="$DIR_UM_VIDEO"

# 1 = cenas geradas por ffmpeg;  0 = cenas suas
SINTETICO=$SINTETICO
CFG

titulo "CONFIGURAÇÃO GRAVADA"
echo "  $CONFIG"
echo
if [ "$SINTETICO" = "1" ]; then
    echo "  Cenas SINTÉTICAS (geradas agora)."
else
    printf "  ${VERDE}Cenas SUAS${FIM} — nada foi criado nem modificado.\n"
fi
echo
echo "  ★ ABRA o arquivo e confira os papéis. Para testar outras cenas, é só"
echo "    trocar os valores — não precisa rodar este script de novo."
echo
echo "  Depois:  bash teste_manual.sh"
