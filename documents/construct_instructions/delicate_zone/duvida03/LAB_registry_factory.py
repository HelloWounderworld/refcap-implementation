"""
LABORATÓRIO — Como funciona `get_capgen_class(nome)(cfg, models)`
=================================================================
Rode com:  python3 LAB_registry_factory.py
Mexa nele. O objetivo é ver os TIPOS em cada estágio — é aí que a confusão morre.
"""

print("\n" + "="*74)
print(" NÍVEL 0 — O problema que o padrão resolve (a versão ingênua)")
print("="*74)

class GeradorBLIP_v0:
    def __init__(self, cfg): self.cfg = cfg

class GeradorMiniGPT_v0:
    def __init__(self, cfg): self.cfg = cfg

def get_gerador_INGENUO(nome):
    if nome == "blip":
        return GeradorBLIP_v0
    elif nome == "minigpt":
        return GeradorMiniGPT_v0
    raise ValueError(nome)

print("""
  def get_gerador(nome):
      if   nome == "blip":    return GeradorBLIP
      elif nome == "minigpt": return GeradorMiniGPT      <- para adicionar um 3o gerador,
      raise ValueError(nome)                                voce TEM que editar esta funcao

  Problema: a funcao de busca CONHECE todos os geradores. Cada gerador novo exige
  MODIFICAR codigo existente (e arriscar quebra-lo). E o oposto do Open/Closed.
""")
print("  Mas repare no que ela ja faz, e que e' o fato fundamental:")
print(f"     ela devolve UMA CLASSE, nao uma instancia -> {get_gerador_INGENUO('blip')}")


print("\n" + "="*74)
print(" NÍVEL 1 — O fato que habilita tudo: CLASSES SÃO VALORES")
print("="*74)
print("""
  Em Python, uma classe nao e' "codigo especial". E' um OBJETO comum, criado
  pela metaclasse `type`. Logo ela pode ser: guardada numa variavel, colocada
  numa lista, passada como argumento, e -- o que interessa -- ARMAZENADA NUM DICT.
""")
print(f"  type(GeradorBLIP_v0)          = {type(GeradorBLIP_v0)}")
print(f"  isinstance(GeradorBLIP_v0, object) = {isinstance(GeradorBLIP_v0, object)}")

REGISTRY_MANUAL = {"blip": GeradorBLIP_v0, "minigpt": GeradorMiniGPT_v0}
print(f"\n  REGISTRY_MANUAL = {{'blip': GeradorBLIP_v0, ...}}")
print(f"  REGISTRY_MANUAL['blip'] = {REGISTRY_MANUAL['blip']}")
print("""
  Agora a busca vira UMA linha, e ela nao conhece gerador nenhum:
      def get_gerador(nome): return REGISTRY[nome]
  A pergunta que sobra: quem POVOA o dicionario? -> Nivel 2.
""")


print("\n" + "="*74)
print(" NÍVEL 2 — O decorator-fábrica desmontado (as 3 camadas)")
print("="*74)

CAPGEN_REGISTRY = {}

def REGISTER_CAPGEN(names):              # CAMADA 1: recebe o(s) NOME(S)
    print(f"      [C1] REGISTER_CAPGEN({names!r}) executou -> devolve o decorador real")
    def register_capgen_cls(cls):        # CAMADA 2: o decorador de verdade, recebe a CLASSE
        print(f"      [C2] register_capgen_cls({cls.__name__}) executou -> registra e devolve a classe")
        if isinstance(names, str):
            CAPGEN_REGISTRY[names] = cls
        else:
            for n in names:
                if n in CAPGEN_REGISTRY:
                    raise ValueError(f"duplicado: {n}")
                CAPGEN_REGISTRY[n] = cls
        return cls                       # <- DEVOLVE A CLASSE INTACTA (nao a substitui!)
    return register_capgen_cls

print("""
  A sintaxe do RefCap:

      @REGISTER_CAPGEN(["blip"])
      class CapGeneratorBLIP(BaseCapGen): ...

  A EQUIVALÊNCIA EXATA (grave esta, e o misterio acaba):

      class CapGeneratorBLIP(BaseCapGen): ...
      CapGeneratorBLIP = REGISTER_CAPGEN(["blip"])(CapGeneratorBLIP)
                         └──────┬──────┘ └───┬────┘
                            camada 1      camada 2
                         devolve o      recebe a classe,
                         decorador      registra, devolve

  Ou seja: `@REGISTER_CAPGEN(["blip"])` NAO e' o decorador. E' uma CHAMADA que
  PRODUZ o decorador. Por isso ha duas funcoes aninhadas: a de fora captura o
  NOME (via closure), a de dentro recebe a CLASSE. Sem os parenteses/argumento,
  bastaria uma funcao so'.
""")

