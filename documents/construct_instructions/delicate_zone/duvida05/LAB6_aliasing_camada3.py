import copy
print("="*72); print("PROVA A — `return self.captions` devolve a REFERENCIA, nao uma copia")
print("="*72)

class BaseCapGen:
    def __init__(self):
        self.captions = []
    def __call__(self, vid_list):
        for v in vid_list:
            self.captions.append({'vid_name': v, 'frame_captions': {'0': {'cap': 'crua'}}})
        return self.captions          # <- capgenerator/base.py:48

gen = BaseCapGen()
captions = gen(["vidA"])              # <- constructpipe/base.py:69
print(f"\n  captions is gen.captions  ->  {captions is gen.captions}   (mesmo objeto!)")
print(f"  id(captions)={id(captions)}  id(gen.captions)={id(gen.captions)}")

print("\n" + "="*72); print("PROVA B — o denoiser MUTA os dicionarios originais no lugar")
print("="*72)

def denoise_caption(meta):            # <- denoiser/window.py:20-35 (fiel)
    meta['frame_captions']['0'] = copy.deepcopy({'cap': 'DENOISED'})
    return meta                       # <- devolve o MESMO objeto

print(f"\n  ANTES : gen.captions[0]['frame_captions'] = {gen.captions[0]['frame_captions']}")
denoised = [denoise_caption(c) for c in captions]
print(f"  DEPOIS: gen.captions[0]['frame_captions'] = {gen.captions[0]['frame_captions']}   <-- ★ MUDOU")
print(f"\n  denoised[0] is captions[0] is gen.captions[0]  ->  {denoised[0] is captions[0] is gen.captions[0]}")
print("""
  >>> As legendas CRUAS foram DESTRUIDAS na memoria. `captions` e
      `denoised_captions` sao aliases dos MESMOS dicionarios. A distincao
      "crua vs denoised" existe apenas nos objetos-LISTA, nao no conteudo.
      O estado interno do gerador (`self.captions`) tambem foi contaminado.""")

print("\n" + "="*72); print("PROVA C — cfg e' compartilhado e MUTAVEL entre todos")
print("="*72)
from dataclasses import dataclass
@dataclass
class Cfg:
    res_dir: str = "results"          # exp_dir NAO existe na definicao!

cfg = Cfg()
try:
    cfg.exp_dir
except AttributeError as e:
    print(f"\n  Cfg() recem-criado -> AttributeError: {e}")
cfg.exp_dir = "results/construct/x"   # <- construct.py:36 injeta o campo
print(f"  Depois de `cfg.exp_dir = ...` -> cfg.exp_dir = {cfg.exp_dir!r}")
print("""
  >>> 4 modulos usam `self.cfg.exp_dir`, mas o campo NAO existe em BuildArguments.
      Ele so' existe porque o main() o injetou na linha 36. Se voce construir
      BuildArguments() no seu proprio script e passar ao pipeline, quebra.""")
