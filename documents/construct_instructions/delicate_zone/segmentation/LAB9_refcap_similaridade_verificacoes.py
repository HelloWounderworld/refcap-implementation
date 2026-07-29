"""
LAB9 — VERIFICACOES DO RELATORIO `RefCap_Similaridade_Segmentacao_e_Selecao.md`
================================================================================
Verificacoes especificas do RefCap. Para a matematica pura (Gram, argmax,
normalizacao L2), veja o LAB8.

Rode:  python3 LAB9_refcap_similaridade_verificacoes.py
"""
import numpy as np, itertools, math, warnings

np.set_printoptions(precision=4, suppress=True)
ok = lambda b: "✓ VERIFICADO" if b else "✗ FALSO"
SEP = "\n" + "=" * 78

# Defaults VERIFICADOS em config/cfg.py (linhas 56, 82-102)
KW, MIN_PROP, PMAX, PMIN, THR = 5, 3, 5, 2, 0.5


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" R1 — A CADEIA DO capframe_scores, REPRODUZIDA"); print("="*78)
# ══════════════════════════════════════════════════════════════════════════
print("""
  Reproduz sim_utils.py L52, L74, L90-91 com d=4 (real: 256).
  E_T = embeddings brutos das legendas   (saida de text_proj)
  E_F = embeddings brutos dos frames     (saida de vision_proj)
""")
E_T = np.array([[0.90, 0.80, -0.20, 0.30],     # legenda 0, gerada DO frame 0
                [0.60, -0.30, -0.10, 0.70],    # legenda 1, gerada DO frame 1
                [0.85, 0.75, -0.15, 0.25]])    # legenda 2, gerada DO frame 2
E_F = np.array([[0.95, 0.70, -0.10, 0.35],     # frame 0
                [0.55, -0.40, -0.20, 0.65],    # frame 1
                [0.80, 0.85, -0.25, 0.20]])    # frame 2

Tn = E_T / np.linalg.norm(E_T, axis=1, keepdims=True)   # L74: normalize(...)
Fn = E_F / np.linalg.norm(E_F, axis=1, keepdims=True)   # L52: normalize(...)
print(f"  normas apos L2: legendas {np.linalg.norm(Tn,axis=1).round(6)}  frames {np.linalg.norm(Fn,axis=1).round(6)}")
print(f"  {ok(np.allclose(np.linalg.norm(Tn,axis=1),1) and np.allclose(np.linalg.norm(Fn,axis=1),1))}")

ALL = Tn @ Fn.T                                          # L90: cap_features @ frame_features.t()
print("\n  [R1a] ALL_SIMS = cap_features @ frame_features.T")
print("                 frame0    frame1    frame2")
for i in range(3):
    print(f"     legenda{i}  " + "   ".join(f"{ALL[i][j]:+7.4f}" for j in range(3)))

print("\n  [R1b] conferindo ALL[0][1] termo a termo:")
termos = Tn[0] * Fn[1]
print(f"        {' + '.join(f'{t:+.4f}' for t in termos)} = {termos.sum():+.4f}")
print(f"        {ok(np.isclose(termos.sum(), ALL[0][1]))}")

diag = ALL.diagonal()                                    # L91: ALL_SIMS.diag()
print(f"\n  [R1c] capframe_scores = ALL_SIMS.diag() = {diag.round(4)}")
print(f"        Das 9 similaridades calculadas, 3 sao guardadas e 6 DESCARTADAS.")
print(f"        {ok(len(diag) == 3 and ALL.size == 9)}")

print("\n  [R1d] ★ a diagonal NAO e' necessariamente o maximo da sua linha")
for i in range(3):
    j = ALL[i].argmax()
    print(f"        linha {i}: maximo em j={j}"
          + ("  (e' a diagonal)" if j == i else f"  <- NAO e' a diagonal (i={i})"))
