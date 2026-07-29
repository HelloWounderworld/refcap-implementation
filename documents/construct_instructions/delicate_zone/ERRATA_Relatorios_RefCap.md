# ERRATA — Afirmações Refutadas nos Relatórios do RefCap
## Registro de Correções, com Localização Exata e Verificação

---

> **O que é este documento.** O registro das afirmações feitas em relatórios anteriores que **verificação posterior refutou**, com a localização exata (arquivo e linha) de cada ocorrência e a demonstração da refutação.
>
> **Por que ele existe.** São mais de vinte relatórios acumulados. Sem este registro, um arquivo antigo lido daqui a meses induz ao erro sem nenhum aviso. **[J]** Um conjunto de documentos técnicos sem errata é um conjunto que envelhece mal.
>
> **Método.** Varredura de **todos** os arquivos `.md` e `.py` do diretório, procurando cada afirmação já refutada. Não presumi quais arquivos estariam afetados — busquei por padrão de texto em todos.
>
> **★ Uma das entradas (E4) corrige um erro meu *na própria correção*.** Está registrada com o mesmo peso das demais.

---

## Protocolo

| Marca | Significa |
|---|---|
| **[L]** | Lido no código — arquivo e linha |
| **[V]** | Verificado numericamente (`LAB9`) |
| **[J]** | Julgamento meu |

**Escopo.** Repositório `BUAAPY/RefCap`, branch padrão. Documentos em `/mnt/user-data/outputs`.

---

# E1 — `prop_max_cnt=1` (ou `2`) **não** força um único segmento

## A afirmação refutada
> *"`prop_max_cnt=2` → 1 segmento (vídeo inteiro)"*, apresentada como **✔ PROVADO**.

## Por que é falsa

**[L]** `pipeline/propgenerator/QMPropGener.py:95-99`:
```python
95:      if len(boundaries)==0:
96:          boundaries.append(id)                       # ← entra INCONDICIONALMENTE
97:          continue
98:      if len(boundaries)+1>=self.cfg.prop_max_cnt:    # ← só avaliado a partir da 2ª
99:          break
```

A primeira fronteira candidata é adicionada **antes** de a checagem de `prop_max_cnt` ser avaliada. Logo `boundaries` não fica vazio por essa via, e o caso-base `[0, VID_LEN]` (L109-110) não é alcançado por configuração.

**[V]** Simulação fiel com 200 vídeos sintéticos: `prop_max_cnt=1` produziu **2 segmentos em ~95% dos casos**.

## Onde a afirmação aparece

| arquivo | linha(s) | forma |
|---|---|---|
| `RefCap_Fatiamento_ImageToText_Segmentacao.md` | **277–283** | tabela com "✔ PROVADO" |
| `CLEAN_CODE_E_ARCHITECTURE_Mandamentos.md` | **213**, **454** | citada como exemplo de teste de caracterização |
| `CODIGO_LIMPO_Tratado.md` | **446** | idem |

**[J] Nota sobre os dois últimos:** neles a afirmação é usada apenas como *ilustração* do conceito "teste de caracterização". O conceito continua válido; o exemplo é que está errado. Ao ler aquelas passagens, substitua mentalmente por um exemplo verdadeiro — por exemplo, *"provar que o BLIP nunca é invocado com `caption_generator=minigpt`"*, que foi verificado e se sustenta.

## O que vale em lugar dela

"Um segmento por vídeo" **não é alcançável por configuração**. Exige um componente novo — ver `RefCap_Projeto_WholePropGenerator.md`.

**[V] E há um fato mais forte que substitui a intenção original:** para **N ≤ 5** legendas (cenas até ~5 s), o `QMPropGenerator` produz **sempre um único segmento**, independentemente dos scores — teste exaustivo sobre todas as permutações. De **N = 6** em diante, ele passa a partir a cena.

---

# E2 — A guarda de vídeo corrompido **não** torna o tratamento na fronteira desnecessário

## A afirmação refutada
> *"É a rede de proteção que torna o try/except do adapter desnecessário."*

