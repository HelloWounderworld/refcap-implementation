# construct.py + make_annos.py — Manual Operacional (How To Use)
## Rodar a construção do índice RefCap sobre os SEUS vídeos brutos, sem tocar no núcleo

---

> **O que é este documento.** O passo a passo para executar o estágio de **construção** do RefCap usando o adapter `make_annos.py` que criamos — do diretório de vídeos brutos até a `tree.json` (o índice que a recuperação consumirá). Cobre pré-requisitos, o fluxo integrado, o que é produzido, atualização incremental, e — em destaque — as armadilhas que causam falha imediata ou erro silencioso.
>
> **Escopo.** Só a **construção**. A recuperação (alimentar prompts do usuário) é uma etapa separada, tratada depois.
>
> **Estado.** O adapter foi construído e **testado em execução**: o `select_videos` real do RefCap consome o `vcmr.jsonl` gerado, sem uma linha modificada no núcleo.

---

## 1. Visão geral do fluxo integrado

```
   [ SEU diretório de vídeos brutos ]
              │
              ▼  PASSO 1 — make_annos.py  (lista os vídeos, escreve o catálogo)
   annos/{collection}/vcmr.jsonl        (só `vid_name` é real; resto é placeholder)
              │
              ▼  PASSO 2 — construct.py   (núcleo do RefCap, INTOCADO)
   [1] captioning (BLIP) → [2] features → [3] scores → [4] denoise (SWi-Den)
   → [5] recomputa scores → [6] segmentação (QM-Gen) → [7] árvore
              │
              ▼
   results/construct/{collection}/{construct_name}/tree.json   ◄── O ÍNDICE
```

O `collection` é a **chave que costura tudo**: você o define uma vez, o adapter cria `annos/{collection}/`, e o `construct.py` lê de lá e chaveia o cache `meta/` por ele. **Definir o mesmo `collection` nas duas etapas é o que faz o sistema funcionar.**

---

## 2. Pré-requisitos (o que precisa estar pronto ANTES)

Rode este checklist antes da primeira execução — cada item ausente causa falha.