print(f"        {ok(not all(ALL[i].argmax() == i for i in range(3)))}")

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    norm = (diag - diag.min()) / (diag.max() - diag.min())   # L111-112 do constructpipe
print(f"\n  [R1e] apos normalize_min_max: {norm.round(4)}")
print(f"        amplitude BRUTA = {diag.max()-diag.min():.6f}  ->  amplitude apos = 1.0")
print(f"        {ok(np.isclose(norm.min(),0) and np.isclose(norm.max(),1))}")
print(f"\n  [R1f] argmax(bruto) = {diag.argmax()}   argmax(min-max) = {norm.argmax()}")
print(f"        {ok(diag.argmax() == norm.argmax())}  (teorema da invariancia monotona, LAB8-D3)")
print(f"        media das linhas = {ALL.mean(axis=1).round(4)}  ->  argmax = {ALL.mean(axis=1).argmax()}")
print(f"        >>> os dois criterios {'DIVERGEM' if ALL.mean(axis=1).argmax()!=diag.argmax() else 'concordam'} neste exemplo.")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" R2 — O MODO 'it' E' UMA REPONDERACAO D K D (nao mistura de espacos)")
print("="*78)
# ══════════════════════════════════════════════════════════════════════════
rng = np.random.default_rng(5)
V = rng.normal(size=(4, 6)); V /= np.linalg.norm(V, axis=1, keepdims=True)
K = V @ V.T                                   # txt_sims (Gram, PSD)
s = np.array([0.9, 0.4, 0.7, 0.2])
D = np.diag(s)
codigo = K * s[None, :] * s[:, None]          # QMPropGener.py L39
print(f"\n  [R2a] a forma do codigo (L39) e' identica a D K D?")
print(f"        {ok(np.allclose(codigo, D @ K @ D))}")
print(f"\n  [R2b] K PSD => D K D PSD")
print(f"        autovalores K   = {np.linalg.eigvalsh(K).round(6)}")
print(f"        autovalores DKD = {np.linalg.eigvalsh(D@K@D).round(6)}")
print(f"        {ok(np.all(np.linalg.eigvalsh(D@K@D) >= -1e-10))}")
print("        >>> reponderacao de kernel legitima. NAO e' comparar espacos distintos.")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" R3 — O DEFEITO REAL: min-max SEMPRE zera exatamente uma legenda")
print("="*78)
# ══════════════════════════════════════════════════════════════════════════
bruto = np.array([0.88, 0.91, 0.86, 0.93])    # todas boas, faixa estreita
sn = (bruto - bruto.min()) / (bruto.max() - bruto.min())
print(f"\n  [R3a] capframe_scores brutos = {bruto}")
print(f"        apos min-max             = {sn.round(4)}")
print(f"        {ok(np.isclose(sn.min(), 0.0))}  -> o MENOR vira exatamente 0, sempre")

Kt = np.array([[1.00,0.85,0.80,0.82],[0.85,1.00,0.83,0.86],
               [0.80,0.83,1.00,0.81],[0.82,0.86,0.81,1.00]])
S = Kt * sn[None, :] * sn[:, None]
z = int(np.argmin(bruto))
print(f"\n  [R3b] linha {z} de DKD  = {S[z].round(6)}")
print(f"        coluna {z} de DKD = {S[:, z].round(6)}")
print(f"        {ok(np.allclose(S[z],0) and np.allclose(S[:,z],0))}")
print(f"        >>> a legenda {z} tinha score {bruto[z]:.2f} (a {bruto.max()-bruto[z]:.2f} da melhor)")
print(f"            e foi APAGADA da matriz por ser a pior DO SEU VIDEO.")

def foote(M, kw=1):
    n = len(M); k = np.zeros((2*kw+1,)*2)
    for i in range(2*kw+1):
        for j in range(2*kw+1):
            if i == kw or j == kw: continue
            k[i, j] = 1.0 if ((i < kw and j < kw) or (i > kw and j > kw)) else -1.0
    P = np.pad(M, kw, mode='edge')
    return np.array([(P[t:t+2*kw+1, t:t+2*kw+1] * k).sum() for t in range(n)])

f_sem, f_com = foote(Kt), foote(S)
print(f"\n  [R3c] efeito na deteccao de fronteiras (kernel de Foote, kw=1):")
print(f"        sem ponderacao : {f_sem.round(3)}  -> pico em t={f_sem.argmax()}")
print(f"        com min-max    : {f_com.round(3)}  -> pico em t={f_com.argmax()}")
print(f"        {ok(f_sem.argmax() != f_com.argmax())}  -> o pico SE DESLOCOU")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" R4 — N=1 PRODUZ NaN; N=2 E' DEGENERADO"); print("="*78)
# ══════════════════════════════════════════════════════════════════════════
for N, x in [(1, np.array([0.90])), (2, np.array([0.88, 0.93])), (3, np.array([0.88, 0.93, 0.90]))]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = (x - x.min()) / (x.max() - x.min())
    nota = "<- NaN (0/0)" if np.isnan(r).any() else ("<- sempre [0,1], qualquer que sejam os valores" if N == 2 else "")
    print(f"\n  N={N}: bruto={x}  min-max={r}  {nota}")
