# RefCap — A Dissecação de Cenas e a Conversão Vídeo→Texto
## Relatório Técnico Passo a Passo: do `construct.py` até o pixel virar legenda

---

> **O que é este documento.** A rota **completa e verificada linha a linha**, do ponto de entrada (`construct.py::main`) até a instrução exata onde o BLIP transforma um frame de vídeo em texto. Cada passo traz o **arquivo:linha**, o que a sintaxe faz, e *por que* ela existe. Foi escrito para ser lido com os arquivos abertos ao lado.
>
> **O alvo.** Você quer entender **onde e como o vídeo é dissecado em cenas/frames** e **onde ocorre o vídeo→texto**. A resposta curta, para você já ter o mapa: a "dissecação" acontece em **duas granularidades diferentes**, em **dois momentos distintos** do pipeline, e é fácil confundi-las. Este relatório separa as duas com precisão (§0), depois percorre a cadeia (§§1–5).
>
> **Rigor.** Toda afirmação foi conferida contra o código do repositório executando a leitura arquivo por arquivo. Onde há uma sutileza ou um ponto que engana, ele está marcado.

---

## 0. A distinção que você PRECISA fixar antes de tudo

A palavra "dissecação" pode significar duas coisas no RefCap, e elas acontecem em **camadas e momentos diferentes**. Confundi-las é o erro nº 1.

**O foco deste relatório (conforme o seu esclarecimento):** o **mecanismo de FATIAMENTO** — em quais intervalos cada vídeo é cortado, qual frame de cada fatia é usado, e como cada fatia é processada até o vídeo→texto. Esse mecanismo é a "Dissecação TEMPORAL" da tabela abaixo, detalhado com precisão nas Camadas 4 e 5 (§§4–5).

| | **Fatiamento TEMPORAL (o foco)** | **Segmentação em EVENTOS/CENAS** |
|---|---|---|
| **O que faz** | Corta o vídeo em **fatias de 1 segundo**, usando **1 frame de cada** | Agrupa segundos em **eventos** (trechos coerentes) |
| **Intervalo de cada fatia** | `[i, i+1)` segundos, para `i = 0,1,2,...` | vários segundos por evento |
| **Frame usado por fatia** | **o PRIMEIRO** (instante `i.0s`) | — |
| **Onde** | `VideoDatasetPerSec` (`viddataset.py:47-59`) | QM-Gen (`QMPropGener.py`) |
| **Quando** | **Etapa 1** do `construct()` (captioning) | **Etapa 6** do `construct()` (proposals) |
| **Produz** | Uma imagem PIL por segundo (o 1º frame) | Fronteiras `[início, fim]` de cada cena |

> **O ponto crucial para a sua pergunta:** o **vídeo→texto (BLIP)** acontece na **dissecação temporal (Etapa 1)** — cada frame de 1 segundo vira uma legenda. A **segmentação em cenas (Etapa 6)** vem **muito depois** e opera sobre o *texto já gerado*, não sobre pixels. Ou seja: **o BLIP legenda frames individuais; as "cenas" são costuradas a partir das legendas, não do vídeo.**
>
> Este relatório foca na rota que você pediu: **do `construct.py` até o vídeo→texto (Etapas 0 e 1)**. A segmentação em cenas (Etapa 6) é um assunto separado, que toca o texto — mencionamos onde ela entra, mas o coração do "vídeo→texto" está nas Camadas 3 e 4 abaixo.

---

## 1. CAMADA 1 — O ponto de entrada: `construct.py::main`

**Arquivo:** `construct.py` (o que você anexou).

O `main()` faz cinco coisas, em ordem. Vamos ao que importa para a dissecação:

### Linhas 1–3 — Configuração de ambiente (antes de qualquer import)
```python
os.environ["TOKENIZERS_PARALLELISM"] = "false"   # silencia aviso do tokenizer
os.environ["CUDA_VISIBLE_DEVICES"] = '0'          # FORÇA a GPU 0
```
**O que faz / por quê:** roda **antes dos imports**, porque variáveis de ambiente precisam estar setadas antes de o PyTorch/CUDA inicializar. A linha 3 fixa a GPU 0 — é a mesma linha que, quando importada por outro script, causa efeito colateral (foi o que corrigimos no `retrieve_service.py`).

