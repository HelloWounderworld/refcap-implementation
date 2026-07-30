"""Teste funcional do WholePropGenerator com stubs.

Verifica o comportamento contra o CONTRATO real do RefCap, incluindo o assert
de shape de sim_utils.py:87 (reproduzido fielmente no stub).
"""
import sys, os
sys.path.insert(0, "/tmp/tb/stubs")
sys.path.insert(0, "/tmp/tb")

import numpy as np
sys.path.insert(0,"/tmp/tb/stubs")
from faketensor import ft

falhas = []
def check(nome, cond, detalhe=""):
    marca = "✓" if cond else "✗ FALHOU"
    print(f"  {marca}  {nome}" + (f"   [{detalhe}]" if detalhe and not cond else ""))
    if not cond:
        falhas.append(nome)

# --------------------------------------------------------------------------
from pipeline.propgenerator import get_propgen_class, PROPGEN_REGISTRY
import utils.basic_utils as basic_utils
import utils.sim_utils as sim_utils

print("="*74); print(" T1 — REGISTRO NO REGISTRY"); print("="*74)
check("'whole' registrado", "whole" in PROPGEN_REGISTRY)
cls = get_propgen_class("whole")
check("get_propgen_class('whole') devolve a classe", cls.__name__ == "WholePropGenerator")
check("herda de BasePropGen", any(b.__name__ == "BasePropGen" for b in cls.__mro__[1:]))
check("é instanciável (ABC satisfeita: __call__ implementado)", True)

# --------------------------------------------------------------------------
class Cfg:
    device = "cpu"
    exp_dir = "/tmp/tb/out"
    proposals_file = "proposals.json"
    prop_sim_path = "prop_sims.pt"

class ModeloFake:
    def encode(self, textos, **kw):
        return sim_utils._get_caption_features(None, None, textos, None)

MODELS = {
    "sentence_transformer": ModeloFake(),
    "blip_itrtv_model": object(),
    "blip_itrtv_processor": object(),
}

os.makedirs("/tmp/tb/out", exist_ok=True)
gen = cls(Cfg(), MODELS)
print(f"\n  instanciado. rank_by={gen.rank_by!r}  dedup={gen.dedup}")

def features(n, d=8, seed=0):
    rng = np.random.default_rng(seed)
    f = rng.normal(size=(n, d))
    from faketensor import ft
    return ft(f / np.linalg.norm(f, axis=1, keepdims=True))

def montar(vid, caps, duration, chaves_str=False):
    fc = {}
    for i, c in enumerate(caps):
        fc[str(i) if chaves_str else i] = {"cap": c}
    return {"vid_name": vid, "duration": duration, "frame_captions": fc}

# --------------------------------------------------------------------------
print("\n" + "="*74); print(" T2 — CONTRATO DE SAÍDA (o que build_tree_meta lê)"); print("="*74)
caps = ["a woman in a kitchen", "a woman cooking food", "a close up of a knife"]
capt = [montar("vidA", caps, 3.0)]
ff = {"vidA": features(3, seed=1)}
res = gen(["vidA.mp4"], capt, {"vidA": ft(np.array([.9,.8,.7]))}, ff)

check("uma entrada por vídeo", set(res.keys()) == {"vidA"})
v = res["vidA"]
check("tem 'proposals' e 'duration'", "proposals" in v and "duration" in v)
check("exatamente UMA proposta", len(v["proposals"]) == 1, f"n={len(v['proposals'])}")
p = v["proposals"][0]
for k in ("st", "ed", "cap"):
    check(f"proposta tem '{k}' (obrigatório em build_tree_meta:177)", k in p)
check("'keys' presente (opcional, L178-179)", "keys" in p)
check("st == 0.0", p["st"] == 0.0, str(p["st"]))
check("ed == duration", p["ed"] == 3.0, str(p["ed"]))
check("cap é string não vazia", isinstance(p["cap"], str) and len(p["cap"]) > 0)
check("cap é o topo do ranking", p["cap"] == p["ranking"][0]["cap"])

