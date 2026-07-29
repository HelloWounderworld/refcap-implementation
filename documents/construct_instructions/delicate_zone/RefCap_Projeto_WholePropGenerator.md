# Projeto do `WholePropGenerator` — v2
## Especificação Revisada: Um Segmento por Vídeo, com Ranqueamento de Legendas

---

> **O que é este documento.** A especificação de projeto — **antes do código** — de um gerador de propostas para o RefCap que emite **um único segmento por vídeo** (a cena inteira) e **ranqueia** as legendas geradas para ela.
>
> **Versão 2.** Substitui a v1. Três afirmações da v1 foram **refutadas por verificação** e estão corrigidas aqui, com registro explícito (§0.2). Um relatório que revisa a si mesmo sem declarar o que mudou não é confiável.
>
> **Base analítica.** `RefCap_Similaridade_Segmentacao_e_Selecao.md` (o diagnóstico) e `Fundamentos_Embeddings_Gram_e_Argmax.md` (a matemática).
>
> **Companheiro executável.** `LAB9_refcap_similaridade_verificacoes.py`.

---

## Protocolo de verificação

| Marca | Significa |
|---|---|
| **[L]** | **Lido no código** — arquivo e linha; confira abrindo |
| **[V]** | **Verificado numericamente ou empiricamente** — rode o `LAB9` ou o teste indicado |
| **[D]** | **Demonstrado** — prova no texto |
| **[J]** | **Julgamento meu** — decisão de projeto, não fato |

**Escopo.** Repositório `BUAAPY/RefCap`, branch padrão obtido por `git clone`. Linhas referem-se a essa versão. Exemplos numéricos são **sintéticos** e rotulados.

---

# PARTE 0 — Sumário e histórico de correções

## 0.1 O que será construído

Uma classe `WholePropGenerator`, registrada como `"whole"`, que:
1. emite **um segmento** cobrindo `[0, duration]` por vídeo, **declarado** (sem detecção de fronteiras);
2. **deduplica** as legendas do BLIP;
3. calcula **sinais de ranqueamento** a partir da matriz cruzada **bruta** (sem min-max);
4. emite o **ranking completo** como diagnóstico no `proposals.json`;
5. preserva as **keywords** de todos os frames (o ramo GloVe da busca).

**Integração:** três adições, zero modificações em arquivos existentes.

## 0.2 ★ Correções em relação à v1

| # | v1 afirmava | Verificação | v2 |
|---|---|---|---|
| 1 | Múltiplas legendas por segmento são "ganho grátis, zero modificações" | **[L]** `build_tree_meta:177` grava `'caps': [prop['cap']]` — **hardcoded** a um elemento | **Refutado.** Indexar várias exige **modificar** `build_tree_meta`. Ver §3.4 |
| 2 | Ramificar por duração: `N=1` / `1<x≤5s` / `>5s` | **[V-R5a]** o algoritmo de ranqueamento é **idêntico** para N=2 e N=300 | **Refutado.** Ramificar por *dado* (§6), não por duração |
| 3 | Simulação de segmentação com `prop_score_thr=0.2` | **[L]** `config/cfg.py:93-96` — default da dataclass é **0.5**; **[L]** `scripts/construct.sh:16` define **0.2** e o passa via `--prop_score_thr` (L45) | **A v1 estava certa.** 0.2 é o valor **efetivo** ao rodar pelo script distribuído. **[V]** A conclusão de §1.2 vale para **ambos** os valores (teste exaustivo idêntico) |

---

# PARTE 1 — Diagnóstico: por que um componente novo

## 1.1 Por que `prop_max_cnt` não resolve

**[L]** `QMPropGener.py:95-99`:
```python
95:      if len(boundaries)==0:
96:          boundaries.append(id)          # ← a 1ª fronteira entra INCONDICIONALMENTE
97:          continue
98:      if len(boundaries)+1>=self.cfg.prop_max_cnt:   # ← só avaliado a partir da 2ª
99:          break
```

A primeira fronteira candidata entra **antes** de a checagem de `prop_max_cnt` ser avaliada. Logo `boundaries` não fica vazio por essa via, e o caso-base `[0, VID_LEN]` (L109-110) não é alcançado por configuração.

**[J]** Conclusão: "um segmento por vídeo" **não é alcançável por configuração**. Exige um componente.

## 1.2 ★ O comportamento real da segmentação depende de N

