"""
LAB8 — VERIFICACOES DO RELATORIO `Fundamentos_Embeddings_Gram_e_Argmax.md`
===========================================================================
Cada afirmacao marcada [V] no relatorio tem aqui o codigo que a verifica.
Rode e confira voce mesmo:   python3 LAB8_fundamentos_verificacoes.py

Nenhuma afirmacao do relatorio depende de "confie em mim": ou esta' provada
em uma linha de algebra, ou esta' verificada aqui, ou esta' citada com fonte.
"""
import numpy as np
import warnings

np.set_printoptions(precision=4, suppress=True)
ok = lambda b: "✓ VERIFICADO" if b else "✗ FALSO"
SEP = "\n" + "=" * 78


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" BLOCO A — EMBEDDINGS, NORMALIZACAO L2 E COSSENO"); print("="*78)
# ══════════════════════════════════════════════════════════════════════════

print("\n[V-A1] one-hot: todo par distinto e' ortogonal -> sem nocao de similaridade")
V = np.eye(5)
pares = [(i, j) for i in range(5) for j in range(5) if i < j]
print(f"        {ok(all(V[i] @ V[j] == 0 for i, j in pares))}")
print(f"        'gato' esta' tao longe de 'cachorro' quanto de 'democracia'.")

print("\n[V-A2] SEM normalizacao, produto escalar != cosseno")
a, b = np.array([3.0, 4.0]), np.array([6.0, 8.0])   # MESMA direcao, normas 5 e 10
dot = a @ b
cos = dot / (np.linalg.norm(a) * np.linalg.norm(b))
print(f"        a=[3,4] (norma {np.linalg.norm(a):.0f}), b=[6,8] (norma {np.linalg.norm(b):.0f}) — mesma direcao")
print(f"        produto escalar = {dot:.1f}     cosseno = {cos:.4f}")
print(f"        {ok(abs(dot - cos) > 1e-6)}")

print("\n[D/V-A3] TEOREMA: com ||a||=||b||=1, produto escalar == cosseno")
print("        Prova: cos(a,b) = (a.b)/(||a||.||b||) = (a.b)/(1.1) = a.b")
an, bn = a / np.linalg.norm(a), b / np.linalg.norm(b)
print(f"        produto normalizado = {an @ bn:.12f}   cosseno = {cos:.12f}")
print(f"        {ok(abs(an @ bn - cos) < 1e-12)}")

print("\n[V-A4] o contradominio do cosseno e' [-1, 1], NAO [0, 1]")
c1, c2 = np.array([1.0, 0.0]), np.array([-1.0, 0.0])
print(f"        cos([1,0], [-1,0]) = {c1 @ c2:.1f}")
print(f"        {ok(c1 @ c2 == -1.0)}")

print("\n[V-A5] a analogia 'rei - homem + mulher' SEM excluir as palavras de entrada")
print("        (espaco de brinquedo, so' para ilustrar o MECANISMO da exclusao)")
vocab = {"rei":   np.array([0.90, 0.85, 0.10]),
         "rainha":np.array([0.88, 0.10, 0.90]),
         "homem": np.array([0.20, 0.90, 0.05]),
         "mulher":np.array([0.18, 0.08, 0.92])}
alvo = vocab["rei"] - vocab["homem"] + vocab["mulher"]
dist = {p: np.linalg.norm(alvo - v) for p, v in vocab.items()}
ordem = sorted(dist, key=dist.get)
print(f"        vetor alvo = {alvo.round(3)}")
for p in ordem:
    print(f"          {p:<8} distancia {dist[p]:.4f}")
print(f"        mais proximo SEM exclusao : {ordem[0]!r}")
print(f"        mais proximo COM exclusao de (rei, homem, mulher): "
      f"{[p for p in ordem if p not in ('rei','homem','mulher')][0]!r}")
print("        >>> A literatura (Linzen 2016; Drozd et al. 2016) reporta que, em")
print("            embeddings REAIS, sem a exclusao o vizinho mais proximo de")
print("            'rei - homem + mulher' e' o proprio 'rei'. Este exemplo aqui e'")
print("            SINTETICO e serve so' para mostrar o papel da exclusao.")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" BLOCO B — MATRIZ DE GRAM"); print("="*78)
# ══════════════════════════════════════════════════════════════════════════

rng = np.random.default_rng(42)
M = rng.normal(size=(5, 8))
Mn = M / np.linalg.norm(M, axis=1, keepdims=True)
G = Mn @ Mn.T

print("\n[D/V-B1] G = V V^T e' SIMETRICA")
print("        Prova: G[i][j] = <v_i,v_j> = <v_j,v_i> = G[j][i]")
print(f"        {ok(np.allclose(G, G.T))}")

