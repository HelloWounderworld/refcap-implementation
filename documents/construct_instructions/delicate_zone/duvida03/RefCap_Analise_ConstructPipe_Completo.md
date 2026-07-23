# Análise do `BaseConstructPipeline` Completo
## O que os Arquivos Anexados Revelam — Achados Novos e Uma Correção

---

> **O que é este documento.** A análise do `pipeline/constructpipe/base.py` **completo** (203 linhas), que até agora eu só tinha lido em trechos. Ele contém os quatro métodos que fazem o trabalho real do pipeline — `compute_frame_features`, `compute_capframe_scores`, `build_tree_meta` e `select_videos` — e a leitura integral revelou **sete achados novos**, dos quais um **corrige uma afirmação minha em relatório anterior**.
>
> **Verificação.** Os anexos foram conferidos contra o repositório: `BlipCapGener.py` é idêntico (hash `0c747851`), e o `base.py` do `capgenerator` também. (Nota: como os dois arquivos se chamam `base.py`, um sobrescreveu o outro no disco — mas ambos os conteúdos chegaram no contexto, então nada se perdeu.) Cada achado abaixo foi **provado em execução** ou verificado por leitura direta com número de linha.
>
> **Resposta curta à sua pergunta.** A análise do registry/factory (Partes I–III do relatório anterior) **não muda em nada** — está confirmada pelos arquivos. O que muda é a **Parte IV (análise crítica)**, que cresce substancialmente, e o relatório de dissecação de cenas, que tem **um erro a corrigir**.

---

# PARTE 0 — O que muda e o que não muda

| Documento | Status após os anexos |
|---|---|
| `RefCap_Registry_Factory_A_Abstracao_Completa.md` — Partes I–III (mecânica, padrões, teoria) | ✅ **Inalterado e confirmado.** Os anexos batem exatamente com o que foi analisado. |
| Idem — Parte IV (crítica) e Cap. 19 (defeitos) | ⬆️ **Expande.** Sete defeitos novos, listados aqui. |
| Idem — Cap. 10 (Composition Root vs. Orquestrador) | ✅ **Reforçado.** O arquivo completo mostra o orquestrador *também* fazendo trabalho pesado — o que nuança, mas não invalida, a separação de papéis. |
| `RefCap_Disseccao_Cenas_e_Video_to_Text.md` — §4, item [4] | ❌ **CORREÇÃO NECESSÁRIA.** Ver Parte 3. |

---

# PARTE 1 — A anatomia do `BaseConstructPipeline` (agora visível por inteiro)

O arquivo tem quatro responsabilidades além de orquestrar, e é isso que o torna mais do que um orquestrador puro.

## 1.1 O grafo real de dados do `construct()`

```
                    vid_list ──────────────────────┐
                       │                            │
                       ▼                            │
 [1] caption_generator ──► captions ────────────────┼───────┐
                       │      │                     │       │
                       ▼      ▼                     ▼       │
 [2] compute_frame_features ──► features ───────────┼───┐   │
                              │  │  │               │   │   │
                              ▼  │  │               ▼   │   ▼
 [3] compute_capframe_scores ────┼──┼──► scores ────────┼───┤
                                 │  │       │           │   │
                                 │  │       ▼           │   ▼
 [4] caption_denoiser ───────────┼──┼──► denoised_captions ─┤
                                 │  │       │               │
                                 ▼  │       ▼               │
 [5] compute_capframe_scores ────┼──────► denoised_scores   │
                                 │          │               │
                                 ▼          ▼               ▼
 [6] proposal_generator ◄────────┴──────────┴───────────────┘
                       │
                       ▼
 [7] build_tree_meta ──► tree.json
```

**Confirma o Cap. 12 do relatório anterior:** não é uma cadeia. `features` alimenta os passos 3, 5 e 6; `captions` alimenta 2, 3 e 4. É um **DAG com fan-out**, e `compute_capframe_scores` é chamado **duas vezes** com entradas diferentes (antes e depois do denoising).

## 1.2 Os quatro métodos "de trabalho"

