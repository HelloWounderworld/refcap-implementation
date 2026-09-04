#!/usr/bin/env bash
# =============================================================================
# preparar_teste.sh — monta o cenário de cenas para o teste manual
#
# Cria vídeos reais (com ffmpeg) numa estrutura que exercita TODOS os casos:
#
#   /tmp/teste_refcap/
#   └── prog_teste/
#       ├── vidA/
#       │   ├── cena_01.mp4   3.0s   caso normal
#       │   ├── cena_02.mp4   2.0s   caso normal
#       │   └── cena_03.mp4   0.5s   ★ vídeo CURTO — testa o patch do viddataset
#       ├── vidB/
#       │   └── cena_04.mp4   3.0s   ★ OUTRO diretório — testa o agrupamento
#       └── vazio/                   ★ sem vídeos — testa SCENE_NOT_FOUND
#
#   E um segundo programa, para provar o isolamento entre program_id:
#   └── prog_outro/vidX/cena_01.mp4  ★ MESMO scene_id do prog_teste
#
# USO
#     bash preparar_teste.sh
#     bash preparar_teste.sh --limpar     # remove tudo
# =============================================================================

BASE="${BASE:-/tmp/teste_refcap}"

if [ "$1" = "--limpar" ]; then
    rm -rf "$BASE"
    echo "✓ $BASE removido"
    exit 0
fi

command -v ffmpeg >/dev/null || { echo "✗ ffmpeg não encontrado"; exit 1; }

rm -rf "$BASE"
mkdir -p "$BASE/prog_teste/vidA" "$BASE/prog_teste/vidB" \
         "$BASE/prog_teste/vazio" "$BASE/prog_outro/vidX"

criar() {  # criar <caminho> <duracao>
    ffmpeg -f lavfi -i "testsrc=duration=$2:size=320x240:rate=25" \
           -y "$1" -loglevel error 2>/dev/null
    printf "  %-46s %ss\n" "${1#$BASE/}" "$2"
}

echo "Criando cenas de teste em $BASE ..."
echo
criar "$BASE/prog_teste/vidA/cena_01.mp4" 3
criar "$BASE/prog_teste/vidA/cena_02.mp4" 2
criar "$BASE/prog_teste/vidA/cena_03.mp4" 0.5
criar "$BASE/prog_teste/vidB/cena_04.mp4" 3
criar "$BASE/prog_outro/vidX/cena_01.mp4" 2

echo
echo "  prog_teste/vazio/    (diretório sem vídeos, de propósito)"
echo
echo "═══════════════════════════════════════════════════════════════════"
echo " Duração REAL de cada stream (é o que o RefCap lê):"
echo "═══════════════════════════════════════════════════════════════════"
for f in $(find "$BASE" -name '*.mp4' | sort); do
    d=$(ffprobe -v error -select_streams v:0 -show_entries stream=duration \
        -of csv=p=0 "$f" 2>/dev/null)
    n=$(python3 -c "print(max(1,int($d)))" 2>/dev/null)
    printf "  %-46s %6.3fs → %s frame(s)\n" "${f#$BASE/}" "$d" "$n"
done

echo
echo "  ★ a cena_03 tem menos de 1s: sem o patch do viddataset, ela"
echo "    derrubaria o processo. Com o patch, gera 1 frame."
echo
echo "Pronto. Agora rode:  bash teste_manual.sh"