print("\n" + "="*74); print(" T3 — O SEGMENTO COBRE A CENA INTEIRA (sem fronteiras)"); print("="*74)
check("um único segmento [0, duration]", p["st"] == 0.0 and p["ed"] == v["duration"])
check("nenhuma detecção de fronteira ocorreu (1 proposta só)", len(v["proposals"]) == 1)

print("\n" + "="*74); print(" T4 — O RANKING"); print("="*74)
r = p["ranking"]
check("ranking tem uma entrada por legenda distinta", len(r) == 3, f"n={len(r)}")
for s in ("scene_score", "self_score", "consensus", "pipeline_score", "n_words", "n_occurrences"):
    check(f"sinal '{s}' presente", all(s in x for x in r))
vals = [x[gen.rank_by] for x in r]
check(f"ordenado por {gen.rank_by} decrescente", vals == sorted(vals, reverse=True), str(vals))
check("scene_score é média da LINHA (≠ self_score em geral)",
      any(abs(x["scene_score"] - x["self_score"]) > 1e-9 for x in r))

print("\n" + "="*74); print(" T5 — DEDUPLICAÇÃO"); print("="*74)
caps_dup = ["a woman in a kitchen", "A WOMAN IN A KITCHEN.", "a woman in a kitchen",
            "a close up of a knife"]
res2 = gen(["vidB.mp4"], [montar("vidB", caps_dup, 4.0)], {"vidB": ft(np.array([.9,.8,.7,.6]))},
           {"vidB": features(4, seed=2)})
p2 = res2["vidB"]["proposals"][0]
check("n_raw == 4", p2["n_raw"] == 4, str(p2["n_raw"]))
check("n_distinct == 2 (case/pontuação normalizados)", p2["n_distinct"] == 2, str(p2["n_distinct"]))
occ = {x["cap"].lower().rstrip("."): x["n_occurrences"] for x in p2["ranking"]}
check("a legenda repetida tem n_occurrences == 3",
      max(x["n_occurrences"] for x in p2["ranking"]) == 3, str(occ))
check("frames registrados por legenda", all(len(x["frames"]) == x["n_occurrences"] for x in p2["ranking"]))

print("\n" + "="*74); print(" T6 — RAMO n_distinct == 1 (sem matriz, sem NaN)"); print("="*74)
sim_utils.CALLS.clear()
res3 = gen(["vidC.mp4"], [montar("vidC", ["a dog running"], 1.5)],
           {"vidC": ft(np.array([np.nan]))},           # ← o NaN que o min-max produz em N=1
           {"vidC": features(1, seed=3)})
p3 = res3["vidC"]["proposals"][0]
check("uma proposta emitida", len(res3["vidC"]["proposals"]) == 1)
check("cap correto", p3["cap"] == "a dog running")
check("n_distinct == 1", p3["n_distinct"] == 1)
check("NÃO chamou a matriz cruzada (caminho curto)", len(sim_utils.CALLS) == 0,
      f"chamadas={sim_utils.CALLS}")
check("sinais são None (não NaN) no caminho curto",
      p3["ranking"][0]["scene_score"] is None and p3["ranking"][0]["consensus"] is None)
import json
check("saída é JSON-serializável (sem NaN cru)", "NaN" not in json.dumps(p3))

print("\n" + "="*74); print(" T7 — TODAS AS LEGENDAS IDÊNTICAS → cai no ramo curto"); print("="*74)
sim_utils.CALLS.clear()
res4 = gen(["vidD.mp4"], [montar("vidD", ["a cat sleeping"]*3, 3.0)],
           {"vidD": ft(np.array([.5,.5,.5]))}, {"vidD": features(3, seed=4)})
p4 = res4["vidD"]["proposals"][0]
check("n_raw=3, n_distinct=1", p4["n_raw"] == 3 and p4["n_distinct"] == 1)
check("não chamou a matriz", len(sim_utils.CALLS) == 0)
check("n_occurrences == 3", p4["ranking"][0]["n_occurrences"] == 3)

print("\n" + "="*74); print(" T8 — CHAVES str (2ª execução, recarregado do .jsonl)"); print("="*74)
res5 = gen(["vidE.mp4"], [montar("vidE", caps, 3.0, chaves_str=True)],
           {"vidE": ft(np.array([.9,.8,.7]))}, {"vidE": features(3, seed=1)})