| Pré-requisito | Como obter | Falha se ausente |
|---|---|---|
| Ambiente conda (`refcap-test`) + `requirements.txt` | `conda create -n refcap-test python=3.10 && pip install -r requirements.txt` | Import quebra |
| Modelo spaCy | `python -m spacy download en_core_web_sm` | QM-Gen (keywords) quebra |
| **ffmpeg (binário do sistema)** | `apt-get install ffmpeg` / `brew install ffmpeg` | Captioning quebra (amostragem de frames) |
| **GloVe 300d (~1GB)** em `meta/glove.6B/glove.6B.300d.txt` | [Glove](https://github.com/stanfordnlp/GloVe) | **Construção quebra no load de modelos** (ver §7.1) |
| `make_annos.py` na raiz do repo | (já criado) | Adapter não roda |
| Vídeos brutos num diretório | seu corpus | Adapter aborta ("nenhum vídeo") |

> **Nota sobre modelos HF (BLIP, sentence-transformer):** são baixados automaticamente na 1ª execução (ou aponte para caminhos locais nos parâmetros `caption_model`/`blip_itm_model`). Exigem rede na primeira vez.

---

## 3. Passo a passo

### Passo 0 — Preparar os vídeos brutos

Coloque os vídeos num diretório (não-recursivo). Extensões reconhecidas pelo adapter: `.mp4 .mkv .avi .mov .webm .m4v .mpg .mpeg .wmv .flv`.

> **⚠️ A REGRA INVARIÁVEL — nomes únicos e imutáveis por conteúdo.** O RefCap identifica cada vídeo pelo **nome-base** (o nome sem extensão). Duas consequências obrigatórias:
> - **Nomes-base devem ser únicos.** `vidA.mp4` + `vidA.mkv` colapsam no mesmo `vid_name` — o adapter **aborta** nesse caso (proteção que testamos).
> - **Se o conteúdo de um vídeo mudar, o NOME deve mudar** (ex.: `vidA_v2.mp4`). Manter o nome e trocar o conteúdo faz o pipeline servir legendas **obsoletas silenciosamente** (§7.2). Este é o gargalo residual que exige disciplina de processo.

### Passo 1 — Gerar o `vcmr.jsonl` (o adapter)

```bash
python make_annos.py --collection meu_corpus --video_root /dir/para/seus/videos
```

O que observar:
- **stdout** = uma linha: o caminho do `vcmr.jsonl` gerado (`annos/meu_corpus/vcmr.jsonl`).
- **stderr** = os logs (nº de vídeos, confirmação de escrita).
- O arquivo gerado tem uma linha por vídeo: `{"vid_name": "vidA", "desc_name": "vidA#enc#0", "duration": 0, "ts": [0, 0], "desc": ""}`. Só `vid_name` é real; o resto é placeholder inerte na construção.

Casos de erro (o adapter aborta com exit code 1 e mensagem no stderr): diretório inexistente; nenhum vídeo encontrado; colisão de nome-base.

### Passo 2 — Configurar o construct

Abra `construct_with_adapter.sh` e ajuste **três** coisas:
1. `collection` — o **mesmo** nome do Passo 1.
2. `video_root` — o **mesmo** diretório do Passo 1.
3. `caption_generator` — **`blip`** para a 1ª rodada (autossuficiente). Só use `minigpt` se você já rodou o passo externo (§7.3).

Os hiperparâmetros (`figsim_denoise_thr=0.4`, etc.) são os defaults do paper — deixe como estão por ora (ver a ressalva de calibração em §7.5).

### Passo 3 — Rodar a construção

**Opção recomendada (tudo num script):** o `construct_with_adapter.sh` roda o adapter *e* o construct em sequência, com o `collection` como fonte única de verdade:
```bash
bash construct_with_adapter.sh
```

**Opção manual (dois comandos), se preferir controle:**
```bash
python make_annos.py --collection meu_corpus --video_root /dir/para/videos
bash scripts/construct.sh   # (com collection=meu_corpus e caption_generator=blip lá dentro)
```

> **Expectativa de tempo:** a construção é **pesada**. Ela legenda cada vídeo a 1 frame/segundo com o BLIP — para um corpus grande, são horas e é bom ter GPU. É I/O + inferência sobre todo o corpus. O adapter (Passo 1) é instantâneo; o custo está no Passo 2.

---

## 4. O shellscript integrado (referência)

O `construct_with_adapter.sh` (entregue) é o seu `construct.sh` com o adapter embutido. A parte que importa — como o adapter se encaixa:

```bash
collection=meu_corpus            # ← fonte única de verdade
# ...
# PASSO 1 — adapter (antes do construct):
python make_annos.py --collection "${collection}" --video_root "${video_root}" \
  || { echo "make_annos.py FALHOU" >&2; exit 1; }   # ← checagem de erro obrigatória
# PASSO 2 — construct (mesmo $collection):
python construct.py --collection "$collection" ... (resto igual ao original)
```

Os dois pontos não-óbvios embutidos: **(a)** a checagem `|| exit 1` (o `set -e` não pega falha em atribuição, então a checagem é explícita); **(b)** `caption_generator=blip` como default seguro.

---

## 5. O que é produzido (os artefatos e onde caem)

```
annos/{collection}/vcmr.jsonl                         ← criado pelo adapter (Passo 1)

meta/                                    (CACHE — reaproveitado entre rodadas; ver §6)
├── captions/{collection}_{gen}.jsonl    legendas por frame (o insumo do captioning)
├── framefeatures/{collection}.pt        features visuais BLIP
└── scores/{collection}_{gen}.pt         scores legenda-frame (ITM)

results/construct/{collection}/{construct_name}/       (SAÍDA do experimento)
├── settings.json                        config congelada desta rodada
├── denoised_captions.jsonl              legendas após o refino (SWi-Den)
├── denoised_capframe_scores.pt          scores recomputados
├── prop_sims.pt                         matrizes de similaridade
├── proposals.json                       segmentos + legenda + keywords
└── tree.json                            ◄── O ÍNDICE (insumo da recuperação)
```

**O `tree.json` é o produto final** — é ele que a recuperação carregará. **O `denoised_captions.jsonl` é o seu instrumento de diagnóstico de domínio** (§8): leia-o para ver se o BLIP legendou bem os seus vídeos.

---

## 6. Re-execução e atualização incremental (adicionar vídeos)

Este é o fluxo que a nossa escolha de design otimizou. Para adicionar vídeos:

```
1. Copie os novos vídeos para /dir/para/videos  (nomes NOVOS e únicos!)
2. Rode o adapter de novo (mesmo collection)  → regenera o vcmr.jsonl do zero
                                                  com a lista atual (Opção A)
3. Rode o construct de novo (mesmo collection) → o cache meta/ REAPROVEITA os
                                                  vídeos antigos e processa
                                                  APENAS os novos
```

**Por que funciona (verificado no código):** o cache `meta/` é chaveado por `collection` + `video_name`, e é incremental (`if video_name in already_video_names: return`). Com o `collection` fixo, os vídeos já processados são pulados; só os novos pagam o custo de captioning/features. **A incrementalidade cara vive no cache do pipeline; o `vcmr.jsonl` é só um catálogo barato reescrito por completo a cada rodada.**

- **Remover vídeos:** apague-os da pasta e re-rode o adapter. Eles somem do `vcmr.jsonl` e da árvore. Entradas antigas no cache ficam inertes (inofensivas).
- **⚠️ NÃO faça:** mudar o conteúdo de um vídeo mantendo o nome (§7.2).

---

## 7. As armadilhas a evitar (consolidadas)

### 7.1 GloVe é obrigatório já na construção (falha imediata)
`load_pretrained_models` carrega o GloVe **independente do stage** (`model_utils.py:36`). Mesmo que o GloVe só seja *usado* na recuperação, o arquivo de ~1GB precisa existir em `meta/glove.6B/glove.6B.300d.txt` para a construção rodar. Ausência → crash no carregamento de modelos.

### 7.2 Staleness de conteúdo por nome preservado (erro SILENCIOSO — o mais perigoso)
O cache identifica vídeos por nome de arquivo, não por conteúdo. Modificar/substituir um vídeo mantendo o nome → o pipeline reaproveita legendas antigas **sem erro**. Mitigação: **disciplina de nomes** (conteúdo novo = nome novo). O adapter não detecta isso (nem poderia sem hash de conteúdo, o que exigiria tocar o núcleo).

### 7.3 `caption_generator=minigpt` exige passo externo prévio (falha imediata)
Com `minigpt`, o `cap_gen_model = None` (`model_utils.py:14-17`) — as legendas **precisam** ter sido geradas antes pelo script externo `genCaptions_minigpt.py` no repositório do MiniGPT-4, produzindo `meta/captions/{collection}_minigpt.jsonl`. Sem esse passo, a construção quebra numa asserção (`base.py:51`). **Para a 1ª rodada, use `blip`** (autossuficiente). O `minigpt` é uma otimização avançada (legendas mais ricas → melhor desempenho), não o caminho inicial.

### 7.4 Transcodificação .mkv → .mp4 dentro da construção (I/O pesado, descoberto nos testes)
O `select_videos` (`base.py:199`) **converte arquivos `.mkv` para `.mp4` via ffmpeg** durante a construção — não é só leitura do `annos/`. Implicações: se seu corpus tem `.mkv`, espere I/O de transcodificação (lento) na construção; e arquivos `.mkv` corrompidos/vazios fazem o ffmpeg falhar. (O adapter escreve o `vid_name` sem extensão, então isso é transparente para o catálogo.)

### 7.5 Hiperparâmetros sem protocolo de validação (qualidade, não crash)
Os defaults (`θd=0.4`, `θb=0.2`, `α=0.5`, `W=2s`) foram fixados no paper sem conjunto de validação declarado. Eles podem ser subótimos no seu domínio, e sem rótulos seus não há como re-tunar. Isso não quebra a construção — afeta a *qualidade* do índice. Fica para quando você medir (etapa futura de recuperação).

### 7.6 Escopo: isto é metade da solução
O adapter + construção produzem o índice. A **recuperação** (receber prompts do usuário, ignorar `ts`) é a outra metade, ainda por fazer. O `vcmr.jsonl` com `desc` vazio é esperado — as consultas entram em runtime na recuperação, não vêm do arquivo.

---

## 8. Verificação e troubleshooting

**Confirmar que a construção terminou com sucesso:**
```bash
ls -la results/construct/meu_corpus/blip_window_it/tree.json   # deve existir e ter tamanho > 0
```

**Diagnóstico de domínio (o teste de maior valor — sem custo):**
```bash
head -3 meta/captions/meu_corpus_blip.jsonl    # leia as legendas geradas
```
Se as legendas descrevem fielmente o conteúdo dos seus frames, o método tem chance de funcionar no seu domínio. Se são genéricas/erradas/vazias, o gargalo é o captioning (o BLIP não lida bem com seus vídeos) — e nenhum ajuste posterior recupera isso. **É aqui que o seu domínio "responde sozinho" se a abordagem serve.**

**Erros comuns → causa:**
| Sintoma | Causa provável |
|---|---|
| `AssertionError: You should use external scripts...` | `caption_generator=minigpt` sem o passo externo (§7.3) → use `blip` |
| Crash no load de modelos / `Vectors`/`torchtext` | GloVe ausente (§7.1) ou torchtext incompatível |
| `ffmpeg error` durante a construção | `.mkv` corrompido/vazio, ou ffmpeg não instalado (§7.4) |
| Adapter aborta "nomes-base duplicados" | dois arquivos com mesmo nome-base (§7.2) → renomeie |
| Adapter aborta "nenhum vídeo encontrado" | `video_root` errado ou extensões não reconhecidas |
| `tree.json` não aparece | a construção não terminou — veja o stderr do construct |

---

## 9. Cheatsheet

```bash
# ── PRÉ-REQUISITOS (uma vez) ─────────────────────────────────────────
conda activate refcap-test
python -m spacy download en_core_web_sm
# garantir: ffmpeg instalado; meta/glove.6B/glove.6B.300d.txt presente (~1GB)

# ── FLUXO COMPLETO (integrado) ───────────────────────────────────────
# editar construct_with_adapter.sh: collection, video_root, caption_generator=blip
bash construct_with_adapter.sh

# ── OU manual (dois passos) ──────────────────────────────────────────
python make_annos.py --collection meu_corpus --video_root /dir/videos
bash scripts/construct.sh          # collection=meu_corpus, caption_generator=blip

# ── ADICIONAR VÍDEOS (incremental) ───────────────────────────────────
# copie novos vídeos (nomes NOVOS!) → re-rode o adapter → re-rode o construct
# (o cache meta/ reaproveita os antigos automaticamente)

# ── VERIFICAR ────────────────────────────────────────────────────────
ls -la results/construct/meu_corpus/blip_window_it/tree.json   # o índice
head -3 meta/captions/meu_corpus_blip.jsonl                    # diagnóstico de domínio
```

---

### Regras de ouro (cole na parede)
1. **Mesmo `collection`** no adapter e no construct — é a chave que costura tudo e o cache.
2. **Nomes de vídeo únicos e imutáveis por conteúdo** — conteúdo novo = nome novo.
3. **`blip` na 1ª rodada** — `minigpt` exige passo externo.
4. **GloVe presente** antes de rodar — obrigatório já na construção.
5. **Leia as legendas geradas** — é o seu diagnóstico de domínio, de graça.
6. **O núcleo do RefCap permanece intocado** — toda a adaptação vive no adapter e no `.sh`.
