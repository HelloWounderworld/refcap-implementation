# Levantamento de PEPs — CLEAN CODE
## Catálogo de Trabalho Focado em Código Limpo (nível micro)

---

> **Escopo.** Este catálogo cobre *puramente* os PEPs relevantes para **Código Limpo** — o nível micro: como escrever cada função, classe, expressão de forma idiomática, legível e manutenível. A parte de **Arquitetura Limpa** (estrutura de dependências e fronteiras) está no catálogo irmão (`Levantamento_PEPs_CleanArchitecture.md`).
>
> **Por que esta lista é longa.** A força do Python é ser uma linguagem *expressiva*, cheia de idiomas que servem a código limpo — context managers, generators, dataclasses, decorators, type hints. Por isso há *muitos* PEPs de clean code: cada um padroniza um idioma que torna o código mais claro. Dominá-los é dominar o vocabulário Pythônico de escrever bem.
>
> **Como usar.** Três camadas de prioridade (Tier 1 → 3), formato de checklist. Comece pela Tier 1. Cada PEP em `https://peps.python.org/pep-XXXX/`.
>
> **Nota de método.** Curado a partir do índice oficial (peps.python.org). Selecionei o subconjunto de clean code e deixei de fora o irrelevante (C API, empacotamento, governança) e o nichado.

---

# PARTE 1 — Índices úteis para navegar

- [ ] **Índice geral (PEP 0)** — `https://peps.python.org/`
- [ ] **Tópico: Typing** — `https://peps.python.org/topic/typing/` — relevante para a parte de type hints deste catálogo.

---

# PARTE 2 — TIER 1: A fundação do código limpo (comece aqui)

O tripé imprescindível. Se você ler só estes, já escreve código visivelmente mais limpo.

| ☐ | PEP | Título | Status | Por que importa para clean code |
|---|-----|--------|--------|-----------------|
| ☐ | **20** | The Zen of Python | Active | A filosofia — os valores que guiam toda decisão de código. *Já temos tratado completo.* |
| ☐ | **8** | Style Guide for Python Code | Active | Estilo, nomenclatura, formatação, organização de imports. A base do "idiomático se lê no piloto automático". Curto e obrigatório. |
| ☐ | **257** | Docstring Conventions | Active | Como escrever docstrings — o comentário-contrato que documenta a interface sem mentir. |

---

# PARTE 3 — TIER 2: Os idiomas do dia a dia

Os mecanismos que você usa (ou deveria usar) o tempo todo ao escrever funções e classes. Leia conforme o tópico surgir na análise do RefCap.

## 3.1 Type hints — assinaturas auto-documentadas
*Contratos verificáveis no nível da função — a assinatura diz o que entra e o que sai.*
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **484** | Type Hints | Final | ★ A fundação. `def f(x: int) -> str` documenta o contrato de forma checável. |
| ☐ | **585** | Generics in Standard Collections | Final | `list[int]` em vez de `List[int]` — sintaxe moderna e limpa. |
| ☐ | **604** | Union Types as `X \| Y` | Final | `int \| None` em vez de `Optional[int]` — mais legível. |

## 3.2 Objetos de dados — menos boilerplate
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **557** | Data Classes | Final | ★ `@dataclass` — elimina o boilerplate de `__init__`/`__repr__`/`__eq__`. Um dado nomeado e claro em vez de uma tupla anônima. |
| ☐ | **589** | TypedDict | Final | Dar estrutura e tipo a dicionários — em vez do dict cru anônimo (como as `frame_captions` do RefCap). |

## 3.3 Gerência de recursos
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **343** | The "with" Statement | Final | ★ Context managers — o "faça X, garanta desfazer X" (abrir/fechar, adquirir/liberar), à prova de exceção e de esquecimento. |

## 3.4 Composição de comportamento
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **318** | Decorators for Functions and Methods | Final | Envolver comportamento (log, cache, validação) sem poluir a lógica — separar preocupações transversais. |
| ☐ | **3129** | Class Decorators | Final | O mesmo, aplicado a classes. |

## 3.5 Iteração e avaliação preguiçosa
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **234** | Iterators | Final | O protocolo (`__iter__`/`__next__`) que faz o `for` funcionar — a base de tudo que itera. |
| ☐ | **255** | Simple Generators | Final | `yield` — produção sob demanda, memória constante em vez de linear. |
| ☐ | **289** | Generator Expressions | Final | `(x for x in ...)` — lazy e composável, em vez de materializar tudo. |

## 3.6 Tratamento de erros
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **3134** | Exception Chaining (`raise ... from`) | Final | ★ Preservar a exceção original ao relançar — *a lacuna que a auditoria de Anaya apontou.* |
| ☐ | **352** | Required Superclass for Exceptions | Final | A hierarquia de exceções (herdar de `Exception`) — a base de erros bem estruturados. |

---

# PARTE 4 — TIER 3: Aprofundamento por tópico (sob demanda)