## Por que é falsa

**[L]** `pipeline/capgenerator/BlipCapGener.py:23-24` pula o vídeo com `return`, **sem** adicioná-lo a `self.captions`.
**[L]** `pipeline/constructpipe/base.py:137` itera sobre a **`vid_list` inteira**, e a linha **143** faz `vid_2_cap[video_name]`.

As duas etapas **discordam sobre o conjunto**: a primeira remove o vídeo corrompido, a segunda assume que todos estão presentes.

**[V]** Reprodução da interação: `KeyError: 'corrompido'`.

**[J]** A guarda não impede a queda — ela a **transfere** para uma etapa onde a mensagem (`KeyError` com um nome de vídeo) não menciona corrupção. É proteção ilusória: troca uma falha diagnosticável por uma obscura.

## Onde a afirmação aparece

| arquivo | localização | forma |
|---|---|---|
| `RefCap_Disseccao_Cenas_e_Video_to_Text.md` | §4, item **[4]** | frase final do parágrafo |

## O que vale em lugar dela

Tratamento de vídeos corrompidos **na fronteira** continua necessário — mais do que a v1 sugeria. **[J]** Recomendação: validar com `ffprobe` no `make_annos.py` e remover os que falharem, para que `vid_list` e `captions` nunca divirjam.

Correção completa em `RefCap_Analise_ConstructPipe_Completo.md` (Parte 3).

---

# E3 — "Todo vídeo ganha ≥ 1 fronteira interna" é falso no resultado final

## A afirmação refutada
> *"os scores são normalizados min-max, então a magnitude absoluta da novidade é descartada — todo vídeo ganha ≥1 fronteira interna, mesmo sendo um evento único (sobre-segmentação de vídeos uniformes)."*

## O que é certo e o que é errado nela

**[L] A premissa está certa.** `QMPropGener.py:88` normaliza os scores por min-max, e `:96` adiciona a primeira fronteira incondicionalmente. No **estado intermediário**, há de fato ≥ 1 fronteira.

**[V] A conclusão está errada.** As regras de absorção (**[L]** `:112-118`) **removem** essa fronteira quando ela cai a menos de `min_prop_size` de uma ponta. Teste exaustivo:

| N | ≥1 fronteira **antes** da absorção | ≥1 segmento extra **no resultado final** |
|---|---|---|
| 2 | não (ambos os índices são pontas) | **não** |
| 3, 4, 5 | sim | **não** |
| 6, 7, 8 | sim | às vezes |

**[J]** Ou seja: para N ≤ 5 o vídeo sai com **um** segmento e **zero** fronteiras internas — o oposto da "sobre-segmentação" alegada. Para N ≥ 6 pode ou não haver; a partição não é garantida.

## Onde a afirmação aparece

| arquivo | linha | forma |
|---|---|---|
| `RefCap_Guia_Analise_Passo_a_Passo.md` | **83** | *"Note o defeito crítico…"* |

## O que vale em lugar dela

**[V]** O comportamento real é o inverso para cenas curtas e progressivo para longas: **inerte até N=5**, e partindo a cena em ~26 % (N=6), ~49 % (N=8), ~77–80 % (N=10) e ~100 % (N≥20) dos casos em teste aleatório.

**[J]** O "defeito crítico" existe, mas é outro: o min-max sobre `capframe_scores` (**[L]** `constructpipe/base.py:111-112`) atribui peso **exatamente zero** à legenda de menor score de cada vídeo, aniquilando sua linha e coluna na matriz. Ver `RefCap_Similaridade_Segmentacao_e_Selecao.md` §9.

---

# E4 — ★ `prop_score_thr=0.2` **não** era um erro — o erro foi meu ao "corrigi-lo"

## O que aconteceu

Ao revisar, encontrei `prop_score_thr=0.2` em vários documentos e o marquei como valor errado, alegando que **[L]** `config/cfg.py:94` traz `default=0.5`. **Essa "correção" estava errada.**

## Por quê