### Linhas 29–30 — Parse da configuração
```python
parser = HfArgumentParser(BuildArguments)
cfg = parser.parse_args_into_dataclasses(look_for_args_file=False)[0]
```
**O que faz:** transforma os argumentos do `construct.sh` num objeto `cfg` (dataclass `BuildArguments`, definida em `config/cfg.py`). É de `cfg` que sairão os parâmetros da dissecação — em especial `cfg.frame_resolution` (=384, `cfg.py:55`).

### Linha 42 — Carregamento dos modelos
```python
pretrained_models = load_pretrained_models(cfg)
```
**O que faz:** carrega o BLIP de captioning (`cap_gen_model` + `cap_gen_processor`), o BLIP-ITM, o sentence-transformer e o GloVe. **O `cap_gen_model` é o modelo que fará o vídeo→texto** — ele nasce aqui.

### Linhas 43 + 47 — Montagem do gerador de legendas e do pipeline
```python
caption_generator = get_capgen_class(cfg.caption_generator)(cfg, pretrained_models)   # ← "blip" ou "minigpt"
...
construct_pipeline = get_constructpipe_class(cfg.construct_pipeline)(cfg, caption_generator, ...)
```
**O que faz:** `get_capgen_class("blip")` resolve, via *registry*, a classe `CapGeneratorBLIP`. **É esta a instância que dissecará os vídeos e chamará o BLIP.** Ela é injetada no pipeline de construção.

### Linha 49 — O disparo
```python
construct_pipeline.construct()
```
**O que faz:** entra no orquestrador (Camada 2). **A partir daqui, a dissecação começa.**

> ✅ **Confirme abrindo:** `construct.py` linhas 29–49; `config/cfg.py` linha 55 (`frame_resolution=384`).

---

## 2. CAMADA 2 — O orquestrador: `constructpipe/base.py::construct`

**Arquivo:** `pipeline/constructpipe/base.py`, linhas 67–90.

O `construct()` encadeia 7 etapas. **A dissecação e o vídeo→texto são a PRIMEIRA:**

```python
def construct(self):
    print("Generating captions...")
    captions = self.caption_generator(vid_list=self.vid_list)   # ← ★ ETAPA 1: vídeo→texto
    ...                                                          #   (as outras 6 etapas vêm depois)
```

**O que faz / por quê:** a Etapa 1 (`self.caption_generator(...)`, linha 69) é a única que **toca o vídeo em pixels**. Todas as etapas seguintes (features, scores, denoising, segmentação) operam sobre o **texto** que esta etapa produz. **Por isso ela vem primeiro: nada existe sem as legendas.**

- `self.caption_generator` é a instância de `CapGeneratorBLIP` (montada na Camada 1).
- `self.vid_list` é a lista de vídeos a processar (montada no `__init__`, `base.py:44-46`, via `os.listdir` + `select_videos`).

**Onde a segmentação em cenas entra (para você localizar, mas NÃO é o foco):** a Etapa 6 (`base.py:87`, `self.proposal_generator(...)`) é a QM-Gen — ela costura as legendas em eventos. Opera sobre texto, não vídeo.

> ✅ **Confirme abrindo:** `constructpipe/base.py` linha 69 (a chamada) e linhas 44–46 (de onde vem `vid_list`).

---

## 3. CAMADA 3 — A iteração por vídeo: `capgenerator/base.py::__call__`

**Arquivo:** `pipeline/capgenerator/base.py`, linhas 39–48.

A chamada `self.caption_generator(vid_list=...)` cai no `__call__` da classe base (herdada por `CapGeneratorBLIP`):

```python
def __call__(self, vid_list):
    for vid in tqdm(vid_list, total=len(vid_list)):        # ← loop VÍDEO A VÍDEO
        video_name = vid.split('.')[0]                     # "vidA.mp4" → "vidA"
        video_path = os.path.join(self.cfg.video_root, vid)
        print(f"\r{vid}", end="")
        if not os.path.isfile(video_path):                 # guarda: pula arquivo inexistente
            print("video not exists!")
            continue
        self.generate_caption(video_name=video_name, video_path=video_path)   # ← ★ por vídeo
    return self.captions
```

