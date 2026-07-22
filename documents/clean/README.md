# Clean Code & Clean Architecture em Python
## Os Mandamentos — Um Guia de Referência para Escrever e Ler Código sem Depender de IA

---

> **O que é este documento.** Um guia de referência, para colar no seu repositório, sobre as boas práticas de **código limpo** (nível micro: como escrever cada função, classe, nome) e **arquitetura limpa** (nível macro: como organizar as dependências de um sistema inteiro). É destilado do cânone estabelecido da engenharia de software — os princípios sistematizados por Robert C. Martin (*Clean Code*, *Clean Architecture*), a leitura Pythônica de Mariano Anaya (*Clean Code in Python*), a aplicação arquitetural de Sam Keen (*Clean Architecture with Python*), e o próprio [Zen of Python (Tim Peters, PEP 20)](https://github.com/python/peps/tree/main).
>
> **Como usar.** Não é para ler de uma vez. É para consultar. As Partes I–II são os princípios. A Parte III aplica as lentes ao RefCap (o código que você está dissecando) — é onde a teoria vira julgamento concreto. A Parte IV é o checklist destilado (os "mandamentos"). A Parte V trata da questão que você levantou: **quando usar IA e quando codar manualmente.** O Apêndice é um protocolo de prática para recalejar.
>
> **A filosofia por trás de tudo.** Uma única ideia governa este documento inteiro, e vale internalizá-la antes de qualquer regra: **código é lido muito mais vezes do que é escrito.** Você escreve uma função uma vez; você (e outros) a leem dezenas de vezes ao longo da vida do sistema. Portanto, **otimizar para a leitura é quase sempre a decisão certa** — mesmo quando custa mais para escrever. Todo princípio abaixo é, no fundo, uma consequência disso.
>
> **Fontes primárias (PEPs) e documentos companheiros.** Os *princípios* aqui vêm da tradição (Anaya, Martin, Keen — os "porquês"); os *idiomas Python* que os realizam vêm dos **PEPs** (os "comos"), e cada idioma abaixo traz o seu PEP-fonte com link. Dois catálogos companheiros organizam esses PEPs como checklist de estudo: **`Levantamento_PEPs_CleanCode.md`** (o subconjunto de código limpo — lista longa, a força expressiva do Python) e **`Levantamento_PEPs_CleanArchitecture.md`** (o de arquitetura — lista curta, concentrada no PEP 544/Protocols). Quando você vir "*(Ver Levantamento — …)*", é o ponteiro para eles.

---

# PARTE 0 — Por que isto importa (a economia do código limpo)

Antes das regras, o *porquê*, porque regras sem princípio viram dogma.

**O custo do software não está em escrevê-lo — está em mantê-lo.** Um sistema é escrito uma vez e modificado centenas de vezes: correções, novas features, adaptações. O gargalo de todo esse trabalho futuro é uma coisa só: **quanto tempo leva para entender o código antes de mudá-lo com segurança.** Código limpo minimiza esse tempo. Código sujo o multiplica, até o ponto em que "é mais fácil reescrever do que entender" — a morte de um projeto.

Há uma assimetria cruel aqui: **o código sujo parece mais rápido no curto prazo.** Você entrega a feature hoje. Mas cada atalho é um empréstimo com juros — a *dívida técnica*. E os juros são pagos por você, em três meses, quando não lembrar mais por que aquela função tem sete parâmetros e um efeito colateral escondido. **Clean code é disciplina de pagar à vista.**

**A regra de ouro operacional:** deixe o código mais limpo do que você o encontrou. Não precisa refatorar o mundo — só não pioré-lo. É o princípio do escoteiro (*Boy Scout Rule*): "deixe o acampamento mais limpo do que você o achou".

---

# PARTE I — CLEAN CODE (o nível micro)

O domínio de Anaya: como cada linha, função e classe deve ser escrita em Python especificamente.

## 1. Os fundamentos Pythônicos

Python tem uma filosofia própria, codificada em dois documentos que você deveria conhecer de cor.

### PEP (Python Enhancement Proposals) 20 — O Zen of Python (`import this`)
Os **19 aforismos** ([PEP 20](https://peps.python.org/pep-0020/)) que guiam o design da linguagem (são 19 escritos — o "20º" é uma piada de Tim Peters, deixado em branco). O conjunto completo, cada um com porquê e limite, está no tratado dedicado `ZEN_OF_PYTHON_Tratado_Completo.md`. Aqui, uma amostra dos de maior peso prático:

- **"Explicit is better than implicit."** Não esconda comportamento. Uma função que altera estado global silenciosamente viola isto. (Guarde este — o RefCap o viola de forma exemplar, §III.)
- **"Simple is better than complex. Complex is better than complicated."** Prefira a solução simples. Se precisar de complexidade, que seja *complexa* (muitas partes simples e claras), não *complicada* (emaranhada).
- **"Flat is better than nested."** Evite aninhamento profundo. Três `for` dentro de dois `if` dentro de um `try` é um sinal de que algo precisa virar uma função.
- **"Readability counts."** O critério final. Se você tem que escolher entre esperto e legível, escolha legível.
- **"Errors should never pass silently. Unless explicitly silenced."** Não engula exceções. Um `except: pass` mudo é quase sempre um bug esperando acontecer.
- **"There should be one—and preferably only one—obvious way to do it."** Python valoriza convenção. Siga os idiomas estabelecidos em vez de inventar os seus.

### PEP 8 — O guia de estilo
As convenções de formatação ([PEP 8](https://peps.python.org/pep-0008/); docstrings na [PEP 257](https://peps.python.org/pep-0257/)): `snake_case` para funções e variáveis, `PascalCase` para classes, `UPPER_CASE` para constantes, 4 espaços de indentação, ~79-99 caracteres por linha, imports organizados (stdlib → terceiros → locais). **Não decore isto — use um formatador automático** (`black`, `ruff`). A questão não é memorizar regras de espaçamento; é que o estilo consistente reduz a carga cognitiva de leitura. Deixe a máquina cuidar do estilo para você focar na lógica.

> **Princípio:** o estilo não é sobre estética — é sobre *previsibilidade*. Código que segue as convenções da linguagem é lido no piloto automático; código idiossincrático exige atenção a cada linha.

## 2. Nomes significativos

Nomear é uma das coisas mais difíceis e mais importantes. Um bom nome elimina a necessidade de um comentário.

**Regras:**
- **Revele a intenção.** `d` não diz nada; `dias_desde_modificacao` diz tudo. O nome deve responder *por que existe, o que faz, como é usado*.
- **Evite desinformação.** Não chame de `lista_x` algo que é um dicionário. Não use `l`, `O`, `I` (parecem `1` e `0`).
- **Faça distinções significativas.** `dados`, `dados2`, `dados_info` não distinguem nada. Se você precisa de dois nomes, eles precisam de dois *significados*.
- **Use nomes pronunciáveis e buscáveis.** `genymdhms` é impronunciável. `timestamp_geracao` você acha com um grep.
- **Classes são substantivos** (`CapTree`, `SearchService`); **funções/métodos são verbos** (`encode_caps`, `generate_proposal`).
- **Comprimento proporcional ao escopo.** Um `i` de loop de três linhas é aceitável. Uma variável que vive por uma função inteira merece um nome completo. Quanto maior o escopo, mais descritivo o nome.

**A exceção legítima (importante para você, que vem da matemática):** em código numérico denso, variáveis de uma letra que **espelham a notação matemática** são aceitáveis e às vezes *preferíveis* — `i`, `j` para índices de matriz, `n` para tamanho, `x` para entrada. Num loop de convolução, `for i in range(kernel_size)` é mais claro que `for indice_da_linha_do_kernel in range(...)`. **O critério é: o leitor esperado reconhece a convenção?** Um `alpha` num contexto de fusão de scores comunica mais que `peso_de_ponderacao_da_similaridade_de_sentenca`.

## 3. Funções

O coração do clean code. Uma boa função é o átomo de um bom sistema.

**As duas regras cardeais:**
1. **Funções devem ser pequenas.** E depois menores. Se uma função não cabe na sua tela, ela provavelmente faz coisas demais.
2. **Funções devem fazer UMA coisa.** E fazê-la bem. E só ela.

Como saber se faz "uma coisa"? **Se você consegue extrair outra função dela com um nome que não seja apenas uma reafirmação, ela fazia mais de uma coisa.** Uma função que constrói um kernel, aplica uma convolução, seleciona fronteiras, escolhe legendas e coleta keywords faz *cinco* coisas (isto é literalmente o `generate_proposal` do RefCap — §III).

**Outras regras:**
- **Um nível de abstração por função.** Não misture o de-alto-nível (`processar_video`) com o de-baixo-nível (`buffer[i] = byte & 0xFF`) na mesma função. Isso confunde o leitor sobre o que é essencial e o que é detalhe.
- **Poucos argumentos.** Zero é ideal, um ou dois é bom, três é o limite, mais que isso exige justificativa forte. Muitos argumentos geralmente significam que eles deveriam ser um objeto, ou que a função faz coisas demais.
- **Evite argumentos booleanos (flag arguments).** `desenhar(True)` não diz nada no ponto de chamada. Um booleano como argumento quase sempre significa que a função faz duas coisas — divida em duas funções (`desenhar_visivel()` e `desenhar_oculto()`).
- **Sem efeitos colaterais escondidos.** Uma função chamada `validar_senha` que *também* inicializa a sessão está mentindo pelo nome. Faça o que o nome diz, e só isso.
- **Command-Query Separation.** Uma função ou *faz* algo (comando, muda estado) ou *responde* algo (query, retorna valor) — não ambos. `if set_e_verificar_atributo("x")` é confuso.
- **Prefira exceções a códigos de erro** (veja §5).

**Do átomo à molécula — classes, coesão e encapsulamento:** se funções são o átomo, classes são a molécula. Duas regras fecham o tópico. **(1) Coesão:** os métodos e atributos de uma classe devem estar fortemente relacionados, servindo a *uma* responsabilidade — o oposto da "classe balde" que acumula funções não relacionadas. Sinal de baixa coesão: se metade dos métodos usa um subconjunto de atributos e a outra metade usa outro subconjunto disjunto, a classe quer ser *duas*. **(2) Encapsulamento:** exponha o mínimo; esconda o que pode mudar. Em Python, o prefixo `_` é a convenção de "isto é interno, não dependa disso" — não imposto, mas respeitado ("somos todos adultos aqui"). **Cuidado com um equívoco comum (Anaya):** o prefixo `__` (duplo) **não** cria privacidade — ele faz *name mangling* (renomeia `__x` para `_Classe__x` internamente, para evitar colisões em herança). Usar `__` achando que "torna privado" é um erro; para sinalizar "interno", use `_` (simples). *(Tratado de Código Limpo, Cap. 9.)*

## 4. Comentários e docstrings

**A verdade incômoda: a maioria dos comentários é um fracasso.** Um comentário explica *o quê* ou *como* — mas se o código estivesse limpo, ele já diria isso. **O melhor comentário é o que você não precisou escrever porque o código era claro.**

**Comentários ruins (evite):**
- **Redundantes:** `i += 1  # incrementa i`. Ruído.
- **Que reafirmam o código:** se o comentário só traduz a linha para inglês, apague-o.
- **Desatualizados:** um comentário que mente é pior que nenhum. E comentários *sempre* desatualizam, porque o código muda e o comentário não.
- **Código comentado (dead code):** `# max_val = torch.max(scores)`. Isto é lixo — o controle de versão guarda o histórico; apague. (O RefCap tem vários — §III.)

**Comentários bons (use):**
- **Explicam o *porquê*, não o *quê*.** `# usamos Frobenius aqui porque o cosseno por par estourava a memória` — isso o código não consegue dizer.
- **Avisam de consequências:** `# ATENÇÃO: isto força a GPU 0 no import`.
- **Esclarecem intenção não óbvia** ou uma decisão contraintuitiva.
- **TODOs e FIXMEs** honestos.

**Docstrings (o comentário Pythônico legítimo):** diferente de comentários soltos, docstrings são parte da API — documentam o *contrato* de um módulo, classe ou função (o que recebe, o que retorna, o que levanta). Use-as para a interface pública. Uma boa docstring diz *o que a função faz e como usá-la*, não *como ela funciona por dentro*.

```python
def encode_caps(self, caps: list[str]) -> torch.Tensor:
    """Codifica uma lista de legendas em vetores via sentence-transformer.

    Args:
        caps: as legendas a codificar.
    Returns:
        Tensor [N, 768] no device configurado.
    """
```

> **Princípio:** prefira código que se explica a comentários que explicam código. Gaste seu esforço tornando o código claro; reserve os comentários para o que o código genuinamente não consegue expressar — o *porquê*.

## 5. Tratamento de erros

Erros mal tratados poluem a lógica e escondem bugs.

**Regras:**
- **Use exceções, não códigos de erro.** Retornar `-1` ou `None` para sinalizar erro força o chamador a checar toda vez (e ele vai esquecer). Uma exceção separa o caminho de erro do caminho feliz.
- **Não retorne valores-sentinela para sinalizar falha.** Retornar `torch.zeros(1)` quando a decodificação falha, e depois checar `if len(shape) != 4` lá na frente, é frágil: o sentinela pode colidir com um valor válido, e o chamador precisa conhecer a convenção secreta. **Levante uma exceção.** (Isto é *exatamente* a fonte de um bug real no RefCap — §III.)
- **Não engula exceções.** `except: pass` é quase sempre errado. Se você silencia um erro, faça-o explicitamente e comente por quê.
- **Capture exceções específicas**, não `except Exception`. Capturar tudo esconde bugs que você não previu.
- **Falhe cedo e alto.** Valide pré-condições no início (o *fail-fast*). Um erro que aparece perto da causa é fácil de depurar; um que aparece três funções depois é um pesadelo.
- **Não passe nem retorne `None` descuidadamente.** `None` que viaja pelo sistema vira um `AttributeError` distante da origem. Se algo pode faltar, trate na fronteira.
- **Preserve a exceção original** ao relançar: `raise NovaExcecao(...) from exc` — sem o `from`, a cadeia de causa se perde. *(Lacuna que a auditoria contra Anaya apontou.)*

**PEP-fontes de erros:** [PEP 3134](https://peps.python.org/pep-3134/) (`raise ... from`), [PEP 352](https://peps.python.org/pep-0352/) (hierarquia de exceções), [PEP 654](https://peps.python.org/pep-0654/) (`except*`). *(Ver Levantamento — Clean Code, §3.6.)*

**EAFP vs LBYL — o idioma Pythônico:** Python prefere **EAFP** ("Easier to Ask Forgiveness than Permission") a **LBYL** ("Look Before You Leap"). Ou seja: tente e trate a exceção, em vez de checar antes.

```python
# LBYL (menos Pythônico) — e tem race condition
if key in dicionario:
    valor = dicionario[key]
else:
    valor = default

# EAFP (Pythônico)
try:
    valor = dicionario[key]
except KeyError:
    valor = default
```

## 6. DRY — e as suas armadilhas

**DRY (Don't Repeat Yourself):** cada pedaço de conhecimento deve ter uma representação única e autoritativa no sistema. Se você tem a mesma lógica em três lugares, uma correção exige três edições — e você vai esquecer uma.

**Exemplo de violação (real, no RefCap):** o GloVe é carregado no `load_pretrained_models` *e* de novo dentro do `MixPipe.__init__`. A mesma responsabilidade (carregar ~1GB) duplicada. Consequência: memória desperdiçada e duas fontes de verdade para "qual GloVe estamos usando".

**A armadilha do DRY (a nuance que separa o júnior do sênior):** DRY é sobre **conhecimento duplicado, não código parecido.** Duas funções que hoje têm código idêntico mas mudam por *razões diferentes* **não** devem ser unificadas — porque quando uma mudar, você vai ter que separá-las de novo, dolorosamente. Unificar código que só *coincidentemente* se parece cria acoplamento falso. **A pergunta certa não é "esse código se repete?" mas "essa *decisão* se repete?"**. Isto conecta diretamente com o SRP (§II.1) — código muda por razões; unifique o que muda pela mesma razão.

**Os acrônimos irmãos (Anaya):** ao lado de DRY, dois princípios que valem nomear porque são a espinha do anti-over-engineering — **YAGNI** ("You Ain't Gonna Need It": não construa o que você *acha* que vai precisar; construa o que precisa *agora*) e **KIS** ("Keep It Simple": prefira a solução mais simples que resolve). Os dois são o antídoto direto à abstração especulativa — e reaparecem em escala na Parte II.9 (quando *não* usar arquitetura).

## 7. Os idiomas Python que produzem código limpo

Python oferece construções específicas que, bem usadas, tornam o código dramaticamente mais limpo. Dominá-las é a diferença entre "escrever Python" e "escrever Pythônico". Cada idioma traz o seu **PEP-fonte** (a especificação oficial) — o companheiro `Levantamento_PEPs_CleanCode.md` os organiza como checklist.

**Context managers (`with`)** — garantem setup/teardown (abrir/fechar, adquirir/liberar) mesmo diante de exceções. `with open(f) as file:` fecha o arquivo aconteça o que acontecer. `with torch.no_grad():` garante que o gradiente é religado depois. Sempre que houver um par "faça X, depois desfaça X", pense em context manager. → [PEP 343](https://peps.python.org/pep-0343/).

**Generators e iterators (`yield`)** — produzem valores sob demanda, sem materializar tudo na memória. Para processar um arquivo de milhões de linhas, um generator lê uma por vez. É *lazy evaluation* — economia de memória e composição elegante. → [PEP 255](https://peps.python.org/pep-0255/) (generators), [PEP 289](https://peps.python.org/pep-0289/) (generator expressions), [PEP 234](https://peps.python.org/pep-0234/) (protocolo de iteração).

**Comprehensions** — `[f(x) for x in xs if cond(x)]` é mais claro e rápido que o loop equivalente com `append`. Mas **não abuse**: uma comprehension com três `for` e dois `if` aninhados é *menos* legível que um loop. A regra: se não cabe legível em uma linha (ou duas), use um loop. → [PEP 202](https://peps.python.org/pep-0202/) (list), [PEP 274](https://peps.python.org/pep-0274/) (dict).

**Properties (`@property`)** — expõem um método como se fosse um atributo, permitindo computar valores ou validar na atribuição sem mudar a interface. Deixam você começar com um atributo simples e adicionar lógica depois, sem quebrar quem usa a classe. É o *Uniform Access Principle*. → construída sobre o protocolo de *descriptors* ([PEP 252](https://peps.python.org/pep-0252/)/[253](https://peps.python.org/pep-0253/); Anaya, Cap. 6).

**Decorators (`@decorator`)** — envolvem uma função/classe com comportamento adicional (logging, cache, validação, registro) sem tocar no corpo dela. O `@REGISTER_CAPGEN(["blip"])` do RefCap é um decorator que registra a classe num catálogo — um exemplo legítimo e elegante (§III). Decorators são a forma Pythônica de separar responsabilidades transversais (*cross-cutting concerns*). → [PEP 318](https://peps.python.org/pep-0318/) (funções/métodos), [PEP 3129](https://peps.python.org/pep-3129/) (classes).

**Dunder methods (`__x__`)** — os métodos mágicos que integram suas classes ao protocolo da linguagem. `__len__` faz `len(obj)` funcionar; `__getitem__` faz `obj[i]` funcionar; `__iter__` faz o `for` funcionar. **Foi exatamente isso que exploramos no `QueryDataset`:** implementando só `__len__` e `__getitem__`, ele "se passou" por um dataset sem herdar de nada. Isto é *duck typing* — "se anda como um pato e grasna como um pato, é um pato" — e é um dos pilares do Python. → a versão formal e verificável é a **tipagem estrutural** da [PEP 544](https://peps.python.org/pep-0544/) (Protocols).

**Dataclasses / namedtuples** — para objetos que são essencialmente dados, evitam boilerplate de `__init__`, `__repr__`, `__eq__`. Um `@dataclass` substitui vinte linhas por três. → [PEP 557](https://peps.python.org/pep-0557/) (dataclasses), [PEP 589](https://peps.python.org/pep-0589/) (TypedDict).

## 8. Type hints

Python é dinamicamente tipado, mas *type hints* (`def f(x: int) -> str:`) adicionam uma camada de documentação verificável. Eles não mudam a execução (o interpretador os ignora), mas:
- **Documentam o contrato** de forma que não desatualiza silenciosamente (um checker como `mypy` reclama).
- **Habilitam ferramentas** — autocompletar, detecção de erros na IDE, refactoring seguro.
- **Tornam o código auto-explicativo:** `def encode_keys(self, keys: list[str]) -> torch.Tensor` diz o contrato inteiro sem docstring.

→ **PEP-fonte:** [PEP 484](https://peps.python.org/pep-0484/) (fundação) + [PEP 483](https://peps.python.org/pep-0483/) (teoria); sintaxe moderna [PEP 585](https://peps.python.org/pep-0585/) (`list[int]`) e [PEP 604](https://peps.python.org/pep-0604/) (`int | None`). No nível de arquitetura, é a [PEP 544](https://peps.python.org/pep-0544/) (Protocols) que os transforma em *contratos de fronteira*.

Use-os na interface pública e onde o tipo não é óbvio. Não precisa anotar cada `i` de loop. **Para o seu caso** (código de pesquisa que você quer manter): type hints nas fronteiras entre módulos são um dos melhores investimentos de clareza por caractere digitado.

## 9. Code smells — os sinais de alerta

*Code smells* não são bugs — são sintomas de que o design está apodrecendo. Aprender a farejá-los é a habilidade central de quem lê código. Os principais:

- **Função longa** — faz coisas demais; divida.
- **Classe grande (God Object)** — sabe/faz demais; separe responsabilidades.
- **Lista longa de parâmetros** — agrupe em objeto ou reduza responsabilidades.
- **Código duplicado** — viola DRY.
- **Aninhamento profundo** — extraia funções, use *early return*.
- **Nomes ruins** — `tmp`, `data2`, `res`.
- **Números mágicos** — `0.5`, `384`, `1000` soltos no código, sem nome. Vire uma constante nomeada ou um parâmetro de config.
- **Código comentado** — apague.
- **Acoplamento forte** — mudar A quebra B, C e D.
- **Feature envy** — uma função que usa mais dados de *outra* classe do que da própria; talvez pertença à outra.
- **Abstração vazando (leaky abstraction)** — um módulo expõe detalhes internos que deveriam estar escondidos.

## 10. Testes — o clean code que protege o clean code

Código sem testes não pode ser refatorado com confiança — e código que não pode ser refatorado apodrece. **Testes são o que tornam a mudança segura.**

**Princípios:**
- **Testes são código de primeira classe.** Mantenha-os limpos como o resto.
- **F.I.R.S.T.:** Fast (rápidos, para rodar sempre), Independent (não dependem uns dos outros), Repeatable (mesmo resultado sempre), Self-validating (passa ou falha, sem inspeção manual), Timely (escritos junto com o código).
- **Um conceito por teste.** Cada teste verifica uma coisa; quando falha, você sabe exatamente o quê.
- **Arrange-Act-Assert:** prepare o cenário, execute a ação, verifique o resultado.
- **Teste comportamento, não implementação.** Um teste que quebra quando você refatora *sem mudar o comportamento* é um teste ruim (frágil).

**A conexão com o que fizemos:** os scratchpads instrumentados que criamos (provar que o `annos/` não é lido, que o BLIP nunca é invocado, que `prop_max_cnt=1` força um segmento) são *exatamente* testes de caracterização — eles travam o comportamento atual para você poder mudar com confiança. E a disciplina de **prever o resultado antes de rodar** (Parte V) é o hábito que torna cada execução um mini-teste da sua compreensão.

---

# PARTE II — CLEAN ARCHITECTURE (o nível macro)

O domínio de Keen: como organizar as *dependências* de um sistema inteiro para que ele permaneça maleável. Se o clean code é sobre escrever bem cada tijolo, a clean architecture é sobre onde colocar as paredes.

## 1. Os cinco princípios SOLID

A base da arquitetura orientada a objetos. Cada letra é um princípio; juntos, produzem sistemas que resistem à decadência.

### S — Single Responsibility Principle (SRP)
**Uma classe/módulo deve ter uma, e apenas uma, razão para mudar.** Não "fazer uma coisa" (isso é sobre funções) — mas "responder a um único *stakeholder*, um único eixo de mudança". Uma classe que muda quando as regras de negócio mudam *e* quando o formato do banco muda tem duas razões para mudar — separe-as.

*No RefCap:* o `MixPipe.retrieval` mistura codificação, cálculo de similaridade, agregação, fusão e formatação de saída. Se a lógica de fusão mudar, ou o formato de saída mudar, ou a agregação mudar — é a mesma função que é tocada. Múltiplas razões para mudar num só lugar.

### O — Open/Closed Principle (OCP)
**Aberto para extensão, fechado para modificação.** Você deve poder adicionar comportamento novo sem alterar o código existente. A forma de conseguir isso é a abstração: dependa de uma interface, e adicione novas implementações.

*No RefCap (um acerto!):* o padrão de *registry* (`@REGISTER_CAPGEN(["blip"])`, `@REGISTER_PROPGEN(["qm"])`) é OCP bem feito. Para adicionar um novo gerador de legendas, você **cria uma classe nova e a registra** — sem tocar em nenhuma linha do código existente. É exatamente por isso que, no nosso alinhamento, a Alternativa 2 (um `caption_generator` de frame único) seria uma *extensão* limpa: o sistema foi projetado para aceitá-la.

### L — Liskov Substitution Principle (LSP)
**Subtipos devem ser substituíveis por seus tipos base sem quebrar o programa.** Se `B` herda de `A`, qualquer código que espera um `A` deve funcionar com um `B`. Uma subclasse que viola o contrato da base (lança exceções que a base não lança, ou ignora argumentos que a base respeita) quebra o LSP.

*No RefCap:* `CapGeneratorBLIP` herda de `BaseCapGen` e sobrescreve `generate_caption`. Para respeitar o LSP, ela deve honrar o contrato da base — receber `(video_name, video_path)` e popular `self.captions`. Ela o faz. (O caminho MiniGPT, que exige legendas pré-geradas externamente, é uma tensão sutil com o LSP: a "mesma" chamada tem pré-condições diferentes conforme a subclasse.)

### I — Interface Segregation Principle (ISP)
**Muitas interfaces específicas são melhores que uma interface geral.** Nenhum cliente deve ser forçado a depender de métodos que não usa. Interfaces "gordas" acoplam quem as usa a coisas irrelevantes.

*No RefCap (a lição que exploramos!):* o `MixPipe` depende do dataset por uma interface *mínima* — só `vid_name_to_id` + `__getitem__`/`__len__`. Foi *exatamente* essa estreiteza que nos permitiu injetar o `QueryDataset` sem herdar do `DataSet4Test` inteiro. **Se o `MixPipe` dependesse de uma interface gorda (exigindo gabarito, métricas, etc.), o nosso adapter seria impossível.** Interfaces enxutas = flexibilidade.

### D — Dependency Inversion Principle (DIP)
**O mais importante para arquitetura, e o coração de tudo.** Módulos de alto nível não devem depender de módulos de baixo nível — ambos devem depender de *abstrações*. E abstrações não devem depender de detalhes — detalhes devem depender de abstrações.

Traduzindo: a sua lógica de negócio (alto nível) não deve importar diretamente o banco de dados, o framework web, a biblioteca externa (baixo nível). Ela deve depender de uma *interface* que o baixo nível implementa. Assim você pode trocar o banco sem tocar na lógica.

*No RefCap (o que tornou nossa adaptação possível):* o `MixPipe` não depende do `DataSet4Test` concreto — depende de um *contrato* (o duck typing). Nós fornecemos uma implementação diferente (`QueryDataset`) do mesmo contrato. **Isso é inversão de dependência na prática** — e é *por isso* que conseguimos adaptar o sistema sem tocar no núcleo. Quando você entende DIP, você entende por que algumas mudanças são triviais e outras exigem cirurgia.

**PEP-fonte (o mecanismo Python da DIP):** [PEP 544](https://peps.python.org/pep-0544/) (*Protocols* — tipagem estrutural) permite *declarar* a abstração da qual o núcleo depende, sem herança; a alternativa nominal (com herança) é a [PEP 3119](https://peps.python.org/pep-3119/) (*ABCs*). É o subconjunto de PEPs que sustenta a arquitetura — *(Ver Levantamento — Clean Architecture, §Tier 1–2.)*

> **A regra que unifica os cinco:** dependa de abstrações estáveis, não de detalhes voláteis. Tudo em SOLID serve a isso.

## 2. A Regra da Dependência (o coração da Clean Architecture)

Martin organiza um sistema em círculos concêntricos, do mais abstrato (centro) ao mais concreto (borda):

```
   ┌─────────────────────────────────────────┐
   │  Frameworks & Drivers (borda)            │  ← torch, ffmpeg, FastAPI, o banco, a UI
   │  ┌───────────────────────────────────┐   │
   │  │  Interface Adapters               │   │  ← controllers, presenters, gateways
   │  │  ┌─────────────────────────────┐  │   │
   │  │  │  Use Cases (regras de app)  │  │   │  ← "buscar momentos por query"
   │  │  │  ┌───────────────────────┐  │  │   │
   │  │  │  │  Entities (domínio)   │  │  │   │  ← o conceito de "momento", "cena"
   │  │  │  └───────────────────────┘  │  │   │
   │  │  └─────────────────────────────┘  │   │
   │  └───────────────────────────────────┘   │
   └─────────────────────────────────────────┘
```

**A Regra da Dependência, em uma frase:** *as dependências do código-fonte apontam apenas para dentro.* O domínio (centro) não sabe *nada* sobre o mundo externo. As camadas de fora conhecem as de dentro, nunca o contrário.

**Por que isto importa:** o centro — as regras de negócio que dão valor ao sistema — fica **isolado das decisões voláteis** (qual banco, qual framework, qual biblioteca). Você pode trocar o ffmpeg por outro decodificador, o torch por outro backend, a CLI por uma API — **sem tocar na lógica de domínio**, porque ela não depende de nenhum deles.

**As camadas:**
- **Entities (Entidades):** as regras de negócio mais fundamentais e estáveis. O conceito de "cena", "momento de vídeo", "legenda" — as ideias que existiriam mesmo se o sistema fosse manual. Não dependem de nada.
- **Use Cases (Casos de Uso):** orquestram as entidades para realizar uma ação da aplicação. "Buscar os momentos relevantes para uma query." Dependem das entidades, nada mais.
- **Interface Adapters:** convertem entre o formato dos casos de uso e o do mundo externo. Controllers (recebem input), presenters (formatam output), gateways (abstraem persistência).
- **Frameworks & Drivers:** o detalhe concreto. Torch, ffmpeg, o sistema de arquivos, a rede. A camada mais volátil e descartável.

**O mecanismo que faz funcionar:** quando uma camada interna *precisa* falar com uma externa (ex.: o caso de uso precisa salvar algo), ela define uma *interface* (uma abstração), e a camada externa a implementa. A dependência do código aponta para dentro (a implementação externa depende da interface interna), mesmo que o fluxo de controle vá para fora. Isto é a Inversão de Dependência (DIP) operando em escala arquitetural.

**O mapeamento Python concreto (Keen):** as quatro camadas viram quatro pastas — `domain/` (entities e value objects), `application/` (casos de uso), `infrastructure/` (frameworks, banco, libs externas), `interfaces/` (controllers, CLI, API). A estrutura de diretórios *torna a Regra da Dependência visível*: `domain/` não importa de ninguém; `application/` importa só de `domain/`; `infrastructure/` e `interfaces/` importam para dentro. Uma violação (um import de `domain/` para `infrastructure/`) salta aos olhos. *(Tratado de Arquitetura, Cap. 2.)*

## 3. Fronteiras, Portas e Adaptadores (Arquitetura Hexagonal)

Uma forma prática e popular da Clean Architecture. A ideia: o núcleo da aplicação (domínio + casos de uso) se comunica com o mundo através de **portas** (interfaces) que **adaptadores** implementam.

- **Porta:** uma interface que o núcleo define. Ex.: "um repositório de vídeos que sabe listar e buscar."
- **Adaptador:** uma implementação concreta da porta. Ex.: "um repositório que lê do sistema de arquivos" ou "um que lê do S3."

O núcleo não sabe qual adaptador está conectado — só conhece a porta. Isto torna o sistema **testável** (você conecta um adaptador falso nos testes) e **flexível** (troca o adaptador sem tocar no núcleo).

**A conexão com o que fizemos:** o `make_annos.py` e o `retrieve_service.py` são *adaptadores* — eles traduzem entre o seu mundo (uma pasta de vídeos, queries de terminal) e o contrato que o RefCap espera, **sem modificar o núcleo do RefCap**. Nós construímos uma *camada anti-corrupção* (um termo do Domain-Driven Design): uma fronteira que protege o seu código da forma do código alheio. Isto é arquitetura hexagonal aplicada, mesmo que informalmente.

## 4. Mantendo os frameworks à distância

Um corolário crucial: **frameworks são detalhes, não fundações.** Torch, ffmpeg, FastAPI, o ORM — todos são ferramentas na borda. O erro comum é deixá-los *invadir* o núcleo: importar torch na lógica de domínio, espalhar chamadas de framework por todo lado, acoplar a estrutura do código à estrutura do framework.

**O sintoma clássico (e o RefCap é um caso de estudo):** efeitos colaterais de framework no *import* de um módulo. `os.environ["CUDA_VISIBLE_DEVICES"]='0'` no topo do arquivo faz o simples ato de *importar* aquele módulo alterar o ambiente global de CUDA. Isso é o framework (CUDA) vazando para o nível estrutural do código — e foi o bug que nos mordeu no `retrieve_service.py`, forçando a GPU 0 sem que ninguém pedisse. **Frameworks devem ser chamados, não devem se ativar sozinhos no import.**

> **Princípio:** trate cada biblioteca externa como algo que você pode querer trocar amanhã. Isole-a atrás de uma interface sua. Quanto mais o seu código depende dos detalhes de uma lib, mais refém você é dela.

## 5. O mecanismo Python: Protocols, ABC ou duck typing

A DIP (§1) exige que o núcleo dependa de uma *abstração*. Python te dá três formas de expressá-la — e escolher a certa é a decisão técnica central da arquitetura limpa em Python.

- **Duck typing (implícito):** dependa da forma, sem declarar nada. *Flexível, mas o contrato é invisível* — quem implementa tem que descobri-lo lendo o código (foi o que fizemos no `QueryDataset`).
- **`abc.ABC` (nominal, [PEP 3119](https://peps.python.org/pep-3119/)):** declare uma classe base abstrata e *herde* dela. *Contrato explícito, mas exige herança* — acopla, e não serve para objetos que você não controla.
- **`typing.Protocol` (estrutural, [PEP 544](https://peps.python.org/pep-0544/)):** ★ declare o contrato como um `Protocol`, e *qualquer* objeto com a forma certa o satisfaz — **sem herdar**. É duck typing *com contrato escrito e checável por `mypy`*. **É a ferramenta arquitetural ideal em Python:** o núcleo declara a abstração de que precisa, sem forçar a borda a herdar nada.

**Regra prática:** para fronteiras internas, prefira `Protocol` (contrato visível sem acoplamento). É o exercício-âncora do RefCap: reescrever o `QueryDataset` declarando um `Protocol` explícito, em vez de tatear o contrato por duck typing. *(Tratado de Arquitetura, Cap. 4; Levantamento — Clean Architecture, §Tier 1.)*

## 6. Value objects: conceitos de domínio, não primitivos soltos

**A regra:** substitua *primitivos soltos* (tuplas, dicts, floats crus) que carregam significado de domínio por *objetos nomeados e validados*.

**O porquê:** passar `(12.0, 19.0)` por todo o sistema (o que é? segundos? o que garante início < fim?) é *obsessão por primitivos* — um code smell. Um value object `IntervaloDeTempo` que *valida na criação* (início < fim, ambos ≥ 0) e *comunica o conceito* elimina o smell, centraliza a validação, e torna o código auto-documentado. Mecanismo Python: `@dataclass(frozen=True)` ([PEP 557](https://peps.python.org/pep-0557/)).

**No RefCap (smell claro):** o dataset devolve uma *tupla de 7 elementos* desempacotada posicionalmente — a posição carrega significado, sem validação, e um erro de ordem passa silencioso. Um value object tornaria o contrato explícito e à prova de erro posicional.

**O limite:** não crie value object para *cada* dado — um contador de loop não vira `ContadorDeIteracao`. Reserve para conceitos de domínio que se repetem, têm regras de validade, ou cujo significado nu seria ambíguo. *(Tratado de Arquitetura, Cap. 5.)*

## 7. Testabilidade: a consequência, não o objetivo

**A regra:** um sistema bem arquitetado é testável *como consequência*, não como esforço adicional.

**O porquê:** se o núcleo depende de abstrações (Protocols) e não de detalhes, você testa o núcleo conectando *implementações falsas* das portas — sem banco, sem framework, sem GPU. A testabilidade não é uma propriedade que você *adiciona*; é o *sintoma* de que as dependências estão invertidas corretamente. Código difícil de testar é um diagnóstico: quase sempre significa que uma dependência concreta está soldada onde deveria haver uma abstração. **Dificuldade de teste é o alarme de um defeito arquitetural, não um problema de teste.** *(Tratado de Arquitetura, Cap. 10.)*

## 8. Aplicando a legado (a sua situação): destino, não big-bang

**A regra:** arquitetura limpa é um *destino* para onde se caminha incrementalmente, não uma reescrita de tudo de uma vez.

**O porquê:** reescrever um sistema legado inteiro "para ficar limpo" é quase sempre um erro caro e arriscado. O caminho certo é a *camada anti-corrupção*: você constrói uma fronteira limpa *ao redor* do código legado (adaptadores que traduzem entre o seu mundo e o dele), protegendo o código novo da forma do antigo, sem tocar no núcleo legado. **É exatamente o que fizemos com o RefCap:** o `make_annos.py` e o `retrieve_service.py` são adaptadores que envolvem o RefCap sem modificá-lo — arquitetura hexagonal aplicada a legado. Você não limpou o RefCap; você construiu uma fronteira limpa em volta dele. *(Tratado de Arquitetura, Cap. 13.)*

## 9. Contra o dogmatismo: quando NÃO usar arquitetura limpa

**Esta seção é tão importante quanto todas as outras juntas.** Arquitetura limpa é a ideia mais *super-aplicada* da engenharia: gente constrói catedrais de quatro camadas, com Protocols e injeção de dependência, para um script de 200 linhas. O resultado é *pior* que não ter arquitetura nenhuma — é complexidade acidental pura.

**O custo real (nomeie-o):** arquitetura limpa custa *mais código* (interfaces, adaptadores, value objects, request/response models), *mais indireção* (para seguir um fluxo, você salta por várias camadas), e *mais tempo inicial*. Esse custo se paga **só quando** o sistema vive muito, muda muito, e tem regras de domínio que valem isolar.

**A pergunta que decide:** *"este sistema vai viver e mudar o suficiente para que o custo da arquitetura se pague em manutenção futura?"*
- **Script único, throwaway, exploração, protótipo** → **não**. Escreva direto, simples. Aplicar camadas aqui é o dogmatismo em forma de diretório.
- **Sistema de vida longa, com regras de domínio reais e múltiplas integrações voláteis** → **sim**. O custo se paga.

**O gradiente (a saída da falsa dicotomia):** não é "arquitetura limpa completa" vs. "nenhuma arquitetura". É um *contínuo*. Você aplica *o tanto de arquitetura que o problema justifica*: talvez só separar I/O de lógica; talvez um `Protocol` numa fronteira crítica e nada mais; talvez as quatro camadas completas. **A maturidade não é aplicar sempre o máximo — é calibrar o nível à necessidade real.** Um engenheiro escolhe o ponto no gradiente; um dogmático aplica sempre o extremo. *(Tratado de Arquitetura, Cap. 14.)*

---

# PARTE III — O RefCap sob as duas lentes (estudo de caso)

Aqui a teoria vira julgamento. Aplicando os princípios acima ao código que você está dissecando — honestamente, o que ele acerta e onde peca. **Contexto importa:** o RefCap é um *código de pesquisa*, otimizado para produzir um paper, não para manutenção de longo prazo. Julgá-lo pelos padrões de um sistema de produção seria injusto — mas identificar os pontos é exatamente o que te ajuda a *não* repeti-los no seu próprio sistema.

## O que o RefCap ACERTA

**1. O padrão de registry (OCP bem feito).** `@REGISTER_CAPGEN`, `@REGISTER_PROPGEN`, `@REGISTER_DENOISER` — o sistema é extensível por adição, não por modificação. Você adiciona um gerador novo sem tocar nos existentes. É arquitetura de plugins, e é elegante.

**2. Interfaces estreitas em pontos-chave (ISP/DIP).** O fato de o `MixPipe` depender do dataset por um contrato mínimo (duck typing) é o que tornou nossa adaptação possível sem cirurgia. Consciente ou não, é bom design — e foi o que exploramos.

**3. Separação por disco entre construção e recuperação.** Os dois estágios se comunicam por um artefato (`tree.json`), não por acoplamento direto. Isso é uma fronteira limpa — cada estágio pode evoluir independentemente. É quase uma arquitetura de pipeline.

**4. Uso correto de context managers.** `with torch.no_grad():`, `with open(...):` — o gerenciamento de recursos é feito de forma Pythônica.

**5. Polimorfismo via herança (base abstrata + implementações).** `BaseCapGen` define a estrutura, as subclasses implementam. É o Template Method pattern, aplicado corretamente.

## Onde o RefCap PECA

**1. Efeito colateral no import (viola "Explicit is better than implicit" + isolamento de framework).** `os.environ["CUDA_VISIBLE_DEVICES"]='0'` no topo de `construct.py` e `retrieve.py`. Importar o módulo altera o ambiente global. **É um bug esperando acontecer** — e aconteceu conosco. A correção: configuração de ambiente deve ser explícita, no ponto de entrada, não no import.

**2. Funções que fazem coisas demais (viola SRP + "funções pequenas").** `generate_proposal` (~70 linhas) constrói um kernel, aplica convolução, seleciona fronteiras, converte índices em tempo, escolhe legendas *e* coleta keywords. Seis responsabilidades. Deveria ser seis funções, cada uma testável isoladamente. `MixPipe.retrieval` tem o mesmo problema.

**3. Valores-sentinela em vez de exceções (viola tratamento de erros).** `_get_video_frames` retorna `torch.zeros(1)` quando o ffprobe falha, e o chamador checa `if len(shape) != 4`. Frágil e implícito. Deveria levantar uma exceção específica. (E lembre: o bug de colisão de sentinela no denoiser — `last_high_id='0'` colidindo com o frame 0 — é *exatamente* o tipo de erro que valores-sentinela causam.)

**4. Duplicação de carregamento (viola DRY).** O GloVe é carregado em `load_pretrained_models` e de novo no `MixPipe.__init__`. ~1GB duplicado, duas fontes de verdade.

**5. Números mágicos espalhados.** `0.5`, `384`, `1000`, `"a photo of"` aparecem no código sem nome. Alguns estão em config (bom), outros hardcoded (ruim). Um número mágico sem nome é um comentário que faltou.

**6. Código comentado (dead code).** `# max_val = torch.max(scores)`, `# can add all keys here!`, `# boundaries = [0] + boundaries + [VID_LEN]`. Lixo que o controle de versão já guarda. Apague.

**7. Ausência de docstrings e type hints consistentes.** A maioria das funções não documenta seu contrato. Para código que outros (ou você, meses depois) vão ler, é um custo de compreensão desnecessário.

**8. Ausência de testes.** Não há suíte de testes unitários (o `standalone_eval` é avaliação de métricas, não teste de código). É por isso que *nós* tivemos que escrever scratchpads de caracterização para mudar com confiança — o projeto não os fornece.

**9. Abstração vazando (o acoplamento corpus↔queries).** O `compute_tree_feature` podar a árvore pelos vídeos das queries é um detalhe de implementação (otimização de benchmark) que vaza e se torna uma armadilha para qualquer uso fora do benchmark. Uma abstração bem-feita não faria o "corpus pesquisável" depender silenciosamente do arquivo de queries.

## O veredito equilibrado

O RefCap é **bom código de pesquisa**: pragmático, funcional, extensível nos pontos que importavam para os autores (os registries). Ele **não é código de produção**, e não pretende ser. Os pecados que listei são o *delta* entre "funciona para o paper" e "sustentável a longo prazo" — e é precisamente esse delta que o *seu* trabalho de adaptação está preenchendo, com os adapters, os testes de caracterização e a camada anti-corrupção. Você está, na prática, fazendo a engenharia que o código de pesquisa dispensou.

---

# PARTE IV — OS MANDAMENTOS (o checklist destilado)

Cole isto na parede. É a versão executável de tudo acima.

## Clean Code (ao escrever cada função)
1. **Otimize para a leitura.** Código é lido mais do que escrito.
2. **Funções pequenas, uma responsabilidade.** Se não cabe na tela, ou faz mais de uma coisa, divida.
3. **Nomes revelam intenção.** Um bom nome dispensa um comentário. (Exceção: notação matemática consagrada.)
4. **Poucos argumentos.** Três é o teto. Nenhum booleano-flag.
5. **Sem efeitos colaterais escondidos.** A função faz o que o nome diz, e só isso.
6. **Classes coesas, encapsulamento com `_`.** Métodos relacionados a uma responsabilidade; `_` sinaliza "interno" (o `__` é *name mangling*, não privacidade).
7. **Exceções, não códigos de erro nem sentinelas.** Falhe cedo e alto. Preserve a causa com `raise ... from`.
8. **Não engula erros.** `except: pass` é culpado até prova em contrário.
9. **Comentário explica o *porquê*, não o *quê*.** Apague código comentado.
10. **DRY: unifique conhecimento, não código coincidente.** E **YAGNI/KIS:** não construa o especulativo; prefira o simples.
11. **Use os idiomas Python** (context managers, generators, comprehensions moderadas, properties, decorators, dunders) — cada um com seu PEP-fonte.
12. **Type hints nas fronteiras.** Documentação que não desatualiza.
13. **Sem números mágicos.** Dê nome às constantes.
14. **Deixe mais limpo do que encontrou** (Boy Scout Rule).

## Clean Architecture (ao desenhar um sistema)
15. **Dependências apontam para dentro.** O domínio não conhece o mundo externo. (Camadas Keen: `domain`/`application`/`infrastructure`/`interfaces`.)
16. **SRP:** uma razão para mudar por módulo.
17. **OCP:** estenda por adição, não por modificação (registries, plugins).
18. **LSP:** subtipos honram o contrato da base.
19. **ISP:** interfaces estreitas — não force ninguém a depender do que não usa.
20. **DIP:** dependa de abstrações, não de detalhes. É o que torna a mudança barata.
21. **O mecanismo é o `Protocol` (PEP 544).** Para fronteiras internas, declare o contrato como Protocol (visível, sem herança), não como duck typing implícito nem ABC acoplante.
22. **Value objects, não primitivos soltos.** Conceitos de domínio (intervalo, query) viram objetos nomeados e validados, não tuplas/floats anônimos.
23. **Isole os frameworks na borda.** Torch, ffmpeg, o banco — todos descartáveis, atrás de interfaces suas. **E frameworks são chamados, não se ativam no import.**
24. **Camada anti-corrupção nas fronteiras** com código alheio (foi o que fizemos com os adapters).
25. **Testabilidade é consequência de bom design.** Se é difícil testar, o design está acoplado demais.
26. **Em legado: fronteira limpa em volta, não reescrita.** Arquitetura é destino incremental, não big-bang.

## Contra o dogmatismo (a régua que governa tudo)
27. **Calibre a arquitetura à necessidade — não aplique sempre o máximo.** Script throwaway → simples e direto. Sistema de vida longa → camadas. Há um *gradiente*, e maturidade é escolher o ponto certo, não construir catedrais para scripts.

## O princípio-mãe
28. **Toda regra acima é serva de uma só ideia: minimizar o custo da próxima mudança.** Quando uma regra e essa ideia conflitarem, a ideia vence.

---

# PARTE V — Vibe coding: quando usar IA, quando codar manualmente

Você levantou o ponto mais importante para a sua situação atual, e ele merece rigor. "Vibe coding" — deixar a IA gerar código que você aceita sem entender profundamente — não é bom nem mau em si. É uma ferramenta com um *domínio de aplicação correto*. O erro é usá-la fora dele.

## O risco central: a circularidade do oráculo

Há uma armadilha específica no fluxo assistido por IA que corrói a habilidade mais silenciosamente do que se percebe. Ela funciona assim: você pede código à IA, roda, vê se "funciona", e se funcionar, aceita. O problema é que **a própria execução virou o seu oráculo de correção** — você não sabe se o código está certo, só sabe que rodou sem erro *desta vez*. Você terceirizou não só a *escrita* mas o *julgamento*. E o julgamento é a habilidade.

O sintoma: você consegue produzir código que funciona, mas não consegue mais *prever* o que um trecho faz sem rodá-lo. A sua capacidade de ler e raciocinar sobre código atrofia, porque você nunca a exercita — a execução sempre responde por você.

## O antídoto: prever antes de rodar

A disciplina que reconstrói a habilidade é simples de enunciar e difícil de manter: **antes de executar qualquer trecho — seu ou da IA — preveja o que ele vai fazer.** Escreva (mentalmente ou num comentário) o que você *espera* que aconteça. Só então rode. Quando a execução bate com a previsão, seu modelo mental está calibrado. Quando diverge, você acabou de encontrar um buraco no seu entendimento — e preenchê-lo é o aprendizado.

Isto inverte a relação: a execução deixa de ser o oráculo que *substitui* seu julgamento e vira o *teste* que o calibra. É a diferença entre "rodei e funcionou" e "previ que faria X, rodou, fez X — meu modelo está correto". A primeira não ensina nada; a segunda recaleja a cada iteração.

**É exatamente o que praticamos nesta análise inteira do RefCap:** cada scratchpad instrumentado foi uma previsão testada. "Eu afirmo que o BLIP nunca é invocado" → mock explosivo → confirmado. "Eu afirmo que `prop_max_cnt=1` força um segmento" → teste → confirmado. Não aceitamos nada sem prever e verificar. Esse é o hábito que você quer tornar automático.

## O mapa de decisão: quando cada modo é apropriado

**Vibe coding (IA gerando, você supervisionando levemente) é apropriado para:**
- **Exploração e prototipagem** — quando você está descobrindo *se* algo é viável, não construindo o final. Velocidade importa mais que domínio.
- **Boilerplate mecânico** — configuração repetitiva, esqueletos, código que você *poderia* escrever dormindo mas é tedioso. Aqui a IA economiza tempo sem custo de habilidade (você já domina).
- **Superfície de uma API desconhecida** — como ponto de *partida* para aprender uma lib nova. Mas com o compromisso de depois entender o que foi gerado.
- **Scripts descartáveis** — o código que roda uma vez e morre. Não vale investir domínio no que não será mantido.
- **Tradução mecânica** — reescrever algo que você já entende de uma forma para outra.

**Codar manualmente (você escrevendo, com a IA no máximo como consulta pontual) é obrigatório para:**
- **Lógica de domínio central** — o coração do sistema, o que lhe dá valor. Se você não entende isto profundamente, você não controla o sistema.
- **Código que você vai manter** — tudo que viverá e será modificado. A dívida de não-entendimento vence com juros.
- **Código sensível** — segurança, corretude crítica, qualquer coisa onde os modos de falha importam. Você precisa saber *por que* funciona e *como* quebra.
- **Quando você está construindo habilidade** — o seu caso agora. Aqui, o *esforço* de escrever é o ponto, não um custo a eliminar. Terceirizar o esforço terceiriza o aprendizado.
- **Quando você não conseguiria escrever sozinho** — este é o teste diagnóstico definitivo. Se a IA gerou algo que você *não saberia* produzir nem explicar, e isso importa, pare. Você está acumulando dependência, não capacidade.

## O teste diagnóstico de uma frase

Antes de aceitar código gerado, pergunte: **"Eu conseguiria escrever isto sozinho, e consigo explicar por que funciona?"**
- **Sim, e é tedioso** → vibe coding é legítimo, você está economizando tempo sem perder domínio.
- **Sim, e importa** → escreva você mesmo às vezes, para não enferrujar.
- **Não, e não importa** (script descartável) → tudo bem, siga.
- **Não, e importa** → **pare e aprenda.** Este é o único quadrante perigoso, e é onde a habilidade morre.

## A síntese para o seu momento

Você tem tempo e um objetivo claro: recalejar a leitura fluida e o raciocínio sobre código. Para *este* objetivo, a regra é deliberadamente mais rígida que a geral: **durante a fase de reconstrução, codar manualmente é o padrão, e a IA é uma consultora que você interroga — não uma que produz por você.** Use-a para tirar dúvidas conceituais, para revisar o que você escreveu, para explicar um trecho alheio que travou. Não a use para gerar o que você está tentando aprender a gerar. Depois que a habilidade estiver recalejada, você relaxa para o mapa de decisão acima — usando IA onde ela economiza tempo sem custo, e a mão onde o domínio importa. **A maturidade não é rejeitar a ferramenta nem se render a ela; é saber, a cada momento, em qual quadrante você está.**

---

# APÊNDICE — Um protocolo de prática para recalejar

Concreto, para a sua fase de reconstrução. Aproveitando o RefCap como material (você já tem contexto).

**Prática 1 — Prever antes de rodar (o hábito central).** Pegue qualquer função do RefCap que ainda não dissecou. *Antes* de rodar ou de me perguntar, escreva num comentário o que você acha que cada linha faz e o que a função retorna. Depois verifique (rodando um scratchpad, ou me perguntando). Meça a taxa de acerto do seu modelo mental. Ela vai subir.

**Prática 2 — Reimplementar do zero.** Pegue uma função pequena e coesa (ex.: `get_nouns_verbs`, ou o `apply_temporal_nms`) e reimplemente-a sem olhar, a partir só da descrição do que ela deve fazer. Compare com a original. As diferenças ensinam.

**Prática 3 — Refatorar um pecado.** Pegue um dos pontos que o RefCap peca (§III) — uma função longa, um número mágico, um sentinela — e refatore-o aplicando os mandamentos. Não para submeter ao projeto, mas para exercitar o olho crítico e a mão.

**Prática 4 — Ler e narrar.** Pegue um módulo e escreva, em português, o que ele faz — como se explicasse para outro engenheiro. Se você não consegue narrar, você não entendeu. A narração expõe os buracos.

**Prática 5 — O diário de smells.** Enquanto lê, mantenha uma lista dos code smells que encontra (como fizemos). Farejar smells é a habilidade que mais distingue quem lê código com fluência — e ela treina.

**Prática 6 — Escrever o teste antes.** Para qualquer coisa que você for modificar, escreva primeiro um teste de caracterização que trave o comportamento atual (como nossos scratchpads). Isso força você a *entender* o comportamento antes de tocá-lo — e te dá a rede de segurança para mudar com confiança.

> **O princípio da prática:** a fluência não vem de ler *sobre* código, vem de *prever, escrever e verificar* — repetidamente, com atrito. A IA remove o atrito; a reconstrução da habilidade precisa dele. Reintroduza o atrito deliberadamente, agora, para que a fluência volte a ser sua.

---

*Este documento é um destilado dos princípios de clean code e clean architecture da tradição da engenharia de software (Robert C. Martin, Mariano Anaya, Sam Keen, Tim Peters e a comunidade Python), sintetizado e aplicado ao contexto concreto do RefCap. É um guia vivo: à medida que você aprofundar a análise e encontrar novos exemplos — de acerto ou de pecado — vale expandi-lo com os seus próprios casos. O melhor guia de boas práticas é aquele que você reescreve com as suas próprias palavras e os seus próprios exemplos.*
