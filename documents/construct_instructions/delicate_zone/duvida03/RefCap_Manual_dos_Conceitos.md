# Manual dos Conceitos — O Companheiro Teórico dos Três Laboratórios
## Cada Conceito: o que é, como funciona, onde está no RefCap, onde rodar, e o seu limite

---

> **O que é este documento.** O elo que faltava entre os relatórios (a prosa) e os laboratórios (o código executável). Aqui, **cada conceito teórico** aplicado na análise recebe uma entrada padronizada, com um ponteiro para **a seção exata do laboratório que o demonstra** e **a linha exata do RefCap onde ele aparece**. É para ser lido *ao lado* dos scripts, não antes nem depois.
>
> **Por que ele existe.** Os relatórios anteriores explicavam os conceitos em prosa; os laboratórios os executavam. Faltava a tabela de correspondência — e, para vários conceitos introduzidos no relatório do `constructpipe` (Lei de Deméter, CQS, falha adiada), faltava a explicação teórica em profundidade. Este documento fecha as duas lacunas.
>
> **Formato de cada entrada.** *O que é* → *O mecanismo* → *Que problema resolve* → *No RefCap* → *No laboratório* → *O limite*. A última linha é a mais importante: **nenhum conceito aqui é um mandamento**, e saber onde cada um deixa de valer é o que separa entender de repetir.

---

## Como usar: o mapa de leitura

| Laboratório | O que cobre | Quando rodar |
|---|---|---|
| **`LAB_registry_factory.py`** | A cadeia registry → decorator → factory → injeção → OCP, em 6 níveis progressivos | Primeiro. É a espinha do `construct.py`. |
| **`LAB2_mecanicas.py`** | As 10 mecânicas do modelo de objetos do Python, cada uma funcionando **e quebrada** | Depois do LAB 1, quando quiser saber *por que* cada peça funciona. |
| **`LAB3_bugs_constructpipe.py`** | As 3 provas dos defeitos reais do pipeline (KeyError, shadowing, árvore plana) | Quando for processar sua própria coleção. |

**Sugestão de percurso:** leia uma entrada deste manual → rode a seção correspondente do laboratório → abra a linha citada do RefCap. Três ângulos do mesmo fato fixam melhor que três leituras do mesmo texto.

---

# FAMÍLIA A — O modelo de objetos do Python (a mecânica)

Estes sete conceitos são a fundação. Sem eles, o padrão do `construct.py` parece mágica; com eles, é trivial.

## A1. Classes como objetos de primeira classe

**O que é.** Em Python, uma classe não é uma declaração processada e descartada — é um **objeto em tempo de execução**, que existe como valor comum e pode ser guardado, passado e devolvido.

**O mecanismo.** O comando `class X(Base): ...` é *executável*. Ele constrói um objeto chamando a metaclasse `type` com três argumentos — nome, tupla de bases, e o namespace do corpo — e o vincula ao nome `X`. Logo, `type(X)` é `type`, e `isinstance(X, object)` é `True`.

**Que problema resolve.** Habilita **tudo o mais**. Sem isto, não haveria como colocar uma classe num dicionário, e o registry seria impossível.

**No RefCap.** `capgenerator/base.py:15` — `CAPGEN_REGISTRY[names] = cls`. Uma atribuição de dicionário comum, onde o valor é uma classe.

**No laboratório.** LAB 1, Nível 1 (classes num dict). LAB 2, §1 (a equivalência `class X` ≡ `type("X", bases, ns)` provada com as duas formas produzindo o mesmo comportamento).

**O limite.** Poder guardar classes em estruturas não significa que se deva fazê-lo em toda parte. Quando o conjunto é fixo e pequeno, uma referência direta é mais legível que uma busca por string.

---

## A2. O operador de chamada e `type.__call__`

**O que é.** O `()` em Python é **sobrecarregado**: significa coisas diferentes conforme o tipo do objeto à esquerda. É a raiz da confusão sobre `get_capgen_class('blip')(cfg, models)`.

**O mecanismo.** `obj(args)` é açúcar para `type(obj).__call__(obj, args)`. Três casos:
- `obj` é **função** → executa o corpo.
- `obj` é **classe** → `type(classe)` é `type`, e `type.__call__` **constrói um objeto**: chama `__new__` (aloca) e depois `__init__` (inicializa).
- `obj` é **instância** → busca `__call__` na classe dela.

**Que problema resolve.** Uniformiza a sintaxe de invocação. O custo é a ambiguidade visual.

**No RefCap.** `construct.py:43` — `get_capgen_class(cfg.caption_generator)(cfg, pretrained_models)`. O primeiro `()` é chamada de função; o segundo é **construção de objeto**, não chamada.

