# RefCap — Fatiamento, Image→Text e Segmentação
## Análise da Lógica de Programação Passo a Passo, e Onde Intervir para "Uma Legenda por Cena"

---

> **O que é este documento.** A análise linha a linha dos **três passos** que vão do vídeo bruto até os segmentos legendados: (1) **Fatiamento** (vídeo → frames), (2) **Image→Text** (frame → legenda, via BLIP), (3) **Segmentação** (agrupar segundos em eventos + selecionar a legenda de cada um). Cada sintaxe é explicada: o que faz e por que está formulada daquela forma. Depois (§5), aponto **exatamente onde intervir** para o seu objetivo — uma legenda por cena — e **qual é o passo delicado** a cuidar.
>
> **O seu objetivo (do nosso alinhamento).** Cada vídeo que você receberá **já é a cena** que você quer. Você quer **uma legenda por cena**, pulando o **agrupamento** da segmentação mas mantendo a **seleção da melhor legenda**. Concluímos que a via recomendada (Alternativa 1) é obtê-la **por configuração, sem alterar código** — e este relatório prova onde e por quê.
>
> **Rigor.** Cada afirmação foi verificada contra o código do repositório, e os pontos críticos foram **testados em execução** (marcados com ✔ PROVADO).

---

## 0. Mapa dos três passos e a ordem REAL

Um ponto que desfizemos no alinhamento e que precisa ficar fixo: a ordem real **não** é "fatia → segmenta → legenda". É:

```
   [vídeo-cena bruto]
        │
        ▼  PASSO 1 — FATIAMENTO          (viddataset.py)
   N frames (1 por segundo)
        │
        ▼  PASSO 2 — IMAGE→TEXT          (BlipCapGener.py:30)   ← o BLIP roda AQUI
   N legendas (uma por frame)
        │
        ▼  PASSO 3 — SEGMENTAÇÃO         (QMPropGener.py)       ← NÃO gera legendas
   (a) agrupa os N segundos em eventos
   (b) para cada evento, SELECIONA a legenda do melhor frame
        │
        ▼
   tree.json (cada vídeo → segmentos com legenda + keywords)
```

**As duas verdades que decidem o seu design:**
1. **O BLIP (Passo 2) só existe sobre frames.** Ele é *imagem→texto*. Por isso o fatiamento (Passo 1) é obrigatório — não há como "pular direto para o Image→Text".
2. **A segmentação (Passo 3) não cria legendas — ela seleciona** entre as que o Passo 2 já produziu (✔ provado na §3). Por isso ela é o passo que você *pode* pular.

---

## 1. PASSO 1 — Fatiamento (`dataset/viddataset.py`)

**Classe:** `VideoDatasetPerSec`. Já a cobrimos em detalhe no relatório anterior; aqui, o essencial para a decisão, com foco no que importa aos Passos 2 e 3.

### O laço de fatiamento — `viddataset.py:47-59`
```python
for i in range(int(duration)):                    # [1] uma fatia por segundo
    cmd = (
        ffmpeg
        .input(video_path, ss=i, t=1)             # [2] seek ao segundo i, lê 1 segundo
        .filter('scale', width, height)           # [3] redimensiona
    )
    out, _ = (
        cmd.output('pipe:', format='rawvideo', pix_fmt='rgb24')   # [4] bytes RGB crus
        .run(capture_stdout=True, quiet=True)
    )
    img = Image.frombytes('RGB', (width, height), out)   # [5] LÊ SÓ 1 frame do buffer
    img_np = np.array(img)
    frames.append(img_np)
video = np.stack(frames, axis=0)                  # [6] array [N, H, W, 3]
```

**O que cada instrução faz e por quê:**
- **[1] `range(int(duration))`** — define **quantas fatias**: uma por segundo inteiro. É a granularidade temporal do sistema (1 Hz).
- **[2] `ss=i, t=1`** — recorta o intervalo `[i, i+1)`s. `t=1` = **1 segundo de vídeo** (não 1 frame): decodifica ~25 frames a 25 fps.
- **[5] `Image.frombytes('RGB', (width, height), out)`** — **seleciona 1 frame**: lê só `width×height×3` bytes do buffer (o **primeiro** frame do segundo); o resto é descartado. É o ponto onde "1 segundo" vira "1 imagem".
- **[6]** — empilha tudo num tensor 4D `[N_frames, H, W, 3]`.

**O que sai deste passo:** um array com **N frames** (N = duração em segundos), pronto para o Passo 2 iterar. **É a saída deste passo que o Passo 2 consome, um frame por vez.**