**[V-R5a] Teste exaustivo** (todas as permutações de score). Parâmetros: **[L]** `cfg.py:56,97-102` — `prop_kernel_width=5`, `min_prop_size=3`, `prop_max_cnt=5`, `prop_min_cnt=2`; e `prop_score_thr` = **0.2** (**[L]** `scripts/construct.sh:16`, o valor efetivo) ou **0.5** (**[L]** `cfg.py:94`, default da dataclass) — **[V] a tabela abaixo é idêntica para os dois valores**:

| N | ordens testadas | segmentos |
|---|---|---|
| 1–5 | 1, 2, 6, 24, 120 | **sempre 1** |
| 6–8 | 720, 5.040, 40.320 | 1 ou 2 |

**[V-R5b] Teste aleatório** (2.000 sorteios/N, scores ~ N(0,1)):

| N | % que parte a cena |
|---|---|
| 5 | 0.0% |
| 6 | 25.7% |
| 10 | 76.8% |
| 20 | 99.8% |
| 30 | 100.0% |

**A causa [L]:** três travas — `:93-94` descarta as pontas; `:101-103` exige distância ≥ 5; `:112-113` absorve fronteira a menos de 3 do início.

**[J] A dupla implicação, e é o argumento central do projeto:**
- **N ≤ 5** (cenas até ~5s): a detecção de fronteiras é **inerte** — o resultado seria idêntico sem ela.
- **N ≥ 6**: ela é **ativa e crescentemente agressiva**. Sob a premissa "cada vídeo já é o corte desejado", isso é **destrutivo**: parte uma cena que se queria inteira.

Portanto o componente é necessário **precisamente para durações ≥ 6s** — e inofensivo abaixo disso.

**[J] Limite deste teste:** os scores foram sorteados de uma normal, não medidos. O teste caracteriza o **algoritmo**, não estima a frequência de partição numa coleção real.

## 1.3 Por que o critério de seleção também merece revisão

**[L]** `QMPropGener.py:128-133` seleciona por `argmax(capframe_scores[faixa])`, e `capframe_scores` é a **diagonal** da matriz cruzada (**[L]** `sim_utils.py:91`).

**[J]** A legenda *i* foi gerada **a partir do** frame *i*, então `sim(legenda_i, frame_i)` não é medição independente. Detalhamento e limites em `RefCap_Similaridade_Segmentacao_e_Selecao.md` §8 — inclusive o que **não** posso afirmar (que produza escolhas piores nos seus dados).

---

# PARTE 2 — Encaixe arquitetural

## 2.1 O mecanismo: registry

**[L]** `pipeline/propgenerator/base.py`:
- `PROPGEN_REGISTRY = {}` — linha 6
- `REGISTER_PROPGEN(names)` — linhas 8–20, com `return cls` na 19
- `BasePropGen(ABC)` — linha 23, registrada como `"base"` na 22
- `get_propgen_class(name)` — linhas 31–34

**[J]** Adicionar uma estratégia é **extensão pura**: um arquivo novo, uma linha de import, uma string em `choices`. Nenhuma modificação.

## 2.2 O padrão de construtor a seguir

**[L]** `QMPropGener.py:20-25` — o `__init__` **não chama `super()`**; atribui `self.cfg` diretamente e pega os modelos do dicionário:
```python
20:  def __init__(self, cfg, models) -> None:
21:      self.cfg = cfg
22:      self.txt_sim_model = models['sentence_transformer']
23:      self.it_sim_model = models['blip_itrtv_model']
24:      self.it_sim_processor = models['blip_itrtv_processor']
25:      self.nlp = spacy.load('en_core_web_sm')
```

**[L]** `BasePropGen.__init__` (base.py:24-25) recebe `models` mas **não o armazena** — só define `self.cfg`.

**[J] Decisão:** seguir o padrão do `QMPropGenerator` (atribuição direta). Consistência com o repositório, e chamar `super()` não traria benefício, já que a base não guarda nada além de `cfg`.

## 2.3 A assinatura: um defeito herdado

**[L]** `base.py:27-29` declara `@abstractmethod __call__(self, vid_list, captions, scores)` — **3** parâmetros.
**[L]** `QMPropGener.py:44` implementa com **4** (`+ all_frame_features`).
**[L]** `constructpipe/base.py:86` chama com **4**.

**[J]** A classe abstrata não descreve o contrato real — violação do Princípio de Substituição de Liskov. O `@abstractmethod` não detecta isso porque verifica **existência** do método, não compatibilidade de assinatura.

