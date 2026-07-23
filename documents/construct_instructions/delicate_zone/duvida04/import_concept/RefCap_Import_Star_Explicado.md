# O `from modulo import *` — Como Funciona, Quando Ajuda, Quando Atrapalha
## Relatório Baseado nos Nove `import *` do `construct.py`

---

> **O que é este documento.** A explicação prática do `import *`: a mecânica em três regras, os problemas que ele resolve de fato, os que ele cria, e um critério de decisão. Todos os exemplos são verificáveis no laboratório companheiro `LAB5_import_star.py`, e o estudo de caso é o RefCap — que usa `import *` **nove vezes** no `construct.py` e cujo `retrieve.py` contém um bug real causado por isso.

---

# 1. A mecânica: três regras

## Regra 1 — Traz tudo que não começa com `_`

```python
# sensores.py
CALIBRACAO = 1.5
_buffer_interno = []          # NÃO é exportado
def ler_sensor(): ...
def _uso_interno(): ...       # NÃO é exportado
```
`from sensores import *` traz `CALIBRACAO`, `ler_sensor` e a classe — mas não os que começam com underscore. **O underscore é a única proteção**, e é convenção de exportação, não privacidade.

## Regra 2 — Traz também o que o módulo *importou* ★

Esta é a que surpreende, e é a raiz de quase todos os problemas:

```python
# sensores.py
import json
import os as sistema             # ← isto cria o NOME `sistema` no módulo
CALIBRACAO = 1.5
```
`from sensores import *` traz **`json` e `sistema` também**. Por quê? Porque `import json` cria o nome `json` no namespace do módulo, e o `import *` copia **todos os nomes do namespace** — não apenas as definições próprias.

**Consequência:** cada `import *` arrasta a árvore de dependências do módulo importado para dentro do seu arquivo.

## Regra 3 — `__all__` manda, se existir

```python
__all__ = ["funcao_principal", "Config"]
```
Com `__all__` definido, **só** o que está na lista é exportado — nem `json`, nem `os`, nem detalhes internos. É o que transforma o `import *` de "despejo acidental" em "API pública curada".

**O RefCap não define `__all__` em nenhum módulo.** Por isso todos os seus nove `import *` vazam tudo, inclusive dependências transitivas.

---

# 2. O que o `import *` resolve de fato

Sejamos justos: há três situações em que ele tem valor real.

**(a) APIs projetadas para isso.** Bibliotecas que definem `__all__` cuidadosamente e cuja finalidade é povoar seu namespace — `from tkinter import *`, `from math import *` em scripts curtos, DSLs. Aqui o `import *` é a interface pretendida.

**(b) Sessões interativas e scripts descartáveis.** No REPL ou num script de 20 linhas que você roda uma vez, a economia de digitação vale mais que a rastreabilidade. Não há manutenção futura para proteger.

**(c) Re-exportação em `__init__.py`.** Um pacote que quer expor o conteúdo dos submódulos como se fosse seu — `from .base import *` no `__init__.py` para que `pacote.Classe` funcione. É o uso mais defensável, **desde que** cada submódulo defina `__all__`.

**(d) Efeito colateral de import** — o caso do RefCap, tratado na seção 4.

---

# 3. O que ele quebra: cinco problemas

## 3.1 Colisão silenciosa

```
Depois de `from sensores  import *`:  helper() → 'helper de SENSORES'
Depois de `from atuadores import *`:  helper() → 'helper de ATUADORES'   ← MUDOU
```
O segundo import **sobrescreve sem aviso**. Não há warning nem erro. E o comportamento passa a depender da **ordem das linhas de import** — alguém que reordene "para organizar" muda o programa. Com N imports-estrela, há N(N−1)/2 pares de colisão possíveis. **No `construct.py`, N = 9.**

## 3.2 Sequestro de builtins

Um módulo que define `list`, `type`, `id`, `open` ou `max` **sobrescreve o builtin** no seu namespace. Todo código posterior chama a função errada, com erros absurdos e difíceis de rastrear.

## 3.3 Perda de rastreabilidade

Você lê `resultado = processar(dados)` e pergunta: de onde vem `processar`? Com import explícito, a resposta está no topo do arquivo. Com nove `import *`, você precisa abrir os nove módulos — **e os que eles importam com estrela**. E se dois definirem, vence o último.

Consequências: a IDE não consegue "ir para a definição"; o `flake8` emite F405 (*"may be undefined, or defined from star imports"*); refatoração automática fica insegura; `mypy` perde capacidade de verificação.

## 3.4 Poluição transitiva (a Regra 2 em ação)

Cadeias de `import *` propagam nomes por vários níveis. O consumidor recebe nomes que nunca pediu, de módulos que nem conhece.

## 3.5 O Python proíbe dentro de funções

```python
def f():
    from mod import *      # SyntaxError
```
O compilador precisa saber, em tempo de compilação, quais nomes são locais — e o `import *` torna isso indecidível. **É um sinal explícito, no design da linguagem, de que o recurso é problemático.**

---

# 4. O estudo de caso: o RefCap

