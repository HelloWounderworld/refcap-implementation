# Guia de Testes — Índice
## Como Verificar que a Caption API Está Funcionando

---

> **Três documentos, três propósitos:**
>
> | documento | quando usar |
> |---|---|
> | **este** | visão geral, os scripts automáticos, e o que fazer quando algo falha |
> | [`TESTES_CURL.md`](TESTES_CURL.md) | testar caso a caso, à mão, com `curl` |
> | [`TESTES_DIAGNOSTICO.md`](TESTES_DIAGNOSTICO.md) | quando o serviço não sobe, ou os modelos não ficam na GPU |

---

# PARTE 1 — O caminho rápido

Três comandos, e você sabe se está tudo em ordem:

```bash
# 1. descobre as SUAS cenas (ou cria, se o diretório estiver vazio)
bash preparar_teste.sh /caminho/das/suas/cenas

# 2. ★ CONFIRA o teste_config.sh gerado — e edite se quiser outras cenas
cat teste_config.sh

# 3. sobe o serviço COM os modelos — noutro terminal
cd api && python app.py

# 4. roda a bateria de 18 casos
bash teste_manual.sh
```

No fim, você vê:
```
  12 passou   0 falhou   1 pulado

  ✓ Todos os casos executados passaram.
```

Se algo falhar, o script diz **qual caso** e **o que veio em vez do esperado**.

---

# PARTE 2 — `preparar_teste.sh`

**★ Ele usa as SUAS cenas.** Olha o diretório indicado primeiro; só gera vídeos
sintéticos se não achar nenhum `.mp4`.

```bash
bash preparar_teste.sh                        # /tmp/teste_refcap (gera se vazio)
bash preparar_teste.sh /dados/minhas_cenas    # ★ usa as SUAS
BASE=/dados/cenas bash preparar_teste.sh
bash preparar_teste.sh --limpar               # só remove as sintéticas
```

**[J] O `--limpar` recusa apagar um diretório que não seja o sintético.** Suas
cenas nunca são tocadas.

## O que ele faz

1. **Inventaria** o diretório — quantos `.mp4` há
2. **Mapeia** a estrutura `{program_id}/{video_id}/{scene_id}.mp4`, lendo a
   **duração real do stream** de cada um (é o que o RefCap lê, e difere do player)
3. **Escolhe** uma cena para cada papel do teste
4. **Grava** o `teste_config.sh` — que você pode abrir e editar

## Os cinco papéis

| papel | para que serve | se faltar |
|---|---|---|
| `CENA_A1` | caminho feliz e testes de cache | 6 casos pulados |
| `CENA_A2` | lote no mesmo diretório | 3 casos pulados |
| `CENA_B1` | **outro diretório** — prova o agrupamento | 1 caso pulado |
| `CENA_CURTA` | **< 1 s** — prova o patch do `viddataset` | 1 caso pulado |
| `CENA_P2` | **outro `program_id`** — prova o isolamento | 1 caso pulado |

**[J] Papel ausente = teste PULADO, não falhado.** Se o seu conjunto não tem
cena com menos de 1 s, o caso 4 é pulado com aviso — em vez de acusar erro.

## A escolha do programa principal

Ele **não** pega o primeiro em ordem alfabética — pega o **mais rico**: o que
tem mais diretórios, mais cenas, e de preferência uma cena curta. Assim o
máximo de papéis é preenchido.

**Exemplo real, com cenas de verdade:**
```
program_id       video_id     scene_id       duração  frames
──────────────────────────────────────────────────────────────
jornal_y         ed01         abertura        2.000s     2
novela_x         ep01         abertura        3.000s     3
novela_x         ep01         closing         3.000s     3
novela_x         ep01         flash           0.600s     1  <-- < 1s
novela_x         ep02         cena_final      2.000s     2

✓ CENA_A1     abertura      caminho feliz + testes de cache
✓ CENA_A2     closing       lote no MESMO diretório
✓ CENA_B1     cena_final    ★ OUTRO diretório — agrupamento
✓ CENA_CURTA  flash         ★ < 1s — patch do viddataset
✓ CENA_P2     abertura      ★ outro program_id — isolamento

★ o scene_id 'abertura' existe nos DOIS programas — o teste de
  isolamento fica completo.
```

Note que ele escolheu `novela_x` (2 diretórios, 3 cenas, uma curta) e não
`jornal_y` (1 diretório, 1 cena), embora `jornal_y` viesse antes no alfabeto.

## O `teste_config.sh` — seu para editar