print("  Observando a execucao real (repare na ORDEM C1 -> C2):\n")

@REGISTER_CAPGEN(["base", "minigpt"])
class BaseCapGen:
    def __init__(self, cfg, models):
        self.cfg, self.models = cfg, models
        self.captions = []
    def __call__(self, vid_list):                    # <- torna a INSTANCIA chamavel
        for v in vid_list:
            self.generate_caption(v)
        return self.captions
    def generate_caption(self, v):                   # <- HOOK: a subclasse sobrescreve
        raise NotImplementedError("use script externo")

@REGISTER_CAPGEN(["blip"])
class CapGeneratorBLIP(BaseCapGen):
    def __init__(self, cfg, models):
        super().__init__(cfg, models)
        self.modelo = models["cap_gen_model"]
    def generate_caption(self, v):
        self.captions.append(f"[{self.modelo}] legenda de {v} @{self.cfg['res']}px")

def get_capgen_class(name):
    if name not in CAPGEN_REGISTRY:
        raise ValueError(f"{name} nao registrado")
    return CAPGEN_REGISTRY[name]

print(f"\n  Estado final do registry: {CAPGEN_REGISTRY}")
print("""
  ★ SUTILEZA CRÍTICA (e um alçapão real do RefCap):
    O registro so' acontece quando o MODULO E' IMPORTADO -- porque o decorador
    roda no momento em que a classe e' definida. Por isso o
    `pipeline/capgenerator/__init__.py` faz `from .BlipCapGener import *`:
    se ninguem importar esse modulo, `CapGeneratorBLIP` NUNCA se registra e
    `get_capgen_class("blip")` levanta ValueError.
    O `import *` que criticamos por higiene e', aqui, FUNCIONALMENTE NECESSARIO.
""")


print("\n" + "="*74)
print(" NÍVEL 3 — A TRIPLA APLICAÇÃO (o coração da sua dúvida)")
print("="*74)

cfg = {"res": 384}
models = {"cap_gen_model": "BLIP-large"}

print("\n  `get_capgen_class(cfg.caption_generator)(cfg, pretrained_models)` sao TRES")
print("  aplicacoes encadeadas, cada uma devolvendo um tipo diferente:\n")

etapa1 = get_capgen_class
print(f"   [1] get_capgen_class            -> {type(etapa1).__name__:12s}  (uma funcao)")

etapa2 = get_capgen_class("blip")
print(f"   [2] get_capgen_class('blip')    -> {type(etapa2).__name__:12s}  (uma CLASSE: {etapa2.__name__})")

etapa3 = etapa2(cfg, models)
print(f"   [3] ...('blip')(cfg, models)    -> {type(etapa3).__name__:12s}  (uma INSTANCIA)")

etapa4 = etapa3(["vidA.mp4", "vidB.mp4"])
print(f"   [4] ...(cfg, models)(vid_list)  -> {type(etapa4).__name__:12s}  (o RESULTADO)")
print(f"       = {etapa4}")

print("""
  ★ O QUE ISSO É, EM LINGUAGEM MATEMÁTICA (a sua intuicao, tornada precisa):

      get_capgen_class : Nome ───────────────► Classe
      Classe.__init__  : (Cfg × Models) ─────► Instancia      [APLICACAO PARCIAL]
      Instancia.__call__: VidList ───────────► Captions       [a funcao "de verdade"]

  A etapa [3] e' uma APLICACAO PARCIAL (currying): voce pre-carrega cfg e models
  dentro de um objeto, e o que sobra e' uma funcao UNARIA `vid_list |-> captions`.
  O objeto e' um "closure com nome" -- em POO chama-se FUNCTOR ou function object.

  Por isso o `construct()` consegue escrever `self.caption_generator(vid_list=...)`
  como se fosse uma funcao simples: toda a configuracao ja foi absorvida antes.
""")


print("\n" + "="*74)
print(" NÍVEL 4 — Injeção de dependência + Template Method")
print("="*74)

CONSTRUCTPIPE_REGISTRY = {}
def REGISTER_PIPE(names):
    def deco(cls):
        for n in ([names] if isinstance(names, str) else names):
            CONSTRUCTPIPE_REGISTRY[n] = cls
        return cls
    return deco
def get_pipe_class(name): return CONSTRUCTPIPE_REGISTRY[name]

