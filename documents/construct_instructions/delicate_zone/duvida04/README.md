# Instanciação, Ligação de Nomes e Tipagem
## Relatório Teórico Companheiro do `LAB4_instanciacao_e_binding.py`

---

> **O que é este documento.** A explicação teórica completa dos conceitos aplicados no LAB4 — o laboratório que responde *quando* cada classe é instanciada e *por que* a mesma variável parece mudar de tipo conforme o `construct.sh`.
>
> **A pergunta que o originou.** *"A variável parece se comportar como um camaleão — existe nome para essa técnica?"* Existe, mas a formulação precisa **inverte o sujeito**: não é a variável que muda. Este relatório mostra por quê, e o que está de fato acontecendo em cada uma das três camadas envolvidas — construção do grafo de objetos, ligação de nomes, e despacho.
>
> **Estrutura.** Parte 0 dá o enquadramento (os três tempos). Partes I–V tratam cada família de conceitos com o formato *o que é / o mecanismo / por que importa / no RefCap / no LAB4 / o limite*. Parte VI é a análise crítica, com dois defeitos práticos verificados no `construct.py`.

---

# PARTE 0 — O enquadramento: os três tempos do `construct.py`

Antes de qualquer conceito, o mapa temporal. Quase toda confusão sobre este código vem de misturar três momentos distintos:

| Tempo | O que acontece | Linhas | Conceito dominante |
|---|---|---|---|
| **1. Import** | Módulos executam; decoradores rodam; o registry se povoa | `construct.py:4-15` | Efeito colateral de import |
| **2. Composição** | O grafo de objetos é **montado** | `construct.py:42-47` | **Instanciação e ligação de nomes** ← *este relatório* |
| **3. Execução** | O trabalho é feito | `construct.py:49` | Despacho dinâmico |

**Por que separar importa.** No tempo 1, nenhum objeto existe — só classes registradas. No tempo 2, os objetos nascem, mas nenhum vídeo foi processado. No tempo 3, a lógica roda. Sua pergunta ("quando ocorre o instanciamento?") é inteiramente sobre o **tempo 2**, e o "camaleão" que você notou é um fenômeno desse tempo.

---

# PARTE I — O grafo de objetos e a sua construção

## I.1 As duas respostas diretas

```python
# construct.py
42:  pretrained_models  = load_pretrained_models(cfg)
43:  caption_generator  = get_capgen_class(cfg.caption_generator)(cfg, pretrained_models)
     #                    └─── devolve a CLASSE ───────────────┘└── ★ INSTANCIA ──┘
44:  caption_denoiser   = get_denoiser_class(cfg.caption_denoiser)(cfg, pretrained_models)
45:  proposal_generator = get_propgen_class(cfg.proposal_generator)(cfg, pretrained_models)
47:  construct_pipeline = get_constructpipe_class(cfg.construct_pipeline)(cfg, caption_generator, ...)
     #                                                                   └── ★ INSTANCIA ──┘
49:  construct_pipeline.construct()
```

- **`CapGeneratorBLIP` nasce na linha 43**, no *segundo* par de parênteses.
- **`BaseConstructPipeline` nasce na linha 47**, depois de todos os colaboradores.

## I.2 Ordem topológica: por que a ordem não é estilística

**O que é.** Um grafo de dependências só pode ser construído numa **ordem topológica** — cada nó depois de todos os nós de que depende.

**O mecanismo.** A **injeção por construtor** *força* essa ordem: como o pipeline recebe os colaboradores como argumentos, eles precisam já existir como valores no momento da chamada. Construir o pipeline na linha 43 daria `NameError`.

**Por que importa.** O `main()` é, na prática, uma **ordenação topológica feita à mão**. Em sistemas maiores, é exatamente esse trabalho que um *container de injeção de dependência* automatiza — ele lê as assinaturas dos construtores, monta o grafo e resolve a ordem sozinho. Saber disso explica *para que servem* os containers de DI: não são burocracia, são ordenação topológica automatizada.

