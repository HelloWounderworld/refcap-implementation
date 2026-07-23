# Pergunta

## Duvida 2:
No trecho abaixo:

````markdown
### Linha 42 — Carregamento dos modelos
```python
pretrained_models = load_pretrained_models(cfg)
```
**O que faz:** carrega o BLIP de captioning (`cap_gen_model` + `cap_gen_processor`), o BLIP-ITM, o sentence-transformer e o GloVe. **O `cap_gen_model` é o modelo que fará o vídeo→texto** — ele nasce aqui.
````

Levando em consideracao os anexos, model_utils.py, cfg.py e construct.sh, poderia me fornecer um exemplo de parametros para entender melhor quais os parametros essa funcao "load_pretrained_models" ele leva em consideracao para processar?

# Answer
Vou ler os três arquivos. Deixa eu conferir se vieram como anexo novo e, de todo modo, lê-los do repositório clonado (que já tenho).`model_utils.py` lido por completo. (Nota: os anexos não chegaram — a pasta de uploads só tem os arquivos antigos — mas estou lendo tudo do repositório clonado, então dá no mesmo.) Agora o `cfg.py` e o `construct.sh`:Tenho os três arquivos. Deixa eu verificar dois detalhes que afetam a resposta prática — de onde vem o `HfArgumentParser` (se ele impõe os `choices`) e o que o `requirements.txt` fixa:Linha 150: `kwargs = field.metadata.copy()` — os `choices` **são** repassados ao argparse. Isso tem uma consequência que vale provar em execução:Tenho tudo verificado. Deixa eu confirmar um último ponto, já que vou sugerir um exemplo concreto ligado ao seu objetivo:Atenção — a linha 105 usa `prop_min_cnt`, não `prop_max_cnt`. Preciso reverificar isso antes de recomendar qualquer coisa:Isto contradiz o que eu havia afirmado antes. Preciso ver a função inteira e testar, porque é uma conclusão que você usaria para decidir:Preciso resolver isto agora, porque é uma afirmação que eu fiz com confiança antes e você usaria para decidir. Vou simular o algoritmo de fronteiras fielmente:Verificado tudo. Vou à sua dúvida, e no final preciso te dar uma correção importante que apareceu nesta verificação.

## Os parâmetros que `load_pretrained_models` de fato consome

A função lê **exatamente 8 campos** do `cfg` — nem um a mais:

| # | Campo | Linha em `model_utils.py` | Papel |
|---|---|---|---|
| 1 | `cfg.stage` | 9 | **Portão**: só carrega o captioner se `== "construct"` |
| 2 | `cfg.caption_generator` | 10 / 14 / 18 | Escolhe o ramo: `blip` / `minigpt` / `llava` |
| 3 | `cfg.caption_model` | 12–13 (blip), 21–24 (llava) | ID ou caminho do modelo de legendagem |
| 4 | `cfg.device` | 12, 23, 30, 35 | Destino dos pesos (`cuda`/`cpu`) |
| 5 | `cfg.blip_itm_model` | 30–31 | Modelo de *image-text matching* |
| 6 | `cfg.sentence_transformer` | 35 | Modelo de embeddings de sentença |
| 7 | `cfg.glove_model` | 36 | Arquivo GloVe (argumento `name=`) |
| 8 | `cfg.meta_dir` | 36 | Diretório de cache do GloVe (argumento `cache=`) — **fácil de não enxergar** |

**A assimetria estrutural que importa:** apenas **um** dos quatro modelos é condicional (o captioner). Os outros três — BLIP-ITM, sentence-transformer e GloVe — são carregados **sempre**, independente de `stage` e de `caption_generator`. Você paga o GloVe (~1GB, parsing de texto) mesmo num `retrieve` que nem o usaria diretamente.

## Exemplo concreto: os três cenários (parseei de verdade)

**Cenário A — defaults, que é o `construct.sh` como vem no repo:**
```
cfg.stage = 'construct'   |   cfg.caption_generator = 'minigpt'
→ cap_gen_model = None,  cap_gen_processor = None
→ blip_itrtv, sentence_transformer, glove: carregados
```
**Este é o alçapão.** Com o script como distribuído, o BLIP de legendagem **não é sequer carregado** — o ramo `minigpt` (linhas 14–17) só imprime "you should generate captions using external scripts" e devolve `None`. É a confirmação, pela via do carregamento de modelos, daquilo que provamos antes com o mock explosivo: **na configuração default, nenhum vídeo→texto acontece.** O README (linha 40) diz isso explicitamente: *"set `caption_generator` to 'blip' in scripts/construct.sh"*.