**O que faz / por quê, linha a linha:**
- **Linha 40** (`for vid in tqdm(...)`): itera **um vídeo por vez** (serial). O `tqdm` só desenha a barra de progresso.
- **Linha 41** (`vid.split('.')[0]`): extrai o **nome-base** (sem extensão). É a regra que gera o `vid_name` — a mesma que o nosso `make_annos.py` replica, e a razão da regra "nomes-base únicos".
- **Linha 44** (`if not os.path.isfile`): robustez — se o arquivo sumiu, pula sem quebrar.
- **Linha 47** (`self.generate_caption(...)`): delega o trabalho pesado. **Como `self` é uma instância de `CapGeneratorBLIP`, esta chamada vai para o `generate_caption` da subclasse BLIP (Camada 4) — não para o da base.**

> **Sutileza importante (polimorfismo):** o `generate_caption` da *base* (linhas 50–51) é **abstrato** — só faz `assert video_name in self.already_video_names` (é o caminho do MiniGPT, que exige legendas pré-geradas). O `generate_caption` **real** está sobrescrito na subclasse BLIP. É o mecanismo de herança do Python que roteia a chamada para a versão certa. **Se você abrir só a base, verá o `generate_caption` vazio e se confundirá — o de verdade está no BlipCapGener.**

> ✅ **Confirme abrindo:** `capgenerator/base.py` linhas 39–51 (note o `generate_caption` abstrato da base).

---

## 4. CAMADA 4 — O coração: `capgenerator/BlipCapGener.py::generate_caption`

**Arquivo:** `pipeline/capgenerator/BlipCapGener.py`, linhas 17–42.

**Este é o método onde a dissecação temporal e o vídeo→texto acontecem.** Vamos linha a linha, porque é o núcleo da sua análise.

```python
def generate_caption(self, video_name, video_path):
    if video_name in self.already_video_names:            # [1] cache incremental
        return

    dataset_pervideo = VideoDatasetPerSec(video_path, self.cfg.frame_resolution)   # [2] ★ DISSECAÇÃO
    duration = dataset_pervideo.duration                  # [3] duração (do vídeo, via ffprobe)
    if len(dataset_pervideo.frames.shape) != 4:           # [4] guarda: vídeo corrompido
        return
    res = {'vid_name': video_name, 'frame_captions': {}, 'duration': duration}   # [5] estrutura de saída

    for id, frame in tqdm(enumerate(dataset_pervideo), total=len(dataset_pervideo)):   # [6] ★ loop por FRAME
        image_pil = Image.fromarray(frame)                # [7] numpy → PIL Image
        text = "a photo of"                               # [8] prompt-semente do BLIP
        cap_inputs = self.cap_processor(image_pil, text, return_tensors="pt").to(self.cfg.device)   # [9] pré-processa
        out = self.cap_model.generate(**cap_inputs)       # [10] ★★★ VÍDEO→TEXTO (o forward pass do BLIP)
        cap = self.cap_processor.decode(out[0], skip_special_token=True)   # [11] tokens → string
        cap = cap.replace(" [SEP]", ".")                  # [12] limpeza
        cap = cap.replace("a photo of ", "")              # [13] remove o prompt-semente
        res['frame_captions'][id] = {"cap": cap.lower()}  # [14] armazena a legenda do frame

    with open(self.captions_save_file, "a+") as f:        # [15] persiste em disco (append)
        res_s = json.dumps(res)
        f.writelines(f"{res_s}\n")
    self.captions.append(res)                             # [16] guarda em memória
    self.already_video_names.add(video_name)              # [17] marca como processado
```

### Explicação de cada instrução (funcionalidade + motivo)

**[1] `if video_name in self.already_video_names: return`** — **Cache incremental.** Se este vídeo já foi legendado numa rodada anterior (carregado do `.jsonl` no `__init__`, `base.py:33-34`), pula. *Motivo:* legendar é caro; não refazer o que já existe. É o que torna "adicionar vídeos" barato.

**[2] `VideoDatasetPerSec(video_path, self.cfg.frame_resolution)`** — **★ A DISSECAÇÃO TEMPORAL.** Instanciar esta classe **decodifica o vídeo inteiro em frames de 1 por segundo** (detalhado na Camada 5). `self.cfg.frame_resolution` (=384) define o tamanho da imagem. *Motivo:* o BLIP precisa de imagens estáticas; o vídeo precisa virar uma sequência de frames antes de qualquer legenda.