**Uma propriedade estrutural notável.** Injeção **puramente por construtor torna dependências circulares impossíveis**. Se A precisa de B no construtor e B precisa de A, nenhum dos dois pode ser criado primeiro — o ciclo é detectado *na hora de escrever*, não em runtime. Isso é uma garantia de arquitetura obtida de graça pela escolha do mecanismo de injeção. (Injeção por *setter* ou por atributo perde essa garantia.)

**No LAB4.** §1 — a instrumentação mostra os `__init__` disparando na ordem obrigatória, com o pipeline por último.

**O limite.** Ordem topológica só existe se o grafo for acíclico. Sistemas com ciclos legítimos (raros, mas existem — observadores mútuos) precisam de injeção em duas fases, e aí a garantia acima se perde.

## I.3 A cadeia de construtores (`super().__init__`)

**O que é.** Quando uma subclasse é instanciada, a inicialização é **cooperativa**: cada nível da hierarquia inicializa a sua parte.

**O mecanismo.** `CapGeneratorBLIP.__init__` chama `super(CapGeneratorBLIP, self).__init__(cfg, models)`, que resolve pela MRO para `BaseCapGen.__init__`. Este configura `cfg`, `models`, o caminho do cache e **lê o `.jsonl` do disco**; só então o `__init__` da subclasse continua e captura `models['cap_gen_model']`.

**Por que importa.** A ordem observada no LAB4 (`CapGeneratorBLIP` → `BaseCapGen` → volta para `CapGeneratorBLIP`) é contra-intuitiva à primeira vista: o construtor da *subclasse* começa primeiro, mas o da *base* termina primeiro. É a estrutura de pilha da chamada.

**No RefCap.** `BlipCapGener.py:13` → `capgenerator/base.py:27`.

**O limite.** `super()` sem cuidado em herança múltipla produz inicializações duplicadas ou omitidas. A regra prática: ou toda a hierarquia usa `super()` cooperativamente, ou nenhuma usa.

## I.4 Construção *eager* e o problema dos construtores pesados

**O que é.** Todos os objetos são construídos **avidamente** (*eager*) nas linhas 42–47, antes de qualquer trabalho útil. E vários construtores **fazem trabalho pesado**.

**O que os construtores do RefCap de fato fazem:**

| Construtor | Efeitos colaterais |
|---|---|
| `BaseCapGen.__init__` | **lê** o `.jsonl` de cache do disco |
| `QMPropGenerator.__init__` | **carrega o spaCy** (`en_core_web_sm`, ~50MB) |
| `BaseConstructPipeline.__init__` | `os.listdir`, filtra por `annos`, **roda ffmpeg** (mkv→mp4), **cria diretórios** |

**O princípio violado.** A regra clássica — associada a Misko Hevery — é *"construtores não devem fazer trabalho"*. Um construtor deve **atribuir**, não **executar**. As razões:

1. **Testabilidade:** você não consegue criar o objeto sem disparar I/O.
2. **Custo invisível:** `Classe(cfg, models)` parece barato e não é.
3. **CQS:** construir é um comando disfarçado de declaração.
4. **Falha deslocada:** o erro aparece na construção, longe do uso.

**A alternativa** seria construção barata + um método explícito (`prepare()`) ou propriedades *lazy* que carregam sob demanda.

**No LAB4.** §1 — a instrumentação torna visível quanto acontece "só" ao instanciar.

**O limite (anti-dogma).** "Construtores não fazem trabalho" é heurística, não lei. Validar invariantes no construtor é *bom* — é o que garante que um objeto mal-formado nunca exista. A linha divisória: **validar é legítimo; executar I/O pesado e efeitos colaterais externos não é.**

---

# PARTE II — Nomes, objetos e ligação (a mecânica do "camaleão")

Esta é a parte que responde diretamente à sua intuição.

