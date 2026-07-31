# `scratch_prove_no_annos.py` — Documentação Técnica Detalhada
## O que cada parte do código realiza, como, e por quê — com auditoria da própria prova

---

> **O que é este documento.** Uma descrição minuciosa, bloco a bloco, do script de prova `scratch/scratch_prove_no_annos.py`, explicando *o que* cada parte faz, *como* faz (o mecanismo), e *por que* faz (a razão de design). A parte final submete a prova a escrutínio crítico: o que ela estabelece com rigor, e quais suposições residuais e limites ela carrega. Uma prova sem autocrítica é só uma afirmação mais longa; esta documentação separa o que foi demonstrado do que foi assumido.

---

## 1. Visão geral: o que o script prova e por que sua estrutura é o que é

O script prova **uma tese** — *o `annos/` não é condição necessária para o `construct()`* — decomposta em **duas proposições logicamente distintas**. Essa decomposição não é estética; é o que separa uma prova honesta de um teatro de verde.

- **P1 (negativa): a informação que o `annos/` fornecia é substituível.** No ponto exato de leitura, a única informação extraída é `vid_name` — um catálogo de arquivos. Provada mostrando que a lista de vídeos produzida via `annos/` e via `os.listdir` é *idêntica*.
- **P2 (positiva): o núcleo nunca consome o rótulo.** Durante todo o `construct()`, os campos de rótulo (`ts`, `desc`) são lidos *zero vezes*, e o `construct()` completo roda com o `annos/` *fisicamente removido do disco*. Provada por **instrumentação** (espiões no acesso ao arquivo e aos campos), não por "rodou sem quebrar".

**Por que duas proposições, e não uma.** O erro que o script evita deliberadamente é a **circularidade**: um scratch ingênuo troca `select_videos` por `os.listdir`, roda, vê verde e declara vitória. Mas isso removeu o `annos/` *e* tudo que dependia dele — a ausência de crash não prova que o núcleo dispensa a *informação* do rótulo, apenas que o encanamento foi contornado. P1 prova a substituibilidade da informação; P2 prova que o cálculo nunca a tocou. Só as duas juntas constituem prova.

**O princípio de design que dá força a P2 — "dublar o ortogonal, vigiar o julgado".** O script preserva e *instrumenta* o caminho real de acesso ao `annos/` (é exatamente o que está sob julgamento) e dubla apenas as *fronteiras de I/O pesado* (BLIP e leitura de vídeo), que são ortogonais ao `annos/`. Se ele dublasse tudo, um crítico diria com razão: "você trocou metade do sistema; talvez o componente real precise do `annos/`". Ao dublar só o que é comprovadamente independente do `annos/`, a prova permanece sobre o `annos/`.

---

## 2. Walkthrough bloco a bloco

### 2.0 O *docstring* (linhas 1–41)

**O que realiza:** declara o contrato da prova antes de qualquer código — as duas proposições, o que o script *deliberadamente não faz* (dublar tudo), e por quê. **Por que importa:** um script de prova cujo critério de sucesso não está explícito pode "passar" provando a coisa errada. O docstring fixa o alvo (P1 + P2) e o padrão de evidência (instrumentação), de modo que o leitor possa julgar se as asserções de fato o atingem.

### 2.1 BLOCO 0 — Substrato (linhas ~45–72)

**O que realiza:** resolve as duas fricções recorrentes do RefCap e prepara o determinismo.

- **Injeção de `sys.path`** (`REPO_ROOT`): o repositório não é *pip-instalável* (sem `setup.py`), então o import só resolve com a raiz no path — o equivalente Python de `source setup.sh`.
- **`random.seed(0)`**: higiene de determinismo (irrelevante para esta prova específica, que não usa aleatoriedade, mas mantém o padrão).
- **Shim de `torchtext`** (o `try/except` que stuba `torchtext.vocab`): importar `constructpipe.base` cascateia por `capTree → sentence_transformers → torchtext`, que *quebra ao carregar* com torch recente. Como o `construct()` sob prova não usa GloVe, stubar `torchtext` em `sys.modules` desbloqueia a cadeia de import sem instalar a dependência frágil. É inócuo se o `torchtext` funcionar (o `try` passa).
- **`bare(cls, **attrs)`**: instancia via `object.__new__` (sem chamar `__init__`) e injeta à mão só os atributos necessários. **Indispensável aqui:** o `__init__` real do `BaseConstructPipeline` faz `os.listdir`, lê o `annos/`, carrega o BLIP e cria diretórios — quatro efeitos colaterais que impediriam a prova de isolar o que quer.