**[3] `duration = dataset_pervideo.duration`** — pega a duração **medida do próprio vídeo** (via `ffprobe`, na Camada 5). *Motivo:* será gravada na saída e usada mais tarde para converter índices de frame em segundos. (É o `duration` REAL — não o do `annos/`, que é inerte, como estabelecemos antes.)

**[4] `if len(dataset_pervideo.frames.shape) != 4: return`** — **Guarda de robustez.** Um vídeo bem decodificado produz um tensor 4D `[N_frames, H, W, 3]`. Se a decodificação falhou (ffprobe quebrou → retornou `torch.zeros(1)`, shape 1D), este teste pula o vídeo. *Motivo:* impede que um vídeo corrompido derrube todo o processo. **É a rede de proteção que torna o try/except do adapter desnecessário.**

**[5] `res = {'vid_name':..., 'frame_captions': {}, 'duration':...}`** — **A estrutura de saída por vídeo.** Um dicionário que acumulará a legenda de cada frame. *Motivo:* é o formato que todas as etapas seguintes consomem (`frame_captions` é um dict `{id_do_frame: {"cap": texto}}`).

**[6] `for id, frame in tqdm(enumerate(dataset_pervideo), ...)`** — **★ O loop por FATIA.** Itera sobre as fatias já extraídas (o `__getitem__` da Camada 5 devolve o frame **único** de cada fatia — o primeiro frame de cada janela de 1s). `id` é o índice temporal da fatia (0, 1, 2, ... = os segundos `0.0s, 1.0s, 2.0s, ...`). *Motivo:* cada fatia (representada pelo seu primeiro frame) será legendada individualmente. **Granularidade: 1 legenda por segundo, cada uma vinda do primeiro frame daquele segundo.**

**[7] `image_pil = Image.fromarray(frame)`** — converte o array NumPy (RGB) para um objeto `PIL.Image`. *Motivo:* o processador do BLIP espera uma `PIL.Image`, não um array cru.

**[8] `text = "a photo of"`** — **O prompt-semente.** O BLIP-captioning é *condicional*: recebe uma imagem **e** um texto inicial, e continua o texto. *Motivo:* "a photo of" é um prefixo neutro que induz o modelo a descrever a imagem (padrão do BLIP). Será removido depois ([13]).

**[9] `cap_inputs = self.cap_processor(image_pil, text, return_tensors="pt").to(device)`** — **Pré-processamento.** O processador do BLIP: (a) redimensiona/normaliza a imagem em um tensor, (b) tokeniza o texto-semente, (c) empacota tudo em tensores PyTorch (`return_tensors="pt"`) e move para a GPU. *Motivo:* transformar imagem+texto no formato exato que o modelo consome.

**[10] `out = self.cap_model.generate(**cap_inputs)`** — **★★★ O MOMENTO EXATO DO VÍDEO→TEXTO.** Esta é a linha que você procurava. `self.cap_model` é o `blip-image-captioning-large`. O `.generate(...)` executa o **forward pass autorregressivo**: o encoder visual do BLIP transforma a imagem em embeddings, e o decoder de linguagem **gera tokens de texto** condicionados nesses embeddings, um a um, até o token de fim. **É aqui que o pixel vira linguagem.** `out` é uma sequência de IDs de token. *Motivo:* é a função-núcleo do sistema inteiro — a conversão de modalidade que o artigo do RefCap propõe como base.

**[11] `cap = self.cap_processor.decode(out[0], skip_special_token=True)`** — **Detokenização.** Converte os IDs de token de volta para uma string legível. `out[0]` é a primeira (e única) sequência gerada; `skip_special_token` remove marcadores como `[CLS]`. *Motivo:* transformar a saída numérica do modelo em texto.

**[12] `cap = cap.replace(" [SEP]", ".")`** — **Limpeza.** Substitui o token separador `[SEP]` por um ponto final. *Motivo:* o BLIP às vezes deixa `[SEP]` na saída decodificada; troca-se por pontuação natural.

**[13] `cap = cap.replace("a photo of ", "")`** — **Remove o prompt-semente.** Como o texto começou com "a photo of" ([8]), o modelo o repete no início da legenda; aqui ele é removido. *Motivo:* a legenda final deve descrever o conteúdo ("a man opening a door"), não o prefixo técnico.