| Método | Linhas | O que faz | Cache |
|---|---|---|---|
| `select_videos` | 186–203 | Filtra `os.listdir()` pelo arquivo de anotações; converte `.mkv`→`.mp4` | não |
| `compute_frame_features` | 125–170 | Decodifica o vídeo e extrai features visuais BLIP por frame | `meta/framefeatures/{collection}.pt` |
| `compute_capframe_scores` | 100–122 | Calcula similaridade legenda↔frame (ITM) | `.pt` por caminho |
| `build_tree_meta` | 172–184 | Monta a estrutura final e grava `tree.json` | grava |

**Observação estrutural relevante ao Cap. 10 do relatório anterior:** eu havia caracterizado a `BaseConstructPipeline` como *orquestrador puro* (que só decide a ordem). Os anexos mostram que isso é **parcialmente falso**: ela orquestra *e* executa quatro etapas pesadas nos seus próprios métodos. As etapas 1, 4 e 6 são delegadas a colaboradores injetados (Strategy); as etapas 2, 3, 5 e 7 são feitas **por ela mesma**.

Isso é uma **inconsistência de design**: por que `caption_generator` é injetável e trocável, mas `compute_frame_features` é código fixo dentro do pipeline? Ambos são "um algoritmo que pode variar". A resposta honesta é que os autores tornaram extensível só o que precisavam variar no paper (VLLMs e denoisers), deixando o resto rígido. Legítimo para pesquisa — mas significa que a `BaseConstructPipeline` viola SRP: ela é orquestrador **e** implementadora.

---

# PARTE 2 — Os sete achados novos

## Achado 1 — Violação da Lei de Deméter: o pipeline alcança *dentro* do denoiser

**A evidência (verificada, com linhas):**
```python
# constructpipe/base.py:50-51 — o pipeline tem SUA PRÓPRIA referência
self.it_sim_model     = models['blip_itrtv_model']
self.it_sim_processor = models['blip_itrtv_processor']

# constructpipe/base.py:110 — compute_capframe_scores usa a própria (correto)
sims, _ = sim_utils.get_caption_frame_sims(self.it_sim_model, self.it_sim_processor, ...)

# constructpipe/base.py:155 e 159 — compute_frame_features usa a DO DENOISER (!)
frame_features = sim_utils._get_frame_features(
    self.caption_denoiser.it_sim_model,        # ← alcança dentro do colaborador
    self.caption_denoiser.it_sim_processor, ...)

# denoiser/base.py:26-27 — o denoiser tem o MESMO objeto
self.it_sim_model     = models["blip_itrtv_model"]
self.it_sim_processor = models["blip_itrtv_processor"]
```

**Três problemas de uma vez:**

1. **Lei de Deméter** ("fale só com amigos imediatos"): `self.caption_denoiser.it_sim_model` é um *train wreck* — o pipeline atravessa um colaborador para pegar um atributo interno dele.
2. **Inconsistência interna:** o **mesmo objeto** é acessado por **dois caminhos diferentes na mesma classe** — `self.it_sim_model` na linha 110 e `self.caption_denoiser.it_sim_model` na 155. Não há razão funcional; é descuido.
3. **Acoplamento não declarado (o mais grave):** o pipeline agora **exige** que *qualquer* denoiser tenha um atributo chamado `it_sim_model`. Isso não está em contrato nenhum — nem na ABC do denoiser, nem em assinatura, nem em docstring. Se você escrever um denoiser que não herda de `BaseDenoiser` (ou não chama `super().__init__`), o pipeline quebra em `compute_frame_features` com `AttributeError` — numa etapa que aparentemente nada tem a ver com denoising.

**A conexão teórica:** este é exatamente o "dependência implícita" do Cap. 16 do relatório anterior, na sua forma mais aguda. O contrato real do denoiser é maior do que o contrato declarado.

## Achado 2 — ★ A guarda de corrupção **causa** um crash na etapa seguinte

Este é o achado mais importante, e **corrige um erro meu**.

**O mecanismo (provado em execução):**
```python
# BlipCapGener.py:23-24 — a "guarda de robustez"
if len(dataset_pervideo.frames.shape) != 4:
    return                    # ← vídeo NÃO é adicionado a self.captions

# constructpipe/base.py:134,143 — a etapa seguinte
vid_2_cap = {x['vid_name']: x for x in captions}      # falta o vídeo corrompido
for vid in tqdm(vid_list, ...):                        # mas itera vid_list INTEIRA
    raw_cap = vid_2_cap[video_name]                    # ← KeyError!
```

