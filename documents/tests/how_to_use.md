# RefCap — How To Use: Manual Operacional de Scratch e Testes
## O passo a passo do dia a dia para conduzir suas análises

---

> **O que é este documento.** O manual *operacional* — dado que o ambiente está montado (ver *Relatório de Infraestrutura*), **como você de fato roda, escreve, inspeciona, depura e promove** durante a análise. Todos os comandos e saídas abaixo foram **executados de verdade** contra o repositório; não é teoria. Os dois artefatos-exemplo (`scratch/scratch_construct.py` e `scratch/scratch_denoise.py`) existem e rodam, e a promoção a `tests/` foi executada com 4 testes passando.
>
> **A quem serve.** Você, começando a verificar afirmações da análise. O fluxo é: *cutuca no scratch → confirma → promove ao pytest → automatiza.*

---

## 1. O modelo mental em 30 segundos

Dois regimes, um espectro:

- **Scratch** = *"essa lógica anda?"* — cutucar um trecho na hora, sem cerimônia, descartável. Ferramenta: `python scratch/x.py` ou `ipython -i`.
- **Pytest** = *"isto continua andando?"* — travar a lógica confirmada em regressão. Ferramenta: `pytest`.

**O loop:** você explora no scratch; quando confirma, **promove** (recorta a asserção para `tests/`); o pytest a mantém para sempre. Os dois compartilham o mesmo substrato (`_bootstrap.py` ↔ `conftest.py`), então promover é *recorte*, não reescrita.

**A regra de decisão — qual usar agora?**

```
Estou investigando / não sei o que esperar / quero VER   → SCRATCH
Já sei o comportamento certo / quero travá-lo p/ sempre  → PYTEST (promove do scratch)
```

---

## 2. Setup em uma vez (resumo; detalhes no Relatório de Infraestrutura)

```bash
conda create -n refcap-test python=3.10 -y && conda activate refcap-test
pip install -r requirements.txt
python -m spacy download en_core_web_sm
pip install -r requirements-test.txt          # pytest, hypothesis, ipython, matplotlib...
```

Confirme que a fundação está de pé antes de analisar qualquer coisa:

```bash
python scratch/scratch_construct.py            # deve imprimir [OK] em todas as etapas
```

Se isso roda, seu ambiente resolve os imports e o bypass de modelos funciona — você está pronto.

---

## 3. HOW TO USE — Scratch (exploração)

### 3.1 A anatomia de um scratchpad (o esqueleto que você repete)

Todo scratchpad tem cinco blocos, sempre na mesma ordem:

```
BLOCO 0  SUBSTRATO    → sys.path + seed + shim torchtext + bare()  (copie do _bootstrap)
BLOCO 1  AMOSTRA      → gerador de entrada sintética (matriz / meta / keys)
BLOCO 2  MONTAGEM     → importa o trecho REAL; instancia via bare() (sem pesos)
BLOCO 3  EXECUÇÃO     → roda o método REAL sobre a amostra
BLOCO 4  VERIFICAÇÃO  → print (para VER) + assert (para confirmar)
```

### 3.2 Os dois moldes — escolha pela taxonomia

**Antes de escrever, pergunte: o trecho COMPUTA UM VALOR ou COORDENA peças?**

| Se... | Molde | Arquivo-exemplo (feito) |
|---|---|---|
| coordena outras chamadas (orquestrador) | **dublês (spies)** → teste de *interação* | `scratch/scratch_construct.py` |
| transforma entrada→saída (lógica pura / método leve) | **amostra sintética + assert** → teste de *valor* | `scratch/scratch_denoise.py` |

### 3.3 Rodando um scratchpad — os dois modos

**Modo batch (roda e mostra o resultado):**
```bash
python scratch/scratch_denoise.py
```
Saída real:
```
[OK] A) Propagação normal: frame baixo dentro da janela recebe a legenda da âncora.
       ['CAP0','CAP1','CAP2'] --denoise--> ['CAP0', 'CAP1', 'CAP1']
[OK] B) Causalidade: frame baixo ANTES de qualquer âncora fica inalterado.
[OK] C) Janela: frames dentro de W recebem a âncora; frame com gap>W NÃO.
[!!] D) BUG REVELADO — colisão de sentinela no frame 0:
       esperado pelo ARTIGO (Eq.2): ['ANCHOR0', 'ANCHOR0']
       obtido pelo CÓDIGO:          ['ANCHOR0', 'LOW1']
```