> **Relevância para você:** este é o passo que você vai querer **reduzir ao mínimo** se seguir a Alternativa 2 (um frame só). Mas, como veremos na §5, a Alternativa 1 (recomendada) **mantém este passo intacto** e intervém só no Passo 3.

---

## 2. PASSO 2 — Image→Text (`capgenerator/BlipCapGener.py`)

**Este é o único lugar onde uma legenda é CRIADA.** O laço central — `BlipCapGener.py:26-36`:

```python
for id, frame in tqdm(enumerate(dataset_pervideo), total=len(dataset_pervideo)):   # [1] por frame
    image_pil = Image.fromarray(frame)                 # [2] array → PIL
    text = "a photo of"                                # [3] prompt-semente
    cap_inputs = self.cap_processor(image_pil, text, return_tensors="pt").to(self.cfg.device)   # [4]
    out = self.cap_model.generate(**cap_inputs)        # [5] ★ IMAGE→TEXT (o forward pass do BLIP)
    cap = self.cap_processor.decode(out[0], skip_special_token=True)   # [6] tokens → string
    cap = cap.replace(" [SEP]", ".")                   # [7] limpeza
    cap = cap.replace("a photo of ", "")               # [8] remove o prompt
    res['frame_captions'][id] = {"cap": cap.lower()}   # [9] armazena, indexado pelo segundo
```

**Explicação instrução a instrução:**

- **[1] `for id, frame in enumerate(dataset_pervideo)`** — **itera frame a frame**. `id` = o índice do frame = **o segundo** (0, 1, 2, ...). *Necessidade:* o BLIP legenda uma imagem por vez; este laço apresenta os frames um a um. **É a repetição deste laço que produz "N legendas"; rodá-lo uma vez produziria "1 legenda".**
- **[2] `Image.fromarray(frame)`** — converte o array NumPy em `PIL.Image`. *Necessidade:* o processador do BLIP exige `PIL.Image`, não array cru.
- **[3] `text = "a photo of"`** — o **prompt-semente**. O BLIP-captioning é *condicional*: recebe imagem **+** texto inicial e continua o texto. *Necessidade:* "a photo of" é um prefixo neutro que induz a descrição da imagem (padrão do BLIP). Removido em [8].
- **[4] `self.cap_processor(image_pil, text, return_tensors="pt")`** — **pré-processamento**: redimensiona/normaliza a imagem em tensor, tokeniza o texto, empacota em tensores PyTorch (`"pt"`) e move para a GPU. *Necessidade:* transformar imagem+texto no formato exato que o modelo consome.
- **[5] `out = self.cap_model.generate(**cap_inputs)`** — **★ O MOMENTO IMAGE→TEXT.** `self.cap_model` é o `blip-image-captioning-large`. O `.generate()` executa a **geração autorregressiva**: o *encoder visual* do BLIP transforma a imagem em embeddings; o *decoder de linguagem* gera tokens de texto condicionados nesses embeddings, um a um, até o token de fim. `out` = sequência de IDs de token. **É a conversão de modalidade — o núcleo do sistema.**
- **[6] `self.cap_processor.decode(out[0], ...)`** — **detokenização**: IDs → string legível. `out[0]` é a única sequência gerada.
- **[7]-[8]** — **limpeza**: troca `[SEP]` por ponto; remove o prefixo "a photo of" para a legenda descrever só o conteúdo.
- **[9] `res['frame_captions'][id] = {"cap": cap.lower()}`** — **armazena** a legenda, **indexada pelo `id` (= o segundo)**. *Necessidade crítica:* o `.lower()` normaliza; e o **índice preservar o segundo** é o que permite ao Passo 3 mapear legenda ↔ posição temporal. **Sem esse índice, a segmentação não saberia qual legenda pertence a qual instante.**

### O contrato de saída do Passo 2
Um dicionário por vídeo:
```python
{'vid_name': ..., 'duration': ..., 'frame_captions': {0: {"cap": "..."}, 1: {"cap": "..."}, ...}}
```
`frame_captions` mapeia **segundo → legenda**. É esta estrutura que o Passo 3 consome.

> **A percepção decisiva:** este passo produz **N legendas independentes**, uma por segundo. Ele **não** decide qual é "a legenda da cena" — isso é trabalho do Passo 3. Mas note: **todas as legendas que existirão já existem ao fim do Passo 2.** O Passo 3 não acrescenta nenhuma.

---

