# RefCap — Guia Passo a Passo de Análise do Código
## Três Lentes: Crux · Novidade · Extração

---

> **O que é este documento.** Um **protocolo de leitura** do código de `BUAAPY/RefCap` — não *o que* o sistema é (isso está no *Relatório Consolidado*), mas **como analisá-lo, em que ordem, e como saber que você entendeu**. Organizado pelas três lentes que definem seu trabalho, com passos concretos (arquivo:linha + o que observar), um *teste de litmus* por lente (a pergunta que você precisa saber responder), e as armadilhas de leitura a evitar.
>
> **A premissa que organiza tudo.** Para o *seu* objetivo — rodar VCMR sem-rótulo sobre vídeos brutos — vale a identidade **funcionalidade ≡ novidade ≡ a cadeia sem-rótulo**. Consequência para a análise: as Lentes 1 e 2 você **estuda** (leitura, para entender); a Lente 3 você **modifica** (toca, para extrair). E a extração **preserva** as Lentes 1 e 2 intactas — você corta apenas o encanamento. Não há "módulo mágico da novidade" para levantar; há uma *fronteira* (o `annos/`) para cortar.

---

## O MAPA: por que as três lentes são três lugares diferentes

Este é o ponto não-óbvio que evita que você abra os arquivos errados. Cada lente vive em uma camada distinta do código:

| Lente | O que você busca | Onde vive no código | O que você faz |
|---|---|---|---|
| **1 — Crux** | A ideia que faz tudo funcionar | A **arquitetura / o fluxo** (`construct` + `tree.json`) | Estuda |
| **2 — Novidade** | Onde mora o valor científico (SOTA) | Os **módulos do estágio de construção** (QM-Gen, fusão, SWi-Den) | Estuda |
| **3 — Extração** | O que precisa mudar | O **encanamento nas bordas** (tudo que toca `annos/`) | Modifica |

Ler na ordem errada — de cima a baixo do sistema de arquivos, ou começando pela avaliação — é o erro clássico: você se afoga em config e encanamento antes de ver a ideia.

---

## REGRA DE OURO (antes de qualquer análise)

**Rode o pipeline não-modificado uma vez, num micro-corpus, antes de ler ou tocar em qualquer coisa.** Sem uma linha de base do comportamento "correto", você não tem como distinguir um bug seu de um comportamento esperado — e qualquer análise fica sem âncora empírica. Use 5–10 vídeos e um `annos/` dummy mínimo. *Objetivo:* ver a `tree.json` sendo gerada e as predições saindo. Este passo não é análise; é a **fundação** que torna a análise verificável.

---

# LENTE 1 — O CRUX
### (A arquitetura: qual é a ideia que faz tudo funcionar)

**Onde começar (ponto de entrada único):** `constructpipe/base.py::construct` (linhas 67–90), lido **em paralelo com um arquivo `tree.json` de saída** (gerado na Regra de Ouro).

**Por que aqui, e não em outro lugar.** Essas ~20 linhas são a espinha dorsal do sistema: mostram, em sequência, como um vídeo bruto vira uma estrutura textual. Se você entende o que *entra* na `tree.json` e percebe que **nada disso requer rótulo nem conhecimento da consulta**, você pegou o crux. Todo o resto do repositório é serviço a essa transformação.

### Protocolo de leitura (passo a passo)

1. **Leia `construct()` inteiro (l. 67–90) como uma lista de 7 etapas.** Não abra nenhuma sub-função ainda. Apenas identifique a *sequência*: captions → features → scores → denoise → recomputa scores → proposals → árvore. *Observe:* que os scores são computados **duas vezes** (l. 76 e l. 83) — antes e depois do denoising. Pergunte-se por quê (resposta: o denoising altera as legendas, então os scores precisam ser refeitos). Se você entende *por que há dois cálculos de score*, você entendeu a dependência entre as etapas.

2. **Abra uma `tree.json` e localize um nó de proposal.** *Observe* a estrutura de um nó: `st`, `ed` (início/fim em segundos), uma `cap` (legenda representativa), um conjunto de `keys` (palavras-chave). Este é o átomo do sistema. *Confirme:* a raiz é o vídeo; os `subs` são os proposals; a árvore tem **2 níveis** (apesar do nome sugerir mais).

