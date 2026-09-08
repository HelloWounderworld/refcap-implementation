#!/usr/bin/env bash
# =============================================================================
# teste_config.sh — ★ PREENCHA AQUI. É o único arquivo que você edita.
#
# O `preparar_teste.sh` lê estes valores, encontra os .mp4 e monta os papéis
# do teste. O `teste_manual.sh` roda as combinações em cima deles.
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# 1. ONDE A API ESTÁ
# ─────────────────────────────────────────────────────────────────────────────
API_HOST="localhost"
API_PORT="8000"
API_SCHEME="http"


# ─────────────────────────────────────────────────────────────────────────────
# 2. AS CENAS  —  ★ ESCOLHA UM DOS DOIS MODOS
# ─────────────────────────────────────────────────────────────────────────────
#
#   MODO A — DECLARAR (recomendado, e o único que funciona sempre)
#            Você diz quais são as cenas. Nada é lido do disco.
#            É o equivalente ao que você faria montando o curl à mão.
#
#   MODO B — DESCOBRIR
#            O script lista os .mp4. Exige que o HOST (ou o container, via
#            docker exec) consiga ler o diretório.
#
# Se CENAS_A estiver preenchido, o MODO A vence e o resto é ignorado.
# ─────────────────────────────────────────────────────────────────────────────

# O prefixo que vai no `scene_video_path` — o caminho COMO A API O VÊ.
# Em Docker, é o destino do bind-mount (o lado direito do `volumes:`).
BASE_API="/dados/cenas"

# O program_id — vira o `collection` no RefCap
PROGRAM_ID="prog_teste"


# ── MODO A: declare as cenas ───────────────────────────────────────────────
#
# O caminho é montado assim:
#     $BASE_API/$PROGRAM_ID/$VIDEO_A/<cena>.mp4
#
# ★ Preencha VIDEO_B com um SEGUNDO diretório para exercitar o AGRUPAMENTO
#   (cenas em diretórios diferentes viram builds separados). Sem ele, esse
#   teste é pulado.

VIDEO_A="vidA"
CENAS_A="cena_01 cena_02 cena_03"

VIDEO_B=""
CENAS_B=""

# Se alguma cena tiver menos de 1s, informe aqui para testar o patch do
# viddataset. Deixe vazio se não houver.
CENA_CURTA=""
CENA_CURTA_VIDEO=""

# A extensão dos arquivos
EXT=".mp4"


# ── MODO B: descobrir (só se CENAS_A estiver vazio) ────────────────────────
#
# BASE_HOST  onde os SCRIPTS procuram os .mp4 no host
# CONTAINER  se preenchido, lista com `docker exec` em vez de ler o host

BASE_HOST=""
CONTAINER=""
VIDEO_IDS=""          # vazio = todos os subdiretórios


# 3. UM SEGUNDO PROGRAMA — para o teste de ISOLAMENTO
#
# Serve para provar que o mesmo `scene_id` em programas diferentes NÃO
# compartilha cache. Deixe vazio para pular esse teste.
# ─────────────────────────────────────────────────────────────────────────────
PROGRAM_ID_2=""
VIDEO_ID_2=""


# ─────────────────────────────────────────────────────────────────────────────
# 4. AJUSTES DO TESTE
# ─────────────────────────────────────────────────────────────────────────────

# Quantas cenas usar no máximo (0 = todas as encontradas).
# ★ Com modelos reais, cada cena leva alguns segundos. Comece com 4 ou 5.
MAX_CENAS=6

# Timeout de cada requisição, em segundos.
TIMEOUT=900

# O limiar de assíncrono configurado no serviço (REFCAP_LIMIAR_ASSINCRONO).
# O teste do modo assíncrono só roda se der para superá-lo com as cenas
# disponíveis. Com o default 30, provavelmente será pulado.
LIMIAR_ASSINCRONO=30