**[L]** `scripts/construct.sh:16` define `prop_score_thr=0.2` e o passa explicitamente na linha 45 (`--prop_score_thr $prop_score_thr`).

**Há dois valores, e os dois são reais:**

| como se invoca | valor efetivo | fonte |
|---|---|---|
| `bash scripts/construct.sh` (o script distribuído) | **0.2** | **[L]** `scripts/construct.sh:16` |
| `python construct.py` sem argumentos | **0.5** | **[L]** `config/cfg.py:94` |

**[J]** Como o script é o ponto de entrada documentado no README, **0.2 é o valor efetivo na prática** — e os documentos que o usavam estavam corretos.

## A verificação que fecha a questão

**[V]** Rodei o teste exaustivo de segmentação com **os dois** valores. Resultado para N = 1…8: **tabelas idênticas**. No regime aleatório há diferença pequena a partir de N=10 (80.1 % vs 76.1 % de partição), sem alterar a conclusão qualitativa.

**[J]** Portanto: a conclusão sobre o comportamento da segmentação **não depende** dessa escolha, e nenhum documento precisa ser corrigido por causa dela.

## Onde a minha afirmação errada apareceu — e já foi corrigida

| arquivo | estado |
|---|---|
| `RefCap_Projeto_WholePropGenerator.md` (§0.2, item 3) | **corrigido** — a tabela agora registra que a v1 estava certa |
| `RefCap_Similaridade_Segmentacao_e_Selecao.md` (§11) | **corrigido** — nota explicando os dois valores |

## Arquivos que usam `0.2` e estão **corretos**

`RefCap_Analise_Necessidade_annos.md:156`, `RefCap_Infraestrutura_Testes.md:214`, `RefCap_Infraestrutura_Testes_e_Exploracao.md:235,355`, `LAB7_ranking_sem_referencia.py:9`. **Nenhuma ação necessária.**

**[J] A lição de método:** ler o default da dataclass não basta — o script de entrada pode sobrescrevê-lo. Verificar "o valor do parâmetro" exige checar **os dois lugares**. Foi assim que eu errei, e foi a frase *"todas em `scripts/*.sh`"* de um relatório anterior que me fez conferir.

---

# E5 — Indexar múltiplas legendas por segmento **não** é gratuito

## A afirmação refutada
> *"Múltiplas legendas por segmento são suportadas — e é ganho grátis, zero modificações."*

## Por que é falsa

**[L]** `pipeline/constructpipe/base.py:177`:
```python
son = {..., 'caps': [prop['cap']], ...}     # lista de UM elemento, hardcoded
```
Não há override condicional para `caps` — só para `keys` (L178-179). Emitir uma lista `caps` na proposta seria **ignorado**.

**[L]** `pipeline/retrievepipe/MixPipe.py:151`: `cap = node['caps'][0]` — reporta sempre a **primeira** legenda do nó, seja qual for a que casou com a consulta.

## O que é verdade (e me levou ao erro)

**[L]** O `CapTree` (`capTree.py:69-76`) **suporta** múltiplas legendas por nó — itera `len(node['caps'])` genericamente. E **[L]** `MixPipe.py:73` agrega por `torch.max` sobre as legendas de um vídeo, no score de nível de vídeo.

**[J] O erro de método:** verifiquei o **consumidor**, constatei que ele suporta, e **inferi** que o produtor também produziria. Não verifiquei `build_tree_meta`. Verificar uma ponta da cadeia e presumir a outra é exatamente o tipo de atalho que este conjunto de relatórios existe para evitar.

## Onde a afirmação aparecia

| arquivo | estado |
|---|---|
| `RefCap_Projeto_WholePropGenerator.md` §3.4 (v1) | **já substituído pela v2**, que registra a refutação |

Nenhum outro documento repete a afirmação (varredura por "ganho grátis" retornou só esse arquivo).

---

# E6 — O modo `'it'` **não** mistura espaços vetoriais incompatíveis

## A afirmação refutada
> *"O RefCap faz exatamente isso no modo `'it'`: multiplica `txt_sims` (espaço do sentence-transformer) por `capframe_scores` (espaço do BLIP-ITM). […] não tem justificativa principiada."*

## Por que é falsa

**[L]** `QMPropGener.py:39` — `sims = txt_sims * capframe_scores[None,:] * capframe_scores[:,None]`.

**[V]** Com `D = diag(s)`, isso é algebricamente idêntico a `D · txt_sims · D`.

**[D] Teorema:** se K é PSD, `D K D` é PSD. Prova: `x'(DKD)x = (Dx)'K(Dx) ≥ 0`. ∎

**[J] A distinção que eu havia perdido:** o erro real seria calcular `cos(vetor_A, vetor_B)` entre modelos diferentes — tratar **coordenadas** de espaços distintos como comparáveis. Usar um **escalar** de outro modelo como **peso** sobre uma matriz de Gram é reponderação de kernel, operação legítima que preserva a estrutura PSD. São categorias diferentes de operação.

## Onde a afirmação aparecia

Apenas no fluxo da conversa; **[V]** a varredura por "espaços diferentes" retornou somente `RefCap_Similaridade_Segmentacao_e_Selecao.md`, que já contém a **correção** (§2), não a afirmação. **Nenhuma ação necessária.**

---

# Resumo — estado de cada arquivo

| arquivo | entrada(s) | ação |
|---|---|---|
| `RefCap_Fatiamento_ImageToText_Segmentacao.md` | **E1** (L277–283) | ⚠️ **contém afirmação refutada** |
| `RefCap_Disseccao_Cenas_e_Video_to_Text.md` | **E2** (§4 item 4) | ⚠️ **contém afirmação refutada** |
| `RefCap_Guia_Analise_Passo_a_Passo.md` | **E3** (L83) | ⚠️ **contém afirmação refutada** |
| `CLEAN_CODE_E_ARCHITECTURE_Mandamentos.md` | **E1** (L213, L454) | ⚠️ exemplo ilustrativo errado; conceito válido |
| `CODIGO_LIMPO_Tratado.md` | **E1** (L446) | ⚠️ idem |
| `RefCap_Projeto_WholePropGenerator.md` | **E4**, **E5** | ✅ corrigido (v2) |
| `RefCap_Similaridade_Segmentacao_e_Selecao.md` | **E4**, **E6** | ✅ corrigido |
| `RefCap_Analise_ConstructPipe_Completo.md` | **E2** | ✅ contém a correção |
| `RefCap_Analise_Necessidade_annos.md`, `RefCap_Infraestrutura_Testes*.md`, `LAB7_*.py` | **E4** | ✅ **corretos** — `0.2` é o valor do script |

---

# Nota de método

**[J]** As seis entradas têm origens distintas, e vale distinguir os tipos de erro:

- **E1, E3** — afirmei "provado" após um teste que não cobria o caso geral. **Correção:** teste exaustivo (todas as permutações), não amostral.
- **E2, E5** — verifiquei uma ponta da cadeia e **inferi** a outra. **Correção:** rastrear produtor *e* consumidor antes de afirmar sobre a cadeia.
- **E4** — li o default da dataclass e não conferi se o script o sobrescrevia. **Correção:** para "o valor de um parâmetro", checar config *e* script de entrada.
- **E6** — apliquei um princípio correto (não comparar espaços) a um caso que não era dele. **Correção:** verificar se o caso se enquadra antes de invocar a regra.

**[J]** Os quatro padrões — generalizar de amostra, inferir a ponta não verificada, ler uma fonte só, e aplicar regra por analogia — são os modos de falha a vigiar nos próximos relatórios.

---

*Errata do conjunto de relatórios do RefCap. Seis afirmações refutadas, cada uma com localização exata, demonstração da refutação e o que vale em seu lugar. Varredura feita sobre todos os arquivos do diretório por padrão de texto, não por suposição. A entrada **E4** registra um erro meu cometido durante a própria revisão — marcar como errado um valor que estava correto — e a **E5**, um erro de inferência a partir de verificação parcial.*