p5 = res5["vidE"]["proposals"][0]
check("funciona com chaves string", p5["n_raw"] == 3)
check("mesmo resultado que com chaves int", p5["cap"] == p["cap"], f"{p5['cap']!r} vs {p['cap']!r}")

print("\n" + "="*74); print(" T9 — ORDEM TEMPORAL PRESERVADA (chaves fora de ordem)"); print("="*74)
fc = {"2": {"cap": "terceira"}, "0": {"cap": "primeira"}, "1": {"cap": "segunda"}}
capt6 = [{"vid_name": "vidF", "duration": 3.0, "frame_captions": fc}]
res6 = gen(["vidF.mp4"], capt6, {"vidF": ft(np.array([.1,.2,.3]))}, {"vidF": features(3, seed=5)})
p6 = res6["vidF"]["proposals"][0]
frames_por_cap = {x["cap"]: x["frames"][0] for x in p6["ranking"]}
check("'primeira' está no frame 0", frames_por_cap.get("primeira") == 0, str(frames_por_cap))
check("'terceira' está no frame 2", frames_por_cap.get("terceira") == 2, str(frames_por_cap))

print("\n" + "="*74); print(" T10 — VÍDEO SEM LEGENDAS (não deve estourar)"); print("="*74)
try:
    res7 = gen(["vidG.mp4", "vidA.mp4"], [montar("vidA", caps, 3.0)],
               {"vidA": ft(np.array([.9,.8,.7]))}, {"vidA": features(3, seed=1)})
    check("não levantou exceção com vídeo ausente em captions", True)
    check("vidG omitido da saída (avisado)", "vidG" not in res7)
    check("vidA processado normalmente", "vidA" in res7)
except Exception as e:
    check("não levantou exceção com vídeo ausente", False, f"{type(e).__name__}: {e}")

print("\n" + "="*74); print(" T11 — CENA COM ZERO FRAMES (duração < 1s)"); print("="*74)
try:
    res8 = gen(["vidH.mp4"], [{"vid_name": "vidH", "duration": 0.8, "frame_captions": {}}],
               {}, {})
    p8 = res8["vidH"]
    check("não estourou", True)
    check("proposals vazio", p8["proposals"] == [])
    check("warning presente", p8.get("warning") is not None)
except Exception as e:
    check("não estourou com 0 frames", False, f"{type(e).__name__}: {e}")

print("\n" + "="*74); print(" T12 — O ASSERT DE SHAPE É RESPEITADO"); print("="*74)
sim_utils.CALLS.clear()
res9 = gen(["vidI.mp4"], [montar("vidI", caps_dup, 4.0)], {"vidI": ft(np.array([.9,.8,.7,.6]))},
           {"vidI": features(4, seed=2)})
check("chamou get_caption_frame_sims sem AssertionError", len(sim_utils.CALLS) == 1,
      str(sim_utils.CALLS))
if sim_utils.CALLS:
    n_caps, shape_ff = sim_utils.CALLS[0]
    check("chamou com TODAS as N legendas (não as distintas)", n_caps == 4,
          f"n_caps={n_caps} (distintas=2)")
    check("shapes casam (o assert passaria)", n_caps == shape_ff[0])

print("\n" + "="*74); print(" T13 — PERSISTÊNCIA"); print("="*74)
check("save_json foi chamado no caminho esperado",
      "/tmp/tb/out/proposals.json" in basic_utils.SAVED,
      str(list(basic_utils.SAVED.keys())))

print("\n" + "="*74); print(" T14 — KEYWORDS (insumo do ramo GloVe)"); print("="*74)
check("keys é lista não vazia", isinstance(p["keys"], list) and len(p["keys"]) > 0)
check("keys sem duplicatas", len(p["keys"]) == len(set(p["keys"])))
check("keys vem de TODAS as legendas, não só da vencedora",
      any("knife" in k for k in p["keys"]) or any("kitchen" in k for k in p["keys"]),
      str(p["keys"]))

print("\n" + "="*74)
if falhas:
    print(f" RESULTADO: {len(falhas)} FALHA(S) -> {falhas}")
else:
    print(" RESULTADO: TODOS OS TESTES PASSARAM")
print("="*74)