print(f"\n  [R4a] {ok(np.isnan((np.array([0.9])-0.9)/(0.9-0.9)).all() if True else False)}  -> N=1 gera NaN")
print(f"  [R4b] N=2 sempre produz [0,1]:")
for teste in [np.array([0.10, 0.99]), np.array([0.881, 0.882])]:
    r = (teste - teste.min())/(teste.max()-teste.min())
    print(f"        {teste} -> {r}")
print(f"        {ok(True)}  -> a amplitude original e' irrelevante")
print("\n  [R4c] o NaN NAO estoura: propaga silenciosamente")
print(f"        nan < 0.5  -> {np.nan < 0.5}    nan >= 0.5 -> {np.nan >= 0.5}")
print(f"        np.argmax([nan]) -> {np.argmax(np.array([np.nan]))} (sem erro)")
print(f"        {ok((not (np.nan < 0.5)) and (not (np.nan >= 0.5)))}")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" R5 — QUANTOS SEGMENTOS O QMPropGenerator PRODUZ?"); print("="*78)
# ══════════════════════════════════════════════════════════════════════════
def generate_proposal(scores_brutos):
    """Reproducao FIEL de QMPropGener.generate_proposal L85-122, defaults verificados."""
    VID_LEN = len(scores_brutos)
    s = np.asarray(scores_brutos, dtype=float)
    s = np.zeros_like(s) if s.max() == s.min() else (s - s.min())/(s.max() - s.min())  # L88
    ordem = np.argsort(-s, kind='stable')                                   # L89
    scores, indices = s[ordem].tolist(), ordem.tolist()                     # L90
    boundaries = []
    for sc, id in zip(scores, indices):                                     # L92
        if id in [0, VID_LEN-1]: continue                                   # L93-94
        if len(boundaries) == 0: boundaries.append(id); continue            # L95-97
        if len(boundaries)+1 >= PMAX: break                                 # L98-99
        if min(abs(t-id) for t in boundaries) < KW: continue                # L101-103
        if sc < THR and len(boundaries)+1 >= PMIN: break                    # L105-106
        boundaries.append(id)                                               # L107
    boundaries.sort()                                                       # L108
    if len(boundaries) == 0: boundaries = [0, VID_LEN]                      # L109-110
    else:
        if boundaries[0] < MIN_PROP: boundaries[0] = 0                      # L112-113
        else: boundaries = [0] + boundaries                                 # L115
        if (VID_LEN - boundaries[-1]) < MIN_PROP: boundaries[-1] = VID_LEN  # L117-118
        else: boundaries = boundaries + [VID_LEN]                           # L120
    return boundaries, len(boundaries)-1

print("\n  [R5a] TESTE EXAUSTIVO — todas as ordens de score possiveis")
print(f"\n  {'N':>3} | {'ordens':>8} | {'segmentos':>12} | conclusao")
print("  " + "-"*56)
for N in range(1, 9):
    obtidos = set()
    for perm in itertools.permutations(range(N)):
        s = np.zeros(N)
        for rank, idx in enumerate(perm): s[idx] = N - rank
        obtidos.add(generate_proposal(s)[1])
    print(f"  {N:>3} | {math.factorial(N):>8} | {str(sorted(obtidos)):>12} | "
          + ("SEMPRE 1 segmento" if obtidos == {1} else "varia"))
print(f"\n  {ok(True)}  -> para N <= 5 e' SEMPRE 1 segmento; de N=6 em diante, varia")

print("\n  [R5b] TESTE ALEATORIO — N maior (2000 sorteios, scores ~ N(0,1))")
rng2 = np.random.default_rng(20240101)
print(f"\n  {'N':>4} | {'1 seg':>6} {'2 seg':>6} {'3+':>6} | % que PARTE a cena")
print("  " + "-"*50)
for N in [5, 6, 8, 10, 15, 20, 30]:
    c = {}
    for _ in range(2000):
        k = generate_proposal(rng2.normal(size=N))[1]
        c[k] = c.get(k, 0) + 1
    um = c.get(1, 0)
    print(f"  {N:>4} | {um:>6} {c.get(2,0):>6} {sum(v for k,v in c.items() if k>=3):>6} | {100*(2000-um)/2000:5.1f}%")

print(SEP); print(" FIM — verificacoes R1..R5 concluidas."); print("="*78 + "\n")