@REGISTER_PIPE(["base"])
class BaseConstructPipeline:
    def __init__(self, cfg, caption_generator, denoiser, proposal_generator):
        self.cfg = cfg
        self.caption_generator = caption_generator      # <- RECEBE pronto (nao cria!)
        self.denoiser = denoiser
        self.proposal_generator = proposal_generator
        self.vid_list = ["vidA.mp4", "vidB.mp4"]

    def construct(self):                                 # <- TEMPLATE METHOD: fixa a ORDEM
        print("      1. gerando legendas...")
        caps = self.caption_generator(self.vid_list)     # nao sabe QUAL gerador e'
        print("      2. denoising...")
        caps = self.denoiser(caps)
        print("      3. propostas...")
        props = self.proposal_generator(caps)
        return props

class DenoiserFake:
    def __call__(self, caps): return [c + " (limpa)" for c in caps]
class PropGenFake:
    def __call__(self, caps): return [{"seg": i, "cap": c} for i, c in enumerate(caps)]

print("\n  A montagem (isto e' o `main()` do construct.py -- a COMPOSITION ROOT):\n")
capgen = get_capgen_class("blip")(cfg, models)
pipe = get_pipe_class("base")(cfg, capgen, DenoiserFake(), PropGenFake())
print("      construct_pipeline.construct():")
resultado = pipe.construct()
print(f"\n      -> {resultado}")

print("""
  ★ A DISTINCAO QUE REFINA O SEU MODELO MENTAL:
    Ha DOIS papeis diferentes, e e' facil funde-los:

      - COMPOSITION ROOT (o `main()`): decide QUAIS implementacoes existem e as
        MONTA. E' o unico lugar que conhece os nomes concretos ("blip", "qm"...).
      - ORQUESTRADOR (`BaseConstructPipeline.construct()`): decide a ORDEM dos
        passos. NAO sabe qual gerador recebeu -- so' sabe que da' para chama-lo.

    O pipeline NAO "reune as classes": ele as RECEBE prontas. Isso e' INVERSAO
    DE CONTROLE. Analogia: o `main()` e' o empresario que contrata os musicos;
    o pipeline e' o maestro que le' a partitura sem saber quem foi contratado.
""")


print("\n" + "="*74)
print(" NÍVEL 5 — A recompensa: estender SEM modificar (Open/Closed)")
print("="*74)
print("""
  Adicionar um gerador novo agora nao toca em NENHUMA linha existente --
  nem no registry, nem na factory, nem no pipeline. So' se acrescenta:
""")

@REGISTER_CAPGEN(["llava"])
class CapGeneratorLLaVA(BaseCapGen):
    def generate_caption(self, v):
        self.captions.append(f"[LLaVA] descricao detalhada de {v}")

print(f"\n  Registry agora: {sorted(CAPGEN_REGISTRY.keys())}")
novo = get_capgen_class("llava")(cfg, models)
print(f"  get_capgen_class('llava')(cfg, models)(['vidA.mp4']) = {novo(['vidA.mp4'])}")
print("""
  Trocar o gerador do sistema inteiro passou a ser trocar UMA STRING no shell:
      caption_generator=blip   ->   caption_generator=llava
  O grafo de objetos do programa e' decidido por CONFIGURACAO, nao por codigo.
  E' isso que se chama DESIGN ORIENTADO A DADOS (data-driven design).
""")


print("\n" + "="*74)
print(" EXERCÍCIOS (para fixar)")
print("="*74)
print("""
  1. Comente o `return cls` (linha do decorador C2) e rode. O que acontece com
     a classe decorada? Por que? (Dica: o decorador SUBSTITUI o nome pelo que
     ele devolve.) -> entender por que devolver `cls` e' obrigatorio.

  2. Registre duas classes com o mesmo nome. Veja o ValueError. Por que essa
     guarda existe? O que ela protege?

  3. Troque `@REGISTER_CAPGEN(["blip"])` pela forma explicita
     `CapGeneratorBLIP = REGISTER_CAPGEN(["blip"])(CapGeneratorBLIP)`.
     Confirme que o comportamento e' IDENTICO.

  4. Mova a classe `CapGeneratorLLaVA` para outro arquivo e NAO o importe.
     Chame `get_capgen_class("llava")`. Explique o erro. (Este e' o alcapao
     do Nivel 2 -- e a razao do `import *` no `__init__.py` do RefCap.)

  5. Remova o `__call__` de `BaseCapGen` e tente `capgen(vid_list)`.
     Qual e' o erro? O que `__call__` estava fazendo pela instancia?
""")