**No laboratório.** LAB 2, §2 — `__new__` e `__init__` instrumentados mostram a ordem, e a forma explícita `type(C).__call__(C, "Y")` prova a equivalência. LAB 1, Nível 3, imprime os quatro tipos da cadeia.

**O limite.** A distinção só importa quando você precisa intervir na construção (`__new__` customizado, metaclasses, singletons). No uso comum, tratar `Classe(...)` como "uma chamada que devolve objeto" é uma simplificação inofensiva.

---

## A3. Closure e escopo léxico

**O que é.** Uma função **mais o ambiente onde ela nasceu**. As variáveis capturadas sobrevivem ao retorno da função que as criou.

**O mecanismo.** O Python guarda as variáveis livres em **células** (`cell`), acessíveis via `func.__closure__`. Cada célula tem `cell_contents`. A lista de nomes capturados está em `func.__code__.co_freevars`. A captura é por **referência à célula**, não por cópia do valor — daí o clássico problema de closures em laços.

**Que problema resolve.** Permite parametrizar comportamento sem estado global nem argumentos extras. É o que torna possível o decorador-fábrica.

**No RefCap.** `capgenerator/base.py:10-22` — `register_capgen_cls` captura `names` da função externa.

**No laboratório.** LAB 2, §3 — imprime `decorador.__closure__[0].cell_contents` devolvendo `['blip']`, e mostra que a versão que *não usa* `names` tem `__closure__ = None`.

**O limite.** Closures capturam a **variável**, não o valor no instante da criação. Em `[lambda: i for i in range(3)]`, todas as lambdas veem o `i` final. É a armadilha mais comum do conceito.

---

## A4. Functor / objeto chamável (`__call__`)

**O que é.** Um objeto que pode ser invocado como se fosse função, mantendo **estado interno**.

**O mecanismo.** Definir `__call__` na classe. Sem ele, `obj(...)` levanta `TypeError: object is not callable`.

**Que problema resolve.** Une as duas coisas que normalmente se excluem: a **interface simples de uma função** e a **memória de um objeto**. É o que permite ao orquestrador escrever `self.caption_generator(vid_list=...)` sem saber que ali dentro há configuração, modelos e cache.

**No RefCap.** `capgenerator/base.py:39` — o `__call__` que torna o gerador invocável. `constructpipe/base.py:69` — o ponto de uso.

**No laboratório.** LAB 2, §4 — uma classe sem `__call__` produz o `TypeError` real; a mesma com `__call__` funciona.

**O limite.** Um functor esconde que há estado. Se o objeto acumula (como `already_video_names`), chamá-lo duas vezes **não** dá o mesmo resultado — e a aparência de função sugere o contrário. Use quando o estado é intencional; prefira função pura quando não é.

---

## A5. MRO, despacho dinâmico e *late binding*

**O que é.** A resolução de qual método executar acontece **em tempo de execução**, com base no tipo real do objeto — não no texto do código.

**O mecanismo.** Cada classe tem uma **MRO** (*Method Resolution Order*), uma linearização de suas bases (algoritmo C3), acessível em `Classe.__mro__`. Ao avaliar `self.metodo()`, o Python percorre a MRO do tipo real de `self` e usa a primeira definição encontrada.

**Que problema resolve.** É o motor do polimorfismo de subtipo: código escrito contra a base funciona com qualquer subclasse.

**No RefCap.** `capgenerator/base.py:47` chama `self.generate_caption(...)`; como `self` é um `CapGeneratorBLIP`, o despacho encontra `BlipCapGener.py:17`, não `base.py:50`.

**No laboratório.** LAB 2, §5 — imprime a MRO e mostra o `__call__` da base roteando para o método da subclasse.

**O limite (o custo de leitura).** O fluxo de controle **não é local ao texto**. Ler `base.py` isolado engana: você vê um `generate_caption` que só faz um `assert` e conclui que nada acontece. É o imposto do polimorfismo, e é o que torna a leitura de código alheio mais cara.

---

## A6. Decoradores e decorator factories

**O que é.** Açúcar sintático para uma reatribuição. Um *decorator factory* é uma função que **produz** um decorador, para que ele possa receber argumentos.