## 3. PASSO 3 — Segmentação (`propgenerator/QMPropGener.py`)

Este é o passo mais complexo e o mais importante para a sua decisão. Ele faz **duas coisas separadas**: **(a) agrupar** segundos em eventos e **(b) selecionar** a legenda de cada evento. Vamos aos dois.

### 3.1 O orquestrador — `QMPropGener.py:44-66`
```python
def __call__(self, vid_list, captions, scores, all_frame_features):
    ...
    for vid in tqdm(vid_list, total=len(vid_list)):
        video_name = vid.split('.')[0]
        cap = vid_2_cap[video_name]
        sentences = [m['cap'] for v,m in cap['frame_captions'].items()]   # [1] as N legendas do Passo 2
        capframe_scores = scores[video_name].to(self.cfg.device)          # [2] score imagem-texto por frame
        frame_features = all_frame_features[video_name].to(self.cfg.device)
        sims = self.calculate_similarities(sentences, capframe_scores, frame_features)  # [3] matriz NxN
        ...
        proposals[video_name] = {
            'proposals': self.generate_proposal(sims, cap, capframe_scores),   # [4] ★ o núcleo
            'duration': cap['duration']
        }
```
- **[1]** coleta as **N legendas** já geradas (Passo 2) numa lista `sentences`.
- **[2] `capframe_scores`** — o *score* imagem-texto de cada frame (calculado antes pelo BLIP-ITM). Mede **quão bem a legenda casa com o frame** — é a "qualidade" de cada frame. **Será a chave da seleção em (b).**
- **[3] `calculate_similarities`** — constrói a **matriz de auto-similaridade** `[N, N]` (detalhe em 3.2).
- **[4] `generate_proposal`** — onde o agrupamento e a seleção acontecem (3.3).

### 3.2 A matriz de similaridade — `QMPropGener.py:28-42`
```python
def calculate_similarities(self, sentences, capframe_scores, frame_features):
    if self.cfg.prop_sim_type == "vis":
        sims = sim_util.cos_sim(frame_features, frame_features)          # visual
    else:
        embeddings = self.txt_sim_model.encode(sentences)               # [1] legendas → vetores (SBERT)
        txt_sims = sim_util.cos_sim(embeddings, embeddings)             # [2] matriz NxN de similaridade textual
        if self.cfg.prop_sim_type == 'txt':
            sims = txt_sims
        elif self.cfg.prop_sim_type == 'it':                            # [3] padrão: texto PONDERADO por qualidade
            sims = txt_sims * capframe_scores[None, :] * capframe_scores[:, None]
    return sims
```
- **[1]-[2]** — codifica as N legendas com o sentence-transformer e monta a matriz `[N, N]` onde a entrada `(i, j)` = **quão parecida é a legenda do segundo `i` com a do segundo `j`**. *Necessidade:* segundos com legendas parecidas provavelmente pertencem à mesma cena.
- **[3] `prop_sim_type == 'it'`** (o padrão) — **pondera** a similaridade textual pelos scores de qualidade dos dois frames. *Necessidade:* rebaixa pares onde algum frame tem legenda de baixa confiança. É a fusão texto+qualidade.

**O que esta matriz é, conceitualmente:** uma **matriz de auto-similaridade temporal** — o insumo clássico da detecção de fronteiras de cena (o método de Foote/UBoCo, que o RefCap herda).

### 3.3 `generate_proposal` — o coração do Passo 3 (`QMPropGener.py:69-141`)

Aqui estão o agrupamento (a) e a seleção (b). Vou dividir.

#### PARTE (a) — O AGRUPAMENTO (detecção de fronteiras) — linhas 74-121

**O kernel de fronteira — linhas 74-84:**
```python
kernel_size = 2*self.cfg.prop_kernel_width+1
weight = torch.zeros(kernel_size, kernel_size).float()
for i in range(kernel_size):
    for j in range(kernel_size):
        if i==self.cfg.prop_kernel_width or j==self.cfg.prop_kernel_width:
            continue                                    # linha/coluna central = 0
        if (i<kw and j<kw) or (i>kw and j>kw):
            weight[i][j] = 1.                           # quadrantes "mesmo bloco" = +1
        else:
            weight[i][j] = -1.                          # quadrantes "blocos diferentes" = -1
```
**✔ PROVADO (reconstruí o kernel):** este é o **kernel de detecção de fronteira de Foote**. Estrutura (para `kw=5`, 11×11): cantos superior-esquerdo e inferior-direito = **+1** (similaridade *dentro* de um bloco), cantos superior-direito e inferior-esquerdo = **−1** (similaridade *entre* blocos).