3. **Faça a conexão-chave:** cada etapa de `construct()` produz um pedaço desse nó. O captioning produz o texto bruto; o denoising o refina; a segmentação define `st`/`ed` e escolhe a `cap`; a extração de keywords produz `keys`. *Nenhuma etapa consulta um rótulo ou a query.*

4. **Só agora, se quiser profundidade,** abra `build_tree_meta` (l. 169–182) para ver como o nó é montado. Mas o crux já foi capturado no passo 3.

### Teste de litmus (você pegou o crux?)

Responda **sem olhar o código**: *"O que exatamente está dentro de um nó da `tree.json`, e por que construí-la não precisa de nenhuma anotação?"*

Resposta esperada: *um segmento com início, fim, uma legenda representativa e um conjunto de palavras-chave; e não precisa de rótulo porque o captioning é genérico e agnóstico à consulta — o índice é construído sem saber o que será perguntado.* Se você responde isso com fluência, prossiga. Se hesita, releia a espinha (passo 1) antes de avançar. **Não avance para a Lente 2 sem passar neste teste** — sem o crux, os módulos parecem peças soltas.

### Armadilhas desta lente

- **Abrir as sub-funções (denoiser, propgenerator) antes de ler a espinha inteira.** Você perde a *sequência* — que é o próprio crux — nos detalhes de implementação.
- **Ignorar a `tree.json`.** O crux é *o que a transformação produz*; sem olhar a saída, você vê o processo mas não o produto.

---

# LENTE 2 — A NOVIDADE
### (O estágio de construção: onde mora o valor científico)

**Onde focar — e a ordem importa.** A substância empírica é **desigual** entre os módulos, e a retórica do paper não reflete isso. Estude na ordem de impacto empírico (da ablação, Tab. III), não na ordem de destaque do artigo:

| Prioridade | Módulo | Arquivo · função · linha | Impacto na ablação | Racional |
|---|---|---|---|---|
| **1** | QM-Gen | `propgenerator/QMPropGener.py::generate_proposal` (69–105) | +1.29; e o insight "texto > visual" = +2.95 | Onde nascem os eventos e o maior delta. **Se só houver tempo para um, é este.** |
| **2** | Fusão multi-granularidade | `retrievepipe/MixPipe.py` (scoring 66–73; fusão 130) | Fusão +2.13 sobre sentença | Onde a consulta *vira* resultado — e a funcionalidade que você quer, no ato |
| **3** | SWi-Den | `denoiser/window.py::denoise_caption` (20–34) | +0.27 (quase nulo) | Estude por completude e pela interação com QM-Gen, **mas não como o valor do trabalho** |

**A regra:** distribua atenção proporcionalmente ao impacto empírico, não ao destaque retórico. O valor científico está concentrado na Prioridade 1.

### Protocolo de leitura — QM-Gen (Prioridade 1)

1. **Localize as duas deltas sobre o UBoCo [12].** O kernel de detecção de fronteiras é *emprestado* do UBoCo (o paper cita). O que é próprio do RefCap são duas coisas — encontre-as no código:
   - **Delta (a): matriz de similaridade *textual*, não visual.** Em `calculate_similarities` (l. 28), veja os três modos (`vis`/`txt`/`it`). O modo `it` (padrão) é `sim[i][j] = txtsim[i][j] · s_i · s_j` — similaridade de *texto* ponderada pelos quality scores. Compare com o modo `vis` (features visuais). *Esta é a Eq. 3–4 do paper.*
   - **Delta (b): a Quality-Mask.** É o produto externo dos quality scores que pondera a matriz — o `· s_i · s_j` acima. *É o que "incorpora a qualidade das legendas" na segmentação.*

