# A Abstração por trás de `get_capgen_class(nome)(cfg, models)`
## Relatório Completo: Mecânica, Padrões de Design, Teoria e Crítica

---

> **O que é este documento.** A dissecação completa do trecho mais denso do `construct.py` — as linhas 43–47, onde as classes são resolvidas dinamicamente e injetadas no pipeline. O objetivo não é só explicar *o que* o código faz, mas expor **a abstração inteira**: a mecânica do Python que a torna possível (Parte I), os padrões de design que ela instancia (Parte II), a teoria que a formaliza (Parte III), o que ela custa (Parte IV), e como usá-la no seu caso concreto (Parte V).
>
> **Método.** Todas as afirmações foram verificadas contra o código real do repositório (`pipeline/capgenerator/base.py`, `BlipCapGener.py`, `pipeline/constructpipe/base.py`, `pipeline/propgenerator/base.py`) e as mecânicas foram provadas em execução no laboratório companheiro `LAB_registry_factory.py`.
>
> **Como ler.** As Partes I→III sobem em nível de abstração: mecânica → design → teoria. A Parte IV é o contrapeso crítico (o que o padrão custa e quando *não* usá-lo). A Parte V é a aplicação ao seu problema. Se você só tiver tempo para uma coisa, leia o **Capítulo 2** — ele contém a única confusão que realmente importa.

---

# PARTE 0 — O enunciado preciso do problema

O trecho em questão:

```python
# construct.py, linhas 42–49
pretrained_models = load_pretrained_models(cfg)
caption_generator   = get_capgen_class(cfg.caption_generator)(cfg, pretrained_models)
caption_denoiser    = get_denoiser_class(cfg.caption_denoiser)(cfg, pretrained_models)
proposal_generator  = get_propgen_class(cfg.proposal_generator)(cfg, pretrained_models)

construct_pipeline = get_constructpipe_class(cfg.construct_pipeline)(
    cfg, caption_generator, caption_denoiser, proposal_generator, pretrained_models
)
construct_pipeline.construct()
```

**Por que isto parece difícil.** Não é a lógica — a lógica é trivial ("escolha uma classe pelo nome, construa um objeto, passe adiante"). A dificuldade é **sintática e conceitual**, e tem três fontes distintas que se sobrepõem:

1. **O operador `()` significa três coisas diferentes** neste trecho, e a sintaxe não distingue (Cap. 2).
2. **O decorador que popula o registry tem dois níveis de função aninhada**, e a razão do segundo nível não é óbvia (Cap. 3).
3. **O registro acontece num tempo diferente da execução** — no *import*, não na chamada (Cap. 4).

Resolver essas três dissolve a dificuldade inteira. O resto é vocabulário.

---

# PARTE I — A CAMADA MECÂNICA (o que o Python realmente faz)

## Capítulo 1 — Classes são objetos: o fato que habilita tudo

**A regra:** em Python, uma classe **não é uma declaração** processada pelo compilador e descartada. É um **objeto em tempo de execução**, criado pela metaclasse `type`, e que existe como um valor comum.

**Por quê isso importa aqui:** se classes não fossem valores, *nada* deste padrão seria possível. Você não poderia colocar `CapGeneratorBLIP` num dicionário, nem devolvê-la de uma função, nem passá-la como argumento.

**A prova mecânica:** o comando `class X: ...` é *executável*, e é açúcar sintático para uma chamada a `type`:

```python
class CapGeneratorBLIP(BaseCapGen):
    def generate_caption(self, ...): ...

# é aproximadamente equivalente a:
CapGeneratorBLIP = type(
    "CapGeneratorBLIP",              # nome
    (BaseCapGen,),                   # bases
    {"generate_caption": <função>}   # namespace
)
```

Verificado em execução: `type(CapGeneratorBLIP)` devolve `<class 'type'>`, e `isinstance(CapGeneratorBLIP, object)` devolve `True`. **A classe é uma instância de `type`.** Ela vive no namespace do módulo como qualquer variável.

**A consequência direta:** `CAPGEN_REGISTRY[name] = cls` (linha 15 de `base.py`) não é mágica — é uma atribuição de dicionário como qualquer outra, onde o *valor* é uma classe.

**O que isto não é:** não confunda com *reflexão por string* (`eval("CapGeneratorBLIP")`) nem com `getattr(módulo, nome)`. Aqueles são frágeis e inseguros. Aqui não há avaliação de string — há um dicionário explícito cujos valores são objetos-classe. É a diferença entre um *catálogo* e uma *adivinhação*.

---

## Capítulo 2 — O operador `()` é sobrecarregado: **a raiz da confusão**

Este é o capítulo decisivo. A expressão `get_capgen_class('blip')(cfg, models)` parece "uma função que devolve uma função" **porque a sintaxe de chamada é idêntica nos três casos** — mas os três casos são semanticamente distintos.

| Expressão | O que `()` significa | Mecanismo interno | Resultado |
|---|---|---|---|
| `get_capgen_class('blip')` | chamar uma **função** | `function.__call__` | uma **classe** (`type`) |
| `CapGeneratorBLIP(cfg, models)` | **instanciar** uma classe | `type.__call__` → `__new__` + `__init__` | uma **instância** |
| `instancia(vid_list=...)` | chamar um **objeto** | `CapGeneratorBLIP.__call__` (definido em `base.py:39`) | o **resultado** (lista de legendas) |