**Prova executada:**
```
vid_list         = ['bom.mp4', 'corrompido.mp4', 'outro.mp4']
captions gerados = ['bom', 'outro']   <- 'corrompido' ausente (guarda funcionou)
      bom: ok
      >>> KeyError: 'corrompido'  <-- CRASH em constructpipe/base.py:143
```

**A assimetria fatal:** `generate_caption` itera sobre `vid_list` e **pula** o vídeo ruim; `compute_frame_features` itera sobre a **mesma `vid_list`** mas **assume** que todo vídeo tem legendas. As duas etapas discordam sobre quem está no conjunto.

**Por que isso é pior do que um crash normal:** a guarda dá a *ilusão* de robustez. Você lê `if len(shape) != 4: return` e conclui "ele trata vídeo corrompido". Ele não trata — ele **adia** a falha para um ponto onde a mensagem de erro (`KeyError: 'nome_do_video'`) não diz nada sobre corrupção. É o "silenciar erro" do Zen (#10) na sua forma mais cara: o erro não some, só reaparece longe da causa e disfarçado.

**O padrão correto** seria propagar uma exceção nomeada (`VideoDecodeError`) e decidir na fronteira: ou aborta, ou remove o vídeo de `vid_list` de forma **explícita e única**, para que todas as etapas seguintes concordem.

## Achado 3 — O vídeo é decodificado DUAS vezes por execução

**A evidência:**
```
BlipCapGener.py:21          dataset_pervideo = VideoDatasetPerSec(video_path, ...)
constructpipe/base.py:143   dataset_pervideo = VideoDatasetPerSec(video_path, ...)
```

Etapa 1 (legendagem) decodifica o vídeo inteiro. Etapa 2 (features de frame) decodifica **o mesmo vídeo, do zero, de novo** — mesmos frames, mesma resolução, mesmo custo.

**Combinando com o que já sabíamos:** cada decodificação já desperdiça ~25× (o `ffmpeg.input(ss=i, t=1)` decodifica o segundo inteiro para usar 1 frame). Duas decodificações → **~50× de trabalho de decodificação por frame efetivamente usado.**

**Por que não foi cacheado:** os frames existem na memória em `dataset_pervideo.frames` durante a etapa 1, mas são descartados ao fim do `generate_caption`. Os *caches* do projeto guardam as **legendas** (`.jsonl`) e as **features** (`.pt`), nunca os frames. É defensável (frames são grandes), mas as duas etapas poderiam ser fundidas num único passe pelo vídeo.

**Impacto prático:** numa reexecução com cache quente, ambas as etapas pulam (`already_video_names` e `all_frame_features`). O custo dobrado só aparece na **primeira** construção — que é justamente a mais cara.

## Achado 4 — Extensão `.mp4` hardcoded, inconsistente com a etapa anterior

```python
# capgenerator/base.py:42 — usa o NOME REAL do arquivo
video_path = os.path.join(self.cfg.video_root, vid)          # "clip.avi"

# constructpipe/base.py:142 — RECONSTRÓI o nome assumindo .mp4
video_path = os.path.join(self.cfg.video_root, f"{video_name}.mp4")   # "clip.mp4" ✗
```

**Consequência:** um vídeo `.avi`, `.webm`, `.mov` passa pela legendagem sem problema (a etapa 1 usa o nome real), e **quebra** na etapa 2, que procura um `.mp4` que não existe. O `select_videos` (linha 195) converte `.mkv`→`.mp4`, mas **só `.mkv`** — os outros formatos passam direto para a armadilha.

**Relevância direta para você:** você vai processar a **sua própria coleção de vídeos**. Se ela não for uniformemente `.mp4`, isto quebra. É o tipo de bug que só aparece depois de horas de legendagem já rodada.

## Achado 5 — `build_tree_meta` reatribui o nome do próprio parâmetro

```python
def build_tree_meta(self, proposals):          # parâmetro: dict {vid: metas}
    for vid, metas in tqdm(proposals.items()): # itera sobre o dict
        proposals = metas['proposals']         # ★ reatribui o MESMO nome, para uma LISTA
        for prop in proposals:                 # agora `proposals` é outra coisa
```

**Funciona? Sim — por acidente.** Provado em execução: `proposals.items()` é avaliado **uma vez** no início do laço, e o iterador já segura a referência ao dicionário original. Reatribuir o *nome* não afeta o iterador em curso.

**Mas é uma mina.** O nome `proposals` significa **duas coisas diferentes no mesmo escopo**: o dicionário `{vid: metas}` (parâmetro) e a lista de propostas de um vídeo (dentro do laço). Qualquer refatoração que mova o `.items()` para dentro do laço, ou que introduza um segundo laço, quebra silenciosamente. É o *shadowing* que os nossos tratados listam como smell — e aqui ele está a um passo de virar bug.

## Achado 6 — A "árvore" é plana: dois níveis, sem recursão

```python
# build_tree_meta: a raiz tem subs; os filhos NASCEM com subs vazio
tree_meta[vid] = {..., 'subs': [], 'caps': [], ...}          # raiz
son = {..., 'subs': [], 'caps': [prop['cap']], ...}          # filho: subs SEMPRE []
tree_meta[vid]['subs'].append(son)
```

Provado: a estrutura gerada é **raiz (vídeo inteiro) + um nível de folhas (propostas)**. Nunca mais fundo.

**O detalhe que confirma que isso não era o plano:** o `capTree.py:88` tem `if len(node['subs']) > 0:` — código que **existe para descer na recursão** e que **nunca é alcançado**, porque o construtor jamais produz filhos com filhos. O consumidor foi projetado para uma árvore; o produtor entrega uma lista.

**Interpretação:** ou a hierarquia profunda foi planejada e abandonada, ou é resquício de uma versão anterior. De qualquer forma, **o nome `CapTree` induz ao erro** — quem lê espera navegar uma hierarquia e encontra dois níveis fixos.

## Achado 7 — `select_videos`: um método-consulta que **converte arquivos**

```python
def select_videos(self, vid_list, anno_path):
    ...
    if vid.split(".")[-1] == "mkv":
        ...
        ffmpeg.input(mkv_video_path).output(new_video_path).run()   # ← ESCREVE NO DISCO
```

**Violação de Command-Query Separation.** O nome `select_videos` promete uma *query* (filtrar uma lista). Ele de fato **executa o ffmpeg e cria arquivos novos no diretório de vídeos do usuário** — um efeito colateral pesado, irreversível e completamente invisível no nome e na chamada (`self.select_videos(vid_list, anno_path)` na linha 46).

**E é aqui que vive o acoplamento corpus↔anotações:** as linhas 189–201 filtram a lista de vídeos pelo que existe no `annos/{collection}/vcmr.jsonl`. **Um vídeo que não esteja no arquivo de anotações é silenciosamente descartado** — não há aviso, não há log, ele simplesmente não entra em `new_vid_list`. É exatamente o motivo pelo qual o `make_annos.py` que construímos é obrigatório para processar a sua coleção.

---

# PARTE 3 — A correção que eu devo

No relatório `RefCap_Disseccao_Cenas_e_Video_to_Text.md`, §4, item **[4]**, eu escrevi:

> *"**Guarda de robustez.** [...] este teste pula o vídeo. Motivo: impede que um vídeo corrompido derrube todo o processo. **É a rede de proteção que torna o try/except do adapter desnecessário.**"*

**A última frase está errada**, e o Achado 2 a refuta com prova em execução. A guarda **não** impede que o processo caia — ela impede a queda *naquela etapa* e a **transfere** para `compute_frame_features`, onde vira um `KeyError` sem contexto.

**A afirmação correta:** o `if len(shape) != 4: return` protege o *loop de legendagem*, mas cria uma **inconsistência de conjunto** entre `vid_list` e `captions` que a etapa seguinte não tolera. Portanto, tratamento de vídeos corrompidos **na fronteira do seu adapter continua sendo necessário** — na verdade, é *mais* necessário do que eu havia dito, porque o pipeline falha de forma obscura em vez de graciosa.

**Recomendação prática:** valide os vídeos **antes** de entregá-los ao RefCap (um `ffprobe` de sanidade no `make_annos.py`, removendo os que falham). Assim `vid_list` e `captions` nunca divergem.

**Por que eu errei:** li a guarda isoladamente e julguei sua intenção local sem rastrear o que acontecia com o vídeo pulado *depois*. É precisamente o erro que os tratados chamam de raciocínio não-local — e um bom lembrete de que "esta linha trata o erro" só é verdade se você seguir o dado até o fim.

---

# PARTE 4 — Impacto no seu objetivo (uma boa notícia)

Verifiquei como o `CapTree` consome a estrutura, e isso **valida o plano do `WholePropGenerator`**:

```python
# capTree.py:65-76 — as legendas pesquisáveis vêm dos FILHOS, não da raiz
for node in root['subs']:
    if len(node['caps']) > 0:
        self.caps += node['caps']
        self.vidname_to_capids[node['vid_name']] += [...]
```

A raiz nasce com `'caps': []` (vazio) e **não contribui** com nada para a busca. Todo o índice vem dos filhos.

**Consequência para o seu caso:** com um `WholePropGenerator` que emite **uma proposta cobrindo `[0, duration]`**, a árvore fica raiz + 1 filho, e o `CapTree` indexa **exatamente uma legenda por vídeo** — que é precisamente o que você quer. A duplicação aparente (raiz e filho com o mesmo intervalo) é inofensiva, porque a raiz não é indexada.

**O que ainda precisa de decisão empírica:** *qual* legenda representa a cena. O `QMPropGenerator` usa a do frame de maior score ITM (linha 133). Herdar essa política é o ponto de partida natural — mas para cenas com muito movimento, é exatamente onde pode falhar, e só os seus vídeos dirão.

---

# PARTE 5 — Veredito atualizado

**Sobre a abstração do registry/factory:** nada muda. Os anexos confirmam a análise linha a linha. O padrão continua sendo o acerto arquitetural do projeto, e continua sendo o que viabiliza o `WholePropGenerator` sem tocar no `QMPropGenerator`.

**Sobre a qualidade do `BaseConstructPipeline`:** os anexos pioram consideravelmente o quadro. Sete defeitos novos, dos quais **dois são bugs reais** que podem te atingir na prática:

| # | Achado | Severidade | Te afeta? |
|---|---|---|---|
| 2 | Guarda de corrupção → `KeyError` na etapa seguinte | **Bug** | **Sim**, se algum vídeo seu falhar na decodificação |
| 4 | `.mp4` hardcoded em `compute_frame_features` | **Bug** | **Sim**, se sua coleção não for toda `.mp4` |
| 1 | Lei de Deméter + acoplamento não declarado ao denoiser | Design | Se você escrever um denoiser próprio |
| 3 | Decodificação dupla do vídeo (~50× de desperdício) | Performance | Sim, no custo da primeira construção |
| 7 | `select_videos` converte arquivos (viola CQS) + filtra por `annos` | Design/armadilha | **Sim** — é o motivo do `make_annos.py` |
| 5 | *Shadowing* do parâmetro em `build_tree_meta` | Smell | Não hoje |
| 6 | "Árvore" plana; consumidor preparado para recursão que não vem | Design/nome | Não — na verdade favorece seu plano |

**A leitura sóbria:** este é código de pesquisa que **funciona no caminho feliz do dataset dos autores** (Charades/ActivityNet, todos `.mp4`, todos íntegros, todos listados nas anotações). Fora desse caminho, ele falha de formas obscuras. Os dois bugs que te afetam são exatamente do tipo "só aparece com dados de terceiros" — e você é o terceiro.

**A ação concreta antes de rodar na sua coleção:** garanta no `make_annos.py` que (a) todo vídeo é `.mp4`, e (b) todo vídeo passa num `ffprobe` de sanidade. Essas duas linhas de validação na fronteira eliminam os Achados 2 e 4 de uma vez — sem tocar no RefCap.

---

*Esta análise cobriu o `BaseConstructPipeline` completo, revelando sete defeitos não visíveis nas leituras parciais anteriores — dois deles bugs que afetam diretamente o processamento de uma coleção de vídeos própria. Corrige também uma afirmação minha anterior sobre a guarda de vídeos corrompidos, que se mostrou uma proteção ilusória. A análise da abstração registry/factory permanece válida e confirmada, assim como o plano do `WholePropGenerator`, que foi adicionalmente validado contra o modo como o `CapTree` indexa as legendas.*