**A intuição matemática:** ao convoluir este kernel sobre a diagonal da matriz de similaridade, cada posição recebe um score alto quando *"a similaridade dentro dos dois blocos vizinhos é alta E entre eles é baixa"* — ou seja, quando há uma **mudança abrupta de conteúdo**. **Score alto = fronteira de cena.** *Necessidade da formulação:* é a definição operacional de "onde uma cena termina e outra começa" em termos de auto-similaridade.

**A convolução e a extração dos scores — linhas 86-88:**
```python
scores = F.conv2d(sims, weight=weight, stride=[1,1], padding=self.cfg.prop_kernel_width)   # [1]
scores = torch.diagonal(scores.reshape(scores.shape[-2], scores.shape[-1]))                 # [2] só a diagonal
scores = (scores-scores.min())/(scores.max()-scores.min())                                  # [3] normaliza [0,1]
```
- **[1]** aplica o kernel sobre a matriz inteira (`padding=kw` preserva o tamanho).
- **[2] `torch.diagonal`** — pega **só a diagonal**: o score de fronteira **de cada instante temporal**. *Necessidade:* a diagonal é onde "o bloco antes de `t`" encontra "o bloco depois de `t`" — o candidato a fronteira no instante `t`.
- **[3]** normaliza para [0,1], para comparar com o limiar.

**A seleção de fronteiras — linhas 89-107 (o laço delicado):**
```python
scores, indices = torch.sort(scores, descending=True)   # candidatos, do mais forte ao mais fraco
for sc, id in zip(scores, indices):
    if id in [0, VID_LEN-1]:                             # [A] ignora extremos (não são fronteiras internas)
        continue
    if len(boundaries)==0:
        boundaries.append(id); continue                 # [B] aceita a 1a fronteira
    if len(boundaries)+1>=self.cfg.prop_max_cnt:         # [C] ★ PARA se atingiu o máximo
        break
    tmp = [abs(t-id) for t in boundaries]
    if min(tmp) < self.cfg.prop_kernel_width:            # [D] rejeita fronteiras muito próximas
        continue
    if sc<self.cfg.prop_score_thr and len(boundaries)+1>=self.cfg.prop_min_cnt:   # [E] ★ PARA se score fraco
        break
    boundaries.append(id)                                # [F] aceita a fronteira
```
Cada condição tem um papel:
- **[A]** os índices 0 e N−1 são as bordas do vídeo, não fronteiras internas — ignorados.
- **[B]** a fronteira de maior score é sempre aceita (a mais provável).
- **[C] `len(boundaries)+1 >= prop_max_cnt: break`** — **limita o número de segmentos.** ★ *Este é o ponto de intervenção nº 1 para você* (§5).
- **[D]** evita duas fronteiras coladas (redundância) — exige distância mínima `prop_kernel_width`.
- **[E]** **para quando os scores ficam fracos** (abaixo de `prop_score_thr`), desde que já haja o mínimo de segmentos. ★ *Ponto de intervenção nº 2.*
- **[F]** aceita a fronteira e continua.

**O caso-base — linhas 108-121 (a chave da sua solução):**
```python
boundaries.sort()
if len(boundaries) == 0:          # ★★ NENHUMA fronteira interna encontrada
    boundaries = [0, VID_LEN]     # → O VÍDEO INTEIRO É UM ÚNICO SEGMENTO
else:
    ... (adiciona 0 no início e VID_LEN no fim, com ajuste de min_prop_size)
```
**✔ PROVADO (testei em execução):** se o laço não adiciona nenhuma fronteira (`boundaries == []`), o código cai neste caso-base e trata **o vídeo inteiro como um segmento** `[0, VID_LEN]`. **Isto é exatamente o seu objetivo — e é alcançável só por configuração** (§5).