**Cenário B — o que você precisa (`--caption_generator blip`):**
```
BlipForConditionalGeneration.from_pretrained(cfg.caption_model).to(cfg.device)
BlipProcessor.from_pretrained(cfg.caption_model)
```
Aqui `cap_gen_model` nasce — e é ele que executa o `.generate()` da linha 30 do `BlipCapGener.py`.

**Cenário C — `retrieve.py` (`stage='retrieve'`):** cai no `else` da linha 25 → captioner `None`, os outros três carregados.

## Quatro armadilhas práticas (se você for rodar)

**1. Os nomes dos modelos não têm namespace do HuggingFace.** `blip-image-captioning-large` não é um repo-id válido do Hub — o canônico é `Salesforce/blip-image-captioning-large`; e `blip-itm-base-coco` → `Salesforce/blip-itm-base-coco`. O comentário do `construct.sh` (linha 24) diz "Optional: replace with local paths" — mas para os dois BLIPs **não é opcional**, a menos que você tenha diretórios locais com esses nomes exatos. Curiosamente o `sentence_transformer` funciona sem prefixo, porque a lib `sentence_transformers` tenta `sentence-transformers/{nome}` automaticamente. (Não consigo testar a resolução no Hub daqui — sem rede para huggingface.co — mas o padrão de nomenclatura é claro.)

**2. GloVe:** `Vectors(name="meta/glove.6B/glove.6B.300d.txt", cache="meta")`. Na primeira execução ele parseia ~1GB de texto (minutos); depois grava um `.pt` em `meta/` e as execuções seguintes são rápidas. Note que é **este** o carregamento que depois se duplica dentro do `MixPipe.__init__` — a violação de DRY que identificamos.

**3. O ramo `llava` é código morto.** Ele existe em `model_utils.py` (linhas 18–24), mas o `cfg.py` (linha 65) restringe `choices` a `["minigpt", "blip"]`, e o parser **impõe** isso (confirmei: `hf_argparser.py:150` copia o metadata para o argparse). Provei em execução: `--caption_generator llava` é rejeitado. Para usá-lo você teria que editar o `choices`.

**4. `torchtext==0.17.0`** está pinado — projeto descontinuado; só funciona casado com `torch==2.2.0`. É a dependência mais provável de te dar dor de cabeça na instalação.

## O `construct.sh` mínimo para o seu caso

```bash
caption_generator=blip                                    # ← sem isto, cap_gen_model = None
video_root=/caminho/para/suas/cenas
collection=charades                                       # rótulo; afeta só caminhos
construct_name=blip_teste

caption_model=Salesforce/blip-image-captioning-large      # ← namespace obrigatório
blip_itm_model=Salesforce/blip-itm-base-coco              # ← idem
sentence_transformer=paraphrase-distilroberta-v2          # ok sem prefixo
glove_model=meta/glove.6B/glove.6B.300d.txt
```

---

## ⚠️ Correção de algo que eu afirmei antes

Ao reverificar o `QMPropGener` para te dar um exemplo com `prop_max_cnt`, descobri que **eu estava errado** numa conclusão anterior. Eu havia afirmado que `--prop_max_cnt 1` força o caso-base `boundaries=[0, VID_LEN]` ("um segmento = vídeo inteiro"). **Não força.**

O motivo está nas linhas 95–97: o primeiro candidato a fronteira é adicionado **incondicionalmente**, *antes* de a verificação de `prop_max_cnt` (linha 98) sequer ser avaliada. Logo, `boundaries` nunca fica vazio, e o caso-base da linha 109 não é atingido. Simulei o algoritmo fielmente com 200 vídeos sintéticos:

| `prop_max_cnt` | 1 segmento | 2 segmentos | 3+ |
|---|---|---|---|
| **1** | 9 | **191** | 0 |
| **2** | 13 | **187** | 0 |
| 5 | 0 | 0 | 200 |

Com `prop_max_cnt=1` você obtém **dois** segmentos em ~95% dos casos, não um. O único caso que colapsa para um é quando a fronteira escolhida cai a menos de `min_prop_size` de uma das pontas (as linhas 112–119 então a absorvem) — o que é acidente dos dados, não garantia de configuração.

**A consequência para a sua decisão:** "uma legenda por cena via configuração pura" **não é alcançável** como eu havia dito. O caminho limpo passa a ser uma extensão via *registry* — uma classe `WholePropGener` registrada com `@REGISTER_PROPGEN(["whole"])` que devolve um único segmento `[0, VID_LEN]`, sem tocar no `QMPropGener`. É exatamente o OCP que o repo já suporta (só precisaria acrescentar `"whole"` aos `choices` do `cfg.py`).

Se quiser, no próximo passo eu disseco essa alternativa em detalhe — ou seguimos com a Dúvida 3 e voltamos a isso depois.