**[J] Decisão:** seguir a assinatura **real** (4 parâmetros). Corrigir a ABC seria modificar arquivo existente e quebraria o `QMPropGenerator`.

## 2.4 A forma do import

**[L]** `propgenerator/__init__.py` tem 2 linhas: `from .base import *` e `from .QMPropGener import *`.

**[J] Recomendação:** usar `from . import WholePropGener` em vez de `import *`. As duas formas produzem o **mesmo efeito de registro** (executar o módulo dispara o decorador); a segunda adicionalmente despeja todos os nomes do módulo — incluindo os que ele importou — no namespace do pacote, já que o repositório não define `__all__` em lugar nenhum. É divergência deliberada do padrão local, e vale um comentário de uma linha.

---

# PARTE 3 — Contratos de dados

## 3.1 O que o componente recebe

```python
def __call__(self, vid_list, captions, scores, all_frame_features):
```

| argumento | conteúdo |
|---|---|
| `vid_list` | `list[str]` — nomes com extensão |
| `captions` | `list[dict]` — `{'vid_name', 'duration', 'frame_captions'}` por vídeo |
| `scores` | `dict[str, Tensor]` — `capframe_scores` `[N]`, **já normalizado por min-max** se `itm_norm=True` |
| `all_frame_features` | `dict[str, Tensor]` — features visuais `[N, D]`, L2-normalizadas |

## 3.2 ★ Obter a matriz cruzada bruta, sem modificar nada

**[L]** `sim_utils.py:90-92` computa `ALL_SIMS` completa e devolve **dois** valores; **[L]** `constructpipe/base.py:110` descarta o segundo (`sims, _ = ...`).

**A solução:** o componente **recalcula** `ALL_SIMS` internamente. Ele já recebe `all_frame_features` e já pode ter `it_sim_model`/`it_sim_processor` (§2.2):

```python
_, all_sims = sim_utils.get_caption_frame_sims(
    self.it_sim_model, self.it_sim_processor, frame_features, sentences, self.cfg)
```

**[J] Três ganhos de uma vez:**
1. acesso à matriz completa (não só à diagonal);
2. **evita o min-max** — e com ele o NaN em N=1 e a degenerescência em N=2 (**[V-R4]**);
3. **evita a aniquilação** — o min-max zera exatamente uma legenda por vídeo (**[V-R3]**), e a diagonal bruta não tem esse problema.

**[J] Alternativa rejeitada:** modificar `compute_capframe_scores` para persistir `ALL_SIMS`. Rejeitada por modificar arquivo existente e invalidar caches `.pt` já gerados.

**[J] Custo:** um forward do *text encoder* sobre as legendas distintas por vídeo. As features **visuais** — a parte cara — já vêm prontas.

**[L] Nota de precisão:** o que `get_caption_frame_sims` computa é a similaridade pelo **caminho contrastivo** (encoders unimodais + projeções `vision_proj`/`text_proj`), **não** o score da cabeça ITM — que nunca é invocada no repositório. Detalhes em `RefCap_Similaridade_Segmentacao_e_Selecao.md` §3.1.

## 3.3 O que o componente devolve

**[L]** `build_tree_meta` (constructpipe/base.py:169-182) lê:
- do dicionário do vídeo: `metas['duration']` (L172), `metas['proposals']` (L173);
- de cada proposta: `prop['cap']`, `prop['st']`, `prop['ed']` (L177), e `prop['keys']` **se existir** (L178-179).

**[L] Chaves extras em cada proposta são simplesmente ignoradas** — o código acessa apenas essas. Isso permite anexar o ranking completo à proposta: ele sobrevive no `proposals.json` (salvo pelo próprio componente, **[L]** `QMPropGener.py:64`) e **não polui** o `tree.json`.

## 3.4 ★ CORREÇÃO: indexar múltiplas legendas **não** é grátis

A v1 afirmava que múltiplas legendas por segmento eram "ganho grátis". **Verificação refuta.**

**[L]** `build_tree_meta:177`:
```python
son = {..., 'caps': [prop['cap']], ...}      # lista de UM elemento, hardcoded
```
Não há override condicional para `caps` (só `keys`, em L178-179). Emitir uma lista `caps` na proposta seria **ignorado**.

**[L]** E no lado da busca, `MixPipe.py:151`: `cap = node['caps'][0]` — reporta sempre a **primeira** legenda do nó, independentemente de qual casou com a consulta.