```bash
BASE="/tmp/minhas_cenas"
PROG="novela_x"
PROG2="jornal_y"

CENA_A1_ID="abertura"
CENA_A1_VID="ep01"
CENA_A1_PATH="/tmp/minhas_cenas/novela_x/ep01/abertura.mp4"
...
DIR_VAZIO="/tmp/minhas_cenas/novela_x/__vazio_para_teste"
DIR_COM_VIDEO="/tmp/minhas_cenas/novela_x/ep02"
```

**Se a descoberta escolheu cenas diferentes das que você quer**, troque os
valores. O `teste_manual.sh` lê daqui — não precisa rodar o preparador de novo.

**★ Isso é o que torna a bateria portátil:** o mesmo conjunto de 18 testes roda
em qualquer ambiente, sobre qualquer conjunto de cenas, mudando só este arquivo.

## Se a sua estrutura for diferente

O script espera `{program_id}/{video_id}/{scene_id}.mp4`. Com outra estrutura,
ele ainda encontra os `.mp4`, mas `program_id` e `video_id` podem sair errados
— **confira o config gerado** e ajuste.

---

# PARTE 3 — `teste_manual.sh`

**O que faz:** 18 casos contra a API rodando, com PASS/FAIL por caso.

```bash
bash teste_manual.sh              # a bateria inteira
bash teste_manual.sh 10           # só o caso 10
API=http://outro:8000 bash teste_manual.sh
```

## Os 18 casos

**Parte 1 — caminho feliz**

| # | caso | espera |
|---|---|---|
| 1 | `POST /caption` (uma cena) | 200 + legenda + keywords |
| 2 | `POST /caption/batch` (2 diretórios) | 200, `groups` = 2 |
| 3 | assíncrono automático | 202 + `accepted` |
| 4 | **vídeo de 0,5 s** | 200 — prova o patch |

**Parte 2 — cache**

| # | caso | espera |
|---|---|---|
| 5 | reprocessar **sem** `force` | rápido; `estavam_em_cache: 1` |
| 6 | **com** `force` | mais **lento** — reprocessou |
| 7 | as outras cenas sobreviveram | ≥ 4 cenas persistidas |

**[J] O caso 6 mede o tempo de propósito.** Se ele levar o mesmo que o caso 5, o cache não foi limpo — e o `force` não está funcionando.

**Parte 3 — erros**

| # | caso | espera |
|---|---|---|
| 8 | caminho inexistente | `FILE_NOT_FOUND` |
| 9 | diretório sem a cena | `SCENE_NOT_FOUND` |
| 10 | **fallback removido** | `SCENE_NOT_FOUND` |
| 11 | pedido vazio | HTTP 400 ou 422 |
| 12 | **erro parcial no lote** | HTTP **200**, `ok=2 errors=1` |

**[J] O caso 10 merece atenção.** O `vidB` tem **um** vídeo (`cena_04`); pedir `cena_77` apontando para o diretório deve **recusar**. Antes da Etapa 2, isso legendava a `cena_04` e devolvia `success` — silenciosamente errado.

**[J] E o caso 12 confirma que uma cena ruim não derruba o lote:** HTTP 200, com o erro dentro do item.

**Parte 4 — consulta**

| # | caso | espera |
|---|---|---|
| 13 | `GET /caption/{pid}` | todas as cenas |
| 14 | com 1 filtro | 1 cena |
| 15 | com 2 filtros | 2 cenas |
| 16 | programa inexistente | **200** + lista vazia (não 404) |

**Parte 5 — isolamento**

| # | caso | espera |
|---|---|---|
| 17 | mesmo `scene_id`, programas diferentes | legendas **distintas** |
| 18 | `/diagnostics/caption` | responde; cria `annos/diagnostics/` |

**[J] O caso 17 imprime as duas legendas lado a lado.** Se saírem iguais, o isolamento por `collection` falhou — e é o erro silencioso mais grave que existiria.

## Sobre o caso 3 (assíncrono)

Ele exige o limiar baixo:

```bash
REFCAP_LIMIAR_ASSINCRONO=2 python app.py
```

Sem isso, o caso é **pulado com aviso** — em vez de exigir 31 cenas reais só para exercitá-lo.

---

# PARTE 4 — O que conferir no disco

O script termina listando isto, mas vale ter à mão:

```bash
cd <raiz-do-RefCap>

ls annos/                              # prog_teste, prog_outro, diagnostics
ls meta/captions/                      # prog_teste_blip.jsonl, prog_outro_blip.jsonl
ls results/construct/prog_teste/       # proposals.json, tree.json, *.pt
ls results/response/prog_teste/scenes/ # um .json por cena
```