**Por que importa:** sem este bloco, o script nem importaria os módulos, e não conseguiria instanciar a classe sem disparar exatamente o `annos/`-reading e o BLIP-loading que a prova precisa controlar.

### 2.2 BLOCO 1 — Os instrumentos (linhas ~78–115)

Aqui vivem os dois espiões que transformam "rodou" em "medido". Este é o coração técnico da prova.

**`AnnoSpy` (envolve `builtins.open`).**
- **O que realiza:** registra *toda* tentativa de abrir o arquivo de anotação.
- **Mecanismo:** `install(anno_path)` substitui `builtins.open` por uma `spying_open` que compara o caminho aberto (por caminho absoluto) com o `anno_path`; se bate, incrementa `open_calls`; em seguida delega para o `open` real guardado em `self._real_open`. `uninstall()` restaura o original.
- **Por que por caminho absoluto:** evita falsos negativos/positivos por caminhos relativos vs absolutos — a comparação canônica é robusta a como o path foi construído.

**`FieldSpyDict` (subclasse de `dict`).**
- **O que realiza:** registra *qual campo* de cada linha do `annos/` é acessado.
- **Mecanismo:** sobrescreve `__getitem__` para adicionar a chave lida a um conjunto de classe `_accessed` antes de delegar ao `dict` real. Se o código faz `data['vid_name']`, a chave `'vid_name'` é gravada.
- **Por que um conjunto de classe (`_accessed`), não de instância:** as linhas do `annos/` viram múltiplos `FieldSpyDict` (um por linha); um conjunto compartilhado na classe agrega os acessos de *todas* as linhas num único registro global — é isso que permite afirmar "em nenhuma linha, `ts`/`desc` foram lidos".

**Por que importa:** juntos, os dois espiões respondem às duas perguntas empíricas de P2 — *quantas vezes o `annos/` é aberto?* (AnnoSpy) e *quais campos são lidos dele?* (FieldSpyDict). Sem instrumentação, essas perguntas seriam respondidas por inspeção manual do código (falível) em vez de medição (verificável).

### 2.3 BLOCO 2 — O cenário adversarial (linhas ~121–147)

**O que realiza:** monta um micro-mundo real em disco — um diretório temporário com 3 "vídeos" (arquivos vazios) e um `annos/` **real e mínimo**.

- **Os vídeos são arquivos vazios:** o conteúdo não importa porque a *leitura* de vídeo será dublada (é I/O pesado ortogonal ao `annos/`). O que importa é que existam com nomes (`vidA.mp4`, ...) para o catálogo de `vid_name` bater.
- **O `annos/` contém as três naturezas:** cada linha tem `vid_name` (N1, catálogo), `desc` (N2, consulta) e `ts` (N3, gabarito). **Isto é design adversarial deliberado:** plantamos os rótulos (`desc`, `ts`) *justamente para provar que nunca são lidos*. Um cenário que omitisse esses campos não poderia demonstrar sua não-leitura — seria uma prova vazia. Ao incluí-los e mostrar que o espião de campo nunca os registra, a prova é positiva, não por ausência.

**Por que importa:** a força de P2 depende de o `annos/` *conter* os rótulos e o script *demonstrar* que o núcleo os ignora. Plantar a evidência que se espera não encontrar é o que torna a não-detecção significativa.

### 2.4 BLOCO 3 — Prova de P1 (linhas ~153–172)

**O que realiza:** demonstra que a lista de vídeos via `annos/` é idêntica à via `os.listdir`.