Relevantes, mas leia só quando o assunto específico aparecer.

## 4.1 Type hints — teoria e tópicos avançados
| ☐ | PEP | Título | Status | Quando ler |
|---|-----|--------|--------|-----------|
| ☐ | **483** | The Theory of Type Hints | Final | Para entender variância e subtipos por trás do 484. |
| ☐ | **526** | Syntax for Variable Annotations | Final | Ao anotar variáveis e atributos, não só funções. |
| ☐ | **3107** | Function Annotations | Final | A raiz histórica das anotações (contexto). |
| ☐ | **673** | Self Type | Final | Ao tipar métodos que retornam a própria instância. |
| ☐ | **695** | Type Parameter Syntax | Final | A sintaxe moderna de genéricos (3.12+). |
| ☐ | **563 / 649** | Postponed / Deferred Evaluation of Annotations | Final / Accepted | O comportamento de avaliação de anotações (3.14+). |

## 4.2 Iteração e concorrência — avançado
| ☐ | PEP | Título | Status | Quando ler |
|---|-----|--------|--------|-----------|
| ☐ | **342** | Coroutines via Enhanced Generators | Final | Para entender a raiz das corrotinas. |
| ☐ | **380** | `yield from` (Delegating to Subgenerator) | Final | Ao compor generators aninhados. |
| ☐ | **525** | Asynchronous Generators | Final | Se entrar em código assíncrono. |

## 4.3 Erros — avançado
| ☐ | PEP | Título | Status | Quando ler |
|---|-----|--------|--------|-----------|
| ☐ | **409 / 415** | Suppressing Exception Context | Final | Controle fino da cadeia (`raise ... from None`). |
| ☐ | **654** | Exception Groups and `except*` | Final | Múltiplas exceções simultâneas (3.11+). |

## 4.4 Clareza de fluxo e idiomas limpos
| ☐ | PEP | Título | Status | Quando ler |
|---|-----|--------|--------|-----------|
| ☐ | **634 / 635 / 636** | Structural Pattern Matching (spec / motivação / tutorial) | Final | Ao usar `match` — clareza em despacho por estrutura (3.10+). |
| ☐ | **572** | Assignment Expressions (walrus `:=`) | Final | Um ótimo *estudo de caso* do trade-off legibilidade vs. concisão (o debate do Zen). |
| ☐ | **428** | The `pathlib` module | Final | Manipulação de caminhos orientada a objetos — idioma limpo vs. `os.path`. |
| ☐ | **362** | Function Signature Object | Final | Ao inspecionar assinaturas (metaprogramação, decorators). |

---

# PARTE 5 — Onde focar (a orientação)

**Se você tem pouco tempo:** leia **PEP 8, 20, 257** (a fundação) e domine **quatro idiomas** — **484** (type hints), **557** (dataclasses), **343** (context managers), **3134** (raise from). Só isso já transforma a qualidade do seu código.

**Sequência recomendada:**
1. PEP 20 (temos tratado) → PEP 8 → PEP 257.
2. PEP 484 (type hints) → 585 → 604.
3. Os idiomas, conforme surgem no RefCap: 557 (dataclasses) → 343 (with) → 318 (decorators) → 255/289 (generators) → 3134 (raise from).
4. Tier 3, sob demanda.

**Onde o RefCap te dá prática direta:** ao analisar o RefCap, você verá violações de vários destes — dicts crus onde caberiam dataclasses (557), sentinelas onde caberiam exceções (3134/352), `import *` que o PEP 8 desaconselha. Cada violação é um exercício.

---

# PARTE 6 — Nota sobre sobreposição com a Arquitetura

Alguns PEPs aparecem *também* no catálogo de Arquitetura, mas por razão diferente — vale entender por quê:
- **PEP 484 (type hints):** aqui, servem para *assinaturas claras no nível da função* (clean code). Na arquitetura, servem para *definir contratos de fronteira* (via Protocols).
- **PEP 557 (dataclasses):** aqui, *reduzem boilerplate de objetos de dados* (clean code). Na arquitetura, *implementam value objects/entities na camada de domínio* (DDD).
- **PEP 318 (decorators):** aqui, *compõem comportamento sem poluir a lógica* (clean code). Na arquitetura, *habilitam injeção de dependência e preocupações transversais*.

O mesmo mecanismo, dois níveis de aplicação. É o reflexo de que clean code e clean architecture são o mesmo bom senso em escalas diferentes.

---

*Catálogo focado puramente em Código Limpo — os PEPs que padronizam os idiomas Pythônicos de escrever funções e classes claras, legíveis e manuteníveis. A fundação é PEP 8/20/257; os idiomas do dia a dia (type hints, dataclasses, context managers, generators, decorators, erros) estão na Tier 2. É uma lista longa porque a expressividade do Python — a sua riqueza de idiomas limpos — é justamente onde clean code em Python brilha. Para arquitetura (uma lista bem mais curta), veja o catálogo irmão.*
