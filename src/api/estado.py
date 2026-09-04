"""Estado compartilhado do serviço e configuração.

POR QUE ESTE MÓDULO EXISTE
--------------------------
Com as rotas divididas em `rotas/`, elas precisam de acesso aos modelos
residentes, ao registro de jobs e à configuração — mas NÃO podem importar o
`app.py`, porque é ele que importa as rotas. Isso seria um import circular.

A solução: o estado vive AQUI. O `app.py` importa daqui, as rotas importam
daqui, e ninguém importa o `app.py`.

    app.py ──┐
             ├──► estado.py   (os dois importam daqui;
    rotas/ ──┘                 estado.py não importa ninguém)
"""
from __future__ import annotations

import os

from carregador import ModelosResidentes
from jobs import RegistroDeJobs


class ConfigServico:
    """Configuração via ambiente — o supervisord define no bloco `environment=`.

    ⚠️ REFCAP_*_MODEL devem ser CAMINHOS ABSOLUTOS para os modelos locais.
    Os defaults abaixo são repo-ids do Hub e só servem se houver rede. Num
    servidor offline, deixar o default faz o from_pretrained() tentar baixar,
    falhar, e o processo morrer — o que no supervisord vira loop de reinício.

    Valide os caminhos antes de subir:
        python validar_modelos_locais.py --caption <dir> --itm <dir> --st <dir>
    """

    device = os.environ.get("REFCAP_DEVICE", "cuda")
    caption_model = os.environ.get(
        "REFCAP_CAPTION_MODEL", "Salesforce/blip-image-captioning-large")
    blip_itm_model = os.environ.get(
        "REFCAP_BLIP_ITM_MODEL", "Salesforce/blip-itm-base-coco")
    sentence_transformer = os.environ.get(
        "REFCAP_SENTENCE_TRANSFORMER", "paraphrase-distilroberta-v2")
    carregar_no_startup = os.environ.get("REFCAP_CARREGAR_MODELOS", "1") == "1"


#: Acima deste número de cenas, a API muda sozinha para assíncrono.
#:
#: O gargalo não é processamento — é a CONEXÃO HTTP. Uma cena de 1-5s leva
#: ~1-3s, então 30 cenas já se aproximam do timeout típico de proxy (60s).
LIMIAR_ASSINCRONO = int(os.environ.get("REFCAP_LIMIAR_ASSINCRONO", "30"))

#: As rotas de diagnóstico usam um `collection` PRÓPRIO — nunca o program_id.
#: Assim você testa sem contaminar cache, annos e resultados de dados reais.
COLLECTION_DIAGNOSTICO = "diagnostics"


# --------------------------------------------------------------------------- #
# O estado que vive enquanto o processo viver
# --------------------------------------------------------------------------- #
#: Os 4 modelos, carregados UMA vez no startup (ver `app.ciclo_de_vida`).
modelos = ModelosResidentes()

#: A fila serializada: um job por vez, para não concorrer pela GPU.
registro = RegistroDeJobs()