**[14] `res['frame_captions'][id] = {"cap": cap.lower()}`** — **Armazena.** Guarda a legenda (em minúsculas) no dicionário, indexada pelo `id` do frame (= o segundo). *Motivo:* `.lower()` normaliza o texto (consistência para as etapas seguintes de similaridade); o `id` preserva a **posição temporal**, essencial para a segmentação posterior.

**[15] `with open(self.captions_save_file, "a+") as f: ... f.writelines(...)`** — **Persistência em disco.** Anexa (`"a+"`) o resultado deste vídeo ao arquivo `meta/captions/{collection}_{gen}.jsonl`, uma linha JSON por vídeo. *Motivo:* é o **cache**. Se o processo cair ou você adicionar vídeos, o que já foi feito não se perde. O modo *append* é o que permite a incrementalidade.

**[16] `self.captions.append(res)`** — guarda o resultado também em memória, para retorná-lo ao `construct()`. *Motivo:* as etapas seguintes recebem as legendas via valor de retorno, não relendo o disco.

**[17] `self.already_video_names.add(video_name)`** — marca o vídeo como processado. *Motivo:* alimenta o cache incremental ([1]) — na próxima vez, este vídeo é pulado.

> ✅ **Confirme abrindo:** `BlipCapGener.py` linhas 17–42. A **linha 30** é o vídeo→texto. A **linha 21** dispara a dissecação.

> **Nota sobre "cenas":** repare que **não há detecção de cena aqui**. O BLIP legenda cada segundo independentemente. A noção de "cena/evento" só nasce na Etapa 6 (QM-Gen), que agrupa segundos com legendas semelhantes. **A dissecação em Camada 4 é puramente temporal (por segundo), não semântica.**

---

## 5. CAMADA 5 — A dissecação temporal em detalhe: `dataset/viddataset.py`

**Arquivo:** `dataset/viddataset.py`, a classe `VideoDatasetPerSec`.

Esta é a peça que **transforma o vídeo em frames**. Instanciá-la (Camada 4, [2]) dispara `__init__ → _get_video_frames`. Vamos ao método central:

### `__init__` (linhas 11–13)
```python
def __init__(self, video_path, size=384):
    self.size = size
    self.frames = self._get_video_frames(video_path)   # ← decodifica NA CONSTRUÇÃO do objeto
```
**O que faz / por quê:** a decodificação acontece **no construtor** — ao criar o objeto, o vídeo inteiro já é fatiado em frames e guardado em `self.frames`. *Motivo:* deixar os frames prontos para o loop do BLIP iterar. `size=384` é a resolução alvo.

### `_get_video_dim` (linhas 18–26) — medir o vídeo
```python
probe = ffmpeg.probe(video_path)                       # lê metadados via ffprobe
video_stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
width  = int(video_stream['width'])
height = int(video_stream['height'])
duration = float(video_stream['duration'])             # ← a DURAÇÃO real do vídeo
self.duration = duration
return height, width, duration
```
**O que faz / por quê:** usa o `ffprobe` (parte do ffmpeg) para ler **largura, altura e duração** do vídeo **sem decodificá-lo inteiro**. *Motivo:* a duração determina **quantos frames** serão extraídos (1 por segundo); as dimensões, o redimensionamento. **Esta é a fonte do `duration` que percorre todo o pipeline** — do vídeo, não do `annos/`.

### `_get_video_frames` (linhas 36–67) — ★ A DISSECAÇÃO TEMPORAL PROPRIAMENTE DITA
```python
try:
    h, w, duration = self._get_video_dim(video_path)   # mede o vídeo
except Exception as e:
    print(e); print('ffprobe failed at: ...')
    return torch.zeros(1)                               # ← falha → tensor 1D (pego pela guarda [4])

height, width = self._get_output_dim(h, w)             # calcula a resolução de saída
frames = []
for i in range(int(duration)):                         # ← ★ 1 ITERAÇÃO POR SEGUNDO
    cmd = (
        ffmpeg
        .input(video_path, ss=i, t=1)                  # ← ★ extrai 1s começando no segundo i
        .filter('scale', width, height)                # redimensiona
    )
    out, _ = (
        cmd.output('pipe:', format='rawvideo', pix_fmt='rgb24')   # saída crua RGB
        .run(capture_stdout=True, quiet=True)          # executa o ffmpeg
    )
    img = Image.frombytes('RGB', (width, height), out) # bytes → imagem
    img_np = np.array(img)                             # imagem → array NumPy
    frames.append(img_np)                             # acumula
video = np.stack(frames, axis=0)                       # → array [N_frames, H, W, 3]
return video
```