print("\n[D/V-B2] G e' POSITIVA SEMI-DEFINIDA")
print("        Prova: x'Gx = x'VV'x = ||V'x||^2 >= 0  (norma ao quadrado)")
ev = np.linalg.eigvalsh(G)
print(f"        autovalores = {ev.round(6)}")
print(f"        {ok(np.all(ev >= -1e-10))}")

print("\n[D/V-B3] diagonal de G = ||v_i||^2  (portanto 1 se normalizado)")
print(f"        diagonal = {G.diagonal().round(10)}")
print(f"        {ok(np.allclose(G.diagonal(), np.sum(Mn**2, axis=1)))}")

print("\n[V-B4] rank(G) = rank(V), inclusive com V deficiente de posto")
Vd = np.vstack([M[:3], M[0] * 2, M[1] * 3])          # posto 3 forcado
Gd = Vd @ Vd.T
print(f"        rank(V) = {np.linalg.matrix_rank(Vd)}   rank(G) = {np.linalg.matrix_rank(Gd)}")
print(f"        {ok(np.linalg.matrix_rank(Vd) == np.linalg.matrix_rank(Gd))}")

print("\n[V-B5] det(G) = (volume do paralelepipedo)^2   [caso V quadrada]")
W = rng.normal(size=(3, 3))
Gw = W @ W.T
print(f"        det(G) = {np.linalg.det(Gw):.8f}   det(W)^2 = {np.linalg.det(W)**2:.8f}")
print(f"        {ok(np.isclose(np.linalg.det(Gw), np.linalg.det(W)**2))}")

print("\n[V-B6] G determina os vetores a menos de transformacao ortogonal")
Q, _ = np.linalg.qr(rng.normal(size=(8, 8)))
print(f"        Q e' ortogonal (QQ' = I)? {ok(np.allclose(Q @ Q.T, np.eye(8)))}")
print(f"        Gram(Mn) == Gram(Mn Q)?   {ok(np.allclose(Mn @ Mn.T, (Mn @ Q) @ (Mn @ Q).T))}")
print("        >>> girar TODOS os vetores juntos nao muda nenhum angulo entre eles.")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" BLOCO C — GRAM CRUZADA E A REPONDERACAO D K D"); print("="*78)
# ══════════════════════════════════════════════════════════════════════════

T = rng.normal(size=(4, 8)); T /= np.linalg.norm(T, axis=1, keepdims=True)
F = rng.normal(size=(4, 8)); F /= np.linalg.norm(F, axis=1, keepdims=True)
C = T @ F.T

print("\n[V-C1] C = T F^T NAO e' simetrica em geral")
print(f"        {ok(not np.allclose(C, C.T))}")

print("\n[V-C2] a diagonal de C nao e' 1 em geral")
print(f"        diagonal = {C.diagonal().round(4)}")
print(f"        {ok(not np.allclose(C.diagonal(), 1))}")

print("\n[V-C3] C pode ser RETANGULAR (n != m)")
F2 = rng.normal(size=(7, 8)); F2 /= np.linalg.norm(F2, axis=1, keepdims=True)
print(f"        T[4x8] @ F2[7x8]^T -> shape {(T @ F2.T).shape}")
print(f"        {ok((T @ F2.T).shape == (4, 7))}")

print("\n[V-C4] a diagonal NAO e' necessariamente o maximo da sua linha")
linhas_ok = [C[i].argmax() == i for i in range(4)]
for i in range(4):
    print(f"        linha {i}: max em j={C[i].argmax()}  (diagonal em j={i})"
          f"  {'diagonal e o max' if linhas_ok[i] else '<- NAO'}")
print(f"        {ok(not all(linhas_ok))}  -> a diagonal e' CONVENCAO, nao maximo garantido")

print("\n[D/V-C5] TEOREMA: K PSD  =>  D K D PSD, para D diagonal qualquer")
print("        Prova: x'(DKD)x = (Dx)'K(Dx) >= 0  pois K e' PSD")
s = np.array([0.9, 0.0, 0.4, 1.0])
D = np.diag(s)
K = T @ T.T
DKD = D @ K @ D
print(f"        autovalores de K   = {np.linalg.eigvalsh(K).round(6)}")
print(f"        autovalores de DKD = {np.linalg.eigvalsh(DKD).round(6)}")
print(f"        {ok(np.all(np.linalg.eigvalsh(DKD) >= -1e-10))}")