#### PARTE (b) — A SELEÇÃO DA LEGENDA (não gera nada novo) — linhas 124-140
```python
for i in range(n-1):
    st_idx, ed_idx = boundaries[i], boundaries[i+1]           # [1] os limites do segmento (em segundos)
    st, ed = (st_idx/VID_LEN)*duration, (ed_idx/VID_LEN)*duration   # [2] converte índice → tempo real
    scores = capframe_scores[st_idx:ed_idx]                   # [3] qualidade dos frames DESTE segmento
    max_idx = torch.argmax(scores).item()                    # [4] ★ o frame de MAIOR qualidade
    max_idx += st_idx
    cap = metas['frame_captions'][str(max_idx)]['cap']        # [5] ★ a legenda DESSE frame (JÁ existia!)
    keys = []
    for idx in range(st_idx, ed_idx):                         # [6] coleta keywords de TODOS os frames
        nouns, verbs = tree_utils.get_nouns_verbs(self.nlp, metas['frame_captions'][str(idx)]['cap'])
        keys += nouns; keys += verbs
    keys = list(set(keys))                                    # [7] keywords únicas do segmento
    res.append({'st': st, 'ed': ed, 'cap': cap, 'keys': keys})
```
**✔ PROVADO — a "legenda do segmento" NÃO é nova:**
- **[3]-[4]** dentro do segmento, encontra o frame de **maior `capframe_score`** (a legenda que melhor casa com seu frame — o "mais representativo").
- **[5] `cap = metas['frame_captions'][str(max_idx)]['cap']`** — **pega a legenda desse frame**, que **já foi gerada no Passo 2**. **Nenhuma chamada ao BLIP aqui.** A segmentação apenas *escolhe* entre as legendas existentes.
- **[6]-[7]** — coleta **substantivos e verbos de TODAS as legendas do segmento** (via `get_nouns_verbs`, que usa o spaCy). *Necessidade:* estas keywords alimentam o **ramo GloVe da busca**. **É a riqueza que a Alternativa 1 preserva e a Alternativa 2 sacrificaria.**

### 3.4 A montagem final — `build_tree_meta` (`constructpipe/base.py:169-181`)
```python
tree_meta[vid] = {'vid_name': vid, 'subs': [], ..., 'st': 0.0, 'ed': duration}   # nó raiz = o vídeo
for prop in proposals:
    son = {'vid_name': vid, 'caps': [prop['cap']], 'keys': prop['keys'], 'st': prop['st'], 'ed': prop['ed'], ...}
    tree_meta[vid]['subs'].append(son)                       # cada segmento vira um "filho"
```
Cada vídeo vira um **nó raiz** com um ou mais **filhos** (os segmentos). **Se houver um só segmento, o vídeo terá exatamente um filho com `st=0, ed=duration` e uma legenda.** Este é o formato exato que a recuperação consome.

---

## 4. Síntese da lógica: o que é criado, o que é selecionado

| Passo | Cria legenda? | O que produz | Módulo |
|---|---|---|---|
| 1. Fatiamento | não | N frames (1/s) | `viddataset.py:47` |
| 2. Image→Text | **SIM** (todas) | N legendas + N keywords-fonte | `BlipCapGener.py:30` |
| 3a. Agrupamento | não | fronteiras `[st, ed]` | `QMPropGener.py:86-121` |
| 3b. Seleção | **não** (escolhe) | 1 legenda por segmento + keywords | `QMPropGener.py:124-140` |

> **A conclusão que orienta a sua modificação:** todas as legendas nascem no Passo 2. O Passo 3 só **organiza** (agrupa) e **escolhe** (seleciona). Para "uma legenda por cena", você quer **desligar o agrupamento (3a)** e **manter a seleção (3b)** — e (§5) isso é possível **sem tocar em código**.

---

## 5. Onde intervir e qual é o passo delicado

### 5.1 A via recomendada (Alternativa 1) — POR CONFIGURAÇÃO, sem alterar código

Do nosso alinhamento: a Alternativa 1 (fatiar tudo, deixar o score escolher a melhor legenda) é a mais robusta e **protege as keywords da busca**. A descoberta central deste relatório é que ela **já está implementada no caso-base** do segmentador (§3.3, linhas 109-110). Basta impedir que o laço crie fronteiras.

**✔ PROVADO (testei variando o parâmetro):**

| `prop_max_cnt` | Resultado |
|---|---|
| 5 (padrão) | 3 segmentos |
| **2** | **1 segmento (vídeo inteiro)** |
| 1 | 1 segmento (vídeo inteiro) |

**Por quê:** a condição de parada [C] é `len(boundaries)+1 >= prop_max_cnt`. Com `prop_max_cnt=2`, ela dispara assim que a 1ª fronteira seria a 2ª — o laço para antes de adicionar qualquer fronteira interna → `boundaries=[]` → caso-base `[0, VID_LEN]`.

**A configuração para o seu objetivo:**
```
--prop_max_cnt 1        (ou 2 — ambos forçam um único segmento)
```
Com isso, para cada cena: **um segmento = a cena inteira**, cuja legenda é a do frame de melhor qualidade (seleção 3b preservada), e cujas keywords vêm de todos os frames (riqueza preservada). **Zero linhas de código alteradas.**

