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
├── models/                      ★ OS MODELOS BAIXADOS LOCALMENTE
│                                   BLIP-caption, BLIP-ITM, sentence-transformer
│                                   (não versionados — ver models/README.md)
│
├── data/                        ★ CENAS DE TESTE
│                                   copiadas para src/movies/ para validar o
│                                   construct localmente, antes do servidor real
│
├── documents/                   ★ A DOCUMENTAÇÃO DE PROJETO
│   ├── article/                    o paper do RefCap e o do GloVe
│   ├── code_analysis/              análise do código original
│   ├── commandments/               convenções e regras do projeto
│   ├── construct_instructions/     como o construct funciona
│   ├── retrieval_instructions/     o lado do retrieve (fora do escopo hoje)
│   ├── enviroment_settings/        preparo do ambiente
│   ├── diagnosis/                  investigações pontuais
│   └── tests/                      notas de teste
│
├── src/                         ★ O CÓDIGO E OS DADOS DE EXECUÇÃO
│   ├── api/                        O SERVIÇO HTTP  ← o que nós construímos
│   ├── config/ dataset/ pipeline/ utils/     O REFCAP (com 5 patches)
│   ├── movies/                     ★ onde as cenas são MONTADAS (do servidor)
│   ├── meta/                       ★ o GloVe + o CACHE gerado
│   ├── annos/                      as anotações por programa
│   ├── construct.py                ★ o ORIGINAL do BUAAPY — intocado
│   ├── construct_new.py            ★ com build() — é este que o serviço usa
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

### Os quatro diretórios que você preenche

Estes não vêm prontos do Git — cada um tem um `README.md` explicando o que colocar dentro:

| diretório | o que recebe | como |
|---|---|---|
| `models/` | os 3 modelos locais | baixados uma vez, apontados por `REFCAP_*_MODEL` |
| `data/` | cenas de teste | suas, para validar o construct localmente |
| `src/movies/` | as cenas **oficiais** | **montadas** do outro servidor (SMB/NFS) |
| `src/meta/` | o GloVe, e depois o cache | o GloVe você põe; o cache o serviço gera |

**[!] O `src/meta/` acumula os dois papéis:** você põe o GloVe lá, e o serviço grava ali o cache de legendas, features e scores. O `.gitignore` já tem `meta/*` — confira que o GloVe está coberto ou explicitamente liberado.

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
| `construct_new.py` | **cópia** com `build(cfg, pretrained_models)` extraído | permite passar os modelos já carregados; o `construct.py` original fica intocado |
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
/${USERNAME}/
├── models/                            os modelos, montados do host
├── data/                              cenas de teste
└── src/
    ├── movies/                     ★ AS CENAS — montadas do outro servidor
    │   └── Share/{program_id}/{video_id}/{scene_id}.mp4
    ├── meta/                       ★ O GLOVE + O CACHE — perdê-lo custa horas
    │   ├── glove/                       você põe
    │   ├── captions/{program_id}_blip.jsonl      o serviço gera
    │   ├── framefeatures/{program_id}.pt
    │   └── scores/{program_id}_blip.pt
    ├── annos/{program_id}/vcmr.jsonl     o SELETOR da requisição — sobrescrito
    └── results/
        ├── construct/{program_id}/        proposals, prop_sims, tree
        └── response/{program_id}/      ★ O QUE A API PRODUZ
            ├── responses.jsonl              o programa inteiro, uma linha
            ├── scenes/{scene_id}.json       uma cena cada
            ├── summary/summaries.json       uma entrada por requisição
            └── history/history.jsonl        versões substituídas
```

### ⚠️ Os dois volumes se sobrepõem em `src/movies`

```yaml
volumes:
  - ./../movies/Share:/${USERNAME}/src/movies/Share:ro,z   # 1
  - ./../:/${USERNAME}                                      # 2