2. **Leia o kernel contrastivo (l. 74–87).** *Observe:* o `weight` é uma matriz checkerboard (quadrantes superior-esquerdo/inferior-direito = +1, os outros = −1, cruz central = 0; l. 76–83). O `conv2d` (l. 86) + `diagonal` (l. 87) extrai o score de novidade por frame. *Entenda o que ele detecta:* pontos na diagonal da matriz onde a estrutura de blocos muda = fronteiras entre eventos dissimilares.

3. **Leia a seleção gulosa de fronteiras (l. 98–105).** *Observe* as restrições: máximo `prop_max_cnt` (l. 98), separação mínima `prop_kernel_width` (l. 102), parada por limiar `prop_score_thr` (l. 105). *Note o defeito crítico:* os scores são normalizados min-max, então a *magnitude absoluta* da novidade é descartada — todo vídeo ganha ≥1 fronteira interna, mesmo sendo um evento único (sobre-segmentação de vídeos uniformes).

4. **Leia a produção do nó (l. ~133–139):** a `cap` é a legenda do frame de maior quality score no segmento; as `keys` vêm de `get_nouns_verbs` sobre todas as legendas do segmento (l. 136, Eq. 5).

### Protocolo de leitura — Fusão (Prioridade 2)

1. **Encontre onde a consulta vira número.** Em `MixPipe.py` (l. 66–73): `encode_caps(descs)` codifica a query, `cos_sim(desc_features, cap_features)` produz a similaridade de sentença contra *todos* os proposals. *Observe:* o scoring roda contra o corpus inteiro — a query não sabe em qual vídeo está a resposta.
2. **Leia a fusão (l. 130):** `esm_sims = sent·α + key·(1−α)` (Eq. 9). *Confirme:* ambos os sinais são normalizados antes de fundir, e α=0.5.
3. **Leia a agregação de keywords (`Max_Mean`, Eq. 8):** para cada palavra da query, o `max` sobre as palavras do proposal (a melhor correspondência, estilo MIL), depois a *média* sobre as palavras da query (mede o *recall* da query).

### Protocolo de leitura — SWi-Den (Prioridade 3, com ceticismo)

1. **Leia `denoise_caption` (l. 20–34).** *Observe* a lógica: `last_high_id` (l. 27) rastreia a última âncora de alta confiança; o gate `> figsim_denoise_thr` (l. 30) a atualiza; a substituição via `deepcopy` (l. 34) copia a legenda da âncora sobre a legenda ruim, dentro da janela `denoise_window_width` (l. 33). *É a Eq. 2.*
2. **Note as limitações** (para não superestimar): propagação apenas **causal** (para frente), a partir da âncora *imediatamente anterior*; nunca interpola, nunca propaga para trás. E o quality score que serve de gate é min-max **por vídeo** — relativo, não absoluto (pode sobrescrever legenda boa em vídeo bom, ou propagar legenda ruim em vídeo ruim).

### Teste de litmus (você pegou a novidade?)

Responda três perguntas: *(i) Quais são as DUAS deltas do QM-Gen sobre o UBoCo?* (matriz textual + Quality-Mask). *(ii) Por que a ablação diz que texto > visual?* (features de texto dão fronteiras de evento mais nítidas que features visuais). *(iii) Onde exatamente a consulta vira um número?* (`MixPipe.py:66–73`, `cos_sim` contra todos os proposals). Se você responde as três, internalizou onde mora o SOTA.

### Armadilhas desta lente

- **Começar pelo SWi-Den porque é o "módulo de denoising nº 1".** Impacto quase nulo; pior retorno por atenção.
- **Tratar o kernel contrastivo como novidade do RefCap.** É do UBoCo. As deltas são a matriz textual e a Quality-Mask.
- **Ler os módulos como o valor a *extrair* isoladamente.** A novidade é a *composição* + o modo sem-rótulo; você não levanta um módulo — você preserva a cadeia (ver Lente 3).

---

# LENTE 3 — A EXTRAÇÃO
### (O encanamento nas bordas: o que você precisa tocar)