## II.1 Namespaces são dicionários; nomes são chaves

**O que é.** Em Python, um "escopo" é literalmente um **dicionário**. Uma variável é uma **chave** nesse dicionário; o objeto é o **valor**.

**O mecanismo.** `x = obj` é, em essência, `namespace["x"] = obj`. Você pode ver isso com `locals()`, `globals()` e `objeto.__dict__`. `del x` remove a chave. Não há "declaração", não há slot tipado, não há reserva de espaço para um tipo.

**A consequência decisiva:** **o nome não carrega tipo algum.** Não há nada em `caption_generator` que restrinja o que pode ser associado a ele.

**No LAB4.** §3 — `x` recebe um `int`, depois uma `str`, depois um `CapGeneratorBLIP`, sem qualquer objeção.

## II.2 A distinção de três vias: ligação × mutação × despacho

Esta é a distinção mais valiosa deste relatório, porque **quase toda confusão sobre "variáveis que mudam" vem de fundir estas três coisas**:

| | O que muda | O que permanece | Como detectar |
|---|---|---|---|
| **Ligação** (*binding*) | qual objeto o nome aponta | o objeto antigo (intacto) | `id()` **muda** |
| **Mutação** | o estado interno do objeto | a identidade do objeto | `id()` **não muda** |
| **Despacho** | qual código executa | nome e objeto | resolvido na MRO em runtime |

**Aplicado ao seu caso:** o que acontece nas linhas 43–47 é **ligação**, pura e simples. `caption_generator` é religado a um objeto de classe diferente conforme a configuração. Nenhum objeto se transformou. Nenhuma variável mudou de tipo — **porque variáveis não têm tipo para mudar**.

**A prova.** No LAB4 §2 e §3, o `id()` muda a cada atribuição — evidência de que o objeto é **outro**, não o mesmo objeto transformado.

**O nome técnico:** **ligação dinâmica de nomes** (*dynamic name binding*).

## II.3 Semântica de referência e identidade

**O que é.** Em Python, toda variável guarda uma **referência** a um objeto, nunca o objeto "em si" (não há semântica de valor como em C++).

**O mecanismo.** Três predicados distintos, frequentemente confundidos:
- **Identidade** (`a is b` / `id(a) == id(b)`) — é o *mesmo* objeto?
- **Igualdade** (`a == b`) — têm o *mesmo valor*? (definida por `__eq__`)
- **Tipo** (`type(a)`) — de que *classe* é?

**Por que importa aqui.** Quando o LAB4 mostra `id` diferente para cada configuração, está provando **identidade** distinta. Se fosse mutação, o `id` seria o mesmo.

**Uma consequência prática:** como o `models` (dicionário de modelos) é passado por referência a **todos** os colaboradores, todos compartilham **os mesmos objetos de modelo**. Não há cópia. É por isso que a duplicação do GloVe (carregado duas vezes em pontos diferentes) é um desperdício real e não uma ilusão — ali há de fato dois objetos.

**O limite.** Semântica de referência significa que mutação em um lugar é visível em todos os outros. É a fonte clássica de bugs de aliasing — e o motivo pelo qual argumentos mutáveis default são perigosos.

## II.4 Por que "camaleão" é uma metáfora imprecisa

Um camaleão **é o mesmo animal** mudando de cor. Aqui, cada configuração produz um **objeto diferente**, ligado ao mesmo rótulo.

A metáfora mais fiel: **uma etiqueta reutilizável**. Você cola a etiqueta "gerador de legendas" numa caixa; depois descola e cola em outra caixa. A etiqueta não mudou, as caixas são diferentes, e quem lê a etiqueta continua sabendo o que esperar do conteúdo — porque as duas caixas cumprem o mesmo contrato.

---

# PARTE III — O espectro da tipagem

Aqui está o que dá o contexto teórico completo para o efeito que você observou.

## III.1 As duas dimensões independentes (e a confusão comum)

