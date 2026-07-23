"""
LABORATÓRIO 4 — A linha do tempo da instanciação e o efeito "camaleão"
=======================================================================
Responde: QUANDO cada classe e' instanciada, e por que a MESMA variavel
parece "mudar de tipo" conforme o construct.sh.

Rode com:  python3 LAB4_instanciacao_e_binding.py
"""
SEP = "\n" + "="*76

# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 1. A LINHA DO TEMPO — quando cada __init__ dispara (instrumentado)")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

REG = {}
def REGISTER(names):
    def deco(cls):
        for n in ([names] if isinstance(names, str) else names):
            REG[n] = cls
        return cls
    return deco
def get_class(n): return REG[n]

@REGISTER(["base", "minigpt"])
class BaseCapGen:
    def __init__(self, cfg, models):
        print("      [__init__] BaseCapGen        <- le' o cache .jsonl do disco")
        self.cfg, self.models = cfg, models
        self.captions = []
    def __call__(self, vid_list):
        return [self.generate_caption(v) for v in vid_list]
    def generate_caption(self, v):
        return f"BASE: {v} (legenda externa)"

@REGISTER(["blip"])
class CapGeneratorBLIP(BaseCapGen):
    def __init__(self, cfg, models):
        print("      [__init__] CapGeneratorBLIP  <- chama super() primeiro:")
        super().__init__(cfg, models)
        print("                                   <- e pega models['cap_gen_model']")
        self.cap_model = models["cap_gen_model"]
    def generate_caption(self, v):
        return f"BLIP: legenda gerada de {v}"

@REGISTER(["window"])
class WindowDenoiser:
    def __init__(self, cfg, models):
        print("      [__init__] WindowDenoiser    <- pega o modelo ITM")
        self.it_sim_model = models["blip_itm"]
    def __call__(self, caps): return caps

@REGISTER(["qm"])
class QMPropGenerator:
    def __init__(self, cfg, models):
        print("      [__init__] QMPropGenerator   <- carrega o spacy (~50MB!)")
        self.cfg = cfg
    def __call__(self, caps): return [{"seg": 0, "cap": c} for c in caps]

@REGISTER(["pipeline_base"])
class BaseConstructPipeline:
    def __init__(self, cfg, capgen, denoiser, propgen, models):
        print("      [__init__] BaseConstructPipeline  <- ★ POR ULTIMO, e faz MUITO:")
        print("                    - guarda os 3 colaboradores JA' PRONTOS")
        self.capgen, self.denoiser, self.propgen = capgen, denoiser, propgen
        print("                    - os.listdir(video_root)")
        print("                    - select_videos()  <- pode RODAR FFMPEG (mkv->mp4)")
        print("                    - create_dirs()    <- cria diretorios no disco")
        self.vid_list = ["vidA.mp4", "vidB.mp4"]
    def construct(self):
        print("      [construct] agora sim comeca o trabalho...")
        caps = self.capgen(self.vid_list)
        return self.propgen(self.denoiser(caps))

cfg = {"res": 384}
models = {"cap_gen_model": "BLIP-large", "blip_itm": "BLIP-ITM"}

print("\n  Executando as linhas 43-47 do construct.py, em ordem:\n")
print("  linha 43 >> caption_generator = get_capgen_class('blip')(cfg, models)")
caption_generator  = get_class("blip")(cfg, models)
print("\n  linha 44 >> caption_denoiser = get_denoiser_class('window')(cfg, models)")
caption_denoiser   = get_class("window")(cfg, models)
print("\n  linha 45 >> proposal_generator = get_propgen_class('qm')(cfg, models)")
proposal_generator = get_class("qm")(cfg, models)
print("\n  linha 47 >> construct_pipeline = get_constructpipe_class('base')(cfg, ...)")
construct_pipeline = get_class("pipeline_base")(cfg, caption_generator,
                                                caption_denoiser, proposal_generator, models)
print("\n  linha 49 >> construct_pipeline.construct()")
res = construct_pipeline.construct()
print(f"      resultado: {res}")