**[L] O que é verdade:** o `CapTree` (capTree.py:69-76) **suporta** múltiplas legendas por nó — ele itera `len(node['caps'])` genericamente. E a agregação em `MixPipe.py:73` (`torch.max(rel_sims, dim=1)`) é um máximo sobre as legendas de um vídeo, no score de **nível de vídeo**. **O consumidor suporta; o produtor não produz.**

**[J] As duas vias e seus custos:**

| via | custo |
|---|---|
| Modificar `build_tree_meta:177` para `'caps': prop.get('caps', [prop['cap']])` | **1 linha modificada** — deixa de ser "zero modificações" |
| Emitir N propostas com o mesmo `[st, ed]` e legendas diferentes | cria N nós irmãos → **entradas duplicadas** no ranking de momento, e `MixPipe:151` reportaria sempre `caps[0]` |

**[J] Decisão da v2:** o componente emite **uma proposta com uma legenda** (a do topo do ranking). O ranking completo vive no `proposals.json` como diagnóstico. Isso preserva "zero modificações" e evita efeitos colaterais na busca. Indexar mais é uma **decisão futura**, a ser tomada depois de olhar o ranking — e agora com o custo real conhecido.

---

# PARTE 4 — Os critérios de ranqueamento

## 4.1 O enquadramento

Não há legenda de referência — mas há duas fontes de sinal que dispensam referência: o **vídeo** (comparação cross-modal) e o **conjunto de legendas** (centralidade).

## 4.2 Os sinais

Todos calculados sobre a matriz **bruta** `all_sims` `[n_distinct × N]`:

| sinal | fórmula | o que mede | limite |
|---|---|---|---|
| `self_score` | `all_sims[i][frame_de_origem_i]` | aderência ao frame que a gerou | **[J]** viés estrutural (§1.3) |
| `scene_score` | `all_sims[i].mean()` | aderência à cena inteira | **[J]** favorece legenda genérica |
| `consensus` | média da similaridade textual com as outras | centralidade no conjunto | **[J]** com n≤5 é estatística fraca |
| `n_words` | contagem de palavras | proxy grosseiro de especificidade | **[J]** não é medida de qualidade |
| `n_occurrences` | vezes que a legenda apareceu antes da dedup | estabilidade | **[J]** frequência ≠ qualidade |

**[J] Sobre `self_score` com dedup:** após deduplicar, uma legenda pode ter vindo de vários frames. A definição precisa é: `self_score(i) = média de all_sims[i][f]` sobre os frames `f` que geraram aquela legenda. Para `n_occurrences == 1` isso coincide com a diagonal original.

## 4.3 ★ A decisão: colunas, não veredito

**[J]** O componente **não elege** um critério vencedor. Emite todos como colunas, ordenando por um critério configurável (default proposto: `scene_score`).

**A justificativa é epistemológica.** Eleger um critério a priori exigiria saber qual acerta mais — o que exigiria referências, que não existem. Fixar um agora seria afirmar um conhecimento que não temos. Com poucos candidatos por cena, **inspecionar algumas dezenas de casos com as colunas lado a lado é o método mais rigoroso disponível**, e é barato.

---

# PARTE 5 — O algoritmo

Para cada vídeo em `vid_list`:

**5.1 Extrair as legendas** de `cap['frame_captions']`, preservando a ordem temporal. **[L]** As chaves podem ser `int` ou `str` conforme a origem (§6.4) — normalizar antes de usar.

**5.2 Deduplicar.** Normalizar (minúsculas, espaços colapsados, pontuação final) e agrupar idênticas. Guardar, por legenda distinta: texto, índices de frame de origem, contagem.

**5.3 Calcular a matriz bruta** via `get_caption_frame_sims` sobre as legendas **distintas**, capturando o **segundo** retorno. Shape: `[n_distinct × N_frames]`.

**5.4 Calcular os sinais** (§4.2).

**5.5 Ordenar** pelo critério configurado, decrescente.

**5.6 Coletar keywords** de **todas** as legendas de **todos** os frames, via `tree_utils.get_nouns_verbs` com spaCy — como **[L]** `QMPropGener.py:134-139`. **[J]** Coletar de todos (e não só da vencedora) preserva o insumo do ramo GloVe da busca.