**O insight que economiza seu tempo:** a extração **não toca a novidade — ela a preserva intacta**. Você não modifica QM-Gen, SWi-Den nem o scoring. Esses são o núcleo; você os mantém. O que você toca é o **encanamento nas bordas**, e a fronteira exata é **tudo aquilo que o `annos/` toca**. O modelo mental: *o `annos/` particiona o código em "encanamento" (o que ele toca → você re-roteia) e "núcleo" (o que ele não toca → você preserva).* A cirurgia é **subtrativa nas bordas**, não **reconstrutiva no meio**.

**Os três — e apenas três — pontos de contato:**

| # | Ponto | Arquivo · linha | Natureza | Ação |
|---|---|---|---|---|
| 1 | Manifesto (construção) | `constructpipe/base.py::select_videos` (184) | Lê só `vid_name` | Trocar por listagem de diretório |
| 2 | Entrada (recuperação) | `dataset/dataset.py::DataSet4Test` | Exige `ts` (gabarito) | Tornar `ts` opcional; alimentar seus prompts |
| 3 | Saída/corpus (recuperação) | `retrieve.py::eval_epoch` (182) **+** `compute_tree_feature` (`retrieve.py:271`) | Avaliação **+** acoplamento do corpus | Contornar avaliação; desacoplar corpus |

### Protocolo de análise — Ponto 1 (Construção, TRIVIAL)

1. **Leia `select_videos` (l. 184–205).** *Confirme:* lê **só** `data['vid_name']` (l. 191) para filtrar a interseção pasta∩anotação. *Observe:* a única lógica não-trivial a preservar é a conversão mkv→mp4 (l. 193–199).
2. **Localize a chamada:** `__init__`, linha 46 (`new_vid_list = self.select_videos(...)`). *Entenda:* `self.vid_list` = essa lista, usada por todo o `construct()`.
3. **Alvo da mudança:** substituir a lista pela listagem de `os.listdir(video_root)`, preservando o tratamento de mkv.

### Protocolo de análise — Ponto 2 (Entrada, MODERADA)

1. **Leia `DataSet4Test` inteiro.** *Localize a dependência dura:* `self.time_stamps.append(item["ts"])` — quebra sem `ts`. E `__getitem__` retorna `ts[0], ts[1]` em todo item.
2. **Confirme que o scoring NÃO usa o `vid_name` da query** (cruze com `MixPipe.py:66–73`): a query é pontuada contra todos os proposals; `vid_name`/`ts` da query só são ecoados na saída como `gt_vid_name`/`gt_ts`. *Conclusão:* você pode preencher esses campos com dummies.
3. **Alvo da mudança:** um `DataSet4Inference` que aceita `desc` (seu prompt) sem `ts` (default `[0,0]`) e sem `vid_name` de gabarito.

### Protocolo de análise — Ponto 3 (Saída/corpus, contém a ARMADILHA)

1. **Leia `eval_epoch` (l. 182–231).** *Distinção crucial:* as **predições** (`vcmr_res_dict`) são produzidas por `pipeline.retrieval()` **antes** de qualquer métrica; a avaliação (`eval_retrieval`, que consome `ts`) é um passo *separado* depois. *Conclusão:* você obtém os resultados de busca sem gabarito, pulando a avaliação.
2. **A ARMADILHA — leia `retrieve.py:271`:**
   ```python
   captree.compute_tree_feature(resume_video_names=test_dataset.vid_name_to_id.keys())
   ```
   *Entenda o que isso faz:* **o corpus pesquisável é definido pelos vídeos que aparecem no arquivo de consultas.** Se `vid_name_to_id` não contém todos os seus vídeos, a árvore é podada só para os referenciados, e `vid_id = test_dataset.vid_name_to_id[vid_name]` (`MixPipe.py:70`) dá `KeyError`. *Este é o ponto que ninguém percebe até rodar.*
3. **Alvos da mudança:** (a) um laço de inferência que chama `pipeline.retrieval()`, aplica `post_processing_vcmr_nms`, e salva só `vcmr_res_dict['VCMR']`; (b) popular `vid_name_to_id` a partir do conjunto de vídeos da *árvore*, não das consultas.

### O formato do que você recebe (para confirmar o alvo)