Tipagem tem **duas dimensões ortogonais**, e confundi-las é o erro mais comum do assunto:

| | **Forte** (sem coerção implícita) | **Fraca** (coerção implícita) |
|---|---|---|
| **Estática** (checada em compilação) | Java, C#, Rust, Haskell | C |
| **Dinâmica** (checada em execução) | **Python**, Ruby | JavaScript, PHP |

- **Estática vs. dinâmica** = *quando* os tipos são verificados.
- **Forte vs. fraca** = *se* a linguagem converte tipos por conta própria.

**Python é dinâmico e forte.** Dinâmico: `x` pode receber qualquer coisa. Forte: `1 + "2"` levanta `TypeError` em vez de adivinhar — e é exatamente o aforismo *"na face da ambiguidade, recuse a tentação de adivinhar"* virado design de linguagem.

**Por que isso responde à sua dúvida.** O efeito camaleão vem da coluna **dinâmica**, não da linha forte/fraca. Python permite o rebinding livre (dinâmico) *e* proíbe conversões silenciosas (forte). São garantias diferentes.

## III.2 Tipo estático vs. tipo dinâmico de uma variável

**O que é.** Em linguagens com declaração, uma variável tem **dois** tipos:
- **Estático:** o declarado no código. Fixo, verificado pelo compilador.
- **Dinâmico:** a classe do objeto que ela contém agora. Varia.

```java
CapGen caption_generator = factory.get("blip");
└─┬──┘                     └────────┬────────┘
TIPO ESTÁTICO             TIPO DINÂMICO: CapGeneratorBLIP
(a interface — fixa)      (a implementação — varia)
```

**Em Python não existe tipo estático.** Só há o dinâmico. Por isso o efeito camaleão é **total**: nada impede `caption_generator = 42`.

**Por que isso importa arquiteturalmente.** Em linguagem tipada, o "camaleão" é **controlado pelo compilador** — só cabem implementações da interface declarada. Em Python, o contrato existe apenas: (a) na cabeça de quem escreveu, (b) na documentação, ou (c) numa anotação verificada por ferramenta externa.

**No LAB4.** §4 — mostra a anotação `caption_generator: CapGenProtocol = ...` e explica que ela é ignorada pelo interpretador; só o `mypy` a lê.

## III.3 Tipagem gradual e a recuperação do tipo estático