**O mecanismo.** `@deco` sobre `X` ≡ `X = deco(X)`. Com argumento, `@fab(arg)` sobre `X` ≡ `X = fab(arg)(X)` — dois níveis: a fábrica captura o argumento (via closure), o decorador recebe a classe. Aplicar a classes é a [PEP 3129](https://peps.python.org/pep-3129/); a decoradores em geral, a [PEP 318](https://peps.python.org/pep-0318/).

**Que problema resolve.** Adiciona comportamento sem tocar no corpo do que é decorado. Aqui, especificamente: **registra a classe sem que ela precise saber do registry**.

**No RefCap.** `capgenerator/base.py:10-22` (a fábrica) e `BlipCapGener.py:10` (o uso).

**No laboratório.** LAB 1, Nível 2 — imprime a ordem de execução das duas camadas (C1 → C2) e mostra a equivalência explícita.

**O limite.** O `return cls` é **obrigatório**: o decorador substitui o nome pelo que devolve. Esquecê-lo transforma a classe em `None`, com erro distante e incompreensível. E decoradores que *embrulham* (ao contrário deste, que devolve `cls` intacta) escondem a assinatura original — use `functools.wraps`.

---

## A7. Tempo de import vs. tempo de execução

**O que é.** Código no corpo de um módulo roda **quando o módulo é importado**, uma única vez. Isso é um tempo distinto do tempo de execução da lógica.

**O mecanismo.** Na primeira importação, o Python executa o arquivo inteiro de cima a baixo e guarda o resultado em `sys.modules`. Imports subsequentes não reexecutam. Como decoradores rodam na definição da classe, **o registro é um efeito colateral de import**.

**Que problema resolve.** Permite auto-registro: nenhum código central precisa listar os plugins.

**No RefCap.** `pipeline/capgenerator/__init__.py` — as duas linhas de `import *` existem **pelo efeito de registrar**, não pelos nomes. Removê-las esvazia o registry.

**No laboratório.** LAB 2, §9 — cria dois arquivos de plugin reais, importa só um, e mostra o registry com `plug_a` e **sem** `plug_b`, que existe e está correto.

**O limite.** Cria dependência **invisível e ordenada**. *Linters* marcam o import como não utilizado; removê-lo quebra tudo. E o erro aparece em runtime, longe da causa. **Regra prática: antes de "limpar" um import aparentemente inútil, verifique se ele não sustenta um efeito colateral.**

---

# FAMÍLIA B — Padrões de design

## B1. Registry (registro de plugins)

**O que é.** Um mapa `nome → implementação`, povoado pelas próprias implementações.

**O mecanismo.** Dicionário de módulo + decorador que insere + função que busca.

**Que problema resolve.** Inverte a direção da dependência. Sem ele, a função de busca precisa *conhecer e importar* todas as implementações; com ele, cada implementação se anuncia e a busca não conhece nenhuma.

**No RefCap.** Cinco vezes: `capgenerator`, `denoiser`, `propgenerator`, `constructpipe`, `retrievepipe`.

**No laboratório.** LAB 1, Níveis 0→2 (o problema ingênuo, o dict, o auto-registro).

**O limite.** É **estado global mutável**. Ordem de inicialização importa, testes podem contaminar uns aos outros, e não há isolamento por escopo. Em sistemas maiores, injeta-se um container explícito.

---

## B2. Factory (fábrica)

**O que é.** Função cuja responsabilidade é produzir ou selecionar um objeto, escondendo do chamador a decisão de *qual*.

**O mecanismo.** Aqui é uma variante: devolve a **classe**, não a instância. Quem instancia é o chamador.

**Que problema resolve.** Separa **seleção** de **construção**. Se a factory devolvesse a instância pronta, precisaria conhecer `cfg` e `models` — mais acoplamento.

**No RefCap.** `capgenerator/base.py:54` — `get_capgen_class(name)`.

**No laboratório.** LAB 1, Nível 3 (a tripla aplicação com os tipos).

**O limite.** Devolver a classe transfere ao chamador a responsabilidade de saber como construí-la. Se a construção for complexa ou variar por implementação, isso vaza para o `main()`.

---

## B3. Service Locator

**O que é.** O par (registry + factory): um ponto central onde se **pede** uma dependência pelo nome.

**Que problema resolve.** Desacopla quem usa de quem constrói, com seleção dirigida por dados externos.

**No RefCap.** Os cinco pares registry+getter.

**O limite (a crítica séria).** Vários autores — Mark Seemann é o mais conhecido — o consideram **anti-padrão**, porque ele **esconde** as dependências em vez de declará-las: lendo uma assinatura, você não sabe do que a classe precisa. A alternativa preferida é injeção pura. Aqui o custo é aceitável porque a seleção vem de configuração de linha de comando — que é o caso de uso legítimo do padrão.

---

## B4. Strategy

**O que é.** Encapsular algoritmos intercambiáveis atrás de uma interface comum, permitindo trocá-los.

**Que problema resolve.** Elimina condicionais espalhados por tipo de algoritmo; localiza a variação num objeto.

**No RefCap.** `BaseCapGen`/`CapGeneratorBLIP` (legendagem), `QMPropGenerator` (segmentação), os denoisers.

**No laboratório.** LAB 1, Nível 5 (trocar a estratégia trocando uma string).

**O limite.** Strategy só se paga com **implementações reais e múltiplas**. Com uma só, é indireção pura — o que o RefCap faz com `construct_pipeline`, cujo único valor possível é `"base"`.

**Distinção que importa:** Strategy é sobre *ter alternativas*; Registry é sobre *como escolher entre elas*. São ortogonais.

---

## B5. Template Method

**O que é.** A classe base define o **esqueleto** de um algoritmo e deixa *hooks* para as subclasses preencherem.

**O mecanismo.** Um método concreto na base que chama métodos que a subclasse sobrescreve (via despacho dinâmico — A5).

**Que problema resolve.** **Localiza a variação.** Para escrever um gerador novo, você não precisa entender o loop de vídeos, o cache, nem o tratamento de arquivo ausente — só o hook.

**No RefCap.** Duas instâncias: `BaseCapGen.__call__` (base.py:39) com o hook `generate_caption`; e `BaseConstructPipeline.construct()` (constructpipe/base.py:67), que fixa a ordem das sete etapas.

**No laboratório.** LAB 1, Nível 4. A mecânica do hook está no LAB 2, §5.

**O limite.** O esqueleto vira **rígido**. Se uma subclasse precisar de ordem diferente, o padrão atrapalha — e a saída costuma ser herança forçada ou flags. Quando a ordem varia, prefira composição explícita.

---

## B6. Adapter e camada anticorrupção

**O que é.** Um objeto que traduz entre a interface que você tem e a que o outro sistema espera. A *camada anticorrupção* (termo do DDD) é a versão arquitetural: uma fronteira que impede que a forma do sistema alheio contamine o seu.

**Que problema resolve.** Permite usar código de terceiros sem se tornar refém do formato dele.

**No RefCap.** É o que **nós** construímos: `make_annos.py` e `retrieve_service.py` traduzem entre a sua coleção de vídeos e o contrato que o RefCap espera — **sem modificar o RefCap**.

**O limite.** Cada adaptador é código a manter, e ele *duplica conhecimento* sobre o formato alheio. Se o sistema externo muda, o adaptador quebra. Vale quando você não controla o outro lado (exatamente o seu caso).

---

# FAMÍLIA C — Princípios de arquitetura

## C1. Injeção de Dependência (por construtor)

**O que é.** O objeto **recebe** seus colaboradores prontos, em vez de construí-los.

**Que problema resolve.** Desacopla do concreto e torna testável — você injeta dublês.

**No RefCap.** `constructpipe/base.py:37` — o pipeline recebe gerador, denoiser e propgen.

**No laboratório.** LAB 1, Nível 4.

**O limite.** Empurra a complexidade de montagem para cima. Com muitas dependências, o construtor incha — e um construtor com 5+ parâmetros (como o do RefCap) é sinal de que a classe faz coisas demais.

---

## C2. Inversão de Controle

**O que é.** O princípio geral: quem controla a criação e o fluxo **sobe** para quem monta o sistema, em vez de ficar em cada módulo.

**No RefCap.** O pipeline não decide qual gerador usar; o `main()` decide.

**O limite.** IoC dilui a rastreabilidade: para saber o que roda, você precisa ir ao ponto de montagem, não ao ponto de uso.

---

## C3. Composition Root

**O que é.** O **único lugar** que conhece todas as escolhas concretas e monta o grafo de objetos.

**Que problema resolve.** Concentra num só ponto o conhecimento que, espalhado, acoplaria tudo.

**No RefCap.** `construct.py::main` — é o único lugar onde as strings `"blip"`, `"qm"`, `"window"` viram objetos.

**A distinção que refina o modelo mental.** Composition Root ≠ Orquestrador. O `main()` decide *quais* implementações e as monta; o `construct()` decide a *ordem* e **não sabe** o que recebeu. O pipeline **não reúne** as classes — ele as **recebe**.

**O limite.** Só funciona se for realmente **um** lugar. O RefCap o dilui: `BaseConstructPipeline.__init__` também lê `os.listdir`, converte arquivos e cria diretórios — montagem misturada com orquestração.

---

## C4. Open/Closed Principle (OCP)

**O que é.** Aberto para extensão, fechado para modificação.

**No RefCap.** O registry: adicionar um gerador é criar um arquivo, sem tocar em nada existente.

**No laboratório.** LAB 1, Nível 5 — um gerador novo registrado sem alterar registry, factory nem pipeline.

**O limite.** OCP tem custo (indireção) e só se paga onde a extensão **de fato acontece**. Aplicá-lo em toda parte é over-engineering. Um bom teste: se o `if/elif` que ele substitui teria menos de ~5 ramos e não cresce, não vale.

---

## C5. Dependency Inversion Principle (DIP)

**O que é.** Módulos de alto nível não dependem de baixo nível; ambos dependem de abstrações.

**No RefCap.** O `construct()` depende do contrato "é chamável com `vid_list`", não do `CapGeneratorBLIP`.

**O mecanismo Pythônico.** `typing.Protocol` ([PEP 544](https://peps.python.org/pep-0544/)) para abstração estrutural; `abc.ABC` ([PEP 3119](https://peps.python.org/pep-3119/)) para nominal.

**O limite.** Inverter dependências onde não há volatilidade real cria abstrações vazias — interfaces com uma implementação só, que só adicionam um salto de leitura.

---

## C6. Single Responsibility Principle (SRP)

**O que é.** Um módulo deve ter **uma razão para mudar**.

**A violação verificada no RefCap.** `BaseConstructPipeline` **orquestra e executa**: delega as etapas 1, 4 e 6 a colaboradores injetáveis, mas implementa 2, 3, 5 e 7 nos próprios métodos. Muda se a ordem mudar, *e* se o cálculo de features mudar, *e* se o formato da árvore mudar. Três razões.

**O limite.** "Uma responsabilidade" é elástico. O teste operacional é melhor que a definição: *quantos atores diferentes pediriam mudanças nesta classe?* Se for mais de um, separe.

---

## C7. Liskov Substitution Principle (LSP)

**O que é.** Um subtipo deve ser usável onde o supertipo é esperado, sem quebrar o programa.

**O mecanismo formal.** A subclasse pode **enfraquecer** pré-condições e **fortalecer** pós-condições — nunca o contrário.

**A violação verificada no RefCap.** `propgenerator/base.py:28` declara `__call__(self, vid_list, captions, scores)` — 3 parâmetros. `QMPropGener.py:44` exige **4**. A subclasse **fortaleceu a pré-condição**, tornando-se não-substituível.

**No laboratório.** LAB 2, §8 — reproduz a violação e mostra o `TypeError` real.

**O limite (e uma limitação do ABC).** `@abstractmethod` verifica se o método **existe**, nunca se a **assinatura é compatível**. O mecanismo que existe para impor contratos não pega esta violação. Só `mypy` com `Protocol` pegaria.

---

## C8. Lei de Deméter ("fale só com amigos imediatos")

**O que é.** Um método deve chamar apenas: métodos próprios, de seus parâmetros, de objetos que ele criou, e de seus atributos diretos — **nunca atravessar** um objeto para alcançar outro.

**O sintoma.** O *train wreck*: `a.b.c.metodo()`.

**Que problema resolve.** Cada travessia cria uma dependência da **estrutura interna** de outro objeto. Quando ela muda, você quebra.

**A violação verificada no RefCap.** `constructpipe/base.py:155,159` — `self.caption_denoiser.it_sim_model`. E o pipeline **tem a própria referência ao mesmo objeto** na linha 50. Consequência: o contrato real do denoiser é maior que o declarado — ele precisa expor um atributo que nenhuma interface menciona.

**No laboratório.** LAB 2, §10 — um denoiser que cumpre o contrato público mas não tem o atributo produz `AttributeError`.

**O limite.** A lei é frequentemente violada de forma inofensiva com estruturas de dados puras (`config.db.host`) — ali não há comportamento a proteger. Ela importa quando o intermediário é um **objeto com comportamento**, cuja estrutura interna deveria ser privada.

---

## C9. Command-Query Separation (CQS)

**O que é.** Um método ou **faz** algo (comando, muda estado) ou **responde** algo (query, devolve valor) — não ambos.

**Que problema resolve.** Torna seguro chamar queries livremente. Quando um método faz as duas coisas, o leitor não pode prever o efeito de invocá-lo.

**A violação verificada no RefCap.** `constructpipe/base.py:186` — `select_videos` tem nome de query (filtrar uma lista) mas **executa o ffmpeg e cria arquivos** no diretório de vídeos do usuário (linha 197). Efeito colateral pesado, irreversível e invisível no nome.

**O limite.** Alguns idiomas legítimos violam CQS deliberadamente — `pop()` de uma pilha remove *e* devolve, e ninguém reclama, porque a convenção é universalmente conhecida. A regra protege contra **surpresa**, não contra a combinação em si.

---

# FAMÍLIA D — Tipos e abstração

## D1. Tipagem estrutural vs. nominal (duck typing vs. ABC)

**O que é.** Duas filosofias sobre o que faz um objeto "pertencer" a um tipo.
- **Estrutural (duck typing):** pertence se **tem a forma** — os métodos certos. Contrato implícito.
- **Nominal (ABC/herança):** pertence se **declara pertencer** — herda da base. Contrato explícito e imposto.

**Que problema cada uma resolve.** Estrutural dá flexibilidade máxima (funciona com objetos que você não controla). Nominal dá garantia e falha cedo.

**A inconsistência verificada no RefCap.** Os dois módulos irmãos usam filosofias diferentes, sem justificativa: `capgenerator/base.py:26` (`BaseCapGen`) é duck typing puro; `propgenerator/base.py:23` (`BasePropGen`) usa `ABC` + `@abstractmethod`.

**No laboratório.** LAB 2, §7 — lado a lado, com um filho incompleto em cada. O duck typing instancia **em silêncio** e herda o comportamento errado; o ABC falha imediatamente com mensagem precisa.

**A síntese moderna.** `typing.Protocol` ([PEP 544](https://peps.python.org/pep-0544/)) dá o melhor dos dois: contrato **declarado e checável** sem exigir herança. É o mecanismo que o `QueryDataset` tateou por duck typing.

**O limite.** ABC força herança — inútil para objetos de terceiros. Duck typing não avisa nada até o ponto de uso. Protocol resolve os dois, mas só é verificado se você rodar `mypy`.

---

## D2. Polimorfismo — os três tipos

**O que é.** Um mesmo nome operando sobre coisas diferentes. Três variedades clássicas:
- **Ad-hoc** (sobrecarga por tipo de argumento) — Python não tem nativamente.
- **Paramétrico** (genéricos, `list[T]`) — presente na tipagem, não no mecanismo central aqui.
- **De subtipo / inclusão** — **é o que atua no RefCap**.

**No RefCap.** `self.generate_caption()` resolvendo para a subclasse.

**No laboratório.** LAB 2, §5.

**O limite.** Polimorfismo de subtipo exige hierarquia. Quando as "variantes" não têm relação "é-um" genuína, forçar herança para obter polimorfismo produz hierarquias falsas — prefira composição ou Protocol.

---

## D3. Design by Contract (pré-condições, pós-condições, invariantes)

**O que é.** Tratar a fronteira entre componentes como um **contrato explícito**: o chamador garante as pré-condições; a função garante as pós-condições; invariantes valem sempre.

**Que problema resolve.** Localiza a **culpa**. Sem contrato, quando uma função recebe lixo e falha, não se sabe se o defeito é dela (não validou) ou de quem chamou (passou lixo).

**No RefCap (ausente, e a ausência custa).** Nenhuma etapa declara o que espera. O `compute_frame_features` **assume** que todo vídeo em `vid_list` tem legendas — uma pré-condição não escrita e não verificada. Quando ela é violada, o resultado é um `KeyError` sem contexto (ver F2).

**No laboratório.** LAB 3, Prova 1 — a pré-condição implícita sendo violada.

**O limite.** Contratos verificados em runtime custam performance e código. A prática usual é verificar nas **fronteiras públicas** e confiar internamente.

---

# FAMÍLIA E — Teoria funcional

## E1. Currying e aplicação parcial

**O que é.** Transformar uma função de N argumentos numa cadeia de aplicações, fixando argumentos progressivamente.

**A formalização do caso.**
```
get_capgen_class  : Nome            → Classe
Classe.__init__   : (Cfg × Models)  → Instância      [aplicação parcial]
Instância.__call__: VidList         → Captions
```
Ou seja: `capgen : Nome → Cfg → Models → VidList → Captions`.

**Que problema resolve.** Reduz a interface no ponto de uso. O orquestrador chama uma função **unária**, sem saber de `cfg` nem de `models`.

**No RefCap.** `construct.py:43` (a aplicação parcial) e `constructpipe/base.py:69` (o uso unário).

**No laboratório.** LAB 2, §6 — a versão com classe e a versão com `functools.partial` produzindo resultados **idênticos** (`True`).

**O limite (o achado do laboratório).** Se as duas formas são equivalentes, por que classe? **Porque a classe adiciona estado mutável entre chamadas** — o cache `already_video_names`. Esse é o único motivo. Sem estado, `partial` seria mais simples e mais honesto.

---

## E2. Composição de funções vs. DAG

**O que é.** A tentação de modelar um pipeline como `f∘g∘h`. Correto só quando o fluxo é linear.

**A realidade verificada no RefCap.** No `construct()`, `features` é calculado uma vez e consumido por **três** passos (3, 5 e 6); `captions` alimenta três. E `compute_capframe_scores` é chamado **duas vezes** com entradas diferentes. É um **grafo acíclico dirigido com fan-out**, não uma cadeia.

**Por que a distinção importa.** Modelar como cadeia leva a conclusões erradas sobre o que pode ser reordenado, paralelizado ou cacheado.

**O limite.** Mesmo o DAG é uma idealização: há efeitos colaterais (escrita em disco) que não aparecem no grafo de dados.

---

## E3. Pureza, estado e transparência referencial

**O que é.** Uma função é **pura** se o resultado depende só dos argumentos e não há efeitos observáveis. Transparência referencial: poder substituir a chamada pelo resultado sem mudar o programa.

**A realidade no RefCap.** As instâncias carregam estado (`self.captions`, `self.already_video_names`) e escrevem em disco. **Chamar duas vezes não dá o mesmo resultado** — a segunda pula o que já foi feito.

**Que problema o estado resolve aqui.** O cache incremental: legendar é caro, e não refazer é o que torna "adicionar vídeos" barato.

**O limite.** O preço é que o raciocínio equacional some. Você não pode analisar `construct()` como uma expressão; precisa considerar o **histórico** de execuções e o conteúdo do disco. É complexidade essencial (o cache é necessário), mas é complexidade.

---

# FAMÍLIA F — Qualidade, smells e modos de falha

## F1. Shadowing de nomes

**O que é.** Um nome sendo reutilizado para significar coisa diferente no mesmo escopo.

**O caso verificado.** `constructpipe/base.py:174-176` — `build_tree_meta(self, proposals)` recebe um dicionário e, **dentro do laço sobre esse dicionário**, reatribui `proposals = metas['proposals']` (uma lista).

**Por que funciona mesmo assim.** `proposals.items()` é avaliado **uma vez**; o iterador já segura a referência ao objeto original. Rebindar o nome não afeta o iterador em curso.

**No laboratório.** LAB 3, Prova 2 — demonstra que funciona, e por quê.

**O limite / o risco.** Funciona **por acidente da semântica de iteradores**. Qualquer refatoração que mova o `.items()` para dentro do laço, ou introduza um segundo laço, quebra silenciosamente. É uma mina, não um bug — ainda.

---

## F2. Programação defensiva e o modo de falha adiada

**O que é.** A ilusão de robustez: uma guarda que evita a falha **localmente** mas cria uma inconsistência que explode **adiante**.

**O caso verificado (o mais importante para você).** `BlipCapGener.py:23` pula vídeos corrompidos com `return`, sem adicioná-los a `captions`. Mas `constructpipe/base.py:137` itera sobre a **`vid_list` inteira** e faz `vid_2_cap[video_name]` na linha 143 → **`KeyError`**.

**A raiz teórica.** As duas etapas **discordam sobre qual é o conjunto**. Uma guarda que altera implicitamente um conjunto compartilhado, sem comunicar a alteração, transfere a falha para quem assume o conjunto original.

**No laboratório.** LAB 3, Prova 1 — reproduz o `KeyError` exato.

**Por que isto é pior que um crash normal.** A mensagem final (`KeyError: 'nome_do_video'`) **não menciona corrupção**. É o "erro silenciado" do Zen (#10) na forma mais cara: não some, reaparece longe e disfarçado.

**A correção.** Ou propagar exceção nomeada, ou remover o vídeo de `vid_list` de forma **explícita e única**, para que todas as etapas concordem.

---

## F3. Complexidade essencial vs. acidental

**O que é.** A distinção de Fred Brooks. **Essencial** é imposta pelo problema (irredutível); **acidental** é introduzida pela solução (removível).

**Aplicada ao padrão deste estudo.** A necessidade de trocar de VLLM é essencial (o paper compara BLIP e MiniGPT). A **indireção** do registry é acidental — é o preço pago. Ela se justifica porque a variação é real.

**Aplicada ao que é desperdício puro.** A decodificação dupla do vídeo (`BlipCapGener.py:21` e `constructpipe/base.py:143`), somada ao desperdício de ~25× do ffmpeg, é **~50× de trabalho acidental**. Nada no problema exige isso.

**O limite.** A classificação depende do problema, não do código. O mesmo registry é essencial num sistema de plugins e acidental num script com uma implementação só.

---

## F4. Design orientado a dados (*data-driven design*)

**O que é.** Deslocar decisões do **espaço do código** (que exige reescrever) para o **espaço dos dados** (que exige trocar um valor).

**No RefCap.** O `construct.sh` é uma **DSL minúscula**: quatro strings selecionam quatro implementações e determinam o comportamento do sistema. O registry é a tabela de despacho dessa linguagem; o `main()` é o interpretador.

**No laboratório.** LAB 1, Nível 5.

**O limite (relevante para a sua análise).** O comportamento deixa de ser legível no código e passa a ser legível apenas no **par (código, configuração)**. Ler `construct.py` isolado não diz o que o sistema faz — você precisa do `.sh` junto. **É exatamente por isso que analisar este repositório dá mais trabalho: a fonte de verdade está em duas linguagens.**

---

## F5. O custo de rastreabilidade estática

**O que é.** O preço geral de toda indireção dinâmica: ferramentas e leitores perdem a capacidade de responder "o que roda aqui?" sem executar.

**No RefCap.** Lendo `get_capgen_class(cfg.caption_generator)`, nem você, nem a IDE ("ir para definição" falha), nem o `mypy` sabem qual classe será usada. Um nome errado (`caption_generator=blipp`) só explode em runtime, possivelmente depois de carregar vários GB de modelos.

**O limite / a compensação.** Type hints e `Protocol` recuperam parte da verificabilidade; um `Literal["blip","minigpt"]` no cfg pegaria o nome errado estaticamente. **Você paga o custo total quando não usa nenhuma dessas ferramentas** — que é o caso do RefCap.

---

# APÊNDICE — Tabela mestra de correspondência

| Conceito | Laboratório | Linha do RefCap |
|---|---|---|
| Classes como objetos | LAB1 N1 · LAB2 §1 | `capgenerator/base.py:15` |
| `type.__call__` / `__new__`+`__init__` | LAB2 §2 | `construct.py:43` |
| Closure | LAB2 §3 | `capgenerator/base.py:10-22` |
| Functor (`__call__`) | LAB2 §4 | `capgenerator/base.py:39` |
| MRO / despacho dinâmico | LAB2 §5 | `base.py:47` → `BlipCapGener.py:17` |
| Decorator factory | LAB1 N2 | `capgenerator/base.py:10` |
| Efeito colateral de import | LAB2 §9 | `capgenerator/__init__.py` |
| Registry | LAB1 N0-N2 | 5 módulos do `pipeline/` |
| Factory | LAB1 N3 | `capgenerator/base.py:54` |
| Service Locator | LAB1 N2-N3 | registry + getter |
| Strategy | LAB1 N5 | geradores/denoisers |
| Template Method | LAB1 N4 · LAB2 §5 | `base.py:39` · `constructpipe/base.py:67` |
| Injeção de Dependência | LAB1 N4 | `constructpipe/base.py:37` |
| Composition Root | LAB1 N4 | `construct.py::main` |
| OCP | LAB1 N5 | o registry |
| DIP | LAB1 N4-N5 | `construct()` vs. gerador concreto |
| SRP (violado) | — | `BaseConstructPipeline` (orquestra+executa) |
| LSP (violado) | LAB2 §8 | `propgenerator/base.py:28` vs `QMPropGener.py:44` |
| Lei de Deméter (violada) | LAB2 §10 | `constructpipe/base.py:155,159` |
| CQS (violado) | — | `constructpipe/base.py:186,197` |
| Duck typing vs ABC | LAB2 §7 | `capgenerator/base.py:26` vs `propgenerator/base.py:23` |
| Polimorfismo de subtipo | LAB2 §5 | `base.py:47` |
| Design by Contract (ausente) | LAB3 P1 | `constructpipe/base.py:143` |
| Currying / aplicação parcial | LAB2 §6 | `construct.py:43` |
| DAG vs cadeia | — | `constructpipe/base.py:67-90` |
| Estado e impureza | LAB2 §6 | `capgenerator/base.py:34` |
| Shadowing | LAB3 P2 | `constructpipe/base.py:174-176` |
| Falha adiada | LAB3 P1 | `BlipCapGener.py:23` → `constructpipe/base.py:143` |
| Complexidade acidental | — | decodificação dupla: `BlipCapGener.py:21` + `constructpipe/base.py:143` |
| Data-driven design | LAB1 N5 | `scripts/construct.sh` |
| Estrutura plana vs árvore | LAB3 P3 | `constructpipe/base.py:172-184` |

**Três conceitos sem demonstração executável** (CQS, DAG vs cadeia, complexidade acidental) — eles são propriedades *estruturais* do código, verificáveis por leitura, não por execução. Estão marcados com "—" honestamente, em vez de forçar um demo artificial.

---

*Este manual é o companheiro teórico dos três laboratórios. Ele cobre 31 conceitos em seis famílias — do modelo de objetos do Python aos princípios de arquitetura, passando pela teoria de tipos, teoria funcional e modos de falha — cada um com definição, mecanismo, propósito, a linha exata do RefCap onde aparece, a seção do laboratório que o demonstra, e o seu limite. A última linha de cada entrada é deliberada: nenhum conceito aqui é mandamento, e conhecer a fronteira de cada um é o que transforma vocabulário em julgamento.*