print("""
  ★ AS DUAS RESPOSTAS DIRETAS:
     - `CapGeneratorBLIP` e' instanciada na LINHA 43, no SEGUNDO par de parenteses.
     - `BaseConstructPipeline` e' instanciada na LINHA 47, DEPOIS de todas as outras.

  ★ POR QUE essa ordem e' obrigatoria: o pipeline RECEBE os colaboradores como
    argumentos do construtor. Eles precisam EXISTIR antes. O grafo de objetos e'
    montado de BAIXO PARA CIMA -- folhas primeiro, raiz por ultimo.

  ★ E note: instanciar NAO e' barato aqui. O construtor do pipeline ja' lista
    diretorio, filtra por annos, pode converter arquivos com ffmpeg e cria pastas.
    "Construir o objeto" ja' e' parte do trabalho -- e isso viola CQS.
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 2. O 'CAMALEÃO' — o mesmo nome, objetos de classes diferentes")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

print("\n  Trocando APENAS a string de configuracao:\n")
for escolha in ["blip", "minigpt", "base"]:
    caption_generator = get_class(escolha)(cfg, models)   # ← MESMO nome de variavel
    print(f"    cfg.caption_generator = {escolha!r:10s} ->  type = {type(caption_generator).__name__:18s}"
          f" id = {id(caption_generator)}")
    print(f"        uso IDENTICO: caption_generator(['vidA']) = {caption_generator(['vidA'])}")

print("""
  >>> A variavel `caption_generator` "virou" tres coisas diferentes.
      E a LINHA DE USO nunca mudou. Esse e' o efeito que voce percebeu.
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 3. A MECÂNICA: em Python, NOMES não têm tipo — OBJETOS têm")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════

x = 42
print(f"\n    x = 42                 -> type(x) = {type(x).__name__:10s} id(x) = {id(x)}")
x = "quarenta e dois"
print(f"    x = 'quarenta e dois'  -> type(x) = {type(x).__name__:10s} id(x) = {id(x)}")
x = CapGeneratorBLIP(cfg, models)
print(f"    x = CapGeneratorBLIP() -> type(x) = {type(x).__name__:10s} id(x) = {id(x)}")

print("""
  >>> Repare no `id`: ele MUDA a cada atribuicao. Isso prova que o objeto e' outro.
      A variavel `x` nao "se transformou" -- ela e' apenas uma ETIQUETA que foi
      COLADA em objetos diferentes.

  ★ A CORRECAO DA INTUICAO: nao e' a variavel que e' camaleao.
    Em Python, um nome e' uma REFERENCIA SEM TIPO -- um rotulo num dicionario de
    namespace. Ele nao declara nem restringe nada. O tipo pertence ao OBJETO.
    Portanto nao ha' transformacao: ha' RELIGACAO (rebinding) do nome a outro objeto.

    O nome tecnico do mecanismo: LIGACAO DINAMICA DE NOMES (dynamic name binding).
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 4. TIPO ESTÁTICO vs TIPO DINÂMICO — o que uma linguagem tipada mostraria")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════
from typing import Protocol

class CapGenProtocol(Protocol):
    def __call__(self, vid_list) -> list: ...

# a anotacao declara o tipo ESTATICO (o papel); o objeto tem o tipo DINAMICO (a classe)
caption_generator: CapGenProtocol = get_class("blip")(cfg, models)

print(f"""
  Em Java/C# voce escreveria:

      CapGen caption_generator = factory.get("blip");
      └─┬──┘                     └────────┬────────┘
    TIPO ESTATICO              o objeto tem TIPO DINAMICO
    (a interface, fixa)        (CapGeneratorBLIP, varia)

  Em Python, com type hints, o mais proximo e':

      caption_generator: CapGenProtocol = get_capgen_class("blip")(cfg, models)

  tipo ESTATICO declarado : CapGenProtocol   (so' o mypy ve'; o interpretador ignora)
  tipo DINAMICO real      : {type(caption_generator).__name__}

  >>> ESSA e' a chave da sua intuicao. Em linguagem tipada, o "camaleao" e'
      controlado: a variavel e' declarada como a INTERFACE, e so' pode receber
      implementacoes dela. Em Python NAO HA' declaracao nenhuma -- o efeito
      camaleao e' TOTAL, e nada impede de atribuir algo incompativel.
      O contrato existe so' na cabeca de quem escreveu (ou num Protocol/mypy).
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 5. O NOME DA VARIÁVEL É UM PAPEL, NÃO UM TIPO")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════
print("""
  Repare nos nomes escolhidos no construct.py:

      caption_generator   <- NAO se chama `blip_generator`
      caption_denoiser    <- NAO se chama `window_denoiser`
      proposal_generator  <- NAO se chama `qm_generator`

  Eles nomeiam o PAPEL que o objeto exerce na arquitetura, nao a classe concreta
  que esta' la' dentro. E' proposital, e e' o que permite:

    (a) a linha de uso `self.caption_generator(vid_list=...)` ler-se identica
        independentemente de qual implementacao foi injetada;
    (b) trocar a implementacao sem que NENHUM nome fique mentindo.

  >>> Se a variavel se chamasse `blip_generator` e voce trocasse para minigpt,
      o nome viraria mentira -- e nomes que mentem sao o pior tipo de comentario
      desatualizado. Nomear pelo PAPEL e' o que torna o polimorfismo legivel.
""")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" 6. ONDE O POLIMORFISMO REALMENTE ACONTECE: no ponto de USO")
print("="*76)
# ══════════════════════════════════════════════════════════════════════════
print("""
  A religacao do nome (secao 3) e' mecanica trivial. O que e' interessante
  acontece DEPOIS, quando o orquestrador USA o objeto:

      # constructpipe/base.py:69
      captions = self.caption_generator(vid_list=self.vid_list)

  Nessa linha, o Python:
    1. olha o TIPO REAL do objeto ligado a self.caption_generator
    2. procura __call__ na MRO desse tipo
    3. executa a versao encontrada  <- DESPACHO DINAMICO

  >>> A "variavel camaleao" e' so' o SINTOMA. O mecanismo e' o despacho dinamico
      no ponto de uso. Uma variavel guardando objetos diferentes seria inutil se
      o Python nao resolvesse o metodo certo em runtime.
""")

print("  Prova: a MESMA linha de uso, tres resultados diferentes:\n")
for escolha in ["blip", "minigpt"]:
    g = get_class(escolha)(cfg, models)
    print(f"    {escolha:8s} -> {g(['vidA'])}")

print(SEP)
print(" RESUMO DOS NOMES TECNICOS")
print("="*76)
print("""
  O que voce percebeu           | Nome tecnico
  ------------------------------|--------------------------------------------
  variavel "camaleao"           | LIGACAO DINAMICA DE NOMES (dynamic binding)
                                | -- nomes em Python sao referencias SEM tipo
  mesma linha, comportamentos   | POLIMORFISMO DE SUBTIPO
  diferentes                    | + DESPACHO DINAMICO (late binding)
  objeto trocavel por config    | STRATEGY (padrao) + INJECAO DE DEPENDENCIA
  a string do .sh decide tudo   | DESIGN ORIENTADO A DADOS (data-driven)
  montagem de baixo para cima   | COMPOSITION ROOT / construcao do grafo de objetos
  nome = papel, nao classe      | PROGRAMACAO ORIENTADA A INTERFACE / a PAPEIS
""")