**Explicação das instruções decisivas:**

- **Linha 39–44 (`try/except`)** — **A rede de proteção contra vídeos corrompidos.** Se o `ffprobe` falhar, retorna `torch.zeros(1)` (um tensor 1D). *Motivo:* isso é detectado pela guarda [4] da Camada 4 (`len(shape) != 4`), que pula o vídeo. **É por isso que dizemos que o pipeline já trata corrupção — a proteção está exatamente aqui.**

- **Linha 47 (`for i in range(int(duration))`)** — **★ A REGRA DE FATIAMENTO: UMA FATIA POR SEGUNDO.** O loop roda `int(duration)` vezes — `i = 0, 1, 2, ..., D-1`. Cada iteração `i` produz **uma fatia**, cujo intervalo é `[i, i+1)` segundos (definido pelo `ss=i, t=1` da linha 50). *Motivo/consequência:* um vídeo de 55s gera **55 fatias → 55 frames selecionados → 55 legendas**. **Esta é a granularidade temporal do sistema inteiro** (o paper chama de "1 fps"). Como cada fatia contribui com **apenas o seu primeiro frame** (linha 57), o vídeo é efetivamente amostrado nos instantes `0.0s, 1.0s, 2.0s, ...`. Se há uma cena rápida entre dois desses instantes (ex.: algo que dura de 1.2s a 1.8s), ela pode ser **perdida** — limitação estrutural direta desse esquema de fatiamento.

- **Linha 50 (`.input(video_path, ss=i, t=1)`)** — **★ O CORTE TEMPORAL — e aqui há uma sutileza que verifiquei empiricamente.** `ss=i` é um *seek* (posiciona a leitura no segundo `i`); `t=1` define **1 segundo de duração** a ser lido. **O ponto crucial:** `t=1` **não** significa "1 frame" — significa "1 segundo de vídeo". Num vídeo a 25 fps, isso faz o ffmpeg **decodificar ~25 frames** e despejá-los todos no buffer `out` (bytes RGB crus concatenados). **É a linha seguinte que seleciona 1 único frame** — ver linha 57. *Motivo do design:* `ss/t` é um recorte de intervalo temporal padrão do ffmpeg; a intenção era pegar "o começo de cada segundo", mas a forma como foi escrita decodifica o segundo inteiro e descarta quase tudo (ver §8, ponto de eficiência).

- **Linha 51 (`.filter('scale', width, height)`)** — redimensiona para a resolução calculada. *Motivo:* padronizar o tamanho para o BLIP e reduzir custo.

- **Linhas 53–56 (`.output('pipe:', format='rawvideo', pix_fmt='rgb24').run(...)`)** — executa o ffmpeg e captura os **bytes crus RGB** direto na memória (via `pipe:`), sem salvar arquivo temporário. *Motivo:* eficiência — evita I/O de disco por frame.

- **Linha 57 (`Image.frombytes('RGB', (width, height), out)`)** — **★★ AQUI 1 FRAME É SELECIONADO DE FATO (o ponto que engana).** `out` contém **todos os ~25 frames** do segundo (linha 50). Mas `Image.frombytes('RGB', (width, height), out)` lê **apenas `width × height × 3` bytes** — ou seja, **exatamente 1 frame**. Os bytes restantes (os outros ~24 frames) são **silenciosamente ignorados**. **Provei isto numericamente:** um buffer com 3 frames de 2×2 (36 bytes) passado a `Image.frombytes` com dimensões 2×2 consome só 12 bytes e retorna **apenas o primeiro frame**; o resto do buffer é descartado. **Consequência:** o frame amostrado é **o PRIMEIRO frame de cada janela de 1 segundo** (o instante `i.000s`), não um frame "representativo" nem o do meio. *Motivo (provável):* `Image.frombytes` por contrato consome só os bytes necessários para uma imagem do tamanho pedido — o autor extraiu 1 frame por segundo aproveitando esse comportamento, mas ao custo de decodificar o segundo inteiro à toa.

