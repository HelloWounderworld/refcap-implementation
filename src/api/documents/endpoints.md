# Endpoints que queremos no app.py (claro, os testes nao estao inclusos, porem, eu vou criar como pre-caucao)

## POST/job -> POST/caption

### Request:

```json
{
    "scene_id": "scene_id",
    "video_id": "video_id",
    "program_id": "nome_do_programa_seriado",
    "scene_video_path": "path_prefix_mutavel_por_usuario_eu/{program_id}/{video_id}/{scene_id}.mp4"
}
```

**Ainda nao se sabe se sera necessario utilizar o "video_id" ou nao... Agora, o "scene_id" e o "program_id" sera necessario para conseguirmos identificar o diretorio (montado) que iremos realizar o captioning sobre as cenas de cada programa de TV que esta sendo indicado pelo "program_id"... Por isso, vamos precisar verificar e tornar fixo algumas variaveis que ira cofigurar o annos e o result, de modo que, se vier um "program_id" verificarmos se ja existe essa variavel salvo ou nao! Se estiver salvo, utilizar o mesmo, porem, se nao tiver salvo, criar um novo annos com o nome desse programa, e utilizar o result, tambem, em cima desse programa, utilizando todas as funcionalidades dos caches em cima dela!! Os arquivos como Proposal e o Response, terao que ficar guardados de forma cumulativa (claro, com possibilidade de atualizarmos o "scene_id" caso necessario e incluir isso no cache!) e com cache tambem, para caso precisarmos de resgate rapido de uma requisicao durante o retrieval!!**

### Response:
**Precisa desse job_id??? Nao daria para fixar somente para uma para cada {program_id}? No sentido de que, quando for criado o "/results/construct/{nome_da_emissora_tv_fixo_hardcoded = collection}/{program_id = construct_name}, e dentro do diretorio {program_id}, criar os arquivos .pt's, .jsonl, .json's, etc...? Assim, imagino que o annos, ficara fixo, porem, nao dariamos, para considerar, dentro do annos, uma coisa hardcoded, pelo collection = nome_da_emissora_tv_fixo_hardcoded, a sua path ou a variavel em algum lugar, para que, dentro dessa annos, seja criados os respectivos diretorios com o {program_id} com os seus respectivos arquivos. vcmr.jsonl, com as funcionaliddes dos caches e tudo mais??**

**No keywords_en colocar somente as palavras chaves que contem dentro do captioning!!**
```json
{
  "job_id": "9e8adacb...",
  "state": "concluded",
  "resume": {"total": 3, "ok": 3, "errors": 0},
  "items": [
    {
      "scene_id": "cena_01",
      "scene_caption_en": "a woman preparing food in a kitchen",
      "keywords_en": [
        {"token": "woman",   "weight": 0.6},
        {"token": "kitchen", "weight": 0.6},
        {"token": "food",    "weight": 0.6}
      ],
      "model_name": "refcap",
      "model_version": "v1",
      "status": "success"
    }
  ],
  "seconds": 12.4
}
```

**Nao daria para colocar a possibilidade de o status informar o seguinte, caso de algum erro, como abaixo?**

```json
{
  "job_id": "9e8adacb...",
  "state": "concluido",
  "resume": {"total": 3, "ok": 3, "errors": 0},
  "items": [
    {
      "scene_id": "cena_01",
      "scene_caption_en": "a woman preparing food in a kitchen",
      "keywords_en": [
        {"token": "woman",   "weight": 0.6},
        {"token": "kitchen", "weight": 0.6},
        {"token": "food",    "weight": 0.6}
      ],
      "model_name": "refcap",
      "model_version": "v1",
      "status": "error",
      "error_code": "INVALID_REQUEST",
      "message": "Invalid Request (alguma coisa do tipo...)"
    }
  ],
  "seconds": 12.4
}
```

**Sendo os erros de codigos sao como o seguinte**

