# O Que Mudou — Do Esqueleto ao Contrato Acordado
## Relatório Didático das Implementações e Como Cada Uma Atende ao Pedido

---

> **O que é este documento.** A explicação, passo a passo, das mudanças feitas para o serviço atender aos formatos de requisição e resposta que você definiu — e como cada mudança responde a uma exigência específica.
>
> **O ponto de partida.** O `POST /jobs` existia mas **não funcionava de verdade**: reaproveitava os modelos, mas ignorava a lista de vídeos do pedido e não escrevia o arquivo de anotações. O job voltava `concluido` sem ter processado nada.
>
> **O ponto de chegada.** As três rotas — uma cena, lote por diretório, e o `POST /jobs` — produzem **o mesmo contrato de saída**, com os modelos residentes reaproveitados em todas.
>
> **★ ATUALIZADO.** O `POST /jobs` passou a ser **síncrono por padrão**: devolve o resultado completo (HTTP 200) em vez de 202 + `job_id`. O modo assíncrono continua disponível com `"assincrono": true`. Ver Parte 4.

---

## Protocolo

| Marca | Significa |
|---|---|
| **[L]** | Lido no código do RefCap — arquivo e linha |
| **[V]** | Verificado por execução nesta sessão |
| **[J]** | Decisão de projeto — julgamento, não fato medido |

---

# PARTE 1 — O diagnóstico que motivou tudo

Antes das mudanças, o `POST /jobs` foi instrumentado. O que o `build()` recebia:

| item | valor | avaliação |
|---|---|---|
| modelos residentes | `True` | ✓ funcionava |
| `collection` | o default do `cfg` | ✗ não isolava |
| `video_root` | o da configuração | ✗ ignorava o pedido |
| arquivo de anotações | **não existia** | ✗ ninguém escrevia |

**[V] E o job voltava `concluido`.** Esse é o pior desfecho possível: sem o arquivo de anotações, o `select_videos` (**[L]** `constructpipe/base.py:186-203`) descarta **todos** os vídeos **em silêncio** — sem erro, sem aviso. O `build()` roda com lista vazia e devolve `{}`.

**[J] Pior ainda:** se já existisse um arquivo de anotações do `collection` default — de uma execução anterior ou do seu `make_annos.py` — o job processaria **aqueles** vídeos, ignorando o pedido. Você receberia um resultado plausível, do conjunto errado.

Cinco coisas faltavam. Cada uma virou um passo da implementação.

---

# PARTE 2 — A restrição que moldou a arquitetura

**[L]** `constructpipe/base.py:43`:
```python
vid_list = os.listdir(self.cfg.video_root)
```

**Um diretório por execução.** Mas as suas cenas ficam em:
```
/caminho/{program_id}/{video_id}/{scene_id}
```

Cenas de `video_id` **diferentes** estão em **diretórios diferentes**. Um lote misto não cabe numa única chamada de `build()`.

**[J] A solução: agrupar por diretório.** Um `build()` por grupo, cenas do mesmo vídeo processadas juntas.

**[V] Verificado** — um lote com 3 cenas em 2 diretórios gerou exatamente 2 chamadas:
```
root=/tmp/cenas/prog1/vidA  collection=prog1  nomes=['cena_01','cena_02']
root=/tmp/cenas/prog1/vidB  collection=prog1  nomes=['cena_03']
```

**[J] Por que isso importa para você:** não é uma limitação que inventei — é do RefCap. Se um dia o lote tiver cenas de muitos vídeos diferentes, serão muitas chamadas de `build()`. Cada uma reaproveita os modelos (o custo caro), mas há um custo fixo por chamada.

---

# PARTE 3 — O novo módulo `processamento.py`

**[J] Por que um arquivo separado:** o `app.py` já tinha 400+ linhas. A lógica de pipeline e transformação é substancial e **testável sem subir o FastAPI** — por isso `montar_cfg` e `modelos` entram como parâmetros da função, não como imports globais.

São 445 linhas em quatro blocos:

