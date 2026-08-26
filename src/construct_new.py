import os
# --- MUDANÇA 1 de 2: setdefault em vez de atribuição -------------------------
# Antes era:
#     os.environ["TOKENIZERS_PARALLELISM"] = "false"
#     os.environ["CUDA_VISIBLE_DEVICES"]='0'
#
# Com `setdefault`, o que o ambiente já definiu (supervisord, docker, o próprio
# shell) é RESPEITADO; quando nada foi definido, cai no mesmo default de antes
# — então o CLI se comporta de forma idêntica.
#
# Sem isto, bastaria um serviço IMPORTAR este arquivo para a GPU 0 ser forçada,
# ignorando o `environment=` do supervisord.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

from pipeline.denoiser import * 
from pipeline.denoiser.base import get_denoiser_class
from pipeline.treebuilder import *
from pipeline.capgenerator import * 
from pipeline.capgenerator import get_capgen_class
from pipeline.propgenerator import * 
from pipeline.propgenerator import get_propgen_class
from pipeline.constructpipe import * 
from pipeline.constructpipe import get_constructpipe_class

from utils.model_utils import load_pretrained_models
import utils.basic_utils as basic_utils


import warnings
warnings.filterwarnings("ignore")
from config import BuildArguments, HfArgumentParser
from dataclasses import asdict
import random 

from utils.basic_utils import seed_it


# --- MUDANÇA 2 de 2: extrair o núcleo reutilizável ---------------------------
def build(cfg, pretrained_models=None):
    """O núcleo da construção, reutilizável por um serviço.

    Diferenças em relação ao `main()` antigo:

      1. Recebe um `cfg` JÁ PRONTO — não lê `sys.argv`. Num serviço não há
         linha de comando; o chamador monta o BuildArguments e sobrescreve o
         que precisar.

      2. Aceita `pretrained_models` JÁ CARREGADOS. É este o ponto que permite
         manter os modelos residentes entre requisições: carregue uma vez no
         startup e passe aqui a cada chamada.

         Quando é None (o caso do CLI), carrega do jeito tradicional — por isso
         `bash scripts/construct.sh` continua funcionando igual.

      3. RETORNA o `tree_meta`. Antes o resultado do `construct()` era
         descartado; agora vira a resposta da API.

    O dicionário `pretrained_models` precisa ter, no mínimo:
        cap_gen_model, cap_gen_processor        -> etapa 1 (captioning)
        blip_itrtv_model, blip_itrtv_processor  -> etapas 2,3,4,5,6
        sentence_transformer                    -> etapa 6
    `glove_model` pode ser None: só o CapTree o usa, e o CapTree é do retrieve.
    """
    seed_it(cfg.seed)

    exp_dir = os.path.join(cfg.res_dir, cfg.construct_dir, cfg.collection, cfg.construct_name)
    cfg.exp_dir = exp_dir 
    os.makedirs(exp_dir, exist_ok=True)

    cfg_dict = asdict(cfg)
    basic_utils.save_json(cfg_dict, os.path.join(exp_dir, "settings.json"))

    if pretrained_models is None:
        pretrained_models = load_pretrained_models(cfg)

    caption_generator = get_capgen_class(cfg.caption_generator)(cfg, pretrained_models)
    caption_denoiser = get_denoiser_class(cfg.caption_denoiser)(cfg, pretrained_models)
    proposal_generator = get_propgen_class(cfg.proposal_generator)(cfg, pretrained_models)

    construct_pipeline = get_constructpipe_class(cfg.construct_pipeline)(cfg, caption_generator, caption_denoiser, proposal_generator, pretrained_models)

    return construct_pipeline.construct()


def main():
    print("Building parse pipeline")
    parser = HfArgumentParser(BuildArguments)
    cfg  = parser.parse_args_into_dataclasses(look_for_args_file=False)[0]
    print(cfg)

    build(cfg)

    print(cfg.construct_name)
    print("DONE!")

if __name__ == "__main__":
    main()