Leia `MixPipe.py:145–162`. Cada predição de query é uma lista ranqueada de `[vid_id, início, fim, score, nome_do_vídeo, legenda]`. **É precisamente o resultado de busca que você quer** — com a legenda que explica *por que* o trecho foi retornado.

### Teste de litmus (você mapeou a extração?)

Responda: *"Quais são os TRÊS pontos que tocam o `annos/`, e qual deles NÃO é óbvio?"* Resposta: manifesto (`select_videos`), entrada (`DataSet4Test` exige `ts`), saída/corpus (`eval_epoch` + a armadilha em `compute_tree_feature`); **o não-óbvio é a armadilha** — o corpus pesquisável ser definido pelas consultas.

### Verificação (testes da extração)

- **Teste de equivalência (Ponto 1):** a `tree.json` gerada com listagem de diretório deve ser idêntica à gerada com o manifesto, para o mesmo conjunto de vídeos.
- **Teste crítico da armadilha (Ponto 3):** injete um vídeo *não-referenciado por nenhuma consulta* e confirme que ele é buscável (se não for, o desacoplamento falhou).

### Armadilhas desta lente

- **Achar que "a fronteira é o `annos/`" significa "o `annos/` é necessário".** Fronteira = linha de corte = a parte que **sai**. O `annos/` é o **descartável**.
- **Tentar modificar os módulos-núcleo.** Você não toca QM-Gen/SWi-Den/scoring; a extração os preserva.
- **Apagar o `annos/` e rodar.** Quebra em `open(anno_path)` e em `DataSet4Test`. As cirurgias são o caminho.
- **Ignorar a armadilha de acoplamento.** Seu corpus encolhe silenciosamente para os vídeos referenciados nas consultas.

---

# A SEQUÊNCIA UNIFICADA
### (as três lentes numa única ordem executável)

Ordenada por dependência — cada passo pressupõe o anterior:

```
0. LINHA DE BASE (Regra de Ouro)
   Rode o pipeline não-modificado em 5–10 vídeos + annos dummy.
   → Saber como é o "correto" antes de tudo.
        │
        ▼
1. LENTE 1 — CRUX
   Leia construct() (67–90) + inspecione uma tree.json.
   → Teste de litmus do crux. NÃO avance sem passar.
        │
        ▼
2. TRACE UMA CONSULTA
   Siga uma query pelo MixPipe; veja o formato de saída (145–162).
   → Ver a funcionalidade e o resultado que você vai consumir.
        │
        ▼
3. LENTE 2 — NOVIDADE
   Estude QM-Gen (P1) → fusão (P2) → SWi-Den (P3).
   → Teste de litmus da novidade.
        │
        ▼
4. LENTE 3 — EXTRAÇÃO
   Analise os 3 pontos de contato do annos/ (incl. a armadilha).
   → Teste de litmus da extração.
        │
        ▼
5. EXECUTE AS CIRURGIAS + VERIFIQUE
   Ponto 1 (equivalência) → Pontos 2–3 (armadilha) → inferência pura.
        │
        ▼
6. VALIDAÇÃO QUALITATIVA (sem annos)
   Leia as legendas geradas (denoised_captions.jsonl) → diagnóstico de domínio na fonte.
   Rode prompts de resposta conhecida → confirma que a novidade opera nos seus dados.
```

Note a lógica: você **estuda** (0–3), depois **extrai** (4–5), depois **confirma** (6). E a extração (4–5) preserva o que você estudou (1–3), tocando só as bordas.

---

# CHECKLIST DE PROGRESSÃO

Marque cada item só quando o teste de litmus correspondente passar:

- [ ] **Linha de base:** `tree.json` gerada e predições saindo no micro-corpus.
- [ ] **Crux:** sei dizer o que há num nó da `tree.json` e por que a construção dispensa rótulo.
- [ ] **Novidade:** sei as duas deltas do QM-Gen, por que texto > visual, e onde a query vira número.
- [ ] **Extração:** sei os três pontos que tocam `annos/` e qual é a armadilha não-óbvia.
- [ ] **Cirurgias:** teste de equivalência (Ponto 1) e teste da armadilha (Ponto 3) passam.
- [ ] **Validação:** legendas geradas são fiéis ao conteúdo; prompts conhecidos trazem o momento certo no top-K.