- **Caminho original:** `pipe = bare(BaseConstructPipeline, cfg=cfg)` instancia sem `__init__` (sem BLIP), e então chama o **`select_videos` real** — o método verdadeiro que lê o `annos/`. `list_via_annos` é o resultado.
- **Caminho da Cirurgia 1:** `list_via_listdir = sorted(os.listdir(video_root))` — a listagem de diretório pura, o substituto proposto.
- **A asserção:** `sorted(list_via_annos) == list_via_listdir`. Verde ⇒ as duas listas coincidem.

**Por que importa:** estabelece que o `annos/`, *no ponto onde é lido*, não fornece nada além de um catálogo de nomes de arquivo — informação que o sistema de arquivos já possui. É a metade negativa da prova: *o que o `annos/` dava é substituível*.

### 2.5 BLOCO 4 — Prova de P2, parte 1: instrumentação durante `select_videos` (linhas ~178–212)

**O que realiza:** mede, durante a única etapa que toca o `annos/`, quantas vezes ele é aberto e quais campos são lidos.

- **Dupla instrumentação:** instala o `AnnoSpy` (conta aberturas) *e* substitui `json.loads` por `spying_json_loads`, que envolve cada linha-dict do `annos/` num `FieldSpyDict` (detecta linhas do `annos/` pela presença de `vid_name`). Assim, todo acesso a campo durante o parse é gravado.
- **Executa o `select_videos` real** dentro do `try`, e restaura `json.loads`/`open` no `finally` (higiene: a instrumentação não vaza para o resto do script).
- **As asserções:** `FieldSpyDict._accessed == {"vid_name"}` (só o catálogo foi lido) e explicitamente `"ts" not in ... and "desc" not in ...` (os rótulos, zero leituras).

**Por que importa:** é a evidência instrumentada — não a leitura de olho do código — de que o *único* ponto do `construct()` que abre o `annos/` extrai *apenas* `vid_name`. A distinção "medido, não inspecionado" é o que eleva isto de argumento a prova.

### 2.6 BLOCO 5 — Prova de P2, parte 2: `construct()` completo sem `annos/` (linhas ~218–279)

**O que realiza:** roda o fluxo **real** de `construct()` com o `annos/` apagado do disco, e prova zero acessos a ele.

- **Remoção física:** `os.remove(anno_path)` + `os.rmdir(anno_dir)`. Se *qualquer* etapa tentasse abrir o `annos/`, quebraria imediatamente com `FileNotFoundError`. A remoção converte "não deveria ler" em "não pode ler" — o teste mais duro possível.
- **Dublês só das fronteiras pesadas:** `DummyComponent` (para `caption_generator`, `caption_denoiser`, `proposal_generator`) e `lambda`s (para `compute_frame_features`, `compute_capframe_scores`, `build_tree_meta`). Cada um devolve um marcador sintético; o que se preserva é a **orquestração real** do `construct()` encadeando-os.
- **Cirurgia 1 aplicada:** `vid_list=vid_list_sem_annos` (de `os.listdir`) é injetado direto, substituindo o papel do `select_videos`/`annos/`.
- **Contador de aberturas:** `counting_open` envolve `builtins.open` durante *todo* o `construct()`, registrando cada arquivo aberto.
- **As asserções:** `annos_touched == 0` (nenhum arquivo com "annos"/"vcmr.jsonl" foi aberto) e `tree_meta is not None and "mycorpus_tree" in tree_meta` (o `construct()` produziu seu artefato de saída — o insumo do Retrieval).

**Por que importa:** é a demonstração de ponta a ponta. Não só os rótulos não são lidos (BLOCO 4) — o `annos/` inteiro é dispensável para o `construct()` chegar até a `tree_meta`. A prova de que o pipeline atinge seu produto final sem o arquivo é o clímax de P2.

### 2.7 BLOCO 6 — Veredito e limpeza (linhas ~285–305)

