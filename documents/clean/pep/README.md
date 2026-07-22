# Levantamento: PEPs e Categorias para Código e Arquitetura Limpa
## Catálogo de Trabalho — para Marcar Uma a Uma Conforme o Andamento

---

> **O que é este documento.** Um *levantamento* — não um aprofundamento. Uma lista de trabalho, organizada por tema, dos PEPs e índices que importam para Código Limpo e Arquitetura Limpa em Python. Cada entrada traz o número, o título, o **status** (Final = estável; Active = guia vivo; Accepted = aprovado, chegando), e **uma linha** dizendo qual conceito de clean code ela sustenta. Feito para você ir vendo uma por uma, no seu ritmo, conforme avança na análise do RefCap.
>
> **Método e curadoria (honesto).** Baseei-me no índice oficial dos PEPs (peps.python.org). Existem ~600 PEPs e ~40 só de *typing*; **selecionei deliberadamente o subconjunto relevante para clean code/architecture** e deixei de fora as nichadas (variações de `TypedDict`, `TypeVarTuple`, detalhes de `ParamSpec`, etc.) e as irrelevantes (empacotamento, C API, governança, releases). Selecionar o essencial *é* a disciplina — ler os 600 seria complexidade acidental ao seu objetivo.
>
> **Como usar.** Os PEPs estão em **três camadas de prioridade** (Tier 1 → 3). Comece pela Tier 1. Cada PEP está em `https://peps.python.org/pep-XXXX/` (ex.: PEP 544 → https://peps.python.org/pep-0544/).

---

# PARTE 1 — As categorias e índices que vale conhecer

Antes dos PEPs individuais, os *índices* do site — úteis para navegar por conta própria:

- [ ] **Índice geral (PEP 0)** — `https://peps.python.org/` — todos os PEPs, por categoria e status.
- [ ] **Índice numérico** — `https://peps.python.org/numerical/` — tabela de todos por número.
- [ ] **Tópico: Typing** — `https://peps.python.org/topic/typing/` — ★ o índice mais relevante para arquitetura limpa (type hints, Protocols). Vale percorrer.
- [ ] **Tópico: Packaging** — `https://peps.python.org/topic/packaging/` — estruturação de projetos (relevante ao nível macro da arquitetura).
- [ ] **API JSON dos PEPs** — `https://peps.python.org/api/peps.json` — metadados de todos, se quiser processar programaticamente (bom exercício de coding, aliás).
- Tópicos *Governance* e *Release* existem, mas **não** são relevantes para clean code — pode ignorar.

---

# PARTE 2 — TIER 1: A fundação (comece por aqui)

Os cinco imprescindíveis. Se você ler só estes, já cobre o essencial.

| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **20** | The Zen of Python | Active | A filosofia. *Já temos tratado completo.* |
| ☐ | **8** | Style Guide for Python Code | Active | Estilo e nomenclatura — a base do "idiomático se lê no piloto automático". Curto e obrigatório. |
| ☐ | **257** | Docstring Conventions | Active | Como escrever docstrings (o comentário-contrato). |
| ☐ | **484** | Type Hints | Final | A fundação da tipagem gradual — "type hints nas fronteiras". |
| ☐ | **544** | Protocols: Structural Subtyping | Final | ★ **A joia para arquitetura.** Inversão de Dependência sem herança. É o nome do que o `QueryDataset` tateou por duck typing. |

---

# PARTE 3 — TIER 2: Os idiomas centrais de clean code

Os mecanismos que os tratados citam o tempo todo. Leia conforme o tópico surgir na análise.

## 3.1 Type hints — contratos verificáveis
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **483** | The Theory of Type Hints | Final | O fundamento teórico (variância, subtipos) por trás do 484. |
| ☐ | **526** | Syntax for Variable Annotations | Final | Anotar variáveis e atributos, não só funções. |
| ☐ | **585** | Generics in Standard Collections | Final | `list[int]` em vez de `List[int]` — moderniza a sintaxe. |
| ☐ | **604** | Union Types as `X \| Y` | Final | `int \| None` em vez de `Optional[int]`. |
| ☐ | **589** | TypedDict | Final | Dar tipo/estrutura a dicionários — alternativa a value objects para dados. |

## 3.2 Abstrações — o núcleo da arquitetura
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **3119** | Abstract Base Classes (ABCs) | Final | A abstração *nominal* (via herança) — a alternativa ao Protocol. |

## 3.3 Value objects e menos boilerplate
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **557** | Data Classes | Final | ★ `@dataclass` — a base dos *value objects* e da eliminação de boilerplate. |

## 3.4 Gerência de recursos
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **343** | The "with" Statement | Final | ★ Context managers — o "faça X, garanta desfazer X". |

## 3.5 Composição de comportamento
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **318** | Decorators for Functions and Methods | Final | Decorators — separar preocupações transversais (o `@REGISTER_CAPGEN` do RefCap). |
| ☐ | **3129** | Class Decorators | Final | Decorators aplicados a classes. |

## 3.6 Avaliação preguiçosa e iteração
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **234** | Iterators | Final | O protocolo de iteração (`__iter__`/`__next__`) — a base do `for`. |
| ☐ | **255** | Simple Generators | Final | `yield` — produção sob demanda, economia de memória. |
| ☐ | **289** | Generator Expressions | Final | `(x for x in ...)` — lazy, composável. |

## 3.7 Tratamento de erros
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **3134** | Exception Chaining (`raise ... from`) | Final | ★ Preservar a exceção original — *a lacuna que a auditoria de Anaya apontou.* |
| ☐ | **352** | Required Superclass for Exceptions | Final | A hierarquia de exceções (herdar de `Exception`). |

## 3.8 Estrutura de projeto e imports (arquitetura no nível macro)
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **328** | Imports: Multi-Line and Absolute/Relative | Final | ★ As regras de import — *diretamente relevante à crítica do `import *`* (que o RefCap abusa). |
| ☐ | **420** | Implicit Namespace Packages | Final | Como pacotes se organizam (conecta ao aforismo "namespaces são geniais"). |

---

# PARTE 4 — TIER 3: Aprofundamento por tópico (sob demanda)

Relevantes, mas leia só quando o assunto específico aparecer.

## 4.1 Type hints — tópicos avançados
| ☐ | PEP | Título | Status | Quando ler |
|---|-----|--------|--------|-----------|
| ☐ | **3107** | Function Annotations | Final | A raiz histórica das anotações (contexto). |
| ☐ | **673** | Self Type | Final | Ao tipar métodos que retornam a própria instância. |
| ☐ | **695** | Type Parameter Syntax | Final | A sintaxe moderna de genéricos (Python 3.12+). |
| ☐ | **612** | Parameter Specification Variables | Final | Ao tipar decorators que preservam assinaturas. |
| ☐ | **561** | Distributing and Packaging Type Information | Final | Ao publicar uma lib com type hints (`py.typed`). |
| ☐ | **563 / 649** | Postponed / Deferred Evaluation of Annotations | Final / Accepted | O comportamento de avaliação de anotações (relevante em 3.14+). |

## 4.2 Iteração e concorrência — avançado
| ☐ | PEP | Título | Status | Quando ler |
|---|-----|--------|--------|-----------|
| ☐ | **342** | Coroutines via Enhanced Generators | Final | Ao entender a raiz das corrotinas. |
| ☐ | **380** | `yield from` (Delegating to Subgenerator) | Final | Ao compor generators. |
| ☐ | **525** | Asynchronous Generators | Final | Se entrar em código assíncrono. |

## 4.3 Erros — avançado
| ☐ | PEP | Título | Status | Quando ler |
|---|-----|--------|--------|-----------|
| ☐ | **409 / 415** | Suppressing Exception Context | Final | Controle fino da cadeia de exceções (`raise ... from None`). |
| ☐ | **654** | Exception Groups and `except*` | Final | Ao lidar com múltiplas exceções simultâneas (3.11+). |

## 4.4 Estrutura de projeto — empacotamento
| ☐ | PEP | Título | Status | Quando ler |
|---|-----|--------|--------|-----------|
| ☐ | **517 / 518** | Build System Interface / Requirements | Final | Ao estruturar `pyproject.toml` (a "composition root" do projeto). |
| ☐ | **621** | Project Metadata in `pyproject.toml` | Final | Ao definir metadados do projeto de forma moderna. |
| ☐ | **366** | Main Module Explicit Relative Imports | Final | Ao rodar módulos como script (`python -m`). |

## 4.5 Clareza de fluxo e idiomas — moderno
| ☐ | PEP | Título | Status | Quando ler |
|---|-----|--------|--------|-----------|
| ☐ | **634 / 635 / 636** | Structural Pattern Matching (spec / motivação / tutorial) | Final | Ao usar `match` — clareza em despacho por estrutura (3.10+). |
| ☐ | **572** | Assignment Expressions (walrus `:=`) | Final | Um bom *estudo de caso* do trade-off legibilidade vs. concisão (o debate do Zen). |
| ☐ | **428** | The `pathlib` module | Final | Manipulação de caminhos orientada a objetos (idioma limpo vs. `os.path`). |
| ☐ | **362** | Function Signature Object | Final | Ao inspecionar assinaturas (metaprogramação, decorators). |

---

# PARTE 5 — Ordem sugerida de leitura

Para não se perder, uma sequência que acompanha o aprofundamento natural:

1. **Fundação:** PEP 20 (temos tratado) → PEP 8 → PEP 257.
2. **A joia da arquitetura:** PEP 544 (Protocols) — leia com o RefCap em mente; é o exercício de reescrever o `QueryDataset` com `Protocol` explícito.
3. **Contratos:** PEP 484 → 483 → 585 → 604.
4. **Idiomas de clean code, conforme aparecem no RefCap:** PEP 557 (dataclasses/value objects) → PEP 343 (context managers) → PEP 318 (decorators) → PEP 255/289 (generators) → PEP 3134 (raise from).
5. **Abstrações:** PEP 3119 (ABCs), comparando com o PEP 544.
6. **Estrutura/imports:** PEP 328 (relevante ao `import *` do RefCap) → PEP 420.
7. **Tier 3, sob demanda:** só quando o tópico específico surgir na análise.

---

# PARTE 6 — Mapa rápido: PEP ↔ conceito de clean code

Uma tabela-resumo para consulta reversa (quando um conceito surgir, qual PEP consultar):

| Conceito de clean code / architecture | PEP(s) |
|---|---|
| Filosofia / valores | 20 |
| Estilo, nomenclatura, formatação | 8 |
| Docstrings (comentário-contrato) | 257 |
| Type hints (contratos verificáveis) | 484, 483, 526, 585, 604 |
| **Inversão de Dependência / abstração estrutural** | **544** (Protocols), 3119 (ABCs) |
| Value objects / dados estruturados | 557 (dataclasses), 589 (TypedDict) |
| Gerência de recursos | 343 (with) |
| Composição de comportamento | 318, 3129 (decorators) |
| Iteração / lazy evaluation | 234, 255, 289, 342, 380 |
| Tratamento de erros | 3134 (raise from), 352, 409/415, 654 |
| Estrutura de projeto / imports / namespaces | 328, 420, 517/518, 621 |
| Clareza de fluxo | 634/635/636 (match), 572 (walrus) |
| Idiomas limpos diversos | 428 (pathlib), 362 (signatures) |

---

*Este é um levantamento curado — o subconjunto dos ~600 PEPs que importa para Código e Arquitetura Limpa, organizado em camadas de prioridade e formato de checklist para você percorrer uma a uma conforme a análise do RefCap avança. A espinha para arquitetura é o PEP 544 (Protocols); a fundação é PEP 8/20/257; os idiomas de clean code estão na Tier 2. O que ficou de fora (empacotamento profundo, C API, governança, typing nichado) é acidental ao seu objetivo — deliberadamente omitido. Quando você quiser aprofundar qualquer PEP desta lista, é só apontar, e eu abro no detalhe, conectando ao ponto do RefCap que você estiver tratando.*