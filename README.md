# refcap-implementation

Implementação de referência do [RefCap](https://github.com/BUAAPY/RefCap) como **serviço HTTP**, com os modelos residentes em memória e o projeto inteiro confinado num **container Docker com GPU**.

---

## ⚠️ O projeto roda DENTRO de um container

Este não é um projeto que se instala na máquina. Tudo — Python, CUDA, ffmpeg, os modelos, o serviço — vive dentro de um container construído a partir de `.docker/Dockerfile`.

```
  HOST                                    CONTAINER
  ─────────────────────                   ─────────────────────────────
  .docker/docker-compose.yml   ──build──► nvidia/cuda:12.6.1-devel-ubuntu22.04
  ./                           ──mount──► /${USERNAME}
  ../movies/Share              ──mount──► /${USERNAME}/src/movies/Share  (ro)
  ../log/refcap-api            ──mount──► /var/log
                                          │
  localhost:${UI_PORT_PROD}    ──port───► :8000   (uvicorn)
```

**Consequências que valem saber antes de qualquer coisa:**

- **Os caminhos nas requisições são os do CONTAINER**, não os do host. Uma cena em `../movies/Share/prog/vid/c1.mp4` é enviada como `/${USERNAME}/src/movies/Share/prog/vid/c1.mp4`.
- **A porta da URL é a do HOST** (`UI_PORT_PROD`); dentro do container é sempre 8000.
- Um diretório montado no host **depois** de o container subir não aparece nele — é preciso recriar o container.

Subir:
```bash
cd .docker
cp sample-env.txt .env        # e preencha USERNAME, UID, GID, UI_PORT_PROD
docker compose up -d
```

---

## O desenho de diretórios

```
refcap-implementation/
│
├── .docker/                     ★ COMO O CONTAINER É CONSTRUÍDO E SUBIDO
│   ├── Dockerfile                  base CUDA 12.6 + Python + deps
│   ├── docker-compose.yml          GPU, volumes, portas, usuário
│   └── sample-env.txt              modelo do .env (USERNAME, UID, PORT…)
│
├── documents/                   ★ A DOCUMENTAÇÃO DE PROJETO
│   ├── code_analysis/              análise do código original
│   ├── construct_instructions/     como o construct funciona
│   ├── retrieval_instructions/     o lado do retrieve (fora do escopo hoje)
│   ├── enviroment_settings/        preparo do ambiente
│   ├── diagnosis/                  investigações pontuais
│   └── tests/                      notas de teste
│
├── src/                         ★ O CÓDIGO
│   ├── api/                        O SERVIÇO HTTP  ← o que nós construímos
│   ├── config/ dataset/ pipeline/ utils/     O REFCAP (com 5 patches)
│   ├── construct.py                a etapa de construção
│   ├── retrieve.py                 a etapa de busca (fora do escopo)
│   ├── make_annos.py               gera as anotações
│   ├── scripts/                    invocação por linha de comando
│   ├── scratch/                    experimentos e provas pontuais
│   ├── test/                       a suíte pytest
│   └── standalone_eval/            avaliação offline
│
├── supervisord.conf             mantém o serviço vivo e o reinicia
├── requirements.txt             dependências de execução
├── requirements-test.txt        dependências de teste
└── code_analysis.md             notas sobre o código original
```

---

## O papel de cada parte

### `.docker/` — a fronteira do projeto

O `Dockerfile` parte de `nvidia/cuda:12.6.1-devel-ubuntu22.04` e instala o que o RefCap precisa. O `docker-compose.yml` cuida do que o host oferece:

| item | para quê |
|---|---|
| `deploy.resources.devices` | expõe **todas** as GPUs ao container |
| `shm_size: 16gb` | memória compartilhada — os DataLoaders do PyTorch a exigem |
| `user: ${USERNAME}` | roda como usuário não-root, com UID/GID do host |
| `volumes` | as cenas (somente leitura), o projeto, e os logs |
| `ports` | `${UI_PORT_PROD}:8000` |

**[!] O `sample-env.txt` precisa virar `.env`** com o seu `UID`/`GID` — senão os arquivos criados pelo container ficam com dono errado no host.

### `documents/` — por que, não só como

É onde mora o raciocínio: os artigos originais, a análise do código do RefCap, as convenções adotadas, e as investigações que levaram às decisões. Um documento aqui explica **por que** algo é de um jeito; o código mostra **como**.

### `src/api/` — o serviço

O que transformou o RefCap de script em serviço. Detalhado em [`src/api/README.md`](src/api/README.md), mas em resumo:

```
app.py            ciclo de vida: carrega os modelos UMA vez, registra as rotas
estado.py         modelos, fila e config compartilhados (evita import circular)
contratos.py      os modelos Pydantic e os 5 códigos de erro
captioning.py     o pipeline: resolve, agrupa, chama o build, transforma
persistencia.py   o que fica em disco: estado, summary, histórico
carregador.py     os 4 modelos residentes
jobs.py           fila serializada — um job por vez na GPU
ponte_refcap.py   sys.path, caminhos absolutos, guarda contra colisão de nomes
rotas/            caption.py, health.py, diagnostics.py
```

### `src/{config,dataset,pipeline,utils}/` — o RefCap

O upstream, com **5 patches**. Sem eles o serviço não funciona:

| arquivo | mudança | por quê |
|---|---|---|
| `construct.py` | `build(cfg, pretrained_models)` extraído | permite passar os modelos já carregados |
| `dataset/viddataset.py` | `max(1, int(duration))` | vídeo < 1 s daria 0 frames e derrubaria o processo |
| `config/cfg.py` | `"whole"` nos choices | habilita o gerador próprio |
| `pipeline/propgenerator/__init__.py` | registro | idem |
| `pipeline/propgenerator/WholePropGener.py` | **novo** | o gerador de propostas deste projeto |

O `pipeline/` tem seis módulos, um por etapa: `capgenerator`, `constructpipe`, `denoiser`, `propgenerator`, `treebuilder`, `retrievepipe`.

### `src/scripts/` e `src/scratch/`

`scripts/` são os invocadores originais por linha de comando — úteis para rodar o RefCap fora do serviço. `scratch/` guarda experimentos que provaram algo pontual (por exemplo, `scratch_prove_no_annos.py`).

### `supervisord.conf` — manter vivo

Sobe o `uvicorn` e o reinicia se cair. **Três armadilhas** que já custaram tempo neste projeto:

- o **venv não é herdado** — o `command=` precisa do caminho **absoluto** do uvicorn;
- o `startsecs` **não** é limite de carregamento; ele mede quanto o processo precisa ficar vivo para o start contar como bem-sucedido;
- **nunca use `--reload`** — ele recria o processo a cada mudança de arquivo, recarregando os modelos e anulando o estado permanente.

---

## O fluxo de uma requisição

```
POST /caption                                    (porta do HOST)
  │
  ├─ rotas/caption.py      valida o contrato, decide sync ou async
  ├─ jobs.py               entra na fila (um por vez)
  ├─ captioning.py         resolve o caminho, agrupa por diretório
  │     └─ ponte_refcap    monta o cfg: collection = program_id
  │           └─ construct.build(cfg, modelos)      ← RefCap, 7 etapas
  │                 usa os modelos JÁ carregados
  ├─ captioning.py         funde o proposals, monta o contrato
  ├─ persistencia.py       grava estado, summary e histórico
  └─ resposta HTTP
```

---

## Onde os dados ficam (dentro do container)

```
src/
├── annos/{program_id}/vcmr.jsonl     o SELETOR da requisição — sobrescrito
├── meta/                              ★ O CACHE — perdê-lo custa horas
│   ├── captions/{program_id}_blip.jsonl
│   ├── framefeatures/{program_id}.pt
│   └── scores/{program_id}_blip.pt
└── results/
    ├── construct/{program_id}/        proposals, prop_sims, tree
    └── response/{program_id}/         ★ O QUE A API PRODUZ
        ├── responses.jsonl               o programa inteiro, uma linha
        ├── scenes/{scene_id}.json        uma cena cada
        ├── summary/summaries.json        uma entrada por requisição
        └── history/history.jsonl         versões substituídas
```

**Como o volume `./../:/${USERNAME}` monta o projeto inteiro, esses diretórios persistem no host automaticamente.** Vale conferir que estão no `.gitignore` — o `meta/` pode chegar a centenas de MB.

---

## ⚠️ Limpeza pendente no `src/api/`

Ao revisar o repositório, encontrei arquivos que ficaram de refatorações anteriores e **não são mais usados**:

| arquivo | situação |
|---|---|
| `processamento.py` (623 linhas) | virou `pipeline.py`, que virou `captioning.py` |
| `pipeline_api.py` (500 linhas) | idem — versão intermediária |
| `rotas/diagnostics_bkp.py` (505 linhas) | backup da rota antes da reescrita |
| `testar_jobs.sh` (124 linhas) | usa as rotas `/jobs`, que não existem mais |

**Manter versões antigas lado a lado com a atual é fonte de confusão** — quem abrir o projeto não sabe qual arquivo vale. O histórico do Git já guarda tudo.

*(O `pipeline_api.py` merece atenção extra: um arquivo chamado `pipeline.py` dentro de `api/` sequestra o `import pipeline` do RefCap. Foi por isso que ele foi renomeado para `captioning.py`, e o `ponte_refcap.py` hoje **recusa subir** se a colisão voltar.)*

---

## Começar

```bash
# 1. subir o container
cd .docker && cp sample-env.txt .env    # preencha as variáveis
docker compose up -d

# 2. o serviço respondeu?
curl http://localhost:${UI_PORT_PROD}/health

# 3. o contrato está íntegro?
docker compose exec caption_cut_by_prompt bash -c "cd src/api && bash verificar_contrato.sh"

# 4. as 20 combinações de teste
docker compose exec caption_cut_by_prompt bash -c "cd src/api && bash teste_manual.sh"
```

**Documentação detalhada:**

| documento | assunto |
|---|---|
| [`src/api/README.md`](src/api/README.md) | a arquitetura do serviço |
| [`src/api/documents/test/README_TESTES.md`](src/api/documents/test/README_TESTES.md) | os scripts de teste |
| [`src/api/documents/test/TESTES_CURL.md`](src/api/documents/test/TESTES_CURL.md) | testar à mão, caso a caso |
| [`src/api/documents/test/TESTES_DIAGNOSTICO.md`](src/api/documents/test/TESTES_DIAGNOSTICO.md) | GPU, supervisord, montagens |
| [`documents/`](documents/) | os artigos e as decisões de projeto |

---

## O escopo de hoje

**Dentro:** a etapa de **construct** — dado um vídeo, gerar a legenda e as palavras-chave, e persistir o resultado.

**Fora:** a etapa de **retrieve** (`retrieve.py`, `retrieve_service.py`, `pipeline/retrievepipe/`). O código está no repositório e o `documents/retrieval_instructions/` o descreve, mas o serviço HTTP não o expõe. Quando entrar, dois pontos vão importar: ele lê o `annos` e o `prop_sims`, e espera o `construct_name` no caminho — que hoje é vazio.