**5.7 Montar a proposta única:**
```
st = 0.0 ;  ed = duration
cap = ranking[0].texto                      ← contrato obrigatório (§3.3)
keys = keywords deduplicadas                ← contrato opcional
ranking = [ {texto, self_score, scene_score, consensus, n_words,
             n_occurrences, frames}, ... ]  ← diagnóstico (ignorado por build_tree_meta)
n_raw, n_distinct, duration, warning        ← diagnóstico
```

---

# PARTE 6 — Ramificação (corrigida)

**[V-R5a]** O algoritmo de ranqueamento é **idêntico** para qualquer `n_distinct ≥ 2`. **[J]** Portanto ramifica-se pelo que **muda o algoritmo**, não pela duração.

## 6.1 `N = 0` — cenas com menos de 1 segundo

**[L]** `dataset/viddataset.py:47` — `for i in range(int(duration))`. Com `duration < 1.0`, `int()` dá 0 → nenhum frame.

**[L]** `viddataset.py:60` — `video = np.stack(frames, axis=0)`, **fora** do `try/except` que protege apenas o `ffprobe` (L39-44). **[J]** `np.stack([])` levanta `ValueError`; como a linha está fora do bloco protegido, a inferência é que a construção aborta ali. **Não executei o pipeline para observar isso** — a conclusão vem da leitura.

**[J] Decisão:** filtrar `duration < 1.0` **na fronteira** (`make_annos.py`), não no componente — quando ele executa, o dano já teria ocorrido três etapas antes. O componente ainda trata `n_distinct == 0` defensivamente, emitindo proposta vazia com aviso.

## 6.2 `n_distinct == 1` — retorno direto

Cobre dois casos que convergem: **N=1** (uma legenda só) e **todas as legendas idênticas após dedup** (provável em cenas curtas e estáticas).

**[J] Decisão:** caminho curto explícito — sem matriz, sem sinais, sem argmax. Além de economizar, **elimina a classe de erro do NaN**: não há normalização a fazer sobre um único valor.

## 6.3 `n_distinct ≥ 2` — o caminho de ranqueamento

Idêntico para 2 ou 300 legendas distintas. **[J]** O que varia com o tamanho é a **confiabilidade** dos sinais (o `consensus` com n=2 é uma comparação par a par, não consenso) — e isso é **anotação de diagnóstico na saída**, não ramo de código.

## 6.4 Chaves `int` vs `str`

**[L]** `BlipCapGener.py:34` grava com chave `int` (de `enumerate`); **[L]** `capgenerator/base.py:33-34` recarrega do `.jsonl`, e JSON converte chaves em `str`; **[L]** `QMPropGener.py:133` indexa sempre com `str(...)`.

**[J] Decisão:** o componente será **agnóstico ao tipo da chave** — normalizar os índices antes de usar. Defesa barata contra uma inconsistência real.

---

# PARTE 7 — Integração

## 7.1 Adição 1 — `pipeline/propgenerator/WholePropGener.py` (novo)

```python
@REGISTER_PROPGEN(["whole"])
class WholePropGenerator(BasePropGen):
    def __init__(self, cfg, models) -> None: ...          # padrão do §2.2
    def __call__(self, vid_list, captions, scores, all_frame_features): ...   # §2.3
```

**[L]** Salvar no mesmo destino do `QMPropGenerator` — `os.path.join(cfg.exp_dir, cfg.proposals_file)` (`QMPropGener.py:64`; `cfg.proposals_file` default `"proposals.json"`, `cfg.py:20`).

**[L] Atenção:** `cfg.exp_dir` **não está declarado** em `BuildArguments` — é injetado dinamicamente por `construct.py:36`. Funciona no fluxo normal; quebra se o pipeline for instanciado fora dele.

## 7.2 Adição 2 — `pipeline/propgenerator/__init__.py` (1 linha)

```python
from .base import *
from .QMPropGener import *
from . import WholePropGener      # registra sem poluir o namespace (§2.4)
```

## 7.3 Adição 3 — `config/cfg.py:76` (1 string)

**[L]** Estado atual (linhas 74–77):
```python
proposal_generator: str = field(
    default="qm",
    metadata={"choices": ["qm"]}       # ← linha 76
)
```

**[V] Verificado empiricamente** que os `choices` são impostos: com o parser real, `--proposal_generator whole` é **rejeitado** e `qm` é aceito. **[L]** A causa é `config/hf_argparser.py:150` (`kwargs = field.metadata.copy()`) combinado com `:230` (`parser.add_argument(..., **kwargs)`).

**Sem esta adição o componente é inalcançável por linha de comando.**

