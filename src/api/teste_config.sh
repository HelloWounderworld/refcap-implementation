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
# 2. ONDE ESTÃO AS CENAS
#
# A estrutura esperada é a do contrato:
#     <BASE>/{program_id}/{video_id}/{scene_id}.mp4
#
# Exemplo: com BASE=/dados, PROGRAM_ID=novela_x e VIDEO_IDS="ep01 ep02",
# ele procura os .mp4 em
#     /dados/novela_x/ep01/*.mp4
#     /dados/novela_x/ep02/*.mp4
# ─────────────────────────────────────────────────────────────────────────────
BASE="/tmp/teste_refcap"

# O program_id que vai nas requisições — e que vira o `collection` no RefCap
PROGRAM_ID="prog_teste"

# Os video_id (diretórios) DENTRO do program_id.
#
# ★ INFORME PELO MENOS DOIS para exercitar o AGRUPAMENTO: cenas em diretórios
#   diferentes viram chamadas separadas de build(). Com um só, esse teste é
#   pulado.
#
# Deixe VAZIO ("") para descobrir automaticamente todos os subdiretórios.
VIDEO_IDS=""


# ─────────────────────────────────────────────────────────────────────────────
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
