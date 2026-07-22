# Levantamento de PEPs — CLEAN ARCHITECTURE
## Catálogo de Trabalho Focado em Arquitetura Limpa (nível macro)

---

> **Escopo.** Este catálogo cobre *puramente* os PEPs relevantes para **Arquitetura Limpa** — o nível macro: como estruturar as *dependências* e *fronteiras* de um sistema (abstrações, camadas, inversão de dependência, organização de módulos). A parte de **Código Limpo** (idiomas para escrever cada função) está no catálogo irmão (`Levantamento_PEPs_CleanCode.md`).
>
> **⚠️ Leia isto primeiro — por que esta lista é curta (e por que isso é o ponto).** Diferente do catálogo de Código Limpo, este é **deliberadamente enxuto**, e a razão é fundamental: **arquitetura limpa é dirigida por *princípios*, não por *idiomas de linguagem*.** Os princípios — a Regra da Dependência, SOLID, portas e adaptadores, DDD — vêm da tradição de engenharia (Martin, Keen, Evans, Cockburn), **não dos PEPs.** O que os PEPs oferecem à arquitetura é apenas o *mecanismo* para realizar esses princípios em Python — e esse mecanismo está concentrado quase inteiramente **num PEP só: o 544 (Protocols).** Então: **não espere os PEPs te ensinarem arquitetura.** Eles te dão as ferramentas; os princípios estão nos tratados. Este catálogo é a lista de ferramentas.
>
> **Como usar.** Formato de checklist, com o PEP 544 no centro. Cada PEP em `https://peps.python.org/pep-XXXX/`.

---

# PARTE 1 — Índices úteis

- [ ] **Tópico: Typing** — `https://peps.python.org/topic/typing/` — onde vivem Protocols e ABCs, o coração da abstração arquitetural.
- [ ] **Tópico: Packaging** — `https://peps.python.org/topic/packaging/` — estruturação de projetos (o nível macro da arquitetura).

---

# PARTE 2 — TIER 1: A joia da coroa (o que você DEVE dominar)

Se você dominar *um* PEP para arquitetura, é este.

| ☐ | PEP | Título | Status | Por que é central para arquitetura |
|---|-----|--------|--------|-----------------|
| ☐ | **544** | Protocols: Structural Subtyping | Final | ★★ **O mecanismo que torna a Inversão de Dependência Pythônica.** Permite depender da *forma* de um objeto (um contrato), sem herança. É o nome do que o `QueryDataset` do RefCap tateou por duck typing. Dominar isto é dominar a peça-chave da arquitetura limpa em Python. |

**Exercício associado (o mais importante de todos):** reescrever a nossa adaptação do RefCap (`QueryDataset`) usando `Protocol` explícito, transformando o duck typing invisível num contrato verificável. Une o princípio (DIP), o mecanismo (544) e o código real.

---

# PARTE 3 — TIER 2: As abstrações e os contratos de fronteira

Depois do 544, estes completam o ferramental de definir fronteiras limpas.

## 3.1 Abstração — a alternativa ao Protocol
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **3119** | Abstract Base Classes (ABCs) | Final | A abstração *nominal* (via herança explícita) — a alternativa ao Protocol. Estude os dois *lado a lado*: Protocol (estrutural, sem herança) vs. ABC (nominal, com herança), e quando usar cada um. |

## 3.2 Contratos de fronteira — o que cruza as camadas
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **484** | Type Hints | Final | Aqui, os type hints definem os *contratos das fronteiras* — a assinatura de uma porta, o tipo que atravessa uma camada. (No clean code, servem para clareza de função; aqui, para definir interfaces entre camadas.) |
| ☐ | **589** | TypedDict | Final | Dar contrato a dados estruturados que cruzam fronteiras (em vez de dicts anônimos vazando entre camadas). |
| ☐ | **557** | Data Classes | Final | Aqui, `@dataclass` implementa *value objects* e *entities* da camada de domínio (DDD) — objetos de domínio validados e nomeados, não primitivos soltos. |

---

# PARTE 4 — TIER 3: A estrutura de módulos, pacotes e projeto

O nível macro da organização — como as dependências entre módulos são expressas e como o projeto é montado. Leia ao estruturar um sistema seu do zero.