---

# ARMADILHAS COMUNS (consolidadas)

Pontos de partida ou leituras erradas que fazem você perder tempo:

1. **Ler o código em ordem de arquivo / de cima a baixo.** A arquitetura não é linear no sistema de arquivos; você se afoga em config e encanamento antes da ideia.
2. **Começar pela avaliação (`standalone_eval/`).** Isso é *medição*, não *método* — é a parte que você **remove**, não estuda.
3. **Procurar "o módulo da novidade" para levantar isolado.** A novidade é a composição + o modo sem-rótulo; o valor funcional exige a cadeia inteira.
4. **Começar pelo SWi-Den.** Impacto empírico quase nulo; pior retorno por atenção.
5. **Extrair antes de rodar o pipeline original.** Sem a linha de base, um bug seu é indistinguível do comportamento esperado.
6. **Confundir "fronteira da extração" com "componente necessário".** O `annos/` é a linha de corte — a parte que sai.
7. **Ignorar a armadilha de `compute_tree_feature`.** Corpus de busca encolhe silenciosamente.
8. **Ajustar o retrieval quando as legendas são ruins.** Legenda ruim é defeito na fonte; nenhum ajuste de fusão recupera o que o captioning não capturou — diagnostique nas legendas.

---

# APÊNDICE — Mapa de navegação rápida (arquivo → lente → papel)

| Arquivo · âncora | Linha | Lente | Papel na análise |
|---|---|---|---|
| `constructpipe/base.py::construct` | 67–90 | **1 (Crux)** | Espinha dorsal — ponto de entrada do crux |
| `constructpipe/base.py::build_tree_meta` | 169–182 | 1 | Monta o nó da árvore (2 níveis) |
| (arquivo de saída) `tree.json` | — | 1 | O produto da transformação — inspecionar |
| `propgenerator/QMPropGener.py::calculate_similarities` | 28 | **2 (Novidade)** | Matriz `vis`/`txt`/`it` — a delta textual |
| `propgenerator/QMPropGener.py::generate_proposal` | 69–105 | 2 (P1) | QM-Gen: kernel (74–87), fronteiras (98–105) |
| `propgenerator/QMPropGener.py` (keys) | 136 | 2 | Indexing Keyword Set (Eq. 5) |
| `retrievepipe/MixPipe.py` (scoring) | 66–73 | 2 (P2) | Onde a query vira número |
| `retrievepipe/MixPipe.py` (fusão) | 130 | 2 | Fusão α·sent+(1−α)·key (Eq. 9) |
| `retrievepipe/MixPipe.py` (saída) | 145–162 | 2/3 | Formato do resultado de busca |
| `denoiser/window.py::denoise_caption` | 20–34 | 2 (P3) | SWi-Den (Eq. 2) — ler com ceticismo |
| `utils/sim_utils.py::get_caption_frame_sims` | 78 | 2 | Quality Score (Eq. 1) |
| `constructpipe/base.py::select_videos` | 184 | **3 (Extração)** | Ponto 1 — manifesto (lê só `vid_name`) |
| `dataset/dataset.py::DataSet4Test` | — | 3 | Ponto 2 — exige `ts` |
| `retrieve.py::eval_epoch` | 182–231 | 3 | Ponto 3 — avaliação a contornar |
| `retrieve.py::compute_tree_feature` (chamada) | 271 | 3 | **A ARMADILHA** — corpus definido pelas consultas |
| `standalone_eval/eval.py` | 82–164 | (evitar) | Medição — a parte que se remove |

**Hiperparâmetros (defaults):** θd=0.4 (`figsim_denoise_thr`), W=2 (`denoise_window_width`), θb=0.2 (`prop_score_thr`), `prop_kernel_width`=5, α=0.5 (`retrieve_sent_ratio`), `key_policy`=max_mean, 1fps.

---

*Fim do guia. Siga a Sequência Unificada; use os testes de litmus como portões — não avance de lente sem passar no teste da anterior.*