**O que realiza:** imprime a síntese (P1 substituível + P2 nunca consumido ⇒ `annos/` é encanamento removível) e apaga o diretório temporário (`shutil.rmtree`). **Por que importa:** fecha o argumento explicitamente e não deixa resíduo em disco (higiene de scratchpad — experimentos não devem poluir).

---

## 3. As três técnicas de instrumentação (aprofundamento)

O script usa três formas de espionagem, cada uma respondendo a uma pergunta diferente. Vale destacá-las porque são reutilizáveis em qualquer prova de "X não usa Y":

1. **Wrap de `builtins.open` (AnnoSpy / counting_open):** responde *"o recurso Y é acessado?"*. Substitui a função de I/O por uma que registra e delega. Técnica geral para provar (não-)acesso a arquivos.
2. **Subclasse de contêiner com `__getitem__` instrumentado (FieldSpyDict):** responde *"qual parte de Y é lida?"*. Granularidade fina — não só "o arquivo foi aberto", mas "quais campos". Técnica geral para provar que só um subconjunto dos dados é consumido.
3. **Wrap de `json.loads`:** a ponte que *injeta* o contêiner instrumentado no fluxo real, sem alterar o código-fonte. Intercepta o ponto onde os dados brutos viram estrutura, trocando `dict` por `FieldSpyDict`.

A combinação é o que permite afirmações *positivas e específicas* ("só `vid_name`, zero `ts`/`desc`"), muito mais fortes que a negativa genérica ("não quebrou").

---

## 4. Análise crítica: o que a prova estabelece vs. o que ela assume

Rigor exige separar o demonstrado do assumido. A prova é sólida no seu escopo, mas carrega suposições residuais que um revisor implacável apontaria — e que você deve conhecer para não superestimar o alcance.

**O que a prova estabelece com rigor:**
- No único ponto de leitura (`select_videos`), o `annos/` fornece exclusivamente `vid_name`, e esse catálogo é reproduzido identicamente por `os.listdir` (P1).
- Durante `select_videos`, os campos `ts`/`desc` têm zero leituras por acesso-colchete (P2, parte 1).
- A orquestração de `construct()`, com componentes dublados e `vid_list` vindo de `os.listdir`, produz a `tree_meta` com zero aberturas do `annos/`, mesmo com o arquivo removido do disco (P2, parte 2).

**As suposições residuais e limitações (os defeitos honestos):**

1. **BLOCO 5 dubla os componentes reais — logo prova a *orquestração*, não a *execução instrumentada dos componentes reais*.** Um cético diria: "e se o `caption_generator` *real* (BLIP) abrisse o `annos/` internamente?". A mitigação está na **interface**, não na execução: o `construct()` chama `self.caption_generator(vid_list=...)` — o componente recebe *apenas* `vid_list`, nunca o `anno_path`. Sem o caminho, ele *não pode* abrir aquele arquivo específico. Portanto a prova de P2-parte-2 repousa sobre a *fronteira de I/O* (nenhum componente recebe o caminho do `annos/`), reforçada pela remoção física do arquivo — mas *não* sobre rodar os modelos reais com instrumentação. Uma prova maximamente hermética instrumentaria os componentes reais; isso exige carregar BLIP/spaCy e processar vídeo, o custo que o design evita. **Resíduo: a fronteira de interface é evidência forte, não execução direta.**

2. **O espião de campo captura só acesso por colchete (`data['x']`), não `data.get('x')` nem `'x' in data`.** Em `select_videos`, o acesso é `data['vid_name']` (colchete), então é capturado. Mas se algum caminho usasse `.get()` ou o operador `in`, o `FieldSpyDict` não registraria. **Resíduo: a instrumentação assume o padrão de acesso por colchete;** para blindar totalmente, seria preciso interceptar também `__contains__` e `get`.