| bloco | linhas | responsabilidade |
|---|---|---|
| Contratos | 55–127 | os modelos Pydantic de entrada e saída |
| Resolução de caminho | 132–180 | descobrir o arquivo a partir do `scene_video_path` |
| Palavras-chave | 188–252 | ranquear as `keys` contra a legenda |
| O pipeline | 257–445 | os cinco passos + a transformação da saída |

## 3.1 Os contratos — como as duas formas viram uma

**A exigência:** aceitar cena única **e** lote, nos formatos que você definiu.

```python
class PedidoDeJob(BaseModel):
    # forma "cena única" — campos no nível de cima
    scene_id: str | None = None
    video_id: str | None = None
    program_id: str | None = None
    scene_video_path: str | None = None

    # forma "lote"
    items: list[ItemDeCena] | None = None
```

**[J] A decisão que evita duplicação:** o método `como_itens()` normaliza as duas formas numa **lista única**. Cena única vira um lote de um.

```python
def como_itens(self) -> list[ItemDeCena]:
    if self.items:
        return list(self.items)
    if self.scene_id and self.scene_video_path:
        return [ItemDeCena(...)]
    return []
```

**Todo o resto do código trata só listas.** Não há dois caminhos de execução para manter, testar e sincronizar — que é onde bugs de "funciona num, quebra no outro" nascem.

## 3.2 A resolução de caminho — tratando uma ambiguidade

**O problema:** o `scene_video_path` que você especificou é `/caminho/{program_id}/{video_id}/{scene_id}` — **sem extensão**. Isso é ambíguo: pode ser um arquivo cuja extensão foi omitida no esboço, ou um diretório.

**[J] A decisão: tratar os três casos**, em vez de escolher um e falhar nos outros:

```
1. é um ARQUIVO existente     -> usa direto
2. arquivo SEM extensão       -> tenta .mp4, .mkv, .avi, .webm, .mov, .m4v
3. é um DIRETÓRIO             -> procura lá dentro um vídeo com o scene_id
                                 (e, se houver só um vídeo, usa ele)
```

**[V] E a falha é isolada.** Um lote com 4 cenas, uma inexistente:
```
resumo: {"total": 4, "ok": 3, "erros": 1}
  cena_01     -> success
  cena_02     -> success
  cena_03     -> success
  inexistente -> error | não encontrei a cena 'inexistente' em /tmp/.../vidZ/
```

Uma cena ruim **não derruba o lote** — ela recebe `status: "error"` com mensagem diagnóstica, e as outras seguem.

## 3.3 O ranqueamento das palavras-chave

**A exigência:** *"comparar cada palavra-chave da lista `keys` com a legenda `cap`, e ranquear"*.

**Por que é necessário:** o campo `keys` traz substantivos e verbos de **todas** as legendas de **todos** os frames da cena. Muitas não têm relação com a legenda que venceu.

**A fórmula, e o que cada parte mede:**

| sinal | peso | o que capta |
|---|---|---|
| **presença literal** | 0.6 | a palavra aparece na legenda? Sinal forte e inequívoco |
| **similaridade semântica** | 0.4 | cosseno entre a palavra e a legenda, via sentence-transformer |

O segundo sinal capta relação **sem repetição literal** — `cooking` × *"preparing food"*.

**[V] Verificado:**
```
legenda: "a woman preparing food in a kitchen"
  woman     0.6    ← na legenda
  kitchen   0.6    ← na legenda
  food      0.6    ← na legenda
  knife     0.0    ← fora
  dog       0.0    ← fora
```

**[J] Limite declarado no próprio código:** essa ponderação é **decisão de projeto, não resultado medido**. Não há referência para dizer qual peso é certo, e comparar um token isolado a uma frase via embedding é ruidoso — é por isso que a presença literal domina. Se você tiver exemplos anotados no futuro, os pesos 0.6/0.4 são o primeiro lugar a calibrar.

**Sobre a pergunta que você fez** — se já existia recurso pronto:

**[L]** Existe `compute_similarities` em `KeyPipe.py:32-48` e `MixPipe.py:33`, com **GloVe**. Três razões para não servir: é do `retrieve`, o GloVe não é carregado pela API, e compara palavra × palavra (não palavra × legenda).

Entre os quatro modelos residentes:

| modelo | serve? |
|---|---|
| `sentence_transformer` | **sim** — texto × texto ← o usado |
| `blip_itrtv_model` | **sim** — palavra × **frame** (alternativa não usada) |
| `spacy en_core_web_sm` | não — o `_sm` não tem vetores estáticos |
| `cap_gen_model` | não pontua palavras |

**[J] A alternativa do BLIP-ITM** (pontuar a palavra contra o frame, não contra a legenda) seria mais ancorada no vídeo — mas exigiria acesso aos frames no momento de montar a resposta, e ali só existe o `proposals.json`. Fica registrada como opção futura.

## 3.4 Os cinco passos do pipeline

O que faltava ao `POST /jobs`, implementado em `processar_pedido`:

**Passo 1 — resolver os caminhos.** Cada item vira `(diretório, arquivo, nome_base)`, ou uma falha isolada.

**Passo 2 — agrupar por diretório** (Parte 2).

**Passo 3 — decidir o `collection`.**
```python
precedência:  pedido.collection  >  program_id  >  job_id
```
**[J] Por que o `program_id`:** você disse que ele já vem determinado, e é o candidato natural. Cenas do mesmo programa **compartilham cache** — desejável, já que costumam ser reprocessadas juntas. Programas diferentes ficam isolados.

**Passo 4 — tratar o cache.** Lê quem já está processado **antes** de rodar. `limpar_cache` default `False`.

**Passo 5 — escrever o arquivo de anotações.** ★ O passo sem o qual **nada é processado**.

Depois: `build(cfg, modelos.como_dict())` — com os modelos residentes.

---

# PARTE 4 — O contrato de saída, nas três rotas

**A exigência:** o formato que você definiu, e em lote uma lista dele.

```json
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
```

**[V] As três rotas produzem o mesmo contrato:**

| rota | formato | espera? |
|---|---|---|
| `GET /teste/construct` | o objeto, **no topo** da resposta | sim |
| `GET /teste/construct-lote` | `{"items": [ ...o objeto... ]}` | sim |
| `POST /jobs` | `{"job_id", "estado", "resumo", "items": [...]}` | **sim** ★ |
| `POST /jobs` com `"assincrono": true` | 202 + `job_id` | não |

### ★ O envelope do `POST /jobs`

```json
{
  "job_id": "9e8adacb...",
  "estado": "concluido",
  "resumo": {"total": 3, "ok": 3, "erros": 0},
  "items": [ { ...o contrato de cada cena... } ],
  "grupos": [ {"diretorio": "...", "collection": "prog1", "cenas": 2} ],
  "segundos": 12.4
}
```

**[J] Os campos extras são diagnóstico:** `grupos` mostra o agrupamento por diretório (quantas chamadas de `build` houve e com qual `collection`), e `segundos` o tempo total. Ignore-os se só precisar dos `items`.

**Códigos HTTP:**

| situação | HTTP |
|---|---|
| tudo certo | 200 |
| cena individual falhou | **200**, com `status: "error"` no item |
| o job inteiro falhou | 500 |

**[J] Nas rotas de teste, o contrato fica no topo e o diagnóstico ao lado** (`passos`, `modelos_reaproveitados`, `ranking`, `exp_dir`). Você recebe o formato de produção **sem perder** o que torna a rota útil para depurar.

**`model_name` e `model_version`** ficaram configuráveis por ambiente (`REFCAP_MODEL_NAME`, `REFCAP_MODEL_VERSION`), com defaults `refcap` / `v1` — para você decidir depois sem mexer no código.

---

# PARTE 5 — Como cada exigência foi atendida