**Modo interativo (roda e te deixa cutucar o estado vivo):**
```bash
ipython -i scratch/scratch_denoise.py
```
Depois de rodar, você fica no REPL com `denoiser`, `meta`, `out`, etc. vivos:
```python
In [1]: denoiser.denoise_caption(make_meta(["X","Y","Z"]), torch.tensor([0.9,0.1,0.1]))
In [2]: cfg.denoise_window_width = 1        # muda um parâmetro e re-testa na hora
In [3]: # ... itere sem reiniciar nada
```
Este é o coração da flexibilidade: **mudar uma entrada e ver o efeito imediatamente**, sem rerodar o arquivo inteiro.

**Modo visual (para lógica de matriz/tensor):** em `# %%` no editor, ou plotando:
```python
plt.imshow(two_block_sim()); plt.title("matriz de similaridade"); plt.show()
# rode a convolução de Foote e plote a curva de novidade — VER a fronteira aparecer
```

### 3.4 O ciclo de iteração (o que você faz de verdade)

```
1. escreve/ajusta a amostra (BLOCO 1)
2. roda:  python scratch/x.py   (ou re-executa a célula # %%)
3. lê a saída  →  bate com sua hipótese?
      SIM → confirma; considere promover (§5)
      NÃO → ou a lógica do código diverge (achado!), ou SUA amostra está errada
4. ajusta e repete — segundos por ciclo
```

**Um exemplo real deste ciclo pegando um erro:** ao montar o Caso C do `scratch_denoise.py`, a 1ª versão da amostra tinha os frames intermediários *altos* por engano — então o "frame distante" acabou perto de uma âncora e foi denoised. O scratchpad **falhou na hora** com uma mensagem clara, eu vi que o erro era da *minha amostra* (não do código), corrigi em 30 segundos e segui. **É exatamente para isso que o loop rápido existe:** ele te diz imediatamente quando seu modelo mental (ou seu setup) está errado, antes que vire uma crença falsa.

---

## 4. HOW TO USE — Pytest (aparato formal)

### 4.1 As invocações que você vai usar (todas com saída real)

**Rodar um arquivo de teste, verboso:**
```bash
python -m pytest tests/unit/test_denoiser_window.py -v
```
```
tests/unit/test_denoiser_window.py::test_forward_propagation PASSED      [ 25%]
tests/unit/test_denoiser_window.py::test_causal_only PASSED              [ 50%]
tests/unit/test_denoiser_window.py::test_window_boundary PASSED          [ 75%]
tests/unit/test_denoiser_window.py::test_sentinel_collision_bug PASSED   [100%]
============================== 4 passed in 0.09s ===============================
```

**Rodar UM teste por substring do nome (`-k`):**
```bash
python -m pytest tests/unit/test_denoiser_window.py -k "sentinel" -q
```
```
1 passed, 3 deselected in 0.03s
```

**Só LISTAR os testes, sem rodar (`--co`):**
```bash
python -m pytest tests/unit/test_denoiser_window.py --co -q
```
```
tests/unit/test_denoiser_window.py::test_forward_propagation
tests/unit/test_denoiser_window.py::test_causal_only
tests/unit/test_denoiser_window.py::test_window_boundary
tests/unit/test_denoiser_window.py::test_sentinel_collision_bug
```

**Os alvos do Makefile (o dia a dia):**
```bash
make test-fast     # T0 — lógica pura, segundos
make test-int      # T0 + T1
make test          # loop padrão (rápido; pula slow/gpu/e2e por padrão)
make test-e2e      # T2 — modelos reais (só quando quiser validar o pipeline real)
```

### 4.2 Como LER uma falha (a maior vantagem do pytest sobre o `print`)

O pytest introspecta o `assert` e mostra *exatamente* onde diverge. Saída real de uma asserção proposital errada:
```
>       assert _caps(out) == ["A","B","C"]   # ERRADO: o esperado é ["A","B","B"]
E       AssertionError: assert ['A', 'B', 'B'] == ['A', 'B', 'C']
E         At index 2 diff: 'B' != 'C'
tests/unit/demo_fail_test.py:7: AssertionError
1 failed in 0.06s
```
Você não precisa de `print`: o pytest te dá o valor obtido, o esperado, e o *índice exato* da divergência. Isso é o que torna a asserção mais poderosa que a inspeção visual **quando você já sabe o resultado certo** — que é o regime do pytest.

### 4.3 Flags de depuração (quando um teste falha e você não sabe por quê)