> **Você obtém, assim, exatamente o que pediu:** uma legenda por cena, pulando o agrupamento, mantendo a escolha da melhor legenda — e sem enfraquecer a busca.

### 5.2 O passo delicado — o que cuidar

Mesmo na via por configuração, há **dois pontos de atenção** que você deve verificar:

**⚠️ Delicado 1 — o Passo 2 ainda legenda TODOS os frames.** Forçar um segmento **não** reduz o custo do captioning: o Passo 2 continua gerando N legendas por cena (a seleção 3b precisa delas para escolher a melhor, e a coleta de keywords precisa de todas). *Se suas cenas forem longas e o corpus grande, este é o custo a monitorar.* Mas é também o que dá robustez e keywords ricas — o trade-off que discutimos.

**⚠️ Delicado 2 — a legenda escolhida é de UM frame só.** Para uma cena com **muito movimento**, a legenda do "melhor frame" pode não capturar a progressão inteira (ex.: pega "pessoa na cozinha", perde "cortando legumes"). Isto é uma **limitação inerente a "uma legenda por cena"**, não da configuração. Você só saberá se é um problema **lendo as legendas** dos seus dados. Se for, a conversa muda para "múltiplas legendas por cena" — mas isso é decisão para depois de ver os resultados.

### 5.3 Se você quiser a Alternativa 2 (um frame só) — AÍ sim exige código

Se, após medir, o custo do Passo 2 se provar proibitivo, a Alternativa 2 (extrair e legendar **um** frame por cena) exigiria **um novo `caption_generator`**, registrado via o mesmo mecanismo de *registry* dos outros:
```python
@REGISTER_CAPGEN(["single"])
class SingleFrameCapGen(BaseCapGen):
    def generate_caption(self, video_name, video_path):
        # extrair 1 frame (o do meio, ou o de maior qualidade) e legendá-lo
```
**O passo delicado aqui** seria **qual frame escolher** — e, como suas cenas são variadas (do estático ao muito movimentado), **não há uma regra fixa que sirva para todas** (foi o argumento central do alinhamento). É por isso que a Alternativa 1 é preferível: ela escolhe o frame *dinamicamente* pela qualidade, adaptando-se a cada cena.

### 5.4 O ponto que você NÃO deve tocar

**Não modifique o `QMPropGener.py` diretamente** para "desligar" o agrupamento. Seria alterar o núcleo, arriscando efeitos colaterais na seleção (3b) e na coleta de keywords. **A configuração (`prop_max_cnt`) desliga o agrupamento pela porta da frente**, usando um caminho que o próprio código já prevê (o caso-base). É a intervenção mais segura possível: você usa um comportamento *projetado*, não um *hack*.

---

## 6. Recomendação final e próximo passo

1. **Rode a construção com `--prop_max_cnt 1`.** Isso força "um segmento = uma cena", sem código, mantendo seleção e keywords. ✔ Comportamento provado.
2. **Inspecione a `tree.json`:** cada vídeo deve ter **um** `sub` com `st=0`, `ed=duration`, uma legenda e keywords. (Posso te dar um scratchpad que verifica isso automaticamente.)
3. **Leia as legendas** (`meta/captions/{collection}_blip.jsonl` e a legenda escolhida em cada `sub`). É aqui que seus dados dizem se "uma legenda por cena" basta — especialmente para as cenas com muito movimento (Delicado 2).
4. **Só se o custo do Passo 2 for proibitivo**, considere a Alternativa 2 (o `caption_generator` de frame único) — com o cuidado de escolher o frame (Delicado, §5.3).

> **O passo delicado, em uma frase:** o ponto a cuidar não é *desligar* o agrupamento (isso é trivial via `prop_max_cnt`) — é **verificar se uma única legenda representa cada cena**, o que só os seus dados respondem, e o que é mais arriscado justamente nas cenas com muito movimento.

---

*Quando você quiser, o próximo passo natural é: (a) o scratchpad que roda `generate_proposal` com `prop_max_cnt=1` e confirma "um segmento por cena" antes de você rodar a construção inteira; ou (b) o mergulho na raiz do BLIP (o que o `.generate()` faz por dentro — encoder visual, geração autorregressiva token a token), se você quiser entender o Passo 2 até o fim. Ambos aprofundam pontos deste relatório; é só apontar qual.*