```

O volume **2** monta o projeto inteiro — o que inclui `src/movies/`. O volume **1** monta, **por cima**, um diretório que fica **fora** do repositório (`../movies/Share`, irmão da pasta do projeto).

Isso funciona — o Docker aplica os binds do mais curto para o mais longo, e o mais específico vence. Mas tem duas consequências:

- **as cenas oficiais não estão no repositório**; elas vêm de `../movies/Share` no host, que por sua vez costuma ser a montagem SMB/NFS do outro servidor;
- o `src/movies/README.md` versionado **não aparece** dentro do container naquele subcaminho, porque o volume 1 o cobre.

**[J] Vale confirmar que `../movies/Share` existe e está montado ANTES de `docker compose up`.** Se não estiver, o container sobe com um diretório vazio ali — e as requisições falham com `FILE_NOT_FOUND` sem explicação óbvia.

**A persistência do resto vem de graça:** como o volume 2 monta o projeto inteiro, `meta/`, `annos/` e `results/` ficam no host automaticamente. O `.gitignore` já cobre `meta/*` e `results/`.

---

## Os dois `construct.py` — e por que ambos existem

```
src/construct.py        56 linhas   ← o ORIGINAL do BUAAPY, intocado
src/construct_new.py    98 linhas   ← com build(cfg, pretrained_models)
```

**A intenção é boa e vale preservar:** manter o upstream funcionando permite rodar um teste local com o RefCap puro, e comparar com o que este projeto mudou. O `construct.py` continua sendo invocável por `scripts/construct.sh`.

A diferença é uma só, mas decisiva:

| | `construct.py` | `construct_new.py` |
|---|---|---|
| ponto de entrada | `main()` — lê `argv` | `main()` **e** `build(cfg, models)` |
| recebe modelos prontos? | não — carrega sempre | **sim** |

O `build()` extraído é o que torna o serviço viável: sem ele, cada requisição recarregaria os quatro modelos.

---

## ⚠️ O estado atual do `src/api/` — o que está vivo e o que não está

Rastreei as importações a partir do `app.py`. O resultado expõe um problema que impede o serviço de funcionar.

### Vivo — alcançável a partir do `app.py`

```
app.py → estado.py → carregador.py, jobs.py
      → ponte_refcap.py
      → rotas/caption.py, rotas/health.py, rotas/diagnostics.py
             → contratos.py, persistencia.py
```

### Ferramentas — não importadas, mas de uso legítimo

Rodam sozinhas, por linha de comando:

| arquivo | para quê |
|---|---|
| `diagnostico_gpu.py` | o torch vê a GPU? os modelos ficam residentes? |
| `diagnostico_supervisord.py` | o serviço está em loop de reinício? |
| `validar_modelos_locais.py` | os caminhos dos modelos estão corretos? |
| `migrar_cache.py` | move o cache de um `collection` antigo para o novo |
| `verificar_contrato.sh` | 42 checagens do contrato da resposta |
| `preparar_teste.sh` · `teste_manual.sh` · `teste_config.sh` | a bateria de 20 casos |
| `diagnostico_mount.sh` | por que o diretório montado "não é encontrado" |

### ★★ Inconsistência que impede o serviço de rodar

```
rotas/caption.py:15       import pipeline          → pipeline.py NÃO EXISTE
rotas/diagnostics.py      import pipeline          → idem
captioning.py:396         from construct import build → construct.py NÃO TEM build
```

**O `import pipeline` não falha — e é isso que o torna perigoso.** Ele cai silenciosamente no **pacote `pipeline/` do RefCap**:

```
import pipeline  →  src/pipeline/__init__.py     (o pacote do RefCap)
pipeline.processar_pedido  →  não existe
```

O serviço **sobe normalmente**. Quebra na **primeira requisição**, com `AttributeError: module 'pipeline' has no attribute 'processar_pedido'`.

*(É a mesma colisão de nomes de antes, ao contrário: antes um arquivo `pipeline.py` sequestrava o pacote; agora o arquivo sumiu e o import cai no pacote. A guarda do `ponte_refcap.py` detecta o primeiro caso, não este.)*

**As duas correções:**

```python
# rotas/caption.py e rotas/diagnostics.py
import captioning                          # não `import pipeline`
captioning.processar_pedido(...)           # não `pipeline.processar_pedido`

# captioning.py:396
from construct_new import build            # não `from construct import build`
```

**[J] A segunda é a mais importante de acertar conceitualmente:** o serviço precisa do `construct_new`, porque é lá que está o `build()` que recebe os modelos. O `construct.py` deve continuar intocado — é justamente o ponto de manter o upstream funcionando.

### Código morto — versões anteriores do mesmo módulo

| arquivo | situação |
|---|---|
| `processamento.py` (623 linhas) | 1ª versão do pipeline |
| `pipeline_api.py` (500 linhas) | 2ª versão |
| `rotas/diagnostics_bkp.py` (505 linhas) | a rota antes da reescrita |
| `testar_jobs.sh` (124 linhas) | usa as rotas `/jobs`, que não existem mais |

São **1752 linhas**. Os três primeiros ainda importam `construct_new` — o que os faz parecerem atuais numa busca, e foi o que mascarou a inconsistência acima.

**[J] O Git já guarda o histórico.** Manter versões antigas ao lado da atual faz com que uma busca por `from construct_new import build` encontre quatro arquivos, e nenhum deles seja o que roda.

---

## Começar

### 1. Preencher o que o Git não traz

```bash
# os modelos — baixe uma vez e ponha em models/
ls models/            # BLIP-caption, BLIP-ITM, sentence-transformer

# o GloVe
ls src/meta/glove/

# as cenas OFICIAIS: monte o servidor em ../movies/Share (IRMÃO do projeto)
mount | grep -i "cifs\|nfs"
ls ../movies/Share/

# ou, para um teste local primeiro: copie cenas de data/ para src/movies/
cp -r data/exemplo src/movies/
```

**[!] A montagem precisa existir ANTES do `docker compose up`.** Um bind sobre um diretório que ainda não foi montado deixa o container com uma pasta vazia.

### 2. Subir

```bash
cd .docker
cp sample-env.txt .env        # preencha USERNAME, GROUPNAME, UID, GID, UI_PORT_PROD
docker compose up -d
```

### 3. Conferir, em ordem

```bash
# o serviço respondeu? (porta do HOST)
curl http://localhost:${UI_PORT_PROD}/health

# os modelos estão MESMO na GPU?
curl -s http://localhost:${UI_PORT_PROD}/health | grep allocated_mb

# o container enxerga as cenas?
docker compose exec caption_cut_by_prompt ls src/movies/Share/

# o contrato está íntegro? (42 checagens)
docker compose exec caption_cut_by_prompt bash -c "cd src/api && bash verificar_contrato.sh"

# as 20 combinações de teste
docker compose exec caption_cut_by_prompt bash -c "cd src/api && bash preparar_teste.sh && bash teste_manual.sh"
```

**O terceiro comando é o que decide.** Se ele não listar as cenas, o bind-mount está errado — e nenhuma configuração da API resolve.

### A documentação detalhada

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

**Fora:** a etapa de **retrieve** (`retrieve.py`, `retrieve_service.py`, `pipeline/retrievepipe/`). O código está no repositório e o `documents/retrieval_instructions/` o descreve, mas o serviço HTTP não o expõe. Quando entrar, dois pontos vão importar: ele lê o `annos` e o `prop_sims`, e espera o`construct_name` no caminho — que hoje é vazio.
