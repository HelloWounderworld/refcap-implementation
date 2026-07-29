# Fundamentos: Embeddings, Matrizes de Gram e argmax
## Referência Matemática para Sistemas de Similaridade e Seleção

---

> **O que é este documento.** A base matemática por trás de qualquer sistema que compara textos, imagens ou objetos por similaridade vetorial — embeddings, matrizes de Gram, e o argmax. É deliberadamente **independente de projeto**: nada aqui depende do RefCap, e o conteúdo é reutilizável em qualquer trabalho com representações vetoriais.
>
> **Público.** Escrito para um engenheiro que precisa *aplicar* isto corretamente, não apenas reconhecer os nomes. A Parte I.7 (os gargalos) é a seção mais prática do documento.
>
> **Companheiro executável.** `LAB8_fundamentos_verificacoes.py` — 25 verificações numéricas, uma para cada afirmação marcada `[V]`. Rode e confira.

---

## Protocolo de verificação

Toda afirmação deste documento carrega uma marca de status. Não há afirmação sem marca.

| Marca | Significa | Como conferir |
|---|---|---|
| **[D]** | **Demonstrada** — a prova está no texto | leia a prova |
| **[V]** | **Verificada numericamente** | rode o `LAB8` |
| **[C]** | **Citada da literatura** — com fonte nomeada | consulte a fonte |
| **[J]** | **Julgamento meu** — opinião de engenharia, não fato | pondere e discorde |

**Onde eu não pude verificar, digo que não pude.** Exemplos sintéticos estão rotulados como sintéticos e nunca são apresentados como evidência empírica.

---

# PARTE I — EMBEDDINGS

## 1. O que é (e o que não é)

**Definição.** Um *embedding* é uma função φ: X → ℝᵈ que leva objetos de um espaço complicado (palavras, frases, imagens, grafos) para vetores, de modo que **relações geométricas em ℝᵈ reflitam relações semânticas em X**.

```
φ("uma mulher numa cozinha")  ↦  [0.90, 0.80, −0.20, 0.30, …]
```

**O embedding é o vetor.** Não é o modelo que o produziu, nem o algoritmo de treino.

**A confusão que vale desfazer.** Embedding **não** é um método de aprendizado supervisionado; não está na mesma categoria que XGBoost, SVM ou regressão linear:

| | O que é | O que responde |
|---|---|---|
| XGBoost, SVM, regressão | **modelos** — aprendem *f: X → Y* | *"dado X, preveja Y"* |
| Embedding | **representação** — é um vetor | *"como escrevo X em números?"* |

Comparar os dois é comparar *calculadora* com *número*: um produz, o outro é o produto. A confusão é natural porque o embedding **sai de** um modelo treinado — mas ele próprio é a saída, não o método. **[J]**

## 2. O problema que ele resolve

Computadores operam sobre números; texto é símbolo discreto. A solução ingênua é o **one-hot**: cada item vira um vetor com 1 na sua posição e 0 no resto. Dois defeitos fatais:

**Defeito 1 — nenhuma noção de similaridade. [V-A1]** Em one-hot, todos os pares distintos são **ortogonais** (produto interno exatamente 0). "gato" está *tão longe* de "cachorro" quanto de "democracia". Toda estrutura semântica se perde.

**Defeito 2 — dimensionalidade.** A dimensão iguala o tamanho do vocabulário. 50.000 palavras → vetores de 50.000 posições, com 49.999 zeros.

Embeddings corrigem os dois: são **densos** (centenas de dimensões, quase todas não-nulas) e **preservam similaridade**.

## 3. Como são aprendidos

Quatro famílias. Importa conhecê-las porque **cada uma define que *tipo* de similaridade você recebe**:

| Família | Princípio | Exemplos |
|---|---|---|
| **Distribucional** | itens em contextos parecidos têm significados parecidos | Word2Vec, GloVe **[C]** |
| **Contrastiva** | aproxime pares positivos, afaste negativos | CLIP, BLIP, SimCSE, sentence-transformers |
| **Autoencoder** | comprima e reconstrua | autoencoders, VAE |
| **Subproduto supervisionado** | a penúltima camada de um classificador treinado | *features* de redes de visão |

**[C]** Word2Vec: Mikolov et al. (2013). GloVe: Pennington et al. (2014).

## 4. A geometria: o que "significado virou geometria" significa