| # | o que você pediu | onde está | verificado |
|---|---|---|---|
| 1 | aceitar o formato de cena única | `PedidoDeJob` + `como_itens()` | **[V]** |
| 2 | aceitar o formato de lote (`items`) | idem — vira lista única | **[V]** |
| 3 | usar os modelos já carregados | `build(cfg, modelos.como_dict())` | **[V]** |
| 4 | responder no formato acordado | `RespostaDeCena` | **[V]** |
| 5 | em lote, uma resposta por item | `{"items": [...]}` | **[V]** |
| 6 | keywords ranqueadas contra a legenda | `ranquear_keywords` | **[V]** |
| 7 | o mesmo formato nas rotas de teste | as três padronizadas | **[V]** |
| 8 | cache com controle, default **não limpar** | `limpar_cache=False` | **[V]** |
| 9 | aceitar diretório na rota de lote | `?diretorio=...` | **[V]** |

---

# PARTE 6 — Correções feitas no caminho

**[J]** Três coisas que os testes revelaram:

**1. A rota de lote quebrava ao reportar falha.** Ela acessava `cfg.exp_dir`, que é injetado pelo `build()`. Se o build falhasse cedo, o atributo não existia e a rota estourava **ao tentar montar a mensagem de erro**. Corrigido com `getattr`.

**2. As keywords vinham por caminho indireto.** A rota de um vídeo lia via `tree_meta["subs"][0]["keys"]`. Verifiquei que o `build_tree_meta` de fato propaga o campo (**[L]** `constructpipe/base.py:178-179`), mas troquei para ler do `proposals.json` — a fonte — com o `tree_meta` como alternativa.

**3. Rotas duplicadas de sessões anteriores.** Havia duas `/teste/construct-lote` e uma `/teste/captioning` redundante. Removidas — duas versões da mesma rota são fonte de confusão sobre qual vale.

---

# PARTE 7 — O que ainda não foi feito

**[J]** Declarado explicitamente:

- **Nada rodou com GPU ou vídeo real** nesta sessão. Os testes usaram um `build()` falso para verificar o **fluxo** — agrupamento, anotações, cache, formato de saída. O reaproveitamento dos modelos foi provado antes, por instrumentação.
- **Os pesos 0.6/0.4 não foram calibrados** — não há dados anotados para isso.
- **Sem upload de arquivo.** Os vídeos precisam já estar no caminho informado.
- **Sem limite de tamanho de lote** nem timeout por job.
- **A alternativa do BLIP-ITM** para os pesos não foi implementada.

---

# PARTE 8 — Referência rápida

```bash
# cena única
curl -s -X POST localhost:8000/jobs -H 'Content-Type: application/json' -d '{
  "scene_id": "cena_01", "video_id": "vidA", "program_id": "prog1",
  "scene_video_path": "/caminho/prog1/vidA/cena_01"
}'

# lote
curl -s -X POST localhost:8000/jobs -H 'Content-Type: application/json' -d '{
  "items": [
    {"scene_id":"cena_01","video_id":"vidA","program_id":"prog1","scene_video_path":"..."},
    {"scene_id":"cena_02","video_id":"vidB","program_id":"prog1","scene_video_path":"..."}
  ]
}'

# consultar
curl -s localhost:8000/jobs/<job_id> | python -m json.tool

# testes diretos (síncronos)
curl -s "localhost:8000/teste/construct?video=cena_01.mp4"
curl -s "localhost:8000/teste/construct-lote?diretorio=/dados/cenas"
```

Campos opcionais no `POST /jobs`: `collection`, `proposal_generator`, `limpar_cache`, `callback_url`.

---

*Relatório das mudanças que levaram o serviço do esqueleto ao contrato acordado. O diagnóstico inicial mostrou que o `POST /jobs` devolvia `concluido` sem processar nada — porque ninguém escrevia o arquivo de anotações, e o `select_videos` descarta em silêncio. Os cinco passos que faltavam viraram o módulo `processamento.py`, com uma decisão estrutural: agrupar por diretório, já que o `build()` lista um diretório por execução. As três rotas hoje produzem o mesmo contrato, e a Parte 7 declara o que não foi feito.*