- **Linha 60 (`np.stack(frames, axis=0)`)** — empilha todos os frames num único array `[N_frames, H, W, 3]` (o tensor **4D** que a guarda [4] verifica). *Motivo:* formato uniforme para iteração.

### `__getitem__` (linhas 69–70) — a entrega ao loop
```python
def __getitem__(self, idx):
    return self.frames[idx]
```
**O que faz / por quê:** devolve o frame de índice `idx`. É isto que o `enumerate(dataset_pervideo)` da Camada 4 ([6]) consome — cada iteração pega um frame já decodificado. *Motivo:* interface padrão de `Dataset` do PyTorch, permitindo o loop limpo no BLIP.

> ✅ **Confirme abrindo:** `viddataset.py` linhas 47–60 (o loop de amostragem por segundo) e 39–44 (a guarda de corrupção).

---

## 6. O fluxo completo, em um diagrama

```
construct.py::main (L49)
     │  construct_pipeline.construct()
     ▼
constructpipe/base.py::construct (L69)                      ← ETAPA 1 de 7
     │  self.caption_generator(vid_list=...)
     ▼
capgenerator/base.py::__call__ (L40)                        ← loop VÍDEO a vídeo
     │  for vid in vid_list:  self.generate_caption(...)
     ▼
capgenerator/BlipCapGener.py::generate_caption (L21)        ← por vídeo
     │  dataset = VideoDatasetPerSec(video_path, 384)   ─────────┐
     │                                                           │  ★ FATIAMENTO TEMPORAL
     ▼                                                           ▼
     │                              viddataset.py::_get_video_frames (L47)
     │                              for i in range(int(duration)):        ← 1 FATIA por segundo
     │                                  ffmpeg.input(ss=i, t=1)           → decodifica o SEGUNDO
     │                                                                       inteiro (~25 frames)
     │                                  Image.frombytes(RGB,(w,h),out)    → LÊ SÓ O 1º FRAME
     │                                                                       (o resto é descartado)
     │                              → array [N_fatias, H, W, 3] (1 frame/fatia)
     │  ◄──────────────────────────────────────────────────────┘
     │  for id, frame in enumerate(dataset):                 ← loop por FATIA (1º frame de cada s)
     │      image_pil = Image.fromarray(frame)               (L27)
     │      cap_inputs = cap_processor(image_pil, "a photo of")   (L29)
     │      out = cap_model.generate(**cap_inputs)   ★★★ VÍDEO→TEXTO  (L30)
     │      cap = cap_processor.decode(out[0])               (L31)
     │      res['frame_captions'][id] = {"cap": cap}         (L34)
     ▼
  meta/captions/{collection}_{gen}.jsonl                    ← legendas persistidas
     │
     ▼  (as outras 6 etapas: features → scores → denoise → SEGMENTAÇÃO EM CENAS → árvore)
```

---

## 7. Síntese: respostas diretas às suas perguntas

**"Em quais intervalos cada vídeo é fatiado?"**
Em **fatias de 1 segundo, não sobrepostas**: a fatia `i` cobre o intervalo `[i, i+1)` segundos, para `i = 0, 1, 2, ..., int(duration)-1` (`viddataset.py:47`, `ss=i, t=1`). Um vídeo de 55.9s → 55 fatias (a fração final, `.9s`, é truncada pelo `int`).

**"Qual frame de cada fatia é usado, e como cada fatia é processada?"**
De cada fatia usa-se **apenas o primeiro frame** (o instante `i.0s`). O mecanismo exato, verificado: o `ffmpeg.input(ss=i, t=1)` decodifica o **segundo inteiro** (~25 frames a 25 fps) para o buffer `out`; em seguida, `Image.frombytes('RGB',(w,h),out)` (`viddataset.py:57`) lê **só `w×h×3` bytes = 1 frame**, descartando o resto. Esse frame único vira `PIL.Image` (`BlipCapGener.py:27`), é pré-processado com o prompt `"a photo of"` (L29) e enviado ao BLIP (L30). A cadeia por fatia: `frame → PIL → cap_processor → cap_model.generate → decode → legenda`.