Se φ funciona, então **ângulos pequenos = significados próximos**. Num espaço de brinquedo com eixos interpretáveis (cozinha / pessoa / ar livre) — *exemplo sintético, construído para ilustrar*:

```
"a woman standing in a kitchen"   [ 0.90,  0.80, −0.20]
"a woman preparing food"          [ 0.85,  0.75, −0.15]
"a close up of a knife"           [ 0.60, −0.30, −0.10]
"a dog running in a park"         [−0.30, −0.20,  0.90]
```

| par | cosseno | ângulo |
|---|---|---|
| mulher-cozinha × mulher-comida | +0.999 | 1.9° |
| mulher-cozinha × faca | +0.387 | 67.3° |
| mulher-cozinha × cachorro-parque | **−0.515** | 121.0° |

Note que em embeddings reais **os componentes têm os dois sinais**, e por isso cossenos negativos são possíveis e informativos.

### 4.1 O caso das analogias — e o asterisco que quase ninguém menciona

A demonstração mais famosa de estrutura geométrica é a aritmética vetorial: `rei − homem + mulher ≈ rainha`.

**★ O asterisco. [C]** Essa demonstração **depende de uma exclusão que raramente é mencionada**. A implementação padrão da tarefa de analogia **remove as palavras de entrada {a, b, c} do conjunto de candidatos** (Levy & Goldberg, 2014). Sem essa exclusão, o vizinho mais próximo de `rei − homem + mulher` é **o próprio "rei"**; "rainha" fica em segundo.

Fontes: Linzen (2016), *"Issues in evaluating semantic spaces using word analogies"* — reporta que, sem excluir a, b, c, o desempenho "cai a zero". Drozd, Gladkova & Matsuoka (2016), *"Word embeddings, analogies, and machine learning: beyond king − man + woman = queen"* (COLING 2016) — analisa a fragilidade do método de deslocamento linear.

**[V-A5]** O `LAB8` reproduz o *mecanismo* da exclusão num espaço sintético. **Ele não reproduz o resultado em embeddings reais** — para isso a fonte é a literatura citada, não um teste meu.

**[J] A lição prática:** a estrutura linear existe, mas é mais fraca do que a divulgação sugere. Use analogias como intuição, não como evidência de qualidade de um embedding.

## 5. Cosseno, produto escalar, e o teorema da normalização

**Por que cosseno e não distância euclidiana?** O cosseno mede **apenas a direção**, ignorando o comprimento. Dois textos sobre o mesmo tema apontam para o mesmo lado ainda que um seja mais "intenso". E o cosseno vive numa escala fixa, [−1, 1], comparável entre pares.

**[D/V-A3] Teorema.** Se ‖a‖ = ‖b‖ = 1, então `a · b = cos(a, b)`.

> **Prova.** Por definição, `cos(a,b) = (a·b)/(‖a‖·‖b‖)`. Com ‖a‖=‖b‖=1, o denominador é 1, logo `cos(a,b) = a·b`. ∎

**A consequência de engenharia:** depois de normalizar em L2, uma multiplicação de matrizes já entrega **todos** os cossenos, sem raiz quadrada e sem divisão. É por isso que bibliotecas normalizam na saída do encoder e depois usam só `@`.

**[V-A2] O corolário perigoso:** *sem* normalização, produto escalar **não** é cosseno. Para `a=[3,4]` e `b=[6,8]` (mesma direção), o produto escalar é 50 e o cosseno é 1.0000.

## 6. Onde se usam em ML

Busca semântica e *retrieval*; agrupamento (*clustering*); classificação (o embedding como *feature* de entrada); recomendação; deduplicação; detecção de anomalia; e alinhamento entre modalidades (texto↔imagem).

## 7. ★ Os oito gargalos

A seção mais prática. Cada item é um erro que custa caro e que passa despercebido.

### (a) Comparar vetores de modelos diferentes

**O erro:** calcular `cos(vec_modeloA, vec_modeloB)`. Espaços distintos não têm correspondência de eixos — a dimensão 7 de um não é a dimensão 7 do outro. O número resultante não significa nada, mesmo que as dimensões coincidam.

**★ A distinção que precisa acompanhar este alerta. [D/V-C5, C6]** Usar um **escalar** de um modelo como **peso** sobre similaridades de outro **não** é o mesmo erro. A operação
```
S[i][j] = K[i][j] · s[i] · s[j]        (equivalentemente: S = D K D, com D = diag(s))
```
é uma **reponderação de kernel**, legítima, e preserva a estrutura PSD.

