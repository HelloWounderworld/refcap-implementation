"""
LABORATÓRIO 5 — Como funciona o `from modulo import *`
========================================================
Rode com:  python3 LAB5_import_star.py

O script CRIA os modulos de exemplo em /tmp e depois os importa, para voce poder
abrir os arquivos e mexer. Cada secao mostra o namespace RESULTANTE, usando
`exec("from x import *", ns)` -- assim da' para inspecionar exatamente o que entrou.
"""
import os, sys, textwrap

TMP = "/tmp/_lab_importstar"
os.makedirs(TMP, exist_ok=True)
sys.path.insert(0, TMP)

def criar(nome, conteudo):
    with open(f"{TMP}/{nome}.py", "w") as f:
        f.write(textwrap.dedent(conteudo))

def namespace_de(comando):
    """Executa um import e devolve SO' os nomes que ele trouxe."""
    ns = {}
    exec(comando, ns)
    return sorted(k for k in ns if k != "__builtins__")

SEP = "\n" + "="*76


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 1. O BÁSICO — o que exatamente entra no seu namespace")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

criar("sensores", '''
    import json                      # <- um import INTERNO do modulo
    import os as sistema             # <- um alias INTERNO

    CALIBRACAO = 1.5                 # constante publica
    _buffer_interno = []             # "privado" por convencao

    def ler_sensor(id): return CALIBRACAO * id
    def helper(): return "helper de SENSORES"
    def _uso_interno(): return "nao deveria vazar"

    class Sensor: pass
''')

print("\n  Arquivo `sensores.py` define: CALIBRACAO, _buffer_interno, ler_sensor,")
print("                                helper, _uso_interno, Sensor")
print("                    e IMPORTA : json, sistema (alias de os)\n")
nomes = namespace_de("from sensores import *")
print(f"  `from sensores import *` trouxe {len(nomes)} nomes:")
for n in nomes:
    marca = ""
    if n in ("json", "sistema"): marca = "  <-- ★ NAO e' do modulo! e' um import DELE"
    print(f"      {n}{marca}")

