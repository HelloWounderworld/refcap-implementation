# ══════════════════════════════════════════════════════════════════════
# PROVA 1: a "guarda de robustez" contra video corrompido CAUSA um crash
#          na etapa seguinte (KeyError). Reproducao fiel da interacao.
# ══════════════════════════════════════════════════════════════════════
print("="*72)
print("PROVA 1 — A guarda de corrupcao vira KeyError na etapa seguinte")
print("="*72)

# --- Etapa 1: captioning (BlipCapGener.generate_caption) --------------
def generate_caption(video_name, frames_shape, captions, already):
    if len(frames_shape) != 4:      # BlipCapGener.py:23  <- guarda de corrupcao
        return                       # <- NAO adiciona a `captions`
    captions.append({'vid_name': video_name, 'frame_captions': {0: {'cap': 'x'}}, 'duration': 10})
    already.add(video_name)

vid_list = ["bom.mp4", "corrompido.mp4", "outro.mp4"]
shapes   = {"bom": (10,384,384,3), "corrompido": (1,), "outro": (8,384,384,3)}  # (1,) = torch.zeros(1)

captions, already = [], set()
for vid in vid_list:
    generate_caption(vid.split('.')[0], shapes[vid.split('.')[0]], captions, already)

print(f"\n  vid_list         = {vid_list}")
print(f"  captions gerados = {[c['vid_name'] for c in captions]}   <- 'corrompido' ausente (guarda funcionou)")

# --- Etapa 2: compute_frame_features (constructpipe/base.py:137-141) --
print("\n  Agora a etapa seguinte itera sobre vid_list INTEIRA:")
vid_2_cap = {x['vid_name']: x for x in captions}     # linha 134
all_frame_features = {}
try:
    for vid in vid_list:                              # linha 137
        video_name = vid.split(".")[0]
        if video_name in all_frame_features:          # linha 139
            continue
        raw_cap = vid_2_cap[video_name]               # linha 143  <- ★
        print(f"      {video_name}: ok")
except KeyError as e:
    print(f"      >>> KeyError: {e}  <-- CRASH em constructpipe/base.py:143")
    print("      A guarda impediu o crash no captioning, mas o EMPURROU")
    print("      para a etapa seguinte, onde nao ha' protecao nenhuma.")

# ══════════════════════════════════════════════════════════════════════
# PROVA 2: o shadowing em build_tree_meta funciona POR ACIDENTE
# ══════════════════════════════════════════════════════════════════════
print("\n" + "="*72)
print("PROVA 2 — build_tree_meta: rebind de `proposals` dentro do proprio laco")
print("="*72)

def build_tree_meta(proposals):                       # parametro: dict {vid: metas}
    tree_meta = {}
    for vid, metas in proposals.items():              # itera sobre o dict
        duration = metas['duration']
        proposals = metas['proposals']                # ★ REATRIBUI o nome do parametro!
        tree_meta[vid] = {'vid_name': vid, 'subs': [], 'st': 0.0, 'ed': duration}
        for prop in proposals:                        # aqui `proposals` ja' e' uma LISTA
            tree_meta[vid]['subs'].append({'st': prop['st'], 'ed': prop['ed'], 'subs': []})
    return tree_meta

entrada = {
    "vidA": {'duration': 10.0, 'proposals': [{'st':0.0,'ed':5.0}, {'st':5.0,'ed':10.0}]},
    "vidB": {'duration': 8.0,  'proposals': [{'st':0.0,'ed':8.0}]},
}
res = build_tree_meta(entrada)
print(f"\n  Resultado: {len(res)} videos processados -> FUNCIONA")
print("  Por que? `proposals.items()` e' avaliado UMA vez; o iterador ja' segura")
print("  a referencia ao dict original. Reatribuir o NOME nao afeta o iterador.")
print("  >>> Mas o nome `proposals` significa DUAS coisas no mesmo escopo:")
print("      o dict {vid: metas} (parametro) e a lista de propostas (dentro do laco).")
print("      Funciona por acidente da semantica de iteradores -- e' uma mina.")

# ══════════════════════════════════════════════════════════════════════
# PROVA 3: a "arvore" e' PLANA (2 niveis), apesar do nome
# ══════════════════════════════════════════════════════════════════════
print("\n" + "="*72)
print("PROVA 3 — tree_meta nao e' uma arvore: e' uma lista de 2 niveis")
print("="*72)
import json
print(json.dumps(res["vidA"], indent=2))
print("\n  Os filhos tem 'subs': [] SEMPRE vazio -> nao ha' recursao, nao ha' profundidade.")
print("  'CapTree' sugere hierarquia; a estrutura real e' raiz + 1 nivel de folhas.")