> **Prova.** `x'(DKD)x = (Dx)'K(Dx) ≥ 0`, pois K é PSD. ∎

A diferença é categórica: o erro é tratar **coordenadas** de espaços distintos como comparáveis; usar um **escalar** como peso é outra operação. Confundir as duas leva a rejeitar desenhos corretos.

### (b) Esquecer a normalização
Ver 5. Produto escalar sem normalizar mede *magnitude × direção*.

### (c) Achar que o cosseno vive em [0,1]
**[V-A4]** Vive em **[−1, 1]**. Cosseno negativo significa direção oposta, e é informação.

### (d) Tratar o valor absoluto como calibrado
Cosseno 0.8 **não** significa "80% similar". Só é interpretável *relativamente* a outros cossenos **do mesmo modelo**. Limiares fixos não transferem entre modelos nem entre conjuntos de dados.

### (e) Anisotropia — o "efeito cone"

**[C]** Ethayarajh (2019), *"How Contextual are Contextualized Word Representations?"*, demonstrou que representações contextuais de **BERT, ELMo e GPT-2** são **anisotrópicas**: os vetores se concentram num cone estreito em vez de se espalharem pela hiperesfera. Gao et al. (2019) chamaram o mecanismo de *representation degeneration problem*.

**A consequência:** cossenos entre itens **não relacionados** ficam artificialmente altos, e o sinal útil vive nas diferenças pequenas.

**Três qualificações que a literatura faz, e que preciso preservar:**
1. **O escopo é o de embeddings contextuais** dos modelos estudados. Modelos treinados com objetivo contrastivo (SimCSE, sentence-transformers) são justamente projetados para mitigar isso — **o grau varia por modelo**.
2. **Isso não invalida o uso do cosseno para ordenação.** A literatura é explícita: o problema é a *interpretabilidade absoluta*, não a *ordenação relativa*. Ranking continua funcionando; limiares absolutos, não.
3. **Trabalhos posteriores refinaram o quadro** — Cai et al. (2021) e Rajaee & Pilehvar (2021) mostraram que há isotropia *local* dentro de agrupamentos mesmo sob anisotropia global; Rudman et al. (2022) questionaram as próprias métricas de isotropia.

**[J] O que fazer:** meça a distribuição dos seus cossenos antes de escolher qualquer limiar. Se a massa estiver concentrada num intervalo estreito, use ordenação — não corte por valor.

### (f) Negação
Embeddings tratam mal a negação. *"O gato está no tapete"* e *"O gato não está no tapete"* tendem a ter cosseno alto, apesar de significarem o oposto. **[J]** Se o seu domínio depende de negação, o cosseno sozinho não serve.

### (g) A similaridade é a que o modelo treinou
Um modelo treinado em detecção de paráfrase mede paráfrase — não necessariamente proximidade temática, nem factual, nem estilística. **Escolha o modelo pela noção de similaridade que você precisa**, não pelo *benchmark* genérico.

### (h) Escolha de *pooling* e versionamento
`[CLS]` vs. média vs. máximo produzem embeddings diferentes do mesmo texto — mude o *pooling* e o espaço muda. E o mesmo vale entre versões do modelo: **embeddings em cache expiram silenciosamente** quando o modelo é atualizado, e nada avisa. Versione o par (modelo, pooling) junto com os vetores.

---

# PARTE II — MATRIZ DE GRAM

## 8. Definição e propriedades

**Definição.** Dados vetores v₁,…,vₙ num espaço com produto interno, a **matriz de Gram** é
```
G[i][j] = ⟨vᵢ, vⱼ⟩        equivalentemente:   G = V Vᵀ
```
onde V é a matriz [n × d] cujas linhas são os vetores.

**A intuição:** G guarda, num único objeto, **todas as relações geométricas** do conjunto — todos os ângulos e todos os comprimentos.

### As cinco propriedades

**[D/V-B1] Simétrica.**
> Prova: `G[i][j] = ⟨vᵢ,vⱼ⟩ = ⟨vⱼ,vᵢ⟩ = G[j][i]`. ∎