**A regra geral do Python:** `obj(args)` é açúcar para `type(obj).__call__(obj, args)`. Ou seja, o que determina o comportamento não é a sintaxe, mas **o tipo do objeto à esquerda dos parênteses**:

- Se for uma **função** → executa o corpo dela.
- Se for uma **classe** → `type(classe)` é `type`, e `type.__call__` **constrói um objeto**: aloca via `__new__`, inicializa via `__init__`, devolve a instância.
- Se for uma **instância** → procura `__call__` na classe dela. Se existir, a instância é *chamável*. Se não existir, `TypeError: object is not callable`.

**Por que isto resolve a sua dúvida:** você lia `f(x)(y)` e pensava "função que retorna função". Mas o estágio do meio devolve uma **classe**, e o `(cfg, models)` **não é uma chamada de função — é uma construção de objeto**. A ambiguidade é da sintaxe do Python, não do seu raciocínio.

**Verificado em execução (laboratório, Nível 3):**
```
[1] get_capgen_class            -> function
[2] get_capgen_class('blip')    -> type              (a CLASSE CapGeneratorBLIP)
[3] ...('blip')(cfg, models)    -> CapGeneratorBLIP  (uma INSTÂNCIA)
[4] ...(cfg, models)(vid_list)  -> list              (o RESULTADO)
```

**O conceito que dá nome ao estágio [4]:** um objeto que define `__call__` chama-se **functor** (na tradição C++/POO) ou **function object** / *callable object*. Ele é a ponte entre "objeto com estado" e "função". A instância de `BaseCapGen` **guarda estado** (`self.cfg`, `self.models`, `self.captions`, `self.already_video_names`) **e se comporta como função**. Esse é o truque que faz o `construct()` conseguir escrever `self.caption_generator(vid_list=...)` como se estivesse chamando uma função simples.

---

## Capítulo 3 — Decoradores: o açúcar sintático desmontado

### 3.1 A dessugarização básica

Um decorador é **açúcar sintático para uma reatribuição**. A regra, sem exceções:

```python
@deco
def f(): ...
# ≡
def f(): ...
f = deco(f)
```