## 4.1 O bug real, verificado

Esta cadeia existe no repositório e é a demonstração perfeita do problema:

```
pipeline/retrievepipe/base.py:3       import utils.basic_utils as basic_utils
pipeline/retrievepipe/__init__.py     from .base import *
retrieve.py:17                        from pipeline.retrievepipe import *
retrieve.py:252                       basic_utils.load_json(...)      ← funciona por vazamento
```

**O `retrieve.py` nunca importa o módulo `basic_utils`.** Ele importa apenas duas *funções* soltas dele (linhas 12 e 35: `save_json` e `seed_it`). O **nome do módulo** `basic_utils`, usado nas linhas 252 e 260, chega ali por **herança transitiva de três níveis de `import *`**.

**Por que é uma bomba-relógio:** se alguém "limpar" o `retrievepipe/base.py` trocando `import utils.basic_utils as basic_utils` por `from utils.basic_utils import load_json`, o `retrieve.py` quebra na linha 252 com `NameError` — **num arquivo diferente, sem relação aparente com a mudança.**

## 4.2 O caso legítimo: registro por efeito colateral

O `pipeline/capgenerator/__init__.py` tem duas linhas:
```python
from .base import *
from .BlipCapGener import *
```
A segunda existe **só para registrar** `CapGeneratorBLIP` — importar o módulo executa o decorador que popula o registry. Remova-a, e `get_capgen_class("blip")` levanta `ValueError`. **O import é load-bearing.**

**Mas a forma não é necessária.** `from . import BlipCapGener` dispara exatamente o mesmo efeito sem despejar nome nenhum. O que era preciso era o *import*; a estrela era um extra indesejado.

## 4.3 O padrão curioso do `construct.py`

```python
from pipeline.capgenerator import *                    # ← efeito: registrar
from pipeline.capgenerator import get_capgen_class     # ← explícito: o que usa
from pipeline.propgenerator import *
from pipeline.propgenerator import get_propgen_class
```
Cada `import *` é seguido do import **explícito** do getter que será usado. Isso é revelador: o autor separou os dois papéis — a estrela para o *efeito*, o nome para o *uso*. **Está a um passo da forma correta.** Bastaria trocar a primeira linha de cada par por `from pipeline import capgenerator` e o sistema funcionaria idêntico, sem poluição.

---

# 5. As quatro formas comparadas

| Forma | Rastreia? | Colide? | Dispara o módulo? |
|---|---|---|---|
| `import modulo` | sim | não | **sim** |
| `import modulo as m` | sim | raramente | **sim** |
| `from modulo import nome` | sim | possível | **sim** |
| `from modulo import *` | **NÃO** | **SIM** | **sim** |

**A conclusão que a tabela força:** as quatro disparam a execução do módulo — logo, **as quatro servem para "registro por efeito colateral"**. A estrela é a única que perde rastreabilidade e a única com risco alto de colisão. **Ela não oferece nenhuma capacidade exclusiva — só conveniência de digitação.**

---

# 6. Critério de decisão

| Use `import *` quando | Evite quando |
|---|---|
| O módulo define `__all__` curado e foi **projetado** para isso | O módulo não define `__all__` |
| É sessão interativa (REPL) ou script descartável | É código que será mantido |
| É re-exportação em `__init__.py` de submódulos com `__all__` | Há mais de um `import *` no mesmo arquivo (risco de colisão) |
| — | Você precisa apenas do **efeito de import** (use `from . import modulo`) |

**A regra de bolso:** se você não consegue dizer, de cabeça, quais nomes aquela linha vai trazer, não use `import *`.

**A pergunta de diagnóstico:** *"eu preciso dos NOMES, ou só preciso que o módulo EXECUTE?"* Se for a segunda — e no RefCap é — então `from . import modulo` é estritamente melhor: mesmo efeito, zero poluição.

---

# 7. O que fazer no seu caso

Se você for adicionar o `WholePropGenerator` ao RefCap, o `__init__.py` do `propgenerator` vai precisar de uma linha para registrá-lo. Duas opções:

```python
from .WholePropGener import *      # segue o padrão do repo (poluente)
from . import WholePropGener       # mesmo efeito, sem poluição  ← preferível
```

A segunda é melhor e não quebra nada — as duas disparam o registro. Seguir o padrão existente tem valor (consistência), mas aqui o padrão existente é o defeito. Como é código **seu**, adicionado a um repo que você mantém, vale usar a forma correta e documentar por quê num comentário de uma linha.

---

*Este relatório cobriu a mecânica do `import *` em três regras (traz o que não tem underscore; traz também o que o módulo importou; `__all__` manda), seus casos legítimos, seus cinco problemas, e o estudo de caso do RefCap — incluindo um bug real verificado em que `retrieve.py` usa `basic_utils` sem nunca tê-lo importado. A conclusão operacional: como todas as formas de import disparam a execução do módulo, o `import *` não tem capacidade exclusiva — quando você precisa só do efeito colateral, `from . import modulo` entrega o mesmo resultado sem nenhum dos custos.*