**[D/V-B2] Positiva semi-definida.**
> Prova: para qualquer x, `x'Gx = x'VV'x = ‖V'x‖² ≥ 0`. A forma quadrática **é** uma norma ao quadrado. ∎

**[D/V-B3] Diagonal = ‖vᵢ‖²** — portanto exatamente 1 quando os vetores são normalizados.
> Prova: `G[i][i] = ⟨vᵢ,vᵢ⟩ = ‖vᵢ‖²`. ∎

**[V-B4] rank(G) = rank(V)** — inclusive quando V é deficiente de posto.

**[V-B5] det(G) = (volume)²** — para V quadrada, o determinante de Gram é o quadrado do volume do paralelepípedo gerado pelos vetores.

**[V-B6] G determina os vetores a menos de transformação ortogonal.** Se Q é ortogonal, `Gram(V) = Gram(VQ)`. Girar todos os vetores juntos não altera nenhum ângulo entre eles — e a Gram só enxerga ângulos e comprimentos, não a orientação absoluta.

## 9. Matriz de Gram cruzada

**Definição.** Quando os dois conjuntos são **diferentes** — t₁…tₙ e f₁…f_m —
```
C[i][j] = ⟨tᵢ, fⱼ⟩        equivalentemente:   C = T Fᵀ
```

**Nota de terminologia. [J]** "Gram" designa estritamente o caso **auto**-similaridade (um conjunto contra si mesmo). Para o caso cruzado, a literatura usa *cross-kernel matrix*, *matriz de correlação cruzada*, ou (informalmente) *cross-Gram*. Uso "Gram cruzada" por paralelismo, mas o termo canônico é o primeiro.

**O que ela perde:**

| propriedade | Gram | Gram cruzada |
|---|---|---|
| simétrica | ✓ **[V-B1]** | ✗ **[V-C1]** |
| diagonal = 1 (normalizado) | ✓ **[V-B3]** | ✗ **[V-C2]** |
| PSD | ✓ **[V-B2]** | não se aplica |
| quadrada | ✓ | ✗ — pode ser [n × m] **[V-C3]** |

**★ [V-C4] A diagonal não é necessariamente o máximo da sua linha.** Isto merece destaque porque é contraintuitivo: numa Gram cruzada, `C[i][i]` pode ser menor que `C[i][j]` para algum j ≠ i. Verificado no `LAB8`.

**[J] A consequência conceitual:** quando alguém extrai a diagonal de uma Gram cruzada, isso é uma **convenção de indexação** — "o item i da esquerda está pareado com o item i da direita" — e **não** uma propriedade algébrica. Embaralhe uma das listas e os pares casados saem da diagonal. Nenhum teorema privilegia a diagonal; um acordo de indexação, sim.

## 10. A reponderação D K D

Já demonstrada em I.7(a). Recapitulando o essencial:

**[D/V-C5] Teorema.** Se K é PSD e D é diagonal, então DKD é PSD.

**[V-C7] O efeito colateral que precisa ser conhecido:** se algum peso for **exatamente zero**, a linha **e** a coluna correspondentes são **inteiramente anuladas**. Isso não é "rebaixar" aquele item — é **removê-lo** da estrutura. Qualquer normalização que produza zeros (min-max produz sempre um) tem esse efeito.

## 11. Conexão: o kernel do SVM é uma matriz de Gram

**[C]** Em métodos de kernel, a *matriz kernel* `K[i][j] = ⟨φ(xᵢ), φ(xⱼ)⟩` **é** uma matriz de Gram no espaço de *features* φ. É exatamente por isso que kernels válidos precisam ser PSD (condição de Mercer): a PSD é o que garante que existe um espaço de *features* onde aquele kernel é um produto interno.

**[J]** Vale internalizar: se você já usou SVM com kernel, já usou matriz de Gram — só não com esse nome.

## 12. Duas leituras de uma mesma matriz de Gram

Uma matriz de auto-similaridade admite leituras **independentes**, que respondem a perguntas diferentes. As duas mais úteis:

### Leitura local — o kernel de Foote (detecção de fronteiras)

**[C]** Jonathan Foote, *"Automatic audio segmentation using a measure of audio novelty"*, IEEE ICME 2000, vol. 1, pp. 452–455. O termo "checkerboard kernel" é do próprio autor.

**A ideia.** Numa matriz de auto-similaridade, uma **fronteira** no instante *t* produz este padrão local:
```
             antes de t | depois de t
 antes de t [   ALTO    |   BAIXO    ]     ← cada bloco é coeso consigo
depois de t [   BAIXO   |   ALTO     ]     ← mas diferente do outro
```
e o meio de uma região **homogênea** produz `[ALTO|ALTO / ALTO|ALTO]`.

O kernel é um **tabuleiro de damas** com esse mesmo formato — `+1` nos quadrantes diagonais, `−1` nos anti-diagonais — deslizado ao longo da diagonal principal. Na fronteira, `+1` cai sobre valores altos e `−1` sobre baixos → soma grande. Em região homogênea, `+1` e `−1` caem sobre valores parecidos → **se cancelam** → soma perto de zero.

A função resultante (a *novelty function*) tem picos nas transições.

### Leitura global — centralidade (o medoide)

`centralidade(i) = média da linha i, excluindo a diagonal` responde *"quem é mais parecido com todo o resto?"* — o **medoide** do conjunto. Não diz nada sobre fronteiras.

**[J] O ponto que vale reter:** kernel de Foote e soma de linhas são **operadores independentes sobre o mesmo objeto**. Um lê vizinhanças locais em torno da diagonal; o outro agrega globalmente por linha. Um sistema que computa a matriz e aplica só um deles está deixando a outra informação sobre a mesa.

---

# PARTE III — ARGMAX

## 13. Definição formal

```
argmax_{x ∈ S} f(x)  =  { x* ∈ S : f(x*) ≥ f(x) para todo x ∈ S }
```

**[V-D1] `argmax` devolve o argumento; `max` devolve o valor.** Confundi-los é erro de leitura de código frequente.

**[V-D2] O resultado é um conjunto, não um elemento.** Sob empate há múltiplos maximizadores. As implementações escolhem arbitrariamente — NumPy e PyTorch retornam o **primeiro**. Isso significa que **a ordem dos seus dados pode decidir o resultado** quando há empate.

## 14. Os três requisitos

Para o argmax fazer sentido, três condições — e a terceira não é matemática:

**1. Ordem total no contradomínio.** É preciso poder comparar dois valores de f. Reais: ok. **Vetores não têm ordem total** — por isso não existe argmax de vetores sem antes reduzi-los a escalar.

**2. O máximo tem que ser atingido.** Garantido para conjunto finito; para conjunto infinito, exige compacidade e continuidade (Weierstrass). Em seleção sobre listas, é sempre finito.

**3. [J] Monotonicidade do critério.** "Score maior" tem que significar "melhor **para o seu objetivo**". Este requisito é **semântico, não matemático** — nada na definição do argmax o garante, e é onde a maioria dos erros reais mora.

## 15. O teorema da invariância monótona

**[D/V-D3] Teorema.** Se g é estritamente crescente, então `argmax f = argmax (g ∘ f)`.

> **Prova.** g estritamente crescente ⟹ `f(x*) ≥ f(x) ⟺ g(f(x*)) ≥ g(f(x))`. O conjunto de maximizadores é idêntico. ∎

Verificado para g ∈ {min-max, exp, afim positiva, log(x+2)} — todas preservam o argmax.

**[V-D4] A hipótese "crescente" é essencial.** Contraexemplo: `g(x) = −x` inverte o argmax.

**[J] Utilidade prática:** este teorema é o que autoriza reescalar scores livremente (para exibição, para combinar com outros sinais) **sem alterar quem vence** — desde que a transformação seja estritamente crescente. E é o que proíbe transformações decrescentes.

## 16. Onde o argmax falha

**Falha 1 — o requisito semântico.** O maior score é o melhor **para o critério que você mediu**, não necessariamente para o objetivo que você tem. Se o critério é enviesado, o argmax herda o viés com precisão perfeita.

**Falha 2 — margem versus ruído.** O argmax devolve um vencedor com a **mesma aparência de confiança** num caso decisivo e num empate técnico. Ele **não reporta a margem**.

**[V-D6]** Exemplo *sintético*: scores `[0.9921, 0.9868, 0.9917]` — a diferença entre o 1º e o 2º lugar é 0.0004. O argmax escolhe o primeiro sem qualquer sinal de que a decisão foi tomada sobre ruído.

**[J] A recomendação que decorre:** quando os scores puderem estar próximos, **emita o ranking com os valores à vista** em vez do argmax sozinho. O ranking mostra a margem; o argmax a esconde. O custo é uma coluna a mais; o ganho é saber quando não confiar.

## 17. Normalização min-max: a transformação e seus dois defeitos

```
g(x) = (x − min) / (max − min)
```

**A propriedade boa. [V-D3]** É afim com coeficiente angular `1/(max−min) > 0`, logo estritamente crescente, logo **preserva o argmax** pelo teorema de 15.

**[V-D6] Defeito 1 — amplificação.** O menor valor vira exatamente 0 e o maior exatamente 1, **sempre**, qualquer que seja a amplitude original. Uma diferença de 0.005 é esticada até 1.0. Um empate técnico passa a parecer vitória esmagadora, e a informação sobre a magnitude real da diferença é **destruída**.

Corolário: valores min-max **não são comparáveis entre conjuntos**. Todo conjunto passa a ter um 0 e um 1, seja ele bom ou ruim.

**[V-D5] Defeito 2 — indefinição.** Quando `max == min`, a fórmula é `0/0`. Em ponto flutuante isso produz **NaN**, não uma exceção.

**[V-D7] E o NaN propaga silenciosamente:** toda comparação com NaN é `False` (IEEE 754), então guardas condicionais se comportam como se a condição nunca fosse satisfeita, e `argmax([nan])` retorna 0 sem erro. **O caso `max == min` inclui o caso trivial de um único elemento** — que é comum e fácil de não testar.

**[J] Se você usa min-max, trate explicitamente `max == min`.** É uma linha de código e elimina uma classe inteira de falha silenciosa.

---

# APÊNDICE — Referência rápida

| Conceito | Fórmula | Propriedade essencial |
|---|---|---|
| Cosseno | `(a·b)/(‖a‖‖b‖)` | contradomínio [−1, 1] |
| Cosseno com L2 | `a·b` | **[D]** vale só se ‖a‖=‖b‖=1 |
| Matriz de Gram | `G = V Vᵀ` | simétrica, PSD, diag = ‖vᵢ‖² |
| Gram cruzada | `C = T Fᵀ` | nada disso; diagonal é convenção |
| Reponderação | `S = D K D` | **[D]** preserva PSD; peso 0 anula linha+coluna |
| argmax | `{x* : f(x*) ≥ f(x) ∀x}` | conjunto; empate resolvido por implementação |
| Invariância | `argmax f = argmax(g∘f)` | **[D]** exige g estritamente crescente |
| min-max | `(x−min)/(max−min)` | preserva argmax; amplifica; **NaN se max=min** |

**Índice das verificações do `LAB8`:** A1–A5 (embeddings e cosseno), B1–B6 (Gram), C1–C7 (Gram cruzada e DKD), D1–D7 (argmax e min-max).

**Referências citadas [C]:**
- Foote, J. (2000). *Automatic audio segmentation using a measure of audio novelty.* IEEE ICME 2000, vol. 1, pp. 452–455.
- Ethayarajh, K. (2019). *How Contextual are Contextualized Word Representations? Comparing the Geometry of BERT, ELMo, and GPT-2 Embeddings.*
- Gao, J. et al. (2019). *Representation degeneration problem.*
- Cai et al. (2021); Rajaee & Pilehvar (2021) — isotropia local sob anisotropia global.
- Rudman et al. (2022) — crítica às métricas de isotropia.
- Linzen, T. (2016). *Issues in evaluating semantic spaces using word analogies.* Workshop RepEval, ACL.
- Drozd, A., Gladkova, A., & Matsuoka, S. (2016). *Word embeddings, analogies, and machine learning: beyond king − man + woman = queen.* COLING 2016, pp. 3519–3530.
- Levy, O. & Goldberg, Y. (2014) — a exclusão de {a,b,c} na tarefa de analogia.
- Mikolov et al. (2013) — Word2Vec. Pennington et al. (2014) — GloVe.

---

*Documento de fundamentos, independente de projeto. Toda afirmação carrega marca de status: **[D]** demonstrada no texto, **[V]** verificada em `LAB8_fundamentos_verificacoes.py` (25 verificações), **[C]** citada com fonte nomeada, **[J]** julgamento de engenharia. Exemplos sintéticos estão rotulados como tal e não são apresentados como evidência empírica. Onde a literatura qualifica um resultado — como no escopo da anisotropia e no asterisco das analogias — a qualificação está preservada, não simplificada.*