Aplicado a classes (isto é a [PEP 3129](https://peps.python.org/pep-3129/), *class decorators*), vale identicamente:

```python
@deco
class C: ...
# ≡
class C: ...
C = deco(C)
```

**A consequência que quase todo mundo esquece:** o decorador **substitui o nome** pelo que ele devolve. Se `deco` devolver `None`, sua classe vira `None`. É por isso que a linha 21 de `base.py` (`return cls`) é **obrigatória** — sem ela, `CapGeneratorBLIP` seria `None` e todo o resto quebraria com um `TypeError` incompreensível.

### 3.2 Por que há DUAS funções aninhadas (o *decorator factory*)

O `REGISTER_CAPGEN` do RefCap não é um decorador — é uma **fábrica de decoradores**:

```python
def REGISTER_CAPGEN(names):              # CAMADA 1 — recebe o NOME
    def register_capgen_cls(cls):        # CAMADA 2 — recebe a CLASSE (o decorador real)
        CAPGEN_REGISTRY[names] = cls     #            registra
        return cls                       #            devolve a classe INTACTA
    return register_capgen_cls           # CAMADA 1 devolve o decorador
```

**A equivalência exata — grave esta, e o mistério acaba:**

```python
@REGISTER_CAPGEN(["blip"])
class CapGeneratorBLIP(BaseCapGen): ...

# ≡

class CapGeneratorBLIP(BaseCapGen): ...
CapGeneratorBLIP = REGISTER_CAPGEN(["blip"])(CapGeneratorBLIP)
#                  └──── camada 1 ────┘└──── camada 2 ────┘
#                  devolve o decorador  recebe a classe
```

**A razão do nível extra:** a sintaxe `@algo` sempre chama `algo(classe)`. Se você quer que o decorador receba **também um argumento seu** (o nome `"blip"`), precisa de um nível a mais: `@FABRICA(arg)` primeiro *executa* `FABRICA(arg)`, e o **resultado** é que decora. O argumento fica capturado numa **closure** — a função interna "lembra" de `names` mesmo depois de `REGISTER_CAPGEN` ter retornado.

**Ordem de execução, provada no laboratório:**
```
[C1] REGISTER_CAPGEN(['blip']) executou -> devolve o decorador real
[C2] register_capgen_cls(CapGeneratorBLIP) executou -> registra e devolve a classe
```
Primeiro a fábrica (com o nome), depois o decorador (com a classe). Sempre nessa ordem.

**Regra prática para reconhecer:** se você vê `@algo` (sem parênteses), `algo` é o decorador. Se você vê `@algo(...)` (com parênteses), `algo` é uma **fábrica** e o decorador é o que ela devolve. Um nível de aninhamento por argumento.

### 3.3 O decorador aqui não transforma nada

Uma sutileza que distingue este uso do caso comum: a maioria dos decoradores **embrulha** a função (`@cache`, `@log` devolvem um *wrapper* diferente do original). Este **não**: ele devolve `cls` sem modificação. Seu efeito é **puramente colateral** — registrar no dicionário.

Isso é bom (a classe permanece exatamente o que era, sem surpresas) mas é também uma ironia digna de nota: **o mecanismo inteiro depende de um efeito colateral**, o que colide frontalmente com "explicit is better than implicit". Voltaremos a isso na Parte IV.

---

## Capítulo 4 — Tempo de import vs. tempo de execução: o alçapão

### 4.1 O modelo de execução dos módulos

Quando o Python importa um módulo pela primeira vez, ele **executa o arquivo de cima a baixo**, uma única vez, e guarda o resultado em `sys.modules`. Imports subsequentes não reexecutam nada.

**A consequência:** o comando `class C: ...` e o decorador aplicado a ele **rodam no momento do import**, não quando alguém usa a classe.

### 4.2 O registro é um efeito colateral de import

Junte 4.1 com o Cap. 3: `@REGISTER_CAPGEN(["blip"])` executa **quando `BlipCapGener.py` é importado**. Logo:

> **Se o módulo nunca for importado, a classe nunca se registra, e `get_capgen_class("blip")` levanta `ValueError: Capgen name blip not registered`** — mesmo que o arquivo exista, esteja correto e a classe esteja lá.

**É por isso que `pipeline/capgenerator/__init__.py` tem exatamente duas linhas:**
```python
from .base import *
from .BlipCapGener import *   # ← existe pelo EFEITO de registrar, não pelos nomes
```

Esse `import *` **não está importando nomes para uso** — está **forçando a execução do módulo** para popular o registry. Ele é *load-bearing*: remova-o e o sistema quebra.

**Isto refina uma crítica que fizemos antes.** Nós apontamos os `import *` do RefCap como violação de higiene de namespace (e são). Mas aqui o import em si é **necessário**; o pecado é a *forma*. `from . import BlipCapGener` teria o mesmo efeito de registro sem colapsar o namespace. A lição: **antes de "consertar" um import aparentemente inútil, verifique se ele não está sustentando um efeito colateral.**

### 4.3 A fragilidade que isto introduz

Este mecanismo cria uma dependência **invisível e ordenada**: o conteúdo do registry depende de *quais módulos foram importados até agora*. Consequências reais:

- Um erro de digitação no `__init__.py` produz um `ValueError` em runtime, longe da causa.
- Ferramentas de análise estática e *linters* frequentemente marcam o `import *` como "não utilizado" — e removê-lo quebra tudo.
- A ordem de import pode importar se houver dependências circulares entre módulos que se registram.

É complexidade **acidental** introduzida pelo padrão. Real, mas geralmente aceita em troca da extensibilidade.

---

## Capítulo 5 — A cadeia completa, traçada

Juntando os quatro capítulos, eis a linha do tempo completa de `get_capgen_class(cfg.caption_generator)(cfg, pretrained_models)`:

```
── TEMPO DE IMPORT ────────────────────────────────────────────────
 1. `import construct` executa `from pipeline.capgenerator import *`
 2. que executa `pipeline/capgenerator/__init__.py`
 3. que executa `base.py`:
       - cria o dict vazio CAPGEN_REGISTRY
       - define REGISTER_CAPGEN e get_capgen_class
       - avalia @REGISTER_CAPGEN(["base","minigpt"]) → registra BaseCapGen
 4. que executa `BlipCapGener.py`:
       - avalia @REGISTER_CAPGEN(["blip"]) → registra CapGeneratorBLIP
    ► ESTADO: CAPGEN_REGISTRY = {"base": BaseCapGen,
                                 "minigpt": BaseCapGen,      ← MESMO objeto
                                 "blip": CapGeneratorBLIP}

── TEMPO DE EXECUÇÃO ──────────────────────────────────────────────
 5. cfg = parser.parse_args(...)          → cfg.caption_generator = "blip"
 6. get_capgen_class("blip")              → devolve a CLASSE CapGeneratorBLIP
 7. CapGeneratorBLIP(cfg, models)         → type.__call__ → __new__ + __init__
       - __init__ do BLIP chama super().__init__(cfg, models)   [herança]
       - guarda cfg, models, carrega o cache de legendas do disco
       - guarda models['cap_gen_model'] e models['cap_gen_processor']
    ► resultado: uma INSTÂNCIA com toda a configuração absorvida

 8. essa instância é passada ao pipeline   [injeção de dependência]
 9. construct() chama self.caption_generator(vid_list=...)
       → CapGeneratorBLIP.__call__ (herdado de BaseCapGen:39)
       → loop por vídeo → self.generate_caption(...)
       → DESPACHO DINÂMICO: vai para a versão do BLIP (BlipCapGener:17),
         não para a da base (base.py:50)
```

**Repare no passo 4:** `"base"` e `"minigpt"` apontam para o **mesmo objeto-classe** `BaseCapGen`. Isso é um *alias*, e é o mecanismo pelo qual o modo MiniGPT "funciona": ele usa a classe base, cujo `generate_caption` (linha 50–51) apenas verifica que as legendas já existem em disco, geradas por script externo.

---

# PARTE II — A CAMADA DE DESIGN (os padrões e o porquê deles)

A Parte I explicou *como* funciona. Esta explica *por que* alguém escreveria assim.

## Capítulo 6 — Registry Pattern

**O que é:** um mapa global `nome → implementação`, povoado por auto-registro das implementações.

**O problema que resolve.** A alternativa ingênua:
```python
def get_capgen_class(nome):
    if   nome == "blip":    return CapGeneratorBLIP
    elif nome == "minigpt": return BaseCapGen
    elif nome == "llava":   return CapGeneratorLLaVA
```
Três defeitos: **(a)** a função genérica precisa *conhecer* todas as implementações específicas — dependência na direção errada; **(b)** cada extensão **modifica** código existente; **(c)** o módulo da factory precisa **importar** todos os geradores, criando um nó de dependências.

**Como o registry corrige:** a factory conhece apenas o dicionário. Cada implementação **se anuncia**. A seta de dependência inverte: em vez de `factory → implementações`, temos `implementações → registry ← factory`.

**O limite:** o registry é **estado global mutável**. Isso traz os problemas usuais — ordem de inicialização importa, testes podem contaminar uns aos outros, e não há isolamento por escopo. Em sistemas maiores, injeta-se um *container* explícito em vez de um global.

## Capítulo 7 — Factory Function e Service Locator

**Factory** (`get_capgen_class`): uma função cuja responsabilidade é **produzir** (ou selecionar) um objeto, escondendo do chamador a decisão de *qual*. Aqui é uma variante específica: ela devolve a **classe**, não a instância — às vezes chamada de *class factory*. Quem instancia é o chamador.

**Por que devolver a classe e não a instância?** Porque separa **seleção** de **construção**. O `main()` fica com a liberdade de decidir *como* construir (quais argumentos passar). Se a factory devolvesse a instância pronta, ela precisaria conhecer `cfg` e `models` — mais acoplamento.

**Service Locator:** o par (registry + factory) forma este padrão — um ponto central onde se *pede* uma dependência pelo nome. Vale saber que ele é considerado um **anti-padrão por alguns autores** (Mark Seemann é o crítico mais conhecido), pelo motivo do Cap. 16: ele esconde as dependências em vez de declará-las. A alternativa preferida é injeção pura. Neste projeto, o custo é aceitável porque a seleção é dirigida por configuração de linha de comando — que é exatamente o caso de uso legítimo do Service Locator.

## Capítulo 8 — Strategy Pattern

**O que é:** encapsular algoritmos intercambiáveis atrás de uma interface comum, permitindo trocá-los em runtime.

**Onde está:** `BaseCapGen` / `CapGeneratorBLIP` são *estratégias* de legendagem; `QMPropGenerator` é uma estratégia de segmentação; os denoisers, estratégias de limpeza. O pipeline consome qualquer uma.

**A distinção que importa:** Strategy é sobre *ter alternativas*; o Registry é sobre *como escolher entre elas*. São ortogonais — você pode ter Strategy com um `if/elif` (sem registry), ou registry sem estratégias reais (com uma implementação só). O RefCap combina os dois.

## Capítulo 9 — Template Method

**O que é:** a classe base define o **esqueleto** de um algoritmo, deixando *pontos de extensão* (*hooks*) para as subclasses preencherem.

**Onde está — duas instâncias distintas no mesmo projeto:**

1. **`BaseCapGen.__call__`** (base.py:39–48) fixa o esqueleto "itere pelos vídeos, monte o caminho, valide, delegue" e deixa `generate_caption` como *hook* (linha 50). O `CapGeneratorBLIP` preenche o hook (BlipCapGener.py:17) — e é ali, e só ali, que a subclasse difere.

2. **`BaseConstructPipeline.construct()`** fixa a **ordem das sete etapas**. Este é um Template Method em escala arquitetural: a ordem é invariante, os *executores* de cada etapa são injetados.

**Por que este padrão é poderoso aqui:** ele localiza a variação. Para escrever um gerador novo, você não precisa entender o loop de vídeos, o cache, nem o tratamento de arquivo inexistente — **só o hook**. A base cuida do resto, uma vez, corretamente.

## Capítulo 10 — Injeção de Dependência, Inversão de Controle e Composition Root

Aqui está o conceito que **refina o seu modelo mental** — você havia lido a `BaseConstructPipeline` como "o núcleo que reúne as classes". É quase isso, mas a distinção precisa importa muito.

**Injeção de Dependência (por construtor):** o pipeline **não constrói** seus colaboradores — ele os **recebe prontos**:
```python
def __init__(self, cfg, caption_generator, caption_denoiser, proposal_generator, models):
    self.caption_generator = caption_generator   # recebido, não criado
```
Compare com o que ele *poderia* ter feito (e que seria pior):
```python
def __init__(self, cfg):
    self.caption_generator = CapGeneratorBLIP(cfg, ...)   # ← acoplado ao concreto
```

**Inversão de Controle:** o nome do princípio geral. Normalmente, um módulo controla suas dependências (ele as cria). Aqui isso é *invertido*: o controle sobe para quem monta o sistema.

**Composition Root:** o **único lugar** que conhece todas as escolhas concretas e monta o grafo de objetos. No RefCap, é o `main()` do `construct.py`. É por design que ele é o único lugar onde as strings `"blip"`, `"qm"`, `"window"` viram objetos.

**Os dois papéis, que é fácil fundir:**

| | **Composition Root** (`main()`) | **Orquestrador** (`construct()`) |
|---|---|---|
| Decide | *quais* implementações existem | a *ordem* dos passos |
| Conhece | os nomes concretos ("blip", "qm") | apenas os contratos |
| Muda quando | você adiciona/troca implementações | o algoritmo de alto nível muda |

**A analogia:** o `main()` é o empresário que contrata os músicos; o `construct()` é o maestro que rege a partitura **sem saber quem foi contratado**. E é justamente *por não saber* que ele funciona com qualquer gerador — inclusive um que você escreva amanhã.

**Portanto, respondendo diretamente à sua leitura:** a `BaseConstructPipeline` **não reúne** as classes — ela as **recebe**. Quem reúne é o `main()`. O pipeline é o *orquestrador*, não o *montador*. Essa separação é o que torna o pipeline testável (você injeta dublês) e reutilizável.

## Capítulo 11 — Como os padrões se compõem

Nenhum destes padrões faz muito sozinho. O valor está na composição:

```
        construct.sh  (uma string: "blip")
              │
              ▼
    ┌─────────────────────────────────────────┐
    │  Registry  ──── povoado por ────► Decorator Factory   │  ← quem existe
    │     │                             (no import)         │
    │     ▼                                                 │
    │  Factory  ─── seleciona ──► a Classe                  │  ← qual usar
    └─────────────────────────────────────────┘
              │
              ▼  instanciação com (cfg, models)
    ┌─────────────────────────────────────────┐
    │  Composition Root (main)  ── monta ──►  │              ← como construir
    │  Injeção de Dependência   ── entrega ─► │
    └─────────────────────────────────────────┘
              │
              ▼
    ┌─────────────────────────────────────────┐
    │  Orquestrador (construct)  ── Template Method: fixa a ordem  │
    │      chama os colaboradores ── Strategy: são intercambiáveis │
    │      via despacho dinâmico ── Polimorfismo                   │
    └─────────────────────────────────────────┘
```

Cada padrão responde a **uma pergunta diferente**: *quem existe?* (registry) → *qual usar?* (factory) → *como construir?* (composition root + DI) → *em que ordem?* (template method) → *como variar?* (strategy + polimorfismo).

---

# PARTE III — A CAMADA TEÓRICA

## Capítulo 12 — Currying e aplicação parcial: a sua intuição, formalizada

Você intuiu "uma sequência de composições de funções escolhidas conforme os parâmetros". Isso está **essencialmente correto**, e a formalização precisa é:

```
get_capgen_class   : Nome              ──►  Classe
Classe.__init__    : (Cfg × Models)    ──►  Instância        [aplicação parcial]
Instância.__call__ : VidList           ──►  Captions         [a função "real"]
```

Lendo como uma função curried:

```
capgen : Nome → Cfg → Models → VidList → Captions
```

**O estágio do meio é literalmente aplicação parcial.** Você fornece `cfg` e `models` *antes*, e o que sobra é uma função **unária** `vid_list ↦ captions`. O objeto é um **closure com nome**: ele captura o ambiente (configuração + modelos) e expõe uma interface mínima.

**É por isso que o `construct()` fica tão limpo.** Ele escreve `self.caption_generator(vid_list=self.vid_list)` — uma aplicação simples — porque toda a complexidade de configuração foi absorvida numa etapa anterior. A aplicação parcial é o que permite que o orquestrador não saiba nada sobre `cfg` ou `models` no ponto de uso.

**A equivalência funcional:** em uma linguagem funcional, você escreveria isso com `partial`:
```python
from functools import partial
gerar = partial(gerar_legendas_blip, cfg=cfg, models=models)
captions = gerar(vid_list)     # a mesma estrutura, sem classes
```
A versão com classe faz o mesmo, **mais** guardar estado mutável entre chamadas (o cache `already_video_names`).

### Onde a analogia com composição de funções **quebra** — três pontos

Conhecer os limites da analogia é o que impede você de raciocinar errado sobre o código.

**1. Não é uma cadeia linear — é um DAG.** Olhando o `construct()` real:
```python
captions          = caption_generator(vid_list)
features          = compute_frame_features(vid_list, captions)
scores            = compute_capframe_scores(vid_list, captions, features, path1)
denoised_captions = caption_denoiser(vid_list, captions, scores)
denoised_scores   = compute_capframe_scores(vid_list, denoised_captions, features, path2)
proposals         = proposal_generator(vid_list, denoised_captions, denoised_scores, features)
tree_meta         = build_tree_meta(proposals)
```
`features` é calculado **uma vez** e consumido por **três** passos distintos. `captions` alimenta três. Há *fan-out*. A notação `f∘g∘h` descreve uma cadeia; isto é um **grafo acíclico dirigido**. Modelar como cadeia leva a conclusões erradas sobre o que pode ser reordenado ou paralelizado.

**2. As funções não são puras.** As instâncias carregam **estado** (`self.captions`, `self.already_video_names`) e produzem **efeitos colaterais** (escrita em `.jsonl`, leitura de cache). Chamar duas vezes **não** produz o mesmo resultado — a segunda vez pula o que já foi feito. Transparência referencial não vale aqui.

**3. Seleção não é composição — é despacho.** A escolha da implementação acontece **antes** e **fora** da composição, num estágio de resolução (registry). Formalmente, é uma função de um *espaço de nomes* para um *espaço de implementações* — mais parecido com uma tabela de despacho de um interpretador do que com um combinador funcional.

**A formulação honesta, então:** o sistema é um **pipeline com estado, estruturado como DAG, cujos nós são selecionados por despacho e parcialmente aplicados na montagem**. Bem menos elegante que "composição de funções", mas é o que é — e a precisão paga.

## Capítulo 13 — Polimorfismo: qual tipo está atuando aqui

"Polimorfismo" é um termo sobrecarregado. Existem três tipos clássicos, e vale saber qual é qual:

| Tipo | O que é | Presente aqui? |
|---|---|---|
| **Ad-hoc** (sobrecarga) | mesmo nome, implementações por tipo de argumento | não (Python não tem sobrecarga) |
| **Paramétrico** (genéricos) | mesmo código opera sobre qualquer tipo | não centralmente |
| **De subtipo** (inclusão) | um subtipo substitui o supertipo | **sim — é o mecanismo central** |

**O mecanismo concreto: despacho dinâmico (late binding).** Quando `BaseCapGen.__call__` (linha 47) executa `self.generate_caption(...)`, o Python **não sabe em tempo de escrita** qual método será chamado. Ele resolve em runtime, procurando na **MRO** (*Method Resolution Order*) do tipo real de `self`. Como `self` é um `CapGeneratorBLIP`, a busca encontra a versão da subclasse (BlipCapGener.py:17) antes da versão da base (base.py:50).

**Por que isto engana ao ler:** se você abrir só `base.py`, verá um `generate_caption` que só faz um `assert` e concluirá — erradamente — que nada acontece. A implementação real está em *outro arquivo*. **Este é o custo de leitura do polimorfismo: o fluxo de controle não é local ao texto.**

### 13.1 As duas filosofias de abstração — e o RefCap usa AS DUAS

Uma descoberta desta análise, que vale destacar por ser um achado real de inconsistência:

- **`BaseCapGen` (capgenerator/base.py:26)** é uma classe comum. O contrato é **implícito** — *duck typing*. Nada força uma subclasse a implementar `generate_caption`; se ela não o fizer, herda a versão da base silenciosamente.
- **`BasePropGen` (propgenerator/base.py:23)** herda de **`ABC`** e marca `__call__` com **`@abstractmethod`**. O contrato é **explícito e imposto** — tentar instanciar uma subclasse que não implementa `__call__` levanta `TypeError` na hora.

São as duas abordagens à abstração — **estrutural** (duck typing / `Protocol`, [PEP 544](https://peps.python.org/pep-0544/)) versus **nominal** (ABC, [PEP 3119](https://peps.python.org/pep-3119/)) — coexistindo no mesmo projeto sem razão aparente. É inconsistência de design: dois módulos irmãos, com o mesmo papel arquitetural, usando mecanismos de garantia diferentes.

### 13.2 Um defeito real: violação do LSP no contrato abstrato

Verificando as assinaturas:

```python
# propgenerator/base.py:28  — o contrato ABSTRATO declara 3 parâmetros
@abstractmethod
def __call__(self, vid_list, captions, scores): pass

# propgenerator/QMPropGener.py:44  — a implementação exige 4
def __call__(self, vid_list, captions, scores, all_frame_features): ...

# constructpipe/base.py:86  — e o chamador passa 4
proposals = self.proposal_generator(vid_list=..., captions=..., scores=...,
                                     all_frame_features=features)
```

**A classe abstrata mente sobre o contrato.** Qualquer código escrito contra a assinatura declarada em `BasePropGen` quebraria com o `QMPropGenerator`. Isto é uma violação do **Princípio de Substituição de Liskov**: a subclasse *fortalece* a pré-condição (exige mais um argumento obrigatório), tornando-a não-substituível pela base.

Ironicamente, o mecanismo de ABC — que existe justamente para *impor* contratos — não pega isso: `@abstractmethod` verifica apenas a **existência** do método, nunca a **compatibilidade da assinatura**. É uma limitação real do ABC que vale conhecer: ele garante presença, não conformidade.

## Capítulo 14 — A direção das setas: OCP e DIP

O valor arquitetural do padrão inteiro se resume ao que ele faz com a **direção das dependências**.

**Antes (ingênuo):**
```
   factory ────► CapGeneratorBLIP
       │────────► BaseCapGen
       └────────► CapGeneratorLLaVA
   (o genérico depende dos específicos — cada novo específico MODIFICA o genérico)
```

**Depois (registry):**
```
   CapGeneratorBLIP ────┐
   BaseCapGen ──────────┼──► REGISTRY ◄──── factory
   CapGeneratorLLaVA ───┘
   (os específicos dependem do genérico — adicionar um específico não toca em nada)
```

**Open/Closed Principle:** o sistema fica *aberto para extensão* (novo arquivo + decorador) e *fechado para modificação* (nenhuma linha existente muda). Verificado no laboratório (Nível 5): adicionar um `CapGeneratorLLaVA` não exigiu editar registry, factory nem pipeline.

**Dependency Inversion Principle:** o `construct()` (alto nível) não depende do `CapGeneratorBLIP` (baixo nível); ambos dependem de uma abstração — aqui, o contrato implícito "é chamável com `vid_list` e devolve legendas".

## Capítulo 15 — Configuração como linguagem: *data-driven design*

O nível de abstração mais alto deste desenho: **o grafo de objetos do programa é determinado por dados, não por código.**

O `construct.sh` é, efetivamente, uma **DSL minúscula**:
```bash
caption_generator=blip
caption_denoiser=window
proposal_generator=qm
construct_pipeline=base
```
Quatro strings que **selecionam quatro implementações** e determinam o comportamento do sistema inteiro. O registry é a **tabela de despacho** dessa linguagem; o `main()` é o seu **interpretador**.

**A generalização conceitual:** você deslocou decisões do *espaço do código* (que exige recompilar/reescrever) para o *espaço dos dados* (que exige apenas trocar um valor). É o mesmo princípio por trás de tabelas de configuração de compiladores, sistemas de plugins, e frameworks de ML (o `model_name` do HuggingFace faz exatamente isto). É a razão pela qual o RefCap consegue publicar resultados para BLIP *e* MiniGPT *e* variações de denoiser sem manter quatro versões do código.

**O trade-off:** o comportamento do sistema deixa de ser legível no código e passa a ser legível apenas no **par (código, configuração)**. Ler `construct.py` isolado não te diz o que o sistema faz — você precisa do `.sh` junto. Isso é o que torna a análise de um repo assim mais trabalhosa: **a fonte de verdade está espalhada por duas linguagens.**

---

# PARTE IV — ANÁLISE CRÍTICA (o contrapeso)

Todo padrão tem custo. Um relatório que só louvasse este seria propaganda, não análise.

## Capítulo 16 — O que este padrão custa

**1. Perda de rastreabilidade estática.** Lendo `get_capgen_class(cfg.caption_generator)`, você **não consegue saber** qual classe será usada. Nem você, nem a IDE ("ir para definição" falha), nem o `mypy` (o tipo de retorno é essencialmente `type`). Para descobrir, é preciso caçar decoradores espalhados por vários arquivos. **Foi exatamente esse custo que você pagou** ao dissecar o repositório.

**2. Erros deslocados para runtime.** Um nome errado (`caption_generator=blipp`) não é pego por nenhuma ferramenta estática — só explode em execução, possivelmente depois de carregar vários GB de modelos.

**3. Estado global mutável.** O registry é um dicionário de módulo. Testes podem contaminar uns aos outros; não há escopo nem isolamento.

**4. Dependência de efeito colateral de import.** Cap. 4.3 — frágil, invisível, e conflita com "explicit is better than implicit".

**5. Imposto de indireção.** Para entender um fluxo, o leitor salta: config → factory → registry → decorador → classe → método herdado → método sobrescrito. Sete saltos onde uma chamada direta teria zero. **O custo de leitura é real e recorrente.**

**6. Dependências escondidas (a crítica ao Service Locator).** Uma classe que pede coisas ao locator não *declara* do que precisa na assinatura. Aqui isso é mitigado porque o `cfg` e `models` são injetados no construtor — mas o `models` é um **dicionário genérico**, o que reintroduz o problema: `CapGeneratorBLIP` exige `models['cap_gen_model']` sem que nada na assinatura o diga. É uma dependência implícita.

## Capítulo 17 — Quando NÃO usar este padrão

O anti-dogma. Este padrão **só se paga sob condições específicas**:

| Use registry+factory quando | Não use quando |
|---|---|
| Há **3+ implementações reais** intercambiáveis | Há **uma só** (YAGNI — a indireção é puro custo) |
| Terceiros vão adicionar implementações (plugins) | Todas as implementações são suas e estáveis |
| A escolha é feita por **configuração externa** | A escolha é conhecida em tempo de escrita |
| O conjunto cresce com frequência | O conjunto é fixo há anos |

**Se há duas implementações e elas não vão mudar, um `if/else` é melhor.** É mais legível, estaticamente verificável, e a IDE navega. Trocar clareza por extensibilidade que você não vai usar é over-engineering — a versão em código do problema que discutimos na arquitetura limpa.

**Um critério simples:** se o `if/elif` que o registry substitui teria menos de ~5 ramos e não cresce, o registry provavelmente não se paga.

## Capítulo 18 — Respostas comuns porém erradas

**"É uma função que retorna uma função."** Errado — retorna uma **classe**. A confusão vem da sobrecarga do `()` (Cap. 2). A distinção importa porque o estágio seguinte não é uma chamada, é uma **construção de objeto** com semântica própria (`__new__`/`__init__`, herança, MRO).

**"O decorador `@REGISTER_CAPGEN([...])` modifica a classe."** Errado — ele devolve `cls` **intacta** (linha 21). O efeito é *puramente* colateral (registro). Diferente de `@cache` ou `@property`, que substituem o objeto decorado.

**"O `import *` no `__init__.py` é inútil e pode ser removido."** Errado e perigoso — ele é *load-bearing* (Cap. 4.2). Removê-lo esvazia o registry.

**"A `BaseConstructPipeline` reúne/instancia as classes."** Impreciso — ela **recebe** instâncias prontas. Quem monta é o `main()` (Cap. 10). Confundir os dois papéis é confundir orquestração com composição, e é o que impede de enxergar a Inversão de Controle.

**"É só composição de funções."** Boa intuição, imprecisa em três pontos (Cap. 12): é um DAG (não cadeia), com estado e efeitos colaterais (não puras), e a seleção é despacho (não composição).

**"Este padrão é sempre melhor que `if/elif`."** Dogma. Ele é melhor sob condições específicas (Cap. 17); fora delas, é indireção sem contrapartida.

## Capítulo 19 — Defeitos verificados na implementação do RefCap

Distinguindo o *padrão* (bom) da *implementação dele aqui*:

1. **Duplicação massiva de código.** Os cinco registries (`capgenerator`, `denoiser`, `propgenerator`, `constructpipe`, `retrievepipe`) são **cópias literais** da mesma lógica de ~15 linhas, com os nomes trocados. É violação de DRY: o *conhecimento* "como registrar implementações" está replicado cinco vezes. Uma única função genérica `make_registry("capgen")` devolveria `(REGISTRY, REGISTER, getter)` para todos.

2. **Inconsistência de mecanismo de abstração.** `BaseCapGen` usa duck typing; `BasePropGen` usa `ABC`+`@abstractmethod` (Cap. 13.1). Mesmo papel, garantias diferentes, sem justificativa.

3. **Violação de LSP no contrato abstrato.** `BasePropGen.__call__` declara 3 parâmetros; `QMPropGenerator.__call__` exige 4 (Cap. 13.2).

4. **Nenhuma validação de contrato no registro.** O decorador aceita **qualquer** classe. Registrar algo que não implementa a interface só falha muito depois, no ponto de uso. Um `Protocol` com `runtime_checkable` permitiria validar no momento do registro — falha imediata, em vez de tardia.

5. **`models` como dicionário genérico.** Dependências implícitas (Cap. 16, item 6). Um dataclass tipado tornaria explícito quem precisa de quê.

---

# PARTE V — APLICAÇÃO PRÁTICA AO SEU PROBLEMA

Toda esta teoria converge num ponto útil: **é este padrão que te dá o caminho limpo para "uma legenda por cena"**, agora que sabemos que `prop_max_cnt=1` não resolve.

Como o `proposal_generator` é selecionado por registry, você pode acrescentar uma estratégia nova **sem tocar no `QMPropGenerator`**. São três adições e zero modificações:

**1. Criar `pipeline/propgenerator/WholePropGener.py`:**
```python
from .base import BasePropGen, REGISTER_PROPGEN

@REGISTER_PROPGEN(["whole"])
class WholePropGenerator(BasePropGen):
    """Um segmento por vídeo: a cena inteira. Sem detecção de fronteiras."""
    def __init__(self, cfg, models) -> None:
        super().__init__(cfg, models)
        # (guarde aqui o que precisar de `models`)

    def __call__(self, vid_list, captions, scores, all_frame_features):
        # mesma assinatura do QMPropGenerator (ver Cap. 13.2: a da base está errada)
        # devolver a MESMA estrutura de proposals, com um único segmento
        # [0, VID_LEN] por vídeo, e a legenda do frame de maior score.
        ...
```

**2. Registrar o módulo em `pipeline/propgenerator/__init__.py`:**
```python
from .base import *
from .QMPropGener import *
from .WholePropGener import *      # ← sem isto, o registro nunca acontece (Cap. 4.2)
```

**3. Liberar o nome no `config/cfg.py` (linha 76):**
```python
proposal_generator: str = field(
    default="qm",
    metadata={"choices": ["qm", "whole"]}     # ← o argparse IMPÕE choices (verificado)
)
```

Depois, é só `proposal_generator=whole` no `construct.sh`. **Nenhuma linha do `QMPropGenerator` foi tocada** — é o OCP em ação, e a razão pela qual vale a pena ter entendido este padrão a fundo.

**O que ainda precisa ser decidido** (e que a Parte I–III não resolve, porque é questão de dados): qual legenda representa a cena inteira. O `QMPropGenerator` escolhe a do frame de maior score (linha 133); a mesma política é o ponto de partida natural — mas para cenas com muito movimento, ela pode ser insuficiente, e só os seus vídeos dirão.

---

# PARTE VI — Roteiro de estudo

Para consolidar, na ordem de retorno decrescente:

1. **Rode o `LAB_registry_factory.py`** e faça os exercícios 1 e 4 — eles quebram o mecanismo de duas formas diferentes e você *vê* o que cada peça sustentava.
2. **Reescreva o registry do zero**, sem olhar, a partir da descrição: "um dict, um decorador parametrizado que registra, uma factory que busca". Comparar com o original ensina mais que ler dez vezes.
3. **Trace um fluxo real** com `pdb` ou prints: coloque um `print(type(x))` em cada estágio da cadeia do Cap. 5 e confirme os quatro tipos.
4. **Estude a MRO**: `CapGeneratorBLIP.__mro__` e entenda por que `self.generate_caption` resolve para a subclasse.
5. **Implemente o `WholePropGenerator`** (Parte V) — é o exercício que une tudo: registry, herança, contrato, e o seu objetivo real.
6. **Leia o [PEP 3129](https://peps.python.org/pep-3129/)** (class decorators) e o [PEP 318](https://peps.python.org/pep-0318/) (decorators) como fontes primárias.

---

*Este relatório dissecou o trecho mais denso do `construct.py` em quatro camadas: a mecânica do Python que o torna possível (classes como objetos, a sobrecarga do operador de chamada, decoradores parametrizados, o tempo de import), os padrões de design que ele instancia (Registry, Factory, Service Locator, Strategy, Template Method, Injeção de Dependência), a teoria que o formaliza (aplicação parcial, despacho dinâmico, inversão de dependências, design orientado a dados), e a crítica honesta do que ele custa e quando não usá-lo. A conclusão prática é a receita do `WholePropGenerator` — três adições, zero modificações — que só é possível justamente por causa da abstração aqui descrita.*