```bash
pytest tests/unit/x.py -s          # mostra os print() dentro do teste
pytest tests/unit/x.py --pdb       # cai no debugger no ponto da falha
pytest tests/unit/x.py --lf        # re-roda só o que falhou da última vez
pytest tests/unit/x.py -x          # para no 1º erro
pytest tests/unit/x.py::test_nome  # roda exatamente um teste pelo nome completo
```
E dentro de um teste, `breakpoint()` te deixa inspecionar o estado ao vivo — o análogo, no pytest, do `ipython -i` do scratch.

---

## 5. HOW TO USE — A promoção (scratch → pytest)

Quando um scratchpad confirma uma lógica que vale travar, a promoção é mecânica. **Exemplo real, feito:** promovi os quatro casos do `scratch_denoise.py` para `tests/unit/test_denoiser_window.py`. O recorte:

**No scratch (uma asserção solta no BLOCO 3):**
```python
out = denoiser.denoise_caption(make_meta(["CAP0","CAP1","CAP2"]), torch.tensor([0.9,0.9,0.1]))
assert caps_of(out) == ["CAP0","CAP1","CAP1"]
```

**No pytest (a mesma asserção, embrulhada numa função `test_`):**
```python
def test_forward_propagation(denoiser):          # `denoiser` vem do conftest (fixture)
    out = denoiser.denoise_caption(_meta(["CAP0","CAP1","CAP2"]), torch.tensor([0.9,0.9,0.1]))
    assert _caps(out) == ["CAP0","CAP1","CAP1"]
```

As **três** diferenças, e só elas: (1) embrulhar em `def test_...(denoiser):`; (2) o `denoiser`/`cfg` vêm da fixture do `conftest.py` (não do BLOCO 2 do scratch); (3) helpers (`_meta`, `_caps`) copiados ou movidos para o topo do arquivo de teste. **Zero reescrita da lógica.** Foi isso que rodou verde em 0.09s.

**Quando promover:** quando a afirmação é (a) confirmada, (b) importante o suficiente para você querer ser avisado se o comportamento mudar. O Caso D (o bug de colisão de sentinela) é o exemplo canônico: promovido, ele **trava a divergência código-vs-artigo** — se alguém "corrigir" o denoiser, o teste sinaliza a mudança. A crítica vira conhecimento executável.

---

## 6. Uma sessão completa (o loop de ponta a ponta, com exemplo real)

Cenário: *"Quero verificar a afirmação — o SWi-Den propaga legendas só para frente, dentro de uma janela."*

```
PASSO 1  —  LER O CÓDIGO
    Abro pipeline/denoiser/window.py:20-35. Vejo denoise_caption: gate por
    score, last_high_id, substituição por deepcopy dentro da janela.

PASSO 2  —  CLASSIFICAR
    "Computa um valor (meta limpo) a partir de meta+scores?"  → SIM.
    Logo: molde de VALOR (amostra + assert), não dublês.

PASSO 3  —  ESCREVER O SCRATCHPAD
    scratch/scratch_denoise.py: bare(WindowSimDenoiser, cfg=...), make_meta(),
    e casos A (propaga p/ frente), B (causal), C (janela), D (o frame 0).

PASSO 4  —  RODAR E ITERAR
    python scratch/scratch_denoise.py
    → Caso C FALHA: minha amostra tinha frames intermediários altos. Corrijo.
    → re-rodo: A,B,C passam; D revela um BUG (colisão de sentinela no frame 0).

PASSO 5  —  DECIDIR
    A,B,C confirmam a afirmação. D é um achado novo (divergência código-artigo).
    Todos valem travar.

PASSO 6  —  PROMOVER
    Recorto os 4 asserts para tests/unit/test_denoiser_window.py (fixture do
    conftest). python -m pytest ... -v → 4 passed in 0.09s.

PASSO 7  —  REGISTRAR O ACHADO
    O bug do frame 0 vira uma linha na sua análise: "implementação diverge da
    Eq. 2 quando a âncora é o frame 0 (colisão de sentinela em window.py:27,33)".
```

Este é o fluxo que você repete para cada afirmação da lista de análise. O scratch é onde você *descobre*; o pytest é onde você *fixa*.

---

## 7. Cheatsheet (cole na parede)