**"Onde ocorre o vídeo→texto (BLIP)?"**
Na **linha 30 de `BlipCapGener.py`**: `out = self.cap_model.generate(**cap_inputs)`. A rota completa: `construct.py:49 → base.py:69 → capgenerator/base.py:40 → BlipCapGener.py:21 (dispara o fatiamento) → viddataset.py:47-59 (fatiamento) → BlipCapGener.py:30 (vídeo→texto)`.

**A percepção-chave sobre o fatiamento (a mais fácil de errar):** o vídeo é amostrado nos instantes `0.0s, 1.0s, 2.0s, ...` — **um frame no início de cada janela de 1 segundo**, não um frame "representativo" nem o do meio. E o BLIP legenda cada uma dessas fatias **de forma independente**; ele não "vê cenas". As cenas/eventos só são costurados *depois* (Etapa 6), a partir da semelhança entre as legendas de segundos consecutivos. Portanto: **o fatiamento é temporal e uniforme (1 Hz), pegando o primeiro frame de cada segundo; a estrutura de cenas é construída sobre o texto, não sobre o vídeo.**

---

## 8. Pontos de atenção verificados (para a sua análise aprofundada)

1. **O fatiamento é 1 fatia/segundo, fixo e não configurável** (`viddataset.py:47`, `range(int(duration))`). Não há parâmetro para mudar a taxa. O vídeo é amostrado em `0.0s, 1.0s, 2.0s, ...`; eventos entre esses instantes podem ser perdidos. É uma decisão de design com impacto direto na granularidade do sistema.
2. **Cada fatia usa só o PRIMEIRO frame do segundo** (`viddataset.py:57`, `Image.frombytes` lê 1 frame do buffer). Não é o frame do meio nem um "keyframe representativo" — é literalmente o primeiro. Se o primeiro frame de um segundo for atípico (transição, corte, borrão de movimento), a legenda daquele segundo inteiro será enviesada por ele.
3. **⚠️ Ineficiência de decodificação (verificada):** o `ffmpeg.input(ss=i, t=1)` (`viddataset.py:50`) **decodifica o segundo inteiro** (~25 frames a 25 fps) para depois usar **1 só**. Os outros ~24 são trabalho jogado fora. Um `fps=1` ou `-frames:v 1` no ffmpeg pegaria 1 frame diretamente, muito mais rápido. Para corpora grandes, isso multiplica o custo de construção sem benefício.
4. **O `int(duration)` trunca.** Um vídeo de 55.9s gera 55 fatias — a fração final (`.9s`) é descartada. Impacto pequeno, mas real.
5. **O `ss` é *input seek* (antes do `-i`).** É rápido, mas em alguns contêineres/codecs pode alinhar ao keyframe mais próximo em vez do timestamp exato `i.0s`, introduzindo uma pequena imprecisão no instante amostrado. Não afeta a contagem de fatias, só *qual* frame exato é pego.
6. **O prompt "a photo of" é fixo** (`BlipCapGener.py:28`). Toda fatia é legendada com o mesmo prefixo. Trocá-lo mudaria o estilo das legendas (e, portanto, todo o resto do pipeline).
7. **O `generate_caption` da base é abstrato** (`base.py:50-51`) — o polimorfismo roteia para a versão BLIP. Ao ler, não confunda a base com a implementação real.
8. **O caminho MiniGPT é externo** — para `caption_generator=minigpt`, as legendas precisam existir *antes* (geradas por script externo); o pipeline apenas as carrega. O fatiamento+captioning descrito aqui é o do **BLIP**.
9. **A decodificação é fatia-a-fatia via subprocessos ffmpeg** (`viddataset.py:48-56`) — um `ffmpeg.run()` por segundo de vídeo. Combinado com o ponto 3, para vídeos longos e muitos vídeos este é um custo de I/O significativo (e sequencial).

---

*Próximo passo natural:* quando você quiser aprofundar um ponto específico — por exemplo, o que exatamente o `.generate()` do BLIP faz por dentro (o mecanismo autorregressivo), ou por que a amostragem 1 fps foi escolhida e suas alternativas — é só apontar o trecho, que eu disseco na profundidade que você pedir. E, se for útil, posso preparar um scratchpad que **instrumenta** a Camada 4/5 (contando frames extraídos e medindo o tempo de decodificação vs. o tempo do BLIP) sobre um vídeo real seu.