## As quatro verificações que valem o olho

**1. A fusão do `proposals.json` funcionou**
```bash
python -c "import json;print(sorted(json.load(open('results/construct/prog_teste/proposals.json'))))"
```
Deve listar **todas** as cenas processadas. Se tiver só as do último lote, a fusão não rodou.

**2. O histórico guarda todas as versões**
```bash
wc -l results/response/prog_teste/responses.jsonl
ls results/response/prog_teste/scenes/ | wc -l
```
O `.jsonl` deve ter **mais linhas** que `scenes/` tem arquivos — o `force` gerou uma versão nova da mesma cena.

**3. Uma cena guarda tudo**
```bash
python -m json.tool results/response/prog_teste/scenes/cena_01.json
```
Deve ter `scene_caption_en`, `keywords_en`, `timestamp`, e dentro de `diagnostics`: `ranking`, `n_raw`, `n_distinct`, `warning`.

**4. Os modelos continuam residentes**
```bash
curl -s localhost:8000/health | python -m json.tool | grep allocated_mb
```
Rode **antes e depois** da bateria. O número deve ser **o mesmo** — se crescer, algo está recarregando modelo a cada requisição.

---

# PARTE 4.5 — ★ Onde as cenas podem estar

**Em qualquer lugar.** O caminho vai **absoluto** na requisição, e a API deriva
o `video_root` dele — por requisição, por grupo.

**[V] Verificado:** uma cena em `/tmp/longe/muito/fundo/prog_z/vid9/cena_x.mp4`
processou normalmente, e o grupo reportou `video_root` = aquele diretório.

Não há exigência de que as cenas estejam perto do `api/`, dentro do RefCap, ou
sob o `video_root` do `cfg.py`.

**As duas exceções**, ambas em rotas de diagnóstico:

| rota | como se refere ao vídeo |
|---|---|
| `GET /diagnostics/caption?video=X.mp4` | **nome do arquivo** no `video_root` configurado |
| `GET /diagnostics/caption-batch?diretorio=...` | caminho absoluto, como as de produção |

## Se o preparador errar a estrutura

Ele espera `{program_id}/{video_id}/{scene_id}.mp4`. Com outra organização, o
`program_id` e o `video_id` descobertos podem sair errados — **edite o
`teste_config.sh`**, que é para isso que ele existe.

---

# PARTE 5 — Quando algo falha

| sintoma | provável causa | onde olhar |
|---|---|---|
| **pré-voo: "serviço não respondeu"** | o serviço não está no ar, ou está noutra porta | o script diz a causa e os 4 passos. **Não tem relação com o caminho das cenas** |
| pré-voo: `models.ready: False` | subiu com `REFCAP_CARREGAR_MODELOS=0` | remova a variável |
| caso 4 falha (vídeo curto) | patch do `viddataset` não aplicado | `grep n_amostras dataset/viddataset.py` |
| caso 6 tão rápido quanto o 5 | o `force` não limpou o cache | veja `cache_limpo` na resposta |
| caso 10 devolve `success` | o fallback antigo ainda está lá | `grep "último recurso" api/pipeline.py` |
| caso 17: legendas iguais | o `collection` não isolou | confira que é `program_id`, não fixo |
| `allocated_mb` cresce | modelos recarregando | veja [`TESTES_DIAGNOSTICO.md`](TESTES_DIAGNOSTICO.md) |

---

# PARTE 6 — Os limites deste guia

**[J]**

- Os scripts foram **validados sintaticamente** e o `preparar_teste.sh` foi executado, mas a bateria completa **não** foi rodada ponta a ponta contra um serviço com GPU real — isso depende do seu ambiente.
- Os tempos citados (~1–3 s por cena) são estimativa, não medição.
- A bateria testa o **contrato e o fluxo**, não a **qualidade** das legendas. Se o BLIP produzir uma legenda ruim, todos os 18 casos passam.
- Não há teste de carga nem de concorrência real — a fila é serializada por projeto, e testá-la exigiria disparar requisições simultâneas.

---

*Guia de testes da Caption API. Comece pela Parte 1; se algo falhar, a Parte 5 aponta onde olhar. Para testar caso a caso à mão, veja `TESTES_CURL.md`; para problemas de infraestrutura (GPU, supervisord, modelos), veja `TESTES_DIAGNOSTICO.md`.*