## 7.4 Configuração adicional (opcional)

| campo | default proposto | papel |
|---|---|---|
| `whole_rank_by` | `"scene_score"` | qual sinal ordena |
| `whole_dedup` | `True` | deduplicar antes de ranquear |

**[J]** Não proponho `whole_max_caps` na v2 — dado o §3.4, indexar mais de uma legenda exigiria modificar `build_tree_meta`, e essa decisão fica para depois da inspeção.

## 7.5 Uso

```bash
proposal_generator=whole    # no construct.sh
```

---

# PARTE 8 — O que deliberadamente não faremos

| não faremos | por quê |
|---|---|
| Detecção de fronteiras | **[J]** a premissa é que cada vídeo já é o corte |
| Modificar `compute_capframe_scores` | **[J]** quebraria OCP e invalidaria caches |
| Modificar `build_tree_meta` | **[J]** §3.4 — decisão adiada, com custo agora conhecido |
| Corrigir a ABC (§2.3) | **[J]** modificaria arquivo existente e quebraria o `QMPropGenerator` |
| Usar `capframe_scores` como vem do pipeline | **[J]** §3.2 — traz min-max, NaN e aniquilação junto |
| Introduzir modelo novo | **[J]** a maquinaria necessária já está carregada |
| Fundir legendas (gerar um "resumo") | **[J]** exigiria um LLM; fora de escopo |
| Eleger um critério vencedor | **[J]** §4.3 — sem referências, seria afirmar o que não sabemos |
| Aprender pesos para combinar sinais | **[J]** exigiria supervisão inexistente |

---

# PARTE 9 — Plano de validação

**[J] Passo 0 — medir a distribuição antes de codificar.** Um script curto sobre `meta/captions/{collection}_{gen}.jsonl` responde: quantas cenas têm `n_distinct == 1`? Qual a mediana de legendas distintas?

**Se a maioria tiver 1–2 distintas, boa parte deste projeto é desnecessária** — e descobrir isso antes de codificar é o objetivo de ter feito a especificação primeiro.

**Passo 1 — concordância entre critérios.** Em quantas cenas `argmax(self_score) == argmax(scene_score)`? Se convergirem quase sempre, a escolha do critério é irrelevante.

**Passo 2 — inspeção manual** de ~30 cenas com as colunas lado a lado. **[J]** É aqui que o critério se decide.

**Passo 3 — diagnóstico do viés genérico.** Se o topo por `scene_score` for sistematicamente a legenda mais curta (coluna `n_words`), o efeito previsto em §4.2 está presente.

---

# PARTE 10 — O que esta especificação **não** estabelece

**[J]** Registro explícito, porque uma especificação que não declara seus limites convida à leitura excessiva:

- **Não medi nada em dados reais.** Todos os números vêm de testes sobre o *algoritmo* com entradas sintéticas.
- **Não estabeleci que `scene_score` produz escolhas melhores** que `self_score`. Mostrei que os critérios diferem e argumentei por que a diagonal tem viés estrutural — a comparação exigiria referências.
- **Não estimei a frequência de partição indevida** numa coleção real; os testes usam scores sorteados.
- **Não executei o pipeline** para observar o `ValueError` de N=0 (§6.1) nem a inconsistência de chaves (§6.4) — ambos decorrem de leitura de código.
- **Não avaliei** o impacto do componente sobre as métricas de recuperação. Isso exigiria rodar a avaliação.

---

# PARTE 11 — Decisões pendentes de aprovação

1. **Ordenação padrão** — proponho `scene_score`, com a ressalva do viés genérico (§4.2). Aceita?
2. **Uma legenda indexada** (§3.4) — proponho manter, dado o custo real agora conhecido. Concorda em adiar a decisão de indexar várias?
3. **Filtro de cenas < 1s** no `make_annos.py` (§6.1), não no componente. Concorda?
4. **Ordem de execução** — proponho rodar o Passo 0 (§9) **antes** de escrever o componente.

---

*Especificação v2 do `WholePropGenerator`. Toda afirmação carrega marca: **[L]** lida no código com arquivo e linha, **[V]** verificada numericamente ou empiricamente, **[D]** demonstrada, **[J]** decisão ou julgamento de projeto. A §0.2 registra as três afirmações da v1 que a verificação refutou — em especial a de que indexar múltiplas legendas seria gratuito, que `build_tree_meta:177` desmente. A §10 delimita o que a especificação não estabelece.*