print("""
  ★ A REGRA (quando NAO ha' `__all__`):
    entra TUDO que nao comeca com underscore -- inclusive os IMPORTS do modulo.
    `json` e `sistema` vieram junto, embora nada tenham a ver com sensores.
    Repare que `_buffer_interno` e `_uso_interno` NAO entraram.
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 2. `__all__` — o controle explícito da superfície pública")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

criar("api_limpa", '''
    import json
    import os

    __all__ = ["funcao_principal", "Config"]    # <- a superficie DECLARADA

    def funcao_principal(): return "esta e' a API"
    def detalhe_interno(): return "nao deveria vazar"
    class Config: pass
    class ImplementacaoInterna: pass
''')

print("\n  `api_limpa.py` define __all__ = ['funcao_principal', 'Config']\n")
print(f"  `from api_limpa import *` trouxe: {namespace_de('from api_limpa import *')}")
print("""
  ★ Com `__all__`, SO' o que esta' na lista entra. `json`, `os`,
    `detalhe_interno` e `ImplementacaoInterna` ficaram de fora.

  >>> `__all__` transforma o `import *` de "despejo acidental" em
      "API publica curada". E' a diferenca entre um modulo que voce PROJETOU
      para ser usado com estrela e um que so' te deixa fazer isso.
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 3. ★ COLISÃO SILENCIOSA — o perigo principal")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

criar("atuadores", '''
    def acionar(v): return f"acionando {v}"
    def helper(): return "helper de ATUADORES"      # <- MESMO nome de sensores.helper
''')

ns = {}
exec("from sensores import *", ns)
print(f"\n  Depois de `from sensores  import *`:  helper() -> {ns['helper']()!r}")
exec("from atuadores import *", ns)
print(f"  Depois de `from atuadores import *`:  helper() -> {ns['helper']()!r}   <-- ★ MUDOU")

print("""
  >>> O segundo import SOBRESCREVEU `helper` sem AVISO NENHUM. Nao ha' warning,
      nao ha' erro -- o comportamento do programa mudou em silencio.

  ★ E o pior: a colisao depende da ORDEM DAS LINHAS de import. Alguem que
    reordene os imports "para organizar" muda o comportamento do programa.
    Com N imports-estrela, ha' N*(N-1)/2 pares de colisao possiveis.
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 4. ★ POLUIÇÃO TRANSITIVA — o caso real do RefCap, reproduzido")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

criar("meus_utils", '''
    def carregar(x): return f"carregado: {x}"
    def salvar(x):   return f"salvo: {x}"
''')

criar("pipe_base", '''
    import meus_utils as mu          # <- ★ o modulo importa OUTRO modulo com alias
    def processar(x): return mu.carregar(x)
''')

criar("pipe_init", '''
    from pipe_base import *          # <- re-exporta TUDO, inclusive `mu`
''')

print("""
  A cadeia (identica a' do RefCap):

     pipe_base.py   : import meus_utils as mu        <- cria o nome `mu`
     pipe_init.py   : from pipe_base import *        <- RE-EXPORTA `mu`
     consumidor     : from pipe_init import *        <- recebe `mu` de brinde
""")
ns = {}
exec("from pipe_init import *", ns)
nomes = sorted(k for k in ns if k != "__builtins__")
print(f"  O consumidor recebeu: {nomes}")
print(f"  E consegue usar `mu` sem NUNCA te-lo importado: mu.carregar('x') -> {ns['mu'].carregar('x')!r}")

print("""
  ★ ISTO E' EXATAMENTE O QUE ACONTECE NO REFCAP:

     pipeline/retrievepipe/base.py:3   import utils.basic_utils as basic_utils
     pipeline/retrievepipe/__init__.py from .base import *
     retrieve.py:17                    from pipeline.retrievepipe import *
     retrieve.py:252                   basic_utils.load_json(...)   <- FUNCIONA por vazamento

    O `retrieve.py` NUNCA importa o modulo `basic_utils` (so' duas funcoes soltas
    dele, nas linhas 12 e 35). O nome `basic_utils` chega ali por herança
    transitiva de tres niveis de `import *`.

  ★ POR QUE E' UMA BOMBA-RELOGIO: se alguem "limpar" o base.py trocando
    `import utils.basic_utils as basic_utils` por `from utils.basic_utils import load_json`,
    o `retrieve.py` quebra na linha 252 com NameError -- num arquivo DIFERENTE,
    sem relacao aparente com a mudanca.
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 5. SHADOWING DE BUILTINS — quando a estrela sequestra a linguagem")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

criar("perigoso", '''
    def list(x):  return f"MINHA list() falsa, recebi {x}"
    def max(*a):  return "MEU max() falso"
    CONST = 1
''')

ns = {}
print(f"\n  Antes : list((1,2,3)) -> {list((1,2,3))}")
exec("from perigoso import *", ns)
exec("resultado = list((1,2,3))", ns)
print(f"  Depois: list((1,2,3)) -> {ns['resultado']!r}   <-- ★ o builtin foi SEQUESTRADO")

print("""
  >>> Um modulo que define `list`, `max`, `type`, `id`, `open`... sobrescreve o
      builtin no SEU namespace. Todo codigo posterior que usar `list(...)`
      chamara' a funcao errada -- com erros absurdos e dificeis de rastrear.
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 6. PERDA DE RASTREABILIDADE — 'de onde veio esse nome?'")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════
print("""
  Voce esta' lendo um arquivo e encontra:

      resultado = processar(dados)

  Com imports explicitos, a resposta esta' no topo do arquivo:
      from pipe_base import processar          <- veio DAQUI. Fim.

  Com `import *`, voce tem:
      from pipe_init import *
      from sensores  import *
      from atuadores import *

  ...e precisa ABRIR OS TRES (e os modulos que ELES importam com estrela) para
  descobrir quem define `processar`. E se dois definirem, vence o ultimo.

  >>> Consequencias praticas:
      - a IDE nao consegue "ir para a definicao"
      - linters marcam nomes como indefinidos (F405 do flake8: "may be undefined,
        or defined from star imports")
      - refatoracao automatica fica insegura
      - `mypy` perde a capacidade de verificar
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 7. O CASO LEGÍTIMO — registro por efeito colateral (o RefCap)")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

criar("registry_base", '''
    REGISTRY = {}
    def REGISTER(nome):
        def deco(cls):
            REGISTRY[nome] = cls
            return cls
        return deco
    def get_class(nome): return REGISTRY[nome]
''')

criar("plugin_blip", '''
    from registry_base import REGISTER
    @REGISTER("blip")
    class GeradorBLIP: pass
''')

criar("pacote_init", '''
    from registry_base import *
    from plugin_blip import *      # <- NAO traz nomes uteis: traz o EFEITO de registrar
''')

ns = {}
exec("from registry_base import REGISTRY", ns)
print(f"\n  Registry antes de importar o pacote: {ns['REGISTRY']}")
ns2 = {}
exec("from pacote_init import *", ns2)
exec("from registry_base import REGISTRY", ns2)
print(f"  Depois de `from pacote_init import *`: {ns2['REGISTRY']}")

print("""
  ★ AQUI o `import *` esta' sendo usado pelo EFEITO COLATERAL, nao pelos nomes.
    `from plugin_blip import *` existe para FORCAR a execucao do modulo, que
    dispara o decorador e popula o registry. Remova a linha e o registry esvazia.

  >>> MAS: mesmo neste caso, `import *` NAO e' a melhor forma. Isto funciona
      igual e nao polui o namespace:

          from . import plugin_blip        # importa o modulo, dispara o efeito
          import plugin_blip               # idem

      A necessidade real e' o IMPORT; a estrela e' um extra indesejado.
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 8. AS QUATRO FORMAS DE IMPORTAR, COMPARADAS")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════
print("""
  ┌────────────────────────────────┬───────────┬───────────┬──────────────────┐
  │ Forma                          │ Rastreia? │ Colide?   │ Dispara o modulo?│
  ├────────────────────────────────┼───────────┼───────────┼──────────────────┤
  │ import modulo                  │ sim       │ nao       │ sim              │
  │ import modulo as m             │ sim       │ raramente │ sim              │
  │ from modulo import nome        │ sim       │ possivel  │ sim              │
  │ from modulo import *           │ NAO       │ SIM       │ sim              │
  └────────────────────────────────┴───────────┴───────────┴──────────────────┘

  >>> As QUATRO disparam o modulo (logo, as quatro servem para "registro por
      efeito colateral"). A estrela e' a UNICA que perde rastreabilidade e a
      unica com risco alto de colisao. Ou seja: ela nao oferece nenhuma
      capacidade exclusiva -- so' conveniencia de digitacao.
""")

print(SEP); print(f" Modulos de exemplo criados em {TMP}/ -- abra e modifique.")
print("="*76 + "\n")
