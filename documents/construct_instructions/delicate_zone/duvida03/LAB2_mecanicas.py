"""
LABORATÓRIO 2 — As MECÂNICAS que o Laboratório 1 apenas NOMEOU
==============================================================
O LAB 1 demonstrou a cadeia registry -> decorator -> factory -> injecao.
Este demonstra os 10 conceitos que ficaram so' na prosa do relatorio.

Cada secao segue o mesmo formato:
    (a) o conceito FUNCIONANDO
    (b) o conceito QUEBRADO de proposito  <- e' aqui que se aprende
    (c) o vinculo com a linha exata do RefCap

Rode com:  python3 LAB2_mecanicas.py
"""
import sys, os, types, inspect
from functools import partial

SEP = "\n" + "="*76


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 1. METACLASSE — `class` é açúcar para uma chamada a `type`")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

class Base_A:
    def cumprimenta(self): return "oi da Base_A"

# forma normal
class Normal(Base_A):
    def extra(self): return "extra"

# forma explicita: type(nome, bases, namespace) -- EXATAMENTE o que o `class` faz
Manual = type("Manual", (Base_A,), {"extra": lambda self: "extra"})

print(f"""
  class Normal(Base_A):                     Manual = type("Manual", (Base_A,), {{...}})
      def extra(self): ...

  type(Normal)  = {type(Normal)}         type(Manual)  = {type(Manual)}
  Normal().extra() = {Normal().extra()!r}                 Manual().extra() = {Manual().extra()!r}
  Normal().cumprimenta() = {Normal().cumprimenta()!r}
  Manual().cumprimenta() = {Manual().cumprimenta()!r}

  >>> Os dois sao a MESMA coisa. `class` nao e' declaracao -- e' um COMANDO que
      executa e produz um objeto. Por isso `CAPGEN_REGISTRY[name] = cls` funciona:
      `cls` e' so' um valor.
  RefCap: capgenerator/base.py:15
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 2. `type.__call__` — o que REALMENTE acontece em `Classe(args)`")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

class Instrumentada:
    def __new__(cls, *a, **k):
        print(f"      [1] __new__  chamado -> ALOCA o objeto (cls={cls.__name__})")
        return super().__new__(cls)
    def __init__(self, cfg):
        print(f"      [2] __init__ chamado -> INICIALIZA (cfg={cfg})")
        self.cfg = cfg

print("\n  (a) `Instrumentada('X')` -- observe a ordem:")
obj = Instrumentada("X")

print("\n  (b) A forma explicita, que prova a equivalencia:")
obj2 = type(Instrumentada).__call__(Instrumentada, "Y")   # == type.__call__(Instrumentada, "Y")

print(f"""
  >>> `Classe(args)` NAO e' "chamar uma funcao". E' `type.__call__(Classe, args)`,
      que faz DUAS coisas: __new__ (aloca) e depois __init__ (inicializa).
      E' por isso que `get_capgen_class('blip')(cfg, models)` parece uma segunda
      chamada de funcao mas e' CONSTRUCAO DE OBJETO -- semantica completamente
      diferente (herança, MRO, super()).
  RefCap: construct.py:43
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 3. CLOSURE — como o decorador 'lembra' do nome depois de retornar")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

REG = {}
def REGISTER(names):
    def register_cls(cls):
        for n in ([names] if isinstance(names, str) else names):
            REG[n] = cls
        return cls
    return register_cls

decorador = REGISTER(["blip"])     # a funcao EXTERNA ja' retornou!

print(f"""
  `REGISTER(["blip"])` ja' terminou. Mesmo assim o decorador que ela devolveu
  ainda "sabe" que o nome e' ["blip"]. Onde essa informacao esta' guardada?

  decorador.__closure__          = {decorador.__closure__}
  celulas capturadas             = {len(decorador.__closure__)}
  conteudo da celula [0]         = {decorador.__closure__[0].cell_contents!r}   <-- ★ o `names`!
  variaveis livres               = {decorador.__code__.co_freevars}
""")

def SEM_closure(names):
    def register_cls(cls):
        return cls                 # nao usa `names` -> nao captura nada
    return register_cls
d2 = SEM_closure(["blip"])
print(f"""  (b) Quebrado: se a funcao interna NAO usa `names`, nao ha' captura:
      SEM_closure(["blip"]).__closure__ = {d2.__closure__}

  >>> Uma CLOSURE e' uma funcao + o ambiente onde ela nasceu. O Python guarda
      as variaveis capturadas em "celulas" que sobrevivem ao retorno da funcao
      externa. E' isso que permite o decorador-fabrica ter dois niveis.
  RefCap: capgenerator/base.py:10-22
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 4. FUNCTOR (`__call__`) — o que torna uma INSTÂNCIA chamável")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

class SemCall:
    def __init__(self, cfg): self.cfg = cfg

class ComCall:
    def __init__(self, cfg): self.cfg = cfg
    def __call__(self, vid_list): return [f"legenda de {v}" for v in vid_list]

print("\n  (a) SEM __call__:")
try:
    SemCall({})(["vidA"])
except TypeError as e:
    print(f"      TypeError: {e}")

print("\n  (b) COM __call__:")
print(f"      ComCall({{}})(['vidA']) = {ComCall({})(['vidA'])}")

print(f"""
  >>> `obj(args)` procura `__call__` NA CLASSE de obj. Se existir, a instancia
      e' um FUNCTOR: um objeto que guarda ESTADO e se comporta como FUNCAO.
      E' por isso que `construct()` escreve `self.caption_generator(vid_list=...)`
      -- o gerador e' um objeto com cfg, models e cache dentro, mas se usa como
      se fosse uma funcao simples.
  RefCap: capgenerator/base.py:39
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 5. MRO e DESPACHO DINÂMICO — por que `self.generate_caption` acha o BLIP")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

class BaseCapGen:
    def __call__(self, vids):
        print("      [base.__call__] vou chamar self.generate_caption(...)")
        return [self.generate_caption(v) for v in vids]
    def generate_caption(self, v):
        return f"BASE: assert que {v} ja' tem legenda externa"

class CapGeneratorBLIP(BaseCapGen):
    def generate_caption(self, v):
        return f"BLIP: gerei legenda de {v}"

inst = CapGeneratorBLIP()
print(f"\n  MRO de CapGeneratorBLIP:")
for i, c in enumerate(CapGeneratorBLIP.__mro__):
    print(f"      [{i}] {c.__name__}")

print(f"\n  Chamando inst(['vidA']) -- o __call__ esta' na BASE:")
r = inst(["vidA"])
print(f"      resultado: {r}")
print(f"""
  >>> O `__call__` da BASE executa `self.generate_caption(...)`. O Python resolve
      esse nome percorrendo a MRO do tipo REAL de `self` (CapGeneratorBLIP),
      e encontra a versao da SUBCLASSE antes da versao da base. Isso e' DESPACHO
      DINAMICO (late binding): o destino nao e' decidido no texto, e' em runtime.

  ★ E' por isso que ler `base.py` isolado ENGANA: voce ve' um generate_caption
    que so' faz um assert e conclui que nada acontece. A implementacao real esta'
    em OUTRO ARQUIVO. O custo de leitura do polimorfismo e' este.
  RefCap: base.py:47 chama -> BlipCapGener.py:17 executa
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 6. CURRYING / APLICAÇÃO PARCIAL — a equivalência funcional")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

cfg = {"res": 384}; models = {"m": "BLIP"}

# --- versao com CLASSE (o que o RefCap faz) ---
class GeradorClasse:
    def __init__(self, cfg, models): self.cfg, self.models = cfg, models
    def __call__(self, vid_list):
        return [f"{self.models['m']}@{self.cfg['res']}: {v}" for v in vid_list]

# --- versao FUNCIONAL equivalente ---
def gerar_funcional(cfg, models, vid_list):
    return [f"{models['m']}@{cfg['res']}: {v}" for v in vid_list]

g_classe    = GeradorClasse(cfg, models)              # aplicacao parcial via __init__
g_funcional = partial(gerar_funcional, cfg, models)   # aplicacao parcial via functools

print(f"""
  Classe   : GeradorClasse(cfg, models)          -> {g_classe(['vidA'])}
  Funcional: partial(gerar_funcional, cfg, models) -> {g_funcional(['vidA'])}

  Iguais? {g_classe(['vidA']) == g_funcional(['vidA'])}

  >>> As duas formas fazem a MESMA coisa: pre-carregam (cfg, models) e devolvem
      algo que so' precisa de `vid_list`. Formalmente:

          capgen : Nome -> Cfg -> Models -> VidList -> Captions

      A versao com classe adiciona UMA coisa que o `partial` nao da':
      ESTADO MUTAVEL entre chamadas (o cache `already_video_names`).
      E' esse o unico motivo de ser classe e nao funcao.
  RefCap: construct.py:43 (a aplicacao parcial) + base.py:34 (o estado)
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 7. DUCK TYPING vs ABC — as duas filosofias, lado a lado")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════
from abc import ABC, abstractmethod

# --- ESTRUTURAL (duck typing) -- como o capgenerator do RefCap ---
class BaseDuck:
    def gerar(self, v): return "implementacao default da base"

class FilhoDuckIncompleto(BaseDuck):
    pass                                  # ESQUECEU de implementar

# --- NOMINAL (ABC) -- como o propgenerator do RefCap ---
class BaseABC(ABC):
    @abstractmethod
    def gerar(self, v): pass

class FilhoABCIncompleto(BaseABC):
    pass                                  # ESQUECEU de implementar

print("\n  (a) DUCK TYPING (capgenerator/base.py:26) -- filho incompleto:")
inst_duck = FilhoDuckIncompleto()
print(f"      instanciou SEM ERRO. Resultado: {inst_duck.gerar('vidA')!r}")
print("      >>> falha SILENCIOSA: herda o comportamento da base sem avisar.")

print("\n  (b) ABC + @abstractmethod (propgenerator/base.py:23) -- filho incompleto:")
try:
    FilhoABCIncompleto()
except TypeError as e:
    print(f"      TypeError: {e}")
    print("      >>> falha IMEDIATA, na instanciacao, com mensagem precisa.")

print("""
  >>> O RefCap usa AS DUAS filosofias, em modulos irmaos, sem justificativa:
        capgenerator  -> duck typing (estrutural, contrato implicito)
        propgenerator -> ABC        (nominal, contrato imposto)
      Mesmo papel arquitetural, garantias diferentes. E' inconsistencia de design.
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 8. LSP — a violação real do RefCap, reproduzida")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

class BasePropGen(ABC):
    @abstractmethod
    def __call__(self, vid_list, captions, scores):        # <- CONTRATO: 3 params
        pass

class QMPropGenerator(BasePropGen):
    def __call__(self, vid_list, captions, scores, all_frame_features):  # <- EXIGE 4
        return "propostas"

print(f"""
  Contrato declarado : {inspect.signature(BasePropGen.__call__)}
  Implementacao real : {inspect.signature(QMPropGenerator.__call__)}
""")

qm = QMPropGenerator()
print("  (a) Um chamador que confia no CONTRATO DA BASE (3 argumentos):")
try:
    qm(["v"], {}, {})
except TypeError as e:
    print(f"      TypeError: {e}")
    print("      >>> a subclasse NAO e' substituivel pela base -> viola LSP.")

print("  \n  (b) O chamador real do RefCap passa 4 e funciona:")
print(f"      {qm(['v'], {}, {}, {})!r}")

print("""
  >>> A subclasse FORTALECEU a pre-condicao (exige um argumento a mais).
      E o @abstractmethod NAO PEGA isso: ele verifica se o metodo EXISTE,
      nunca se a ASSINATURA e' compativel. Limitacao real do ABC.
  RefCap: propgenerator/base.py:28 (declara 3) vs QMPropGener.py:44 (exige 4)
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 9. REGISTRO POR EFEITO DE IMPORT — o alçapão, reproduzido")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

tmp = "/tmp/_lab_plugins"
os.makedirs(tmp, exist_ok=True)
with open(f"{tmp}/plug_a.py", "w") as f:
    f.write("import __main__\n__main__.REG2['plug_a'] = 'CLASSE_A'\n")
with open(f"{tmp}/plug_b.py", "w") as f:
    f.write("import __main__\n__main__.REG2['plug_b'] = 'CLASSE_B'\n")
sys.path.insert(0, tmp)

REG2 = {}
globals()['REG2'] = REG2

print(f"\n  Dois arquivos de plugin criados em {tmp}/")
print(f"  Registry antes de qualquer import: {REG2}")

import plug_a                                    # SO' o A e' importado
print(f"  Depois de `import plug_a`            : {REG2}")
print(f"""
  O `plug_b.py` EXISTE, esta' correto, e sua classe nunca sera' encontrada:
      'plug_b' in REG2 -> {'plug_b' in REG2}

  >>> O registro e' um EFEITO COLATERAL DO IMPORT. Se o modulo nao for importado,
      a classe nunca se registra -- mesmo estando la', perfeita.
      E' por isso que `pipeline/capgenerator/__init__.py` faz
      `from .BlipCapGener import *`: aquele import nao traz nomes para usar,
      ele FORCA a execucao do modulo. Remova-o e o registry esvazia.
""")
import plug_b
print(f"  Depois de `import plug_b`            : {REG2}   <- agora sim")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 10. LEI DE DEMÉTER — o acoplamento não declarado do RefCap")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

class DenoiserOficial:
    def __init__(self, models):
        self.it_sim_model = models["blip_itm"]     # atributo INTERNO
    def __call__(self, caps): return caps

class DenoiserAlternativo:                          # contrato "publico" cumprido...
    def __call__(self, caps): return caps           # ...mas SEM `it_sim_model`

class Pipeline:
    def __init__(self, models, denoiser):
        self.it_sim_model = models["blip_itm"]      # tem a PROPRIA referencia (L50)
        self.denoiser = denoiser
    def compute_frame_features(self):
        # RefCap constructpipe/base.py:155 -- alcanca DENTRO do colaborador
        return f"features via {self.denoiser.it_sim_model}"

models = {"blip_itm": "BLIP-ITM"}
print(f"\n  (a) Com o denoiser oficial: {Pipeline(models, DenoiserOficial(models)).compute_frame_features()}")
print("\n  (b) Com um denoiser que cumpre o contrato publico mas nao tem o atributo:")
try:
    Pipeline(models, DenoiserAlternativo()).compute_frame_features()
except AttributeError as e:
    print(f"      AttributeError: {e}")

print("""
  >>> O Pipeline TEM `self.it_sim_model` (o mesmo objeto!) mas usa
      `self.denoiser.it_sim_model`. Consequencia: o contrato REAL do denoiser
      e' maior que o declarado -- ele precisa expor um atributo que nenhuma
      interface menciona. Quebra numa etapa que nada tem a ver com denoising.
  RefCap: constructpipe/base.py:50 (tem) vs :155,159 (usa o do denoiser)
""")

print(SEP); print(" FIM — os 10 conceitos, cada um funcionando e cada um quebrado.")
print("="*76 + "\n")
