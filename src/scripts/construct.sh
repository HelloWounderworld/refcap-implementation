#!/bin/bash
# =============================================================================
# construct_with_adapter.sh
# construct.sh do RefCap + o adapter make_annos.py embutido (não-invasivo)
# =============================================================================
# FLUXO:
#   [seus vídeos brutos] --make_annos.py--> annos/{collection}/vcmr.jsonl
#                        --construct.py---> results/construct/{collection}/{name}/tree.json
#
# PRINCÍPIO: o `collection` é definido UMA vez (fonte única de verdade) e passado
# ao adapter E ao construct.py. O núcleo do RefCap NÃO é modificado.
# =============================================================================

set -u  # aborta ao usar variável não definida

# ============================================================================ #
#  PARÂMETROS QUE VOCÊ AJUSTA                                                   #
# ============================================================================ #
collection=meu_corpus                 # <- FIXO, definido por você (chaveia o cache meta/)
video_root=/dir/to/videos             # <- SEU diretório de vídeos brutos
annos_dir=annos                       # raiz das anotações (padrão do RefCap)

# --- Captioning: 'blip' é AUTOSSUFICIENTE (recomendado p/ 1ª rodada). ---------
# 'minigpt' EXIGE rodar o script externo genCaptions_minigpt.py ANTES (no repo
# do MiniGPT-4), gerando meta/captions/${collection}_minigpt.jsonl. Se você não
# fez esse passo, use 'blip'.
caption_generator=blip                # blip (autossuficiente) | minigpt (exige passo externo)

construct_name=${caption_generator}_window_it   # nome do experimento (subpasta de resultados)
caption_denoiser=window               # window (ativa o refino SWi-Den) | base (desliga)
prop_sim_type=it                      # it (padrão) | txt | vis

# ============================================================================ #
#  HIPERPARÂMETROS (defaults do paper — ver ressalva no relatório)             #
# ============================================================================ #
construct_pipeline=base
figsim_denoise_thr=0.4
denoise_window_width=2
proposal_generator=qm
stage=construct
prop_score_thr=0.2
prop_kernel_width=5
prop_min_cnt=2
prop_max_cnt=5
num_samples=-1
seed=42

# ============================================================================ #
#  MODELOS (opcional: troque por caminhos locais de modelos HF)                #
# ============================================================================ #
caption_model=blip-image-captioning-large
blip_itm_model=blip-itm-base-coco
sentence_transformer=paraphrase-distilroberta-v2
glove_model=meta/glove.6B/glove.6B.300d.txt   # ~1GB — OBRIGATÓRIO já na construção

# ============================================================================ #
#  PASSO 1 — ADAPTER: gera annos/{collection}/vcmr.jsonl a partir dos vídeos    #
# ============================================================================ #
echo "== [1/2] Gerando vcmr.jsonl para collection='${collection}' ==" >&2
python make_annos.py \
    --collection "${collection}" \
    --video_root "${video_root}" \
    --annos_dir "${annos_dir}" \
  || { echo "make_annos.py FALHOU — abortando antes do construct." >&2; exit 1; }

# ============================================================================ #
#  PASSO 2 — CONSTRUCT: roda o pipeline do RefCap (núcleo intocado)             #
# ============================================================================ #
echo "== [2/2] Rodando construct.py (construct_name='${construct_name}') ==" >&2
echo "$construct_name"
python construct.py \
    --stage $stage \
    --seed $seed \
    --collection "$collection" \
    --video_root "$video_root" \
    --construct_name "$construct_name" \
    --num_samples $num_samples \
    --figsim_denoise_thr $figsim_denoise_thr \
    --prop_sim_type $prop_sim_type \
    --prop_score_thr $prop_score_thr \
    --prop_kernel_width $prop_kernel_width \
    --prop_min_cnt $prop_min_cnt \
    --prop_max_cnt $prop_max_cnt \
    --caption_model $caption_model \
    --blip_itm_model $blip_itm_model \
    --sentence_transformer $sentence_transformer \
    --glove_model $glove_model \
    --construct_pipeline $construct_pipeline \
    --caption_generator $caption_generator \
    --caption_denoiser $caption_denoiser \
    --proposal_generator $proposal_generator \
    --denoise_window_width $denoise_window_width

echo "== DONE — índice em: results/construct/${collection}/${construct_name}/tree.json ==" >&2