```markdown
INVALID_REQUEST
CAPTION_FAILED
SCENE_NOT_FOUND
FILE_NOT_FOUND
INTERNAL_ERROR
```

## POST/job -> POST/caption/batch

### Request:

```json
{
    "items": [
        {
            "scene_id": "scene_id",
            "video_id": "video_id",
            "program_id": "nome_do_programa_seriado",
            "scene_video_path": "path_prefix_mutavel_por_usuario_eu/{program_id}/{video_id}/{scene_id}.mp4"
        }
    ]
}
```

## GET/health

```json
{
    "status": "ok",
    "service": "caption-api"
}
```

## Calculo do Weight:
Como o weight é calculado

A fórmula:

weight = 0.6 × presença_literal + 0.4 × similaridade_semântica

O primeiro sinal é binário: a palavra aparece na legenda escolhida? Comparação de tokens em minúsculas.

O segundo usa o sentence_transformer — o modelo paraphrase-distilroberta-v2. Ele codifica cada keyword e a legenda como vetores, e o peso é o cosseno entre eles, reescalado de [−1,1] para [0,1].

Resposta: Certo. Entao, por hora, deixa o weight hardcoded para o valor "1.0". Motivo disso, seria por conta de que eu irei ler um artigo do Glove, para entendermos se, de fato, esse weight, ela eh necessario ou nao para conseguirmos realizar o retrieval, que foi construido de forma independente por um outro API, que utiliza o Glove. Eu preciso entender bem se eh ou nao necessario, primeiro, para depois decidir o que fazer com a funcao que calcula o weight! Por hora, eu quero que deixe ela em aberto!!

⚠️ E aqui está a fraqueza que eu preciso apontar

O paraphrase-distilroberta-v2 foi treinado para comparar SENTENÇAS, não palavras isoladas. Usá-lo para pontuar um token contra uma frase é operar fora do domínio de treino dele. Foi por isso que a presença literal ficou com o peso maior (0.6) — mas isso é remendo, não solução.

E os pesos 0.6/0.4 não foram calibrados: escolhi por julgamento, sem dados anotados.

Três alternativas que valem discutir, se você quiser um cálculo mais defensável:

BLIP-ITM contra o frame — "quão bem esta palavra descreve o que se vê". Ancorado no vídeo, mas exige passar os frames adiante no pipeline.
Trocar o sentence-transformer por um modelo que tenha vetores de palavra (en_core_web_md/lg do spaCy, ou GloVe).
Abandonar o sinal semântico e usar só presença literal + frequência entre as legendas dos frames. Mais simples e honesto.

Resposta: Entao, eh mais motivo para deixarmos em aberto por hora para eu procurar a estudar e entender melhor o que deve ser feito!!

## Problema das cenas:
Um erro silencioso que acabei de provar

Este é o mais grave que conheço, e vale priorizar.

Cenário plausível: duas cenas com o mesmo scene_id em vídeos diferentes — cena_01 no vidA e cena_01 no vidB, mesmo program_id.

grupo 1 (vidA): 'cena_01' é novo        → BLIP roda ✓
grupo 2 (vidB): 'cena_01' JÁ está no cache
                → BlipCapGener.py:18 faz `return`
                → devolve a legenda do vidA   ✗ ERRADO

E os dois itens voltam com status: "success". Sem erro, sem aviso — e como ambos têm o mesmo scene_id, você nem consegue distinguir qual veio de qual vídeo.

A raiz: o RefCap identifica vídeos pelo nome-base, e eu usei o program_id como collection, então os dois grupos compartilham o cache. Preciso saber de você: os scene_id são únicos dentro de um program_id, ou podem repetir entre video_id diferentes?

Resposta: Nao tem problema!! O importante eh dividir pelo "program_id" que eh o nome do programa e, se dentro dela, existir algum "scene_id" igual, porem, do outro "program_id" diferente da atual, nao tem problema!! Desde que, tais cenas estejam registrados, unicamente, conforme cada "program_id"!