3. **P1 mostra "listas idênticas" porque o cenário faz o `annos/` enumerar *exatamente* o diretório.** Em geral, `select_videos` retorna a *interseção* `diretório ∩ vid_names-do-annos`. Se o `annos/` for um *subconjunto* (como o split de teste real), `os.listdir` indexaria *mais* vídeos que o `annos/`. Para o seu caso de uso isso é **desejável** (você quer indexar todos os seus vídeos), mas significa que "idêntico" é uma propriedade do *cenário construído*, não uma identidade universal. A afirmação universal correta é mais fraca e mais honesta: *o `annos/` só fornece um catálogo de `vid_name`; `os.listdir` fornece o mesmo tipo de informação (nomes de arquivo), coincidindo quando o `annos/` enumera o diretório e sendo um superconjunto caso contrário.* **Resíduo: a igualdade exata é do cenário; a substituibilidade da informação é geral.**

4. **O monkeypatch global de `open`/`json.loads` é seguro aqui por ser single-thread e restaurado no `finally`, mas é frágil por natureza.** Em código concorrente ou com imports tardios que usem `open`, o patch afetaria terceiros. Dentro deste script isolado não há risco, mas a técnica não é composável sem cuidado. **Resíduo: fragilidade de escopo global, aceitável no contexto.**

5. **Escopo: a prova cobre o estágio de *construção*, não a *recuperação*.** O `annos/` na recuperação cumpre outros papéis (consultas + gabarito de avaliação), governados pelas Cirurgias 2 e 3. Este script não os aborda — e a pergunta original era precisamente sobre "até chegar no `def construct`". **Resíduo: o argumento de ponta a ponta requer um segundo script provando que `ts` é inerte ao *scoring* da recuperação.**

6. **Imperfeição menor de código:** a variável `anno_path_that_would_be` (BLOCO 5) é computada mas não usada na asserção (que filtra por substring `"annos"/"vcmr.jsonl"` em `opened_files`). É código morto vestigial — inofensivo, mas um ponto de limpeza.

**Veredito sobre a validade:** dentro do escopo declarado (construção), a prova é **válida e honesta** — evita a circularidade do scratch ingênuo, planta os rótulos adversarialmente e os mede, e roda o fluxo real com o arquivo removido. As suposições residuais (interface em vez de execução dos componentes reais; acesso por colchete; cenário de igualdade) *refinam* o alcance sem *invalidar* a tese. Nenhuma delas é um defeito fatal; todas são limites de escopo que um leitor deve conhecer.

---

## 5. Como fortalecer a prova (extensões)

Se você quisesse elevar de "válida no escopo" para "hermética", três movimentos:

1. **Instrumentar os componentes reais** (BLOCK 5) em vez de dublá-los — rodando um `caption_generator` real sobre 1 frame minúsculo com o `AnnoSpy` ativo. Custo: carregar BLIP. Ganho: fecha o resíduo nº 1 (execução direta em vez de fronteira de interface).
2. **Ampliar o `FieldSpyDict`** para interceptar `__contains__` e `get` — fechando o resíduo nº 2 (todos os padrões de acesso).
3. **Escrever o script irmão para a recuperação** — provando, no mesmo estilo instrumentado, que `ts`/`desc` são inertes ao `topk`/scoring (o gabarito só é *ecoado* na saída, nunca *pontuado*). Isso fecha o resíduo nº 5 e completa o argumento de ponta a ponta.

---

## 6. Síntese

O script realiza uma prova de duas camadas: **P1** (o que o `annos/` dava é um catálogo substituível por `os.listdir`) e **P2** (o núcleo nunca lê os rótulos e o `construct()` inteiro roda com o `annos/` removido). Cada bloco tem um papel preciso — substrato que viabiliza o import e o bypass de modelos; instrumentos que medem acesso e campos; cenário adversarial que planta os rótulos; e as três asserções que fecham P1 e P2. A prova evita a circularidade do teste ingênuo ao **vigiar o que está sob julgamento (o `annos/`) e dublar só o ortogonal (o I/O pesado)**. Suas limitações — interface em vez de execução dos componentes reais, acesso por colchete, igualdade dependente de cenário, escopo de construção — são reais e declaradas, e nenhuma é fatal. É uma demonstração sólida da não-necessidade do `annos/` no estágio de construção, com o caminho de fortalecimento explícito para quem quiser torná-la hermética.