## 4.1 Dependências entre módulos — a Regra da Dependência concretizada
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **328** | Imports: Multi-Line and Absolute/Relative | Final | ★ Como módulos dependem uns dos outros — a Regra da Dependência no concreto. *Diretamente relevante à crítica do `import *`* (que o RefCap abusa e que quebra a rastreabilidade das dependências). |
| ☐ | **366** | Main Module Explicit Relative Imports | Final | Imports ao rodar módulos como script (`python -m`) — evita armadilhas de estrutura. |

## 4.2 Organização de pacotes e namespaces
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **420** | Implicit Namespace Packages | Final | Como pacotes se organizam e se dividem (conecta ao aforismo "namespaces são geniais" — a organização de nomes que a arquitetura exige). |

## 4.3 Estrutura do projeto — a "composition root" no nível macro
| ☐ | PEP | Título | Status | Por que importa |
|---|-----|--------|--------|-----------------|
| ☐ | **518** | Minimum Build System Requirements (`pyproject.toml`) | Final | Onde o projeto declara como é construído — a raiz da montagem. |
| ☐ | **517** | Build-System Independent Format | Final | A interface entre o projeto e a ferramenta de build (desacoplamento no nível de projeto). |
| ☐ | **621** | Project Metadata in `pyproject.toml` | Final | Metadados do projeto de forma moderna e padronizada — a estrutura declarativa. |
| ☐ | **561** | Distributing and Packaging Type Information | Final | Ao publicar uma lib com type hints (`py.typed`) — a fronteira de tipos que sua lib expõe. |

---

# PARTE 5 — Onde focar (a orientação)

**A verdade nua:** para arquitetura, **80% do valor está no PEP 544.** Dominá-lo — entender tipagem estrutural, e quando usar `Protocol` vs. `ABC` (3119) — te dá o mecanismo central da arquitetura limpa em Python. O resto (contratos de fronteira, estrutura de projeto) é complementar.

**Sequência recomendada:**
1. **PEP 544 (Protocols)** — leia a fundo, com o RefCap em mente. Faça o exercício do `QueryDataset`.
2. **PEP 3119 (ABCs)** — compare com o 544; entenda o trade-off estrutural vs. nominal.
3. **PEP 484** — no ângulo de *contratos de fronteira* (não de clareza de função).
4. **PEP 328** — ao pensar na Regra da Dependência e no problema do `import *`.
5. **PEP 557** — no ângulo de *value objects/entities* de domínio.
6. **Estrutura de projeto (518/517/621/420/561)** — sob demanda, ao montar um sistema seu.

**O lembrete que importa mais que a lista:** os *princípios* de arquitetura — as camadas, a Regra da Dependência, SOLID, portas e adaptadores — **não estão nos PEPs.** Estão nos tratados (Martin, Keen, e o nosso `ARQUITETURA_LIMPA_Tratado.md`). Este catálogo te dá as *ferramentas Python* para realizar esses princípios; a *sabedoria* de quando e como aplicá-los vem de outro lugar. Não confunda dominar as ferramentas com dominar a arquitetura.

---

# PARTE 6 — Nota sobre sobreposição com o Código Limpo

Três PEPs aparecem *também* no catálogo de Código Limpo, mas por razão diferente:
- **PEP 484 (type hints):** lá, para *assinaturas claras* (clean code); aqui, para *contratos de fronteira entre camadas* (arquitetura).
- **PEP 557 (dataclasses):** lá, para *reduzir boilerplate de dados* (clean code); aqui, para *value objects/entities do domínio* (DDD/arquitetura).
- **PEP 318 (decorators)** (implícito): lá, para *compor comportamento* (clean code); na arquitetura, habilitam *injeção de dependência*.

O mesmo mecanismo, escalas diferentes — o reflexo de que arquitetura limpa é o mesmo bom senso do código limpo, aplicado ao sistema inteiro em vez da função.

---

*Catálogo focado puramente em Arquitetura Limpa — deliberadamente curto, porque arquitetura é dirigida por princípios (da tradição de engenharia, não dos PEPs), e a contribuição do Python está concentrada no PEP 544 (Protocols), o mecanismo da Inversão de Dependência Pythônica. Domine o 544 acima de tudo, compare com ABCs (3119), e use os demais (contratos de fronteira, estrutura de projeto) como complemento. Mas lembre: os PEPs te dão as ferramentas; os princípios da arquitetura estão nos tratados. Para os idiomas de escrever cada função (uma lista bem mais longa), veja o catálogo irmão de Código Limpo.*