**O que é.** A [PEP 484](https://peps.python.org/pep-0484/) introduziu *type hints* — anotações opcionais, ignoradas em runtime, verificadas por ferramentas externas. É **tipagem gradual**: você escolhe onde quer garantia.

**O que resolve no nosso caso.** Anotar `caption_generator: CapGenProtocol` recupera precisamente o **tipo estático** que o Python não tem. O `mypy` passa a reclamar se você atribuir algo incompatível — o camaleão volta a ser controlado, mas por opção sua, não por imposição da linguagem.

**A ferramenta certa aqui.** Como as implementações do RefCap não herdam de uma interface comum (o `capgenerator` usa duck typing), a abstração adequada é **estrutural**: `typing.Protocol` ([PEP 544](https://peps.python.org/pep-0544/)). Ela declara o contrato sem exigir herança.

**O limite.** Type hints não fazem nada em runtime. Se você não roda `mypy` no CI, elas são documentação — útil, mas sem garantia. E o RefCap não as usa em lugar nenhum relevante, então paga o custo total da ausência de tipo estático.

## III.4 Nominal vs. estrutural (o que define "pertencer a um tipo")

**O que é.** Duas respostas à pergunta "este objeto é um gerador de legendas?":
- **Nominal:** é, se **declarou** ser (herda de `BaseCapGen` / registra em ABC).
- **Estrutural:** é, se **tem a forma** (implementa os métodos certos).

**No RefCap, ambas coexistem** — `capgenerator` usa estrutural (duck typing informal), `propgenerator` usa nominal (`ABC` + `@abstractmethod`).

**O limite.** Estrutural é flexível mas não avisa nada até o ponto de uso; nominal falha cedo mas exige herança, o que não serve para objetos de terceiros. `Protocol` é a síntese — mas só com verificação externa.

---

# PARTE IV — Polimorfismo e despacho: onde o valor realmente está

## IV.1 A ligação é trivial; o despacho é o que importa

**O que é.** Guardar objetos diferentes numa variável seria inútil se o Python não soubesse **executar o código certo** ao usá-los.

**O mecanismo.** Em `self.caption_generator(vid_list=...)` (`constructpipe/base.py:69`), o Python:
1. obtém o objeto ligado ao atributo;
2. consulta o **tipo real** desse objeto;
3. percorre a **MRO** desse tipo procurando `__call__`;
4. executa a primeira definição encontrada.

Isso é **despacho dinâmico** (*late binding*): o destino da chamada não está no texto, é decidido em execução.

**Por que a distinção importa.** A "variável camaleão" é o **sintoma**; o despacho é o **mecanismo**. Você poderia ter rebinding sem polimorfismo (guardar tipos sem nada em comum — e aí o código de uso quebraria). O que faz o padrão funcionar é o **contrato compartilhado** + o despacho que o honra.

**No LAB4.** §6 — a mesma linha de uso produzindo comportamentos diferentes.

## IV.2 Polimorfismo de subtipo e o princípio da substituição

**O que é.** A forma de polimorfismo em jogo: um subtipo é usável onde o supertipo é esperado.

**A condição para funcionar.** O **LSP** (Liskov): a subclasse não pode fortalecer pré-condições nem enfraquecer pós-condições. Quando viola, o polimorfismo **mente** — o código escrito contra a base quebra com a subclasse.

**No RefCap.** Já verificamos a violação: `BasePropGen.__call__` declara 3 parâmetros; `QMPropGenerator.__call__` exige 4.

**O limite.** Polimorfismo de subtipo exige relação "é-um" genuína. Forçar herança só para obter polimorfismo produz hierarquias falsas — nesses casos, `Protocol` ou composição são melhores.

---

# PARTE V — Nomear como decisão de design

## V.1 Nomes de papel vs. nomes de tipo

**A observação.** As variáveis do `construct.py` se chamam `caption_generator`, `caption_denoiser`, `proposal_generator` — **nunca** `blip_generator`, `window_denoiser`, `qm_generator`.

**O que isso é.** Nomear pelo **papel** que o objeto exerce na arquitetura, não pela classe concreta que está dentro dele.

**Por que é a escolha certa:**
1. **A linha de uso lê-se igual** para qualquer implementação — `self.caption_generator(...)` faz sentido com BLIP, MiniGPT ou LLaVA.
2. **O nome não vira mentira** quando a configuração muda. Se a variável se chamasse `blip_generator` e você rodasse com `minigpt`, o nome estaria mentindo — e **um nome que mente é pior que um comentário desatualizado**, porque ninguém desconfia de nomes.
3. **Documenta a abstração, não o detalhe.** O leitor aprende *o que aquele slot faz no sistema*, que é a informação estável.

**A conexão teórica.** Isto é **programação orientada a interfaces** aplicada ao nível dos nomes: você nomeia o contrato, não a implementação. É o mesmo princípio da *Ubiquitous Language* do DDD — o nome deve refletir o conceito do domínio, não a tecnologia que o realiza.

**No LAB4.** §5.

**O limite.** Quando existe **uma só** implementação e não haverá outra, nomear pelo papel pode ser abstração vazia — `logger` é melhor que `file_logger` se houver vários, mas se só existe um, o nome específico pode informar mais.

---

# PARTE VI — Análise crítica

## VI.1 O que este desenho custa

**Rastreabilidade.** Como o nome não tem tipo e a classe vem de uma string, **nenhuma ferramenta** consegue dizer o que `caption_generator` contém. Você descobre lendo o `.sh` — a fonte de verdade está em duas linguagens.

**Erros tardios.** Um valor de configuração inválido não é pego por nada estático. E como não há `Protocol` nem `mypy`, um objeto incompatível só falha no ponto de uso.

**Custo de leitura.** Para responder "o que roda aqui?", você precisa do triângulo config → registry → classe. Três saltos onde uma chamada direta teria zero.

## VI.2 Dois defeitos práticos verificados no `construct.py`

**Defeito 1 — violação de *fail-fast*: o caro antes do barato.**

A ordem real é:
```
linha 42: load_pretrained_models(cfg)   ← CARO (BLIP + sentence-transformer + GloVe: vários GB)
linha 45: QMPropGenerator.__init__      ← carrega spaCy
linha 47: BaseConstructPipeline.__init__ → os.listdir(video_root)   ← ★ 1ª validação do caminho!
```

**Um erro de digitação em `--video_root` só é detectado na linha 47** — depois de carregar todos os modelos. Você paga minutos de carregamento e vários GB de VRAM para receber um `FileNotFoundError` que poderia ter sido dado em milissegundos.

**O princípio violado:** *fail-fast* — valide o barato e o provável antes de investir no caro. A correção é trivial: um `os.path.isdir(cfg.video_root)` logo após o parse dos argumentos.

**Defeito 2 — construtores que trabalham (Parte I.4).** Instanciar o pipeline lista diretório, filtra por anotações, pode rodar ffmpeg e cria pastas. `Classe(...)` parece declaração e é execução.

**O agravante combinado:** os dois defeitos se reforçam. Como a validação está *dentro* de um construtor pesado, ela não pode ser movida sem reestruturar — a lógica de validação está soldada à lógica de construção.

## VI.3 Quando este desenho **não** vale a pena

O padrão inteiro — factory + ligação dinâmica + injeção — se paga sob condições específicas:

| Vale a pena quando | Não vale quando |
|---|---|
| Há implementações múltiplas e reais | Há uma só (a indireção é custo puro) |
| A escolha vem de configuração externa | A escolha é conhecida ao escrever |
| Terceiros vão estender | Tudo é seu e estável |

**No próprio RefCap há um contraexemplo:** `construct_pipeline` é resolvido por registry, mas o único valor possível é `"base"`. Ali, os três saltos de indireção não compram nada — é o padrão aplicado por simetria, não por necessidade.

---

# APÊNDICE — Correspondência com o LAB4

| Seção do LAB4 | Conceitos deste relatório |
|---|---|
| §1 Linha do tempo | I.1 (as respostas), I.2 (ordem topológica), I.3 (cadeia de construtores), I.4 (construtores pesados) |
| §2 O camaleão | II.2 (ligação vs mutação), II.4 (a metáfora corrigida) |
| §3 Nomes não têm tipo | II.1 (namespaces são dicts), II.3 (identidade e referência) |
| §4 Estático vs dinâmico | III.1 (as duas dimensões), III.2 (os dois tipos), III.3 (tipagem gradual) |
| §5 Nome = papel | V.1 (nomes de papel) |
| §6 Despacho no uso | IV.1 (ligação vs despacho), IV.2 (subtipo e LSP) |

**Percurso sugerido:** leia a seção teórica → rode a seção correspondente do LAB4 → abra a linha citada do RefCap.

---

*Este relatório cobriu os conceitos do LAB4 em cinco famílias — construção do grafo de objetos, mecânica de nomes e ligação, o espectro da tipagem, polimorfismo e despacho, e nomeação como design — mais a análise crítica com dois defeitos práticos verificados no `construct.py`. A correção central da intuição original: o "camaleão" não é a variável, porque em Python **nomes não têm tipo — objetos têm**. O que ocorre é religação de um rótulo sem tipo a objetos distintos, e o que torna isso útil não é a religação (trivial) mas o **despacho dinâmico** no ponto de uso, sustentado por um contrato compartilhado.*