print("\n[V-C6] a forma  K * s[None,:] * s[:,None]  E' identica a  D K D")
print(f"        {ok(np.allclose(K * s[None, :] * s[:, None], DKD))}")
print("        >>> reponderar por pesos escalares NAO e' 'comparar espacos")
print("            diferentes': e' uma reponderacao de kernel, e preserva PSD.")

print("\n[V-C7] peso ZERO ANIQUILA a linha e a coluna inteiras")
print(f"        s = {s}  (o indice 1 tem peso 0)")
print(f"        linha 1 de DKD  = {DKD[1].round(6)}")
print(f"        coluna 1 de DKD = {DKD[:, 1].round(6)}")
print(f"        {ok(np.allclose(DKD[1], 0) and np.allclose(DKD[:, 1], 0))}")


# ══════════════════════════════════════════════════════════════════════════
print(SEP); print(" BLOCO D — ARGMAX"); print("="*78)
# ══════════════════════════════════════════════════════════════════════════

f = np.array([0.3, 0.9, 0.5, 0.9])
print("\n[V-D1] argmax devolve o ARGUMENTO; max devolve o VALOR")
print(f"        f = {f}    argmax = {f.argmax()}    max = {f.max()}")
print(f"        {ok(f.argmax() != f.max())}")

print("\n[V-D2] sob EMPATE o argmax nao e' unico (numpy devolve o PRIMEIRO)")
print(f"        f tem maximos nos indices 1 e 3; np.argmax -> {f.argmax()}")
print(f"        {ok(f[1] == f[3] == f.max() and f.argmax() == 1)}")

print("\n[D/V-D3] TEOREMA: g estritamente crescente => argmax f = argmax (g o f)")
print("        Prova: g crescente =>  f(x*) >= f(x)  <=>  g(f(x*)) >= g(f(x))")
h = np.array([0.31, 0.87, 0.55, 0.42, 0.79])
gs = {"min-max":   lambda x: (x - x.min()) / (x.max() - x.min()),
      "exp":       lambda x: np.exp(x),
      "afim (3x+7)": lambda x: 3 * x + 7,
      "log(x+2)":  lambda x: np.log(x + 2)}
todos = True
for nome, g in gs.items():
    igual = h.argmax() == g(h).argmax()
    todos &= igual
    print(f"        g = {nome:<13} argmax(f)={h.argmax()}  argmax(g(f))={g(h).argmax()}"
          f"  {'igual' if igual else 'DIFERE'}")
print(f"        {ok(todos)}")

print("\n[V-D4] CONTRA-EXEMPLO: g DECRESCENTE inverte o argmax")
print(f"        g(x) = -x :  argmax(f) = {h.argmax()}   argmax(-f) = {(-h).argmax()}")
print(f"        {ok(h.argmax() != (-h).argmax())}  -> a hipotese 'crescente' e' essencial")

print("\n[V-D5] min-max e' INDEFINIDO quando max == min (0/0)")
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    r = (np.array([0.9]) - 0.9) / (0.9 - 0.9)
print(f"        (0.9 - 0.9) / (0.9 - 0.9) = {r}")
print(f"        {ok(np.isnan(r).all())}")

print("\n[V-D6] min-max amplifica diferencas irrisorias ate a escala total [0,1]")
bruto = np.array([0.9921, 0.9868, 0.9917])       # SINTETICO (nao e' dado do RefCap)
norm = (bruto - bruto.min()) / (bruto.max() - bruto.min())
print(f"        bruto  = {bruto}   (amplitude real {bruto.max()-bruto.min():.4f})")
print(f"        min-max= {norm.round(4)}   (amplitude 1.0000)")
print(f"        margem entre 1o e 2o lugar, no BRUTO = {abs(np.sort(bruto)[-1]-np.sort(bruto)[-2]):.6f}")
print(f"        {ok(np.isclose(norm.min(), 0) and np.isclose(norm.max(), 1))}")
print("        >>> o argmax e' formalmente valido e estatisticamente vazio quando")
print("            a margem e' dessa ordem. O ranking com os valores a' vista mostra")
print("            a margem; o argmax sozinho a esconde.")

print("\n[V-D7] NaN faz TODA comparacao virar False (propagacao silenciosa)")
print(f"        nan <  0.2  -> {np.nan < 0.2}")
print(f"        nan >= 0.2  -> {np.nan >= 0.2}")
print(f"        np.argmax([nan]) -> {np.argmax(np.array([np.nan]))}  (sem erro!)")
print(f"        {ok((not (np.nan < 0.2)) and (not (np.nan >= 0.2)))}")

print(SEP)
print(" FIM — todas as afirmacoes [V] do relatorio verificadas acima.")
print("="*78 + "\n")