```bash
# ── SCRATCH (explorar) ──────────────────────────────────────────────
python scratch/x.py                 # roda e mostra
ipython -i scratch/x.py             # roda e deixa o estado vivo p/ cutucar
make scratch F=scratch/x.py         # idem, via Makefile

# ── PYTEST (travar) ─────────────────────────────────────────────────
make test-fast                      # T0 (rápido, sem modelos) — seu loop diário
python -m pytest tests/unit/f.py -v # um arquivo, verboso
pytest -k "nome"                    # filtra por substring do nome
pytest path::test_exato             # um teste específico
pytest --co -q                      # só lista os testes
pytest --lf                         # re-roda só o que falhou
pytest -s                           # mostra os print()
pytest --pdb                        # debugger na falha
make test-e2e                       # T2 (modelos reais) — só quando validar o real
```

---

## 8. Erros comuns de USO (distintos dos de setup)

1. **Rodar `pytest` para explorar.** *Errado:* escrever uma função `test_` + fixture para "só ver se anda" é fricção demais. Explore no scratch; formalize depois. O pytest é para *travar*, não para *descobrir*.
2. **Ficar no scratch e nunca promover.** *Errado:* a lógica confirmada evapora quando você fecha o REPL; a regressão volta sorrateira. Promova o que importa.
3. **Confundir "meu teste falhou" com "o código tem bug".** *Errado (e frequente):* como no Caso C, a falha pode ser da *sua amostra*. Antes de declarar bug, verifique se sua entrada sintética modela o que você acha que modela. (Depois de confirmar a amostra, uma divergência persistente é achado — como o Caso D.)
4. **Instanciar a classe de verdade num teste** (`WindowSimDenoiser(cfg, models)`). *Errado:* dispara o `__init__` que carrega o BLIP e toca disco. Use `bare()` / a fixture `denoiser`.
5. **Asserção exata contra saída de modelo real (T2).** *Errado:* MiniGPT é não-determinístico. Em T2, asserte *propriedades* (não-vazio, N proposals), não conteúdo exato.
6. **Reimplementar o algoritmo no teste e comparar.** *Errado (o mais perigoso):* um bug compartilhado passa verde. Compare com verdade calculada à mão (como o Caso A: você sabe que o resultado é `['CAP0','CAP1','CAP1']`) ou com o comportamento observável.
7. **Deixar o scratch ser coletado pelo pytest.** *Errado:* sem `norecursedirs = scratch`, o pytest tenta rodar seus scratchpads e erra. (O setup já cuida disso.)

---

## 9. O mapa de decisão diário

```
Nova afirmação da análise para verificar
        │
        ▼
Leia o trecho no código  →  classifique: orquestrador ou lógica pura?
        │
        ├─ orquestrador → scratchpad de INTERAÇÃO (dublês)   [molde: scratch_construct.py]
        └─ lógica pura  → scratchpad de VALOR (amostra+assert) [molde: scratch_denoise.py]
        │
        ▼
Rode no scratch  →  itere até a saída bater com a hipótese
        │
        ├─ divergência persistente (amostra confirmada) → ACHADO: registre na análise
        └─ confirma a afirmação
        │
        ▼
Vale travar?  ──sim──►  PROMOVA para tests/ (recorte) ──►  make test-fast (verde)
        │
        └──não──►  descarte o scratchpad (é efêmero por design)
```

---

## 10. O que você já tem pronto para começar (feito e rodando)

- `scratch/scratch_construct.py` — molde de **interação** (orquestrador `construct()`); roda, imprime `[OK]` em tudo.
- `scratch/scratch_denoise.py` — molde de **valor** (`denoise_caption`); roda, verifica A/B/C e **revela o bug do frame 0**.
- `tests/conftest.py` — substrato do aparato (sys.path, seed, shim, fixture `denoiser`).
- `tests/unit/test_denoiser_window.py` — os 4 casos promovidos; **4 passed in 0.09s**.

Copie estes quatro para o seu repositório e você tem os dois moldes + o aparato funcionando. A partir daí, cada afirmação da sua lista de análise segue o mapa da §9: leia → classifique → cutuque no scratch → confirme → promova.

---

*Sugestão de primeiro alvo próprio:* o **kernel de Foote** (`QMPropGener.py:69-105`) — é lógica pura de matriz, ideal para o modo *visual* (`plt.imshow` na matriz + plot da curva de novidade). Molde de valor, mas com a virada de que a asserção certa é *comportamental* (a fronteira aparece onde você sabe que deveria), não uma reimplementação do kernel. Quando você chegar nele, é o caso perfeito para exercitar o `matplotlib` do scratch.*
