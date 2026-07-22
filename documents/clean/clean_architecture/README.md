# Arquitetura Limpa em Python — O Tratado
## Cada Princípio, o Seu Porquê, e o Seu Limite

---

> **O que é este documento.** Um tratado dedicado *exclusivamente* a arquitetura limpa (o nível macro: como organizar as *dependências* de um sistema inteiro para que ele permaneça maleável). É o par simétrico do tratado de código limpo — se aquele trata de escrever bem cada tijolo, este trata de onde colocar as paredes. Como o outro, **toda regra vem com o porquê concreto** (o custo que evita) e **o limite** (quando deixa de valer).
>
> **O compromisso anti-dogmático — e aqui ele é vital.** Arquitetura limpa é a ideia mais *super-aplicada* da engenharia de software: gente constrói catedrais de quatro camadas, com Protocols e injeção de dependência, para um script de 200 linhas. O resultado é pior que não ter arquitetura nenhuma. Por isso este tratado dá igual peso a *quando aplicar* e a *quando não aplicar* — o Capítulo 14 é tão importante quanto todos os outros juntos.
>
> **As referências.** O cânone é a *Clean Architecture* de Robert C. Martin (a Regra da Dependência, as camadas concêntricas, as fronteiras). A aplicação Python-específica segue a abordagem de Sam Keen (*Clean Architecture with Python*): o mapeamento concreto das camadas num projeto (`domain`/`application`/`infrastructure`/`interfaces`), o uso de *type hints e Protocols* como ferramenta arquitetural, o Domain-Driven Design com *value objects* e *entities*, e a perspectiva de refatorar legado. Tudo reescrito em palavras próprias, com exemplos meus e ancorado no RefCap — não é reprodução de nenhum livro.
>
> **Fontes primárias (PEPs) — e por que são poucas.** Cada *mecanismo Python* citado aqui está ancorado ao seu **PEP-fonte**. Mas atenção a uma assimetria que é o próprio recado: **a lista de PEPs de arquitetura é curta.** Isso porque arquitetura limpa é dirigida por *princípios* — a Regra da Dependência, SOLID, portas e adaptadores, DDD — que vêm da tradição (Martin, Keen), **não dos PEPs.** O que os PEPs oferecem é só o *mecanismo* para realizar esses princípios em Python, e ele está concentrado quase inteiramente num PEP só: o **[PEP 544](https://peps.python.org/pep-0544/) (Protocols)**. Então: **não espere os PEPs te ensinarem arquitetura** — eles dão as ferramentas; a sabedoria está neste tratado. O catálogo companheiro **`Levantamento_PEPs_CleanArchitecture.md`** organiza esse subconjunto enxuto como checklist; quando você vir "*(Ver Levantamento — Clean Architecture, §X)*", é o ponteiro para lá.

---

# CAPÍTULO 0 — A raiz: para que serve arquitetura

Assim como "código limpo" não é sobre beleza, "arquitetura limpa" não é sobre diagramas bonitos nem sobre ter muitas camadas. É uma resposta a um problema econômico específico, e todo o resto deriva dele.

**O problema:** os requisitos de um software *mudam* — sempre, continuamente, de formas que ninguém previu. Novas features, novas integrações, troca de banco, troca de framework, uma API que vira também um app mobile. O código que não consegue absorver mudança sem se despedaçar morre — não porque para de funcionar, mas porque cada mudança fica tão cara e arriscada que o progresso trava.

**A tese da arquitetura:** o valor de um sistema de software está em *duas* coisas — o que ele *faz* hoje (comportamento) e o quão *fácil é mudá-lo* amanhã (estrutura). E há uma inversão contraintuitiva de prioridade: **a estrutura é frequentemente mais importante que o comportamento imediato.** Um sistema que faz tudo certo hoje mas é impossível de mudar está condenado; um que faz menos hoje mas absorve mudança prospera. O papel da arquitetura é preservar a *maleabilidade* — manter o custo da próxima mudança baixo.

**A definição operacional (a que vamos usar):** *arquitetura é o conjunto de decisões sobre onde traçar fronteiras e como fazer as dependências as cruzarem, de modo a maximizar as opções que você mantém em aberto e minimizar o custo da mudança.* Uma boa arquitetura **adia decisões** — ela permite que você decida tarde (quando tem mais informação) coisas como qual banco, qual framework, qual UI, mantendo essas escolhas *fora* do núcleo do sistema.

**A consequência que orienta todo julgamento:** a pergunta arquitetural certa nunca é "quantas camadas?" nem "isto segue o padrão?", mas **"esta estrutura mantém o núcleo do sistema — o que lhe dá valor — protegido das decisões que provavelmente vão mudar?"**. Toda regra deste tratado serve a isso. E — crucialmente — quando a estrutura que você impõe *custa* mais do que a maleabilidade que ela compra (Cap. 14), a regra está te traindo.

**Por que isto ataca o dogmatismo:** o dogmático adiciona camadas porque "arquitetura limpa tem camadas". O engenheiro adiciona uma fronteira quando, e apenas quando, o que está dos dois lados dela *muda por razões diferentes e em ritmos diferentes* — porque é isso que uma fronteira protege. A diferença não é conhecer os padrões; é saber *qual problema cada fronteira resolve*, e só pagá-la quando o problema existe.

---

# CAPÍTULO 1 — A Regra da Dependência (a única lei)

Se você esquecer tudo deste tratado menos uma coisa, que seja esta. A arquitetura limpa inteira é, essencialmente, *uma regra* — o resto são técnicas para obedecê-la.

## 1.1 A lei

**A regra:** organize o sistema em camadas, do mais abstrato/estável (centro) ao mais concreto/volátil (borda). E então: **as dependências do código-fonte apontam apenas para dentro.** Uma camada interna nunca sabe nada sobre uma camada externa. O nome de nada que vive num círculo externo pode ser mencionado por código num círculo interno.

```
   ┌──────────────────────────────────────────────────┐
   │  Frameworks & Drivers (infrastructure)           │  torch, ffmpeg, FastAPI, o banco, a UI
   │  ┌────────────────────────────────────────────┐   │        │
   │  │  Interface Adapters (interfaces)           │   │        │  dependências
   │  │  ┌──────────────────────────────────────┐  │   │        │  apontam
   │  │  │  Use Cases (application)             │  │   │        ▼  para
   │  │  │  ┌────────────────────────────────┐  │  │   │      DENTRO
   │  │  │  │  Entities (domain)             │  │  │   │
   │  │  │  │  o núcleo — regras de negócio  │  │  │   │
   │  │  │  └────────────────────────────────┘  │  │   │
   │  │  └──────────────────────────────────────┘  │   │
   │  └────────────────────────────────────────────┘   │
   └──────────────────────────────────────────────────┘
        (entre parênteses: o nome concreto da camada num projeto Python, à la Keen)
```

## 1.2 Por que esta é a lei

**O porquê:** o centro contém o que dá *valor* ao sistema — as regras de negócio, os conceitos do domínio. Essas são as coisas mais estáveis (a ideia de "momento de vídeo", "cena", "busca por relevância" não muda quando você troca o torch por outro backend). A borda contém o que é *volátil e descartável* — qual biblioteca, qual banco, qual framework, coisas que mudam com a moda e a conveniência.

Ao forçar as dependências a apontarem para dentro, você garante que **o volátil depende do estável, nunca o contrário.** Consequência: você pode trocar qualquer coisa na borda — o decodificador de vídeo, o backend de tensores, a interface (CLI → API → app) — **sem tocar no núcleo**, porque o núcleo não sabe que a borda existe. O que muda com frequência (borda) fica isolado do que dá valor duradouro (centro). **Toda a maleabilidade do sistema decorre desta única direção.**

O oposto — deixar o núcleo depender da borda (a lógica de negócio importando o framework diretamente) — acopla o valor duradouro ao detalhe volátil. Aí, trocar o framework exige mexer na lógica; a moda da borda contamina o coração; e cada decisão de infraestrutura vira irreversível. É a arquitetura da imobilidade.

## 1.3 O limite

**O limite:** a Regra da Dependência só compra valor quando há, de fato, um núcleo *estável* que vale a pena proteger de uma borda *volátil*. Se o seu sistema é *todo* borda — um script que orquestra chamadas de biblioteca, sem regras de negócio próprias — não há núcleo para isolar, e impor a regra cria camadas vazias que só adicionam indireção. (Isto é central no Cap. 14.) A regra é uma ferramenta de *separação*; onde não há o que separar, ela é cerimônia.

---

# CAPÍTULO 2 — As camadas concêntricas (e o mapeamento Python concreto)

A Regra da Dependência precisa de camadas para operar. Martin define quatro, do centro para fora. Keen as mapeia para nomes de pastas concretos num projeto Python — e é essa versão concreta que torna a ideia acionável.

## 2.1 As quatro camadas, com o porquê de cada fronteira

**Entities / `domain` — as regras de negócio da empresa.** Os conceitos mais fundamentais e estáveis, que existiriam mesmo se o sistema fosse feito no papel. No RefCap, seriam os conceitos de "momento de vídeo", "cena", "legenda", "relevância". *Por que esta camada existe isolada:* estas regras são as que menos mudam e as que mais valem; isolá-las de tudo o mais garante que nada volátil possa forçá-las a mudar. Elas não dependem de *nada*.

**Use Cases / `application` — as regras de negócio da aplicação.** Orquestram as entidades para realizar uma ação específica do sistema. "Buscar os momentos relevantes para uma query." *Por que separada das entidades:* um caso de uso é específico da *aplicação* (este sistema faz busca), enquanto as entidades são gerais do *domínio* (o conceito de momento existe independentemente de haver busca). Casos de uso mudam quando a aplicação muda; entidades, quando o domínio muda — ritmos diferentes, logo fronteira. Dependem só das entidades.

**Interface Adapters / `interfaces` — os tradutores.** Convertem entre o formato conveniente para os casos de uso e o formato conveniente para o mundo externo. *Controllers* recebem input externo e o traduzem para o caso de uso; *presenters* pegam a saída do caso de uso e a formatam para exibição; *gateways* abstraem a persistência. *Por que separada:* o formato interno (objetos de domínio limpos) não deve ser poluído pelo formato externo (JSON, linhas de banco, tensores). Os adaptadores absorvem essa tradução, mantendo o núcleo limpo. Dependem dos casos de uso.

**Frameworks & Drivers / `infrastructure` — o detalhe concreto.** Torch, ffmpeg, o sistema de arquivos, a rede, o banco, o framework web. A camada mais externa, volátil e descartável. *Por que na borda:* estas são as decisões que você mais quer poder trocar e adiar. Mantê-las na borda, atrás de interfaces, torna-as substituíveis. Aqui você "conecta tudo" (a *composition root*).

## 2.2 O que a estrutura de pastas comunica

A organização Python concreta (Keen) — `domain/`, `application/`, `infrastructure/`, `interfaces/` — não é burocracia: ela *torna a Regra da Dependência visível e verificável*. Você pode olhar os imports e checar: `domain/` não importa de lugar nenhum das outras; `application/` importa só de `domain/`; `infrastructure/` e `interfaces/` importam para dentro. **A estrutura de diretórios vira a expressão física da regra** — e uma violação (um import de `domain/` para `infrastructure/`) salta aos olhos. É arquitetura que se auto-documenta e se auto-fiscaliza.

**O limite:** esta estrutura de quatro pastas é o *destino* de um sistema que cresceu a ponto de precisar dela — não o *ponto de partida* de todo projeto. Começar um script de 100 linhas com quatro pastas vazias é o dogmatismo em forma de diretório (Cap. 14).

**PEP-fontes (a estrutura no concreto):** as regras de import que expressam a dependência entre camadas são a [PEP 328](https://peps.python.org/pep-0328/) (*Imports: Absolute/Relative*) — e é aqui que o `import *` do RefCap é um problema, pois **colapsa a rastreabilidade** das dependências que esta estrutura deveria tornar visível. A organização de pacotes é a [PEP 420](https://peps.python.org/pep-0420/) (*Namespace Packages*); a montagem do projeto (a *composition root* no nível macro) é a [PEP 518](https://peps.python.org/pep-0518/)/[517](https://peps.python.org/pep-0517/)/[621](https://peps.python.org/pep-0621/) (`pyproject.toml`); e a fronteira de tipos que uma lib expõe é a [PEP 561](https://peps.python.org/pep-0561/) (`py.typed`). *(Ver Levantamento — Clean Architecture, §Tier 3.)*

---

# CAPÍTULO 3 — SOLID em escala arquitetural

SOLID são cinco princípios de design orientado a objetos. No tratado de código limpo eu os mencionei; aqui vamos ao que eles significam *para a arquitetura* — porque juntos eles produzem a maleabilidade que a Regra da Dependência exige. Cada um: o quê, o porquê, o limite, e o RefCap.

## 3.1 S — Single Responsibility Principle
**O quê:** um módulo deve ter uma, e só uma, razão para mudar — ou seja, deve responder a um único *ator* (um único grupo de stakeholders cujas necessidades ele serve).
**O porquê arquitetural:** quando um módulo serve a dois atores, uma mudança pedida por um pode quebrar o que o outro depende — os dois ficam acoplados através do módulo compartilhado, e mudanças independentes colidem. Separar por responsabilidade significa que cada ator tem seu módulo, e mudanças de um não afetam o outro. É a fronteira que impede que preocupações distintas se contaminem.
**O limite:** "uma razão para mudar" é sobre *atores/eixos de mudança*, não sobre "fazer uma coisa". Separar demais — um módulo por método — fragmenta o que muda junto, criando o problema oposto. Separe o que muda por razões *diferentes*; mantenha junto o que muda pela *mesma* razão.
**No RefCap:** `MixPipe.retrieval` mistura codificação, similaridade, agregação, fusão e formatação. Se a lógica de fusão mudar, ou o formato de saída mudar, é a mesma função tocada — múltiplos eixos de mudança num só lugar.

## 3.2 O — Open/Closed Principle
**O quê:** entidades de software devem ser abertas para extensão, mas fechadas para modificação. Você adiciona comportamento novo sem alterar o código existente.
**O porquê arquitetural:** este é *o* princípio que torna um sistema extensível com segurança. Se adicionar uma feature exige modificar código existente, cada adição arrisca quebrar o que já funcionava (regressões), e a superfície de risco cresce com o sistema. Se você adiciona por *extensão* (nova classe implementando uma interface existente), o código antigo não é tocado — logo não pode regredir. A técnica que o viabiliza é a abstração: dependa de uma interface, adicione implementações.
**O limite:** OCP tem um custo — a abstração (a interface) é indireção, e indireção especulativa ("posso precisar estender isto um dia") frequentemente adivinha errado *onde* a extensão virá, criando pontos de flexibilidade nos lugares errados enquanto engessa os certos. Aplique OCP nos eixos onde a extensão é *provável e conhecida*, não em todo lugar por precaução.
**No RefCap (um acerto):** o *registry* (`@REGISTER_CAPGEN`, `@REGISTER_PROPGEN`) é OCP exemplar. Adicionar um gerador novo = criar uma classe e registrá-la, sem tocar em nada existente. Foi *por isso* que, no nosso alinhamento, um `caption_generator` de frame único seria uma extensão limpa — o eixo "tipo de gerador" foi corretamente identificado como um ponto de variação provável.

## 3.3 L — Liskov Substitution Principle
**O quê:** subtipos devem ser substituíveis por seus tipos base sem quebrar o programa. Quem depende de uma abstração deve funcionar com qualquer implementação dela.
**O porquê arquitetural:** o LSP é o que torna a *polimorfia confiável* — e a polimorfia é o mecanismo pelo qual a Regra da Dependência opera (o núcleo depende de uma interface; a borda fornece implementações). Se uma implementação viola o contrato da interface (lança exceções que a base não promete, ignora argumentos que a base respeita, exige pré-condições que a base não menciona), então "depender da abstração" deixa de ser seguro — você tem que saber *qual* implementação está lá, e o acoplamento que a interface deveria quebrar volta. LSP é o que faz a abstração *cumprir a promessa* de intercambiabilidade.
**O limite:** herança nem sempre é a ferramenta certa para reúso. Frequentemente, composição (delegar a um objeto) é mais limpa que herança (herdar de uma classe), e evita as armadilhas de LSP por completo. "Prefira composição a herança" é o corolário prático.
**No RefCap:** `CapGeneratorBLIP` herda de `BaseCapGen` e deve honrar seu contrato (receber `video_name, video_path`, popular `self.captions`). O caminho MiniGPT — que exige legendas pré-geradas externamente — é uma tensão sutil com LSP: a mesma chamada tem pré-condições diferentes por subclasse, o que quebra a substituibilidade transparente.

## 3.4 I — Interface Segregation Principle
**O quê:** nenhum cliente deve ser forçado a depender de métodos que não usa. Prefira muitas interfaces pequenas e específicas a uma grande e geral.
**O porquê arquitetural:** interfaces "gordas" criam acoplamento acidental — quem depende delas fica ligado a *tudo* que elas declaram, inclusive o que não usa, e uma mudança numa parte irrelevante da interface propaga recompilação/retrabalho para clientes que nem tocavam aquela parte. Interfaces enxutas minimizam a superfície de acoplamento: cada cliente depende só do que realmente usa. Isto é o que mantém as fronteiras *finas*.
**O limite:** segregar demais — uma interface por método — pode fragmentar conceitos que são coesos, criando um enxame de micro-interfaces que obscurece a intenção. Segregue por *papel do cliente* (agrupe o que um tipo de cliente usa junto), não por método individual.
**No RefCap (a lição que exploramos):** o `MixPipe` depende do dataset por uma interface *mínima* — só `vid_name_to_id` + `__getitem__`/`__len__`. Foi *exatamente* essa estreiteza que nos deixou injetar o `QueryDataset` sem herdar do `DataSet4Test` inteiro. Se a interface fosse gorda (exigindo gabarito, métricas, etc.), o adapter seria impossível. **Interfaces enxutas compram flexibilidade — e nós colhemos essa flexibilidade diretamente.**

## 3.5 D — Dependency Inversion Principle
**O quê (o mais importante para arquitetura):** módulos de alto nível não devem depender de módulos de baixo nível; ambos devem depender de *abstrações*. E abstrações não devem depender de detalhes; detalhes devem depender de abstrações.
**O porquê arquitetural:** este é o *mecanismo* que faz a Regra da Dependência ser possível quando o fluxo de controle vai "para fora". Considere: o caso de uso (alto nível) precisa salvar dados no banco (baixo nível). O fluxo de controle vai do caso de uso *para* o banco. Ingênuamente, isso faria o caso de uso *depender* do banco — violando a Regra. A inversão resolve: o caso de uso define uma *interface* (`RepositorioDeVideos`), e o banco a *implementa*. Agora a dependência do código-fonte do banco aponta *para dentro* (para a interface no núcleo), mesmo que o fluxo de controle vá para fora. **A dependência foi *invertida* em relação ao fluxo de controle** — daí o nome. Sem DIP, a Regra da Dependência seria impossível de obedecer sempre que o núcleo precisasse do mundo externo.
**O limite:** cada inversão introduz uma interface — indireção que tem custo cognitivo (mais um arquivo, mais um salto para entender o fluxo). Inverter *toda* dependência transforma o código num labirinto de interfaces onde rastrear "o que realmente acontece" exige abrir dez arquivos. Inverta nas *fronteiras que importam* — onde o baixo nível é genuinamente volátil ou precisa ser trocável/testável — não em toda chamada de função.
**No RefCap (o que tornou nossa adaptação possível):** o `MixPipe` não depende do `DataSet4Test` concreto — depende de um *contrato* (via duck typing). Nós fornecemos outra implementação (`QueryDataset`) do mesmo contrato. **Isto é inversão de dependência na prática, e é *por isso* que conseguimos adaptar sem tocar no núcleo.** Quando você entende DIP, você entende por que algumas adaptações são triviais (há uma abstração no ponto certo) e outras exigem cirurgia (há uma dependência concreta cravada).

> **A síntese de SOLID:** os cinco convergem numa única capacidade — *depender de abstrações estáveis em vez de detalhes voláteis, nas fronteiras certas*. É essa capacidade que a Regra da Dependência exige e que a maleabilidade requer.

---

# CAPÍTULO 4 — O mecanismo: Inversão e Injeção de Dependência em Python

DIP (Cap. 3.5) é o *princípio*. Injeção de Dependência (DI) é a *técnica* que o realiza na prática. E Python tem suas próprias ferramentas para isso, diferentes das linguagens de tipagem estática nominal.

## 4.1 Injeção de Dependência — a técnica

**O quê:** em vez de um objeto *criar* suas dependências internamente (`self.repo = BancoPostgres()`), ele as *recebe* de fora (`def __init__(self, repo): self.repo = repo`). Quem constrói o objeto decide qual implementação injetar.
**O porquê:** quando um objeto cria a própria dependência, ele fica *acoplado à implementação concreta* que criou — trocar exige mudar o código dele. Quando ele recebe a dependência, ele depende só da *interface*, e quem monta o sistema (a *composition root*, na borda) escolhe a implementação. Isto é o que torna a inversão *operacional*: o alto nível declara "preciso de algo que salve vídeos"; a borda decide "vou te dar o que salva no S3" (produção) ou "o que salva num dict" (teste). **DI é como a dependência efetivamente flui de fora para dentro, em runtime, enquanto o código-fonte permanece apontando para dentro.**
**O limite:** DI tem um custo de *cerimônia* — objetos precisam ser montados em algum lugar, e a cadeia de "quem injeta o quê" pode ficar longa. Frameworks de DI (containers) existem para gerenciar isso, mas adicionam magia e uma dependência a mais. Em Python, para a maioria dos sistemas, **injeção manual via construtor** (passar os argumentos) é suficiente e mais clara que um container — não importe um framework de DI antes de a cerimônia manual doer de verdade.

## 4.2 As ferramentas Python para abstração — o "Type-Enhanced" (Keen)

Aqui Python difere das linguagens de tipagem nominal (Java, C#), e Keen enfatiza isso. Há *três* formas de definir a "abstração" da qual você depende, com trade-offs distintos:

**Duck typing (implícito):** você não declara interface nenhuma — simplesmente depende de que o objeto tenha os métodos certos. "Se implementa `__getitem__` e `__len__`, serve." *Vantagem:* zero cerimônia, máxima flexibilidade (qualquer objeto que sirva funciona, sem herança). *Custo:* o contrato é *invisível* — não está escrito em lugar nenhum, então quem implementa tem que *descobrir* o que é exigido (foi o que fizemos, lendo o `MixPipe` para achar o contrato do dataset). Frágil a mudanças silenciosas.

**`abc.ABC` (Abstract Base Class, explícito e nominal):** você declara uma classe base abstrata com métodos abstratos, e as implementações *herdam* dela. *Vantagem:* o contrato é explícito e verificado (Python impede instanciar uma subclasse que não implementou tudo). *Custo:* exige herança — a implementação tem que *saber* da ABC e descender dela, o que acopla e às vezes é inconveniente (e não funciona bem para objetos que você não controla).

**`typing.Protocol` (explícito e estrutural — o melhor dos dois, Python 3.8+):** você declara um `Protocol` com os métodos esperados, e *qualquer* objeto que os tenha satisfaz o protocolo — **sem precisar herdar dele**. É duck typing *com um contrato escrito e verificável por type checkers*. *Vantagem:* combina a flexibilidade do duck typing (sem herança) com a explicitude da ABC (o contrato existe, documentado e checável por `mypy`). *Por que é a ferramenta arquitetural ideal em Python:* deixa o núcleo *declarar* a abstração de que precisa (o Protocol) sem forçar a borda a herdar nada — a inversão de dependência sem o acoplamento da herança.

**A lição para você, aplicada ao que fizemos:** o `QueryDataset` funcionou por duck typing (implícito) — teve que *descobrir* o contrato. Num sistema *seu*, bem-arquitetado, você *declararia* esse contrato como um `Protocol`:
```python
from typing import Protocol

class QueryProvider(Protocol):
    vid_name_to_id: dict[str, int]
    def __len__(self) -> int: ...
    def __getitem__(self, i: int) -> tuple: ...
```
Agora o contrato é visível, verificável, e quem implementa sabe exatamente o que precisa — sem herdar. **É a diferença entre um acoplamento que se descobre lendo o código e um que se lê na assinatura.** Este é o coração do "Type-Enhanced Python": usar o sistema de tipos não para performance, mas para *tornar as fronteiras arquiteturais explícitas e fiscalizáveis*.

> **★ PEP-fonte (o mecanismo central da arquitetura limpa em Python).** As três ferramentas acima têm especificações oficiais:
> - **`typing.Protocol` → [PEP 544](https://peps.python.org/pep-0544/)** (*Protocols: Structural Subtyping*) — **a joia da coroa.** É o que torna a Inversão de Dependência Pythônica: declarar a abstração sem exigir herança. Se você dominar *um* PEP para arquitetura, é este.
> - **`abc.ABC` → [PEP 3119](https://peps.python.org/pep-3119/)** (*Introducing Abstract Base Classes*) — a alternativa nominal (com herança). Estude os dois lado a lado.
> - **Os type hints do contrato → [PEP 484](https://peps.python.org/pep-0484/)** (fundação) — aqui servindo para definir *contratos de fronteira*, não só clareza de função.
>
> Este é o subconjunto de PEPs que sustenta *toda* a arquitetura limpa em Python — o companheiro `Levantamento_PEPs_CleanArchitecture.md` os organiza como checklist (§Tier 1–2). E o exercício-âncora é justamente reescrever o `QueryDataset` do RefCap com o `Protocol` acima.

---

# CAPÍTULO 5 — A camada de domínio: entities e value objects (DDD)

O centro dos círculos. Keen dedica um capítulo ao Domain-Driven Design porque é aqui que o valor do sistema vive, e modelá-lo bem é o que dá sentido a todas as outras camadas.

## 5.1 Entities — objetos com identidade

**O quê:** uma *entidade* é um objeto de domínio definido por sua *identidade*, não por seus atributos. Um "usuário" com id 42 continua o mesmo usuário mesmo se mudar de nome — a identidade persiste através das mudanças de estado.
**O porquê arquitetural:** entidades encapsulam as regras de negócio mais fundamentais e estáveis. Colocá-las no centro, sem dependências, garante que essas regras — o que dá valor ao sistema — não possam ser corrompidas por decisões de borda. Uma regra de negócio expressa numa entidade ("um pedido não pode ser fechado sem itens") vive num lugar onde nenhum framework, banco ou UI pode alterá-la acidentalmente.
**O limite:** nem todo sistema tem entidades ricas. Um pipeline de transformação de dados (como boa parte do RefCap) é mais sobre *fluxo* que sobre *objetos com identidade e regras*. Forçar um modelo de domínio rico onde o problema é essencialmente um fluxo de transformações é impor uma estrutura que o domínio não pede.

## 5.2 Value Objects — objetos definidos por valor

**O quê:** um *value object* é definido pelos seus atributos, não por identidade, e é *imutável*. Um intervalo de tempo `(início=12.0, fim=19.0)` é um value object — dois intervalos com os mesmos valores são *o mesmo* intervalo; e você não *muda* um intervalo, você cria outro.
**O porquê arquitetural (por que isto importa muito, e é subestimado):** value objects substituem *primitivos soltos* (tuplas, dicts, floats crus) por *conceitos nomeados e validados*. Compare: passar `(12.0, 19.0)` por todo o sistema (o que é? segundos? o que garante que início < fim?) versus passar um `IntervaloDeTempo` que *valida na criação* (início < fim, ambos ≥ 0) e *comunica o conceito*. O value object (a) elimina a "obsessão por primitivos" (um code smell onde tipos básicos carregam significado que deveria ser explícito), (b) centraliza a validação (impossível criar um intervalo inválido), e (c) torna o código auto-documentado. **Ele transforma um dado anônimo num conceito de domínio.**
**No RefCap (um smell claro):** o dataset devolve uma *tupla de 7 elementos* `(desc_name, desc_id, vid_name, vid_id, desc, ts_start, ts_end)`, desempacotada posicionalmente. Isto é obsessão por primitivos: a posição carrega significado (o 6º é `ts_start`), não há validação, e um erro de ordem passa silencioso. Um value object (`Query` com campos nomeados, ou um `@dataclass`) tornaria o contrato explícito, validado e à prova de erro posicional. É exatamente o tipo de coisa que um sistema *seu*, limpo, faria diferente.
**O limite:** criar um value object para *cada* dado é exagero — um contador de loop não precisa virar `ContadorDeIteracao`. Reserve value objects para conceitos de domínio que (a) se repetem, (b) têm regras de validade, ou (c) cujo significado nu (um float) seria ambíguo. Onde o primitivo é claro e local, o primitivo basta.

**PEP-fonte:** o mecanismo Python dos value objects é [PEP 557](https://peps.python.org/pep-0557/) (*Data Classes* — use `@dataclass(frozen=True)` para imutabilidade); para dados estruturados tipados, [PEP 589](https://peps.python.org/pep-0589/) (*TypedDict*). *(Ver Levantamento — Clean Architecture, §Tier 2.)* Note a dupla função: no Código Limpo, dataclass reduz boilerplate; aqui, ela *implementa o conceito de domínio validado* — o mesmo mecanismo, propósito arquitetural.

---

# CAPÍTULO 6 — A camada de aplicação: casos de uso como cidadãos de primeira classe

**O quê:** um *caso de uso* é uma classe/função que orquestra as entidades para realizar *uma ação específica da aplicação* — "buscar momentos por query", "cadastrar usuário", "gerar relatório". Ele contém a lógica de *aplicação* (a sequência de passos, as regras de "o que fazer quando"), delegando a lógica de *domínio* às entidades.

**O porquê arquitetural:** tornar casos de uso explícitos (uma classe `BuscarMomentos`, não um método perdido num controller ou espalhado pela UI) faz três coisas. Primeiro, **torna o que o sistema faz legível** — abrir a pasta `application/` e ver a lista de casos de uso é ler as capacidades do sistema. Segundo, **isola a lógica de aplicação da UI e da infraestrutura** — o caso de uso não sabe se foi chamado por uma CLI, uma API ou um teste; ele recebe input estruturado e devolve output estruturado. É isto que torna o mesmo caso de uso reutilizável por múltiplas interfaces (foi o que projetamos: o `search()` do `retrieve_service` como núcleo reutilizável, servível por REPL *ou* API). Terceiro, **torna a lógica testável sem a borda** — você testa `BuscarMomentos` injetando dependências falsas, sem subir servidor nem banco.

**A forma canônica:** um caso de uso recebe suas dependências por injeção (repositórios, serviços — como *interfaces*), recebe o input como um objeto estruturado (um *request model* / value object), executa a orquestração, e devolve um output estruturado (um *response model*). Ele não retorna objetos de framework, não lança exceções de framework, não sabe de HTTP nem de SQL.

**O limite:** a formalização de casos de uso (request models, response models, interfaces injetadas) tem *cerimônia*. Para uma ação trivial (uma função pura que transforma A em B), envolvê-la nessa cerimônia é overhead sem retorno. Casos de uso como classes formais pagam-se quando a ação (a) coordena múltiplas entidades/serviços, (b) precisa ser servida por múltiplas interfaces, ou (c) tem lógica de aplicação não-trivial. Uma transformação simples pode ser só uma função.

**No RefCap:** não há camada de casos de uso explícita — a lógica de "recuperar" está no `retrieve.py` (que é um script de avaliação) misturada com parsing de config, I/O e métricas. Quando *nós* extraímos o `search()` como um método reutilizável no `retrieve_service`, estávamos, na prática, *destilando um caso de uso* do script — dando-lhe uma fronteira, um input (a query), um output (os momentos), e independência da interface. Foi arquitetura limpa aplicada a legado, mesmo que informalmente.

---

# CAPÍTULO 7 — A camada de adaptadores: controllers, presenters, gateways

**O quê:** os *interface adapters* traduzem entre o formato dos casos de uso e o formato do mundo externo. Três papéis:
- **Controller:** recebe input externo (uma requisição HTTP, um comando de terminal, um evento), valida-o, converte-o no *request model* do caso de uso, e o invoca. Traduz *de fora para dentro*.
- **Presenter:** pega o *response model* do caso de uso e o formata para a saída específica (JSON, HTML, texto de terminal, um DTO). Traduz *de dentro para fora*.
- **Gateway / Repository:** abstrai a persistência — o caso de uso o vê como uma interface (`salvar`, `buscar`), e o gateway a implementa contra o banco/arquivo/API concreto.

**O porquê arquitetural:** esta camada existe para **absorver a impedância entre o núcleo e o mundo.** O núcleo quer trabalhar com objetos de domínio limpos; o mundo fala JSON, SQL, tensores, bytes. Se você deixar esses formatos externos *entrarem* no núcleo, ele se contamina — a lógica de negócio passa a manipular dicts de JSON e linhas de banco, e fica acoplada a esses formatos. Os adaptadores contêm essa tradução na fronteira, mantendo o núcleo falando só a língua do domínio. **Eles são a membrana que deixa o valor entrar e sair sem deixar o formato contaminar.**

**A separação controller/presenter (sutil mas importante):** por que separar quem *recebe* de quem *responde*? Porque input e output variam *independentemente*. A mesma ação pode receber input de uma API e de uma fila, e responder em JSON e em HTML. Separar permite recombinar. Além disso, o presenter separado impede que o caso de uso conheça o *formato* de saída — ele devolve dados estruturados, e o presenter decide se viram JSON ou tabela de terminal. O caso de uso não sabe (nem deve saber) como será exibido.

**O limite:** a tríade completa (controller + presenter + gateway, cada um com suas interfaces) é a forma *plena*, justificada quando há múltiplas interfaces e formatos. Para um sistema com uma única interface e um único formato, colapsar papéis (um adaptador que recebe e responde) é legítimo — a separação plena só se paga quando a *variação independente* que ela permite é real.

**No RefCap:** os adaptadores que *nós* escrevemos — `make_annos.py` (traduz sua pasta de vídeos para o formato de annos que o núcleo espera) e o `retrieve_service.py` (traduz queries de terminal para o contrato do `MixPipe`, e os resultados de volta para texto) — são exatamente interface adapters. Eles formam uma **camada anti-corrupção** (termo do DDD): uma fronteira que protege o seu mundo da forma do código alheio, traduzindo entre os dois sem deixar um contaminar o outro.

---

# CAPÍTULO 8 — A camada externa: mantendo frameworks à distância

**O quê:** a camada mais externa — *frameworks & drivers* / `infrastructure` — contém o detalhe concreto: torch, ffmpeg, o banco, o framework web, o sistema de arquivos. O princípio: **frameworks são detalhes, não fundações.** Eles ficam na borda, atrás de interfaces suas, e são chamados *pelo* núcleo (via inversão), nunca o contrário.

**O porquê arquitetural:** um framework é uma decisão de alto risco e alta volatilidade — ele evolui, muda de API, cai em desuso, é substituído por algo melhor. Se você deixar o framework *invadir* o núcleo (importar torch na lógica de domínio, estruturar seu código conforme a estrutura que o framework impõe, herdar das classes-base dele por todo lado), você **casa o seu sistema com o ciclo de vida do framework** — quando ele mudar, você muda junto, dolorosamente; quando quiser trocá-lo, não consegue, porque ele está entranhado. Mantê-lo na borda, atrás de uma interface sua, torna-o *substituível* e *adiável*: você decide qual framework tarde, e troca quando precisar, sem tocar no núcleo.

**A regra de ouro (Martin):** *"o framework é uma ferramenta a ser usada, não uma arquitetura a ser seguida."* Não deixe o framework ditar a forma do seu sistema. Você usa o framework; ele não usa você.

**O sintoma clássico de violação — e o RefCap é o caso de estudo perfeito:** efeitos colaterais de framework no *import* de um módulo. O `os.environ["CUDA_VISIBLE_DEVICES"]='0'` no topo de `construct.py` e `retrieve.py` faz o *simples ato de importar* o módulo alterar o ambiente global de CUDA. Isto é o framework (CUDA) vazando para o nível estrutural — o import, que deveria ser inerte, ativa configuração de infraestrutura. Foi o bug que nos mordeu no `retrieve_service` (forçou a GPU 0 sem ninguém pedir). **A infraestrutura deve ser configurada explicitamente, na composition root, no momento certo — nunca disparada como efeito colateral de carregar um módulo.**

**O limite:** isolar *todo* framework atrás de uma interface é caro e às vezes absurdo. Você não vai abstrair a biblioteca-padrão do Python atrás de interfaces "para poder trocá-la". A regra se aplica a frameworks que são (a) genuinamente voláteis, (b) grandes o suficiente para o lock-in doer, ou (c) que você tem razão real para querer trocar/testar sem. Para bibliotecas pequenas, estáveis e ubíquas, o isolamento é cerimônia. **Isole o que você teme trocar; use diretamente o que é estável e onipresente.**

---

# CAPÍTULO 9 — Fronteiras, Portas e Adaptadores (Arquitetura Hexagonal)

Uma forma prática e muito usada da Regra da Dependência, que dá nomes concretos ao mecanismo de cruzar fronteiras.

**O quê:** o núcleo da aplicação (domínio + casos de uso) se comunica com o mundo através de **portas** (interfaces que o núcleo define) que **adaptadores** (implementações concretas) preenchem. Uma *porta* é o que o núcleo *precisa* ou *oferece*, expresso como interface; um *adaptador* é como isso se conecta a uma tecnologia específica.
- **Portas de entrada (driving):** como o mundo aciona o núcleo (ex.: a interface de um caso de uso). Adaptadores de entrada: controllers, CLIs, handlers de API.
- **Portas de saída (driven):** o que o núcleo precisa do mundo (ex.: `RepositorioDeVideos`). Adaptadores de saída: implementações contra banco, arquivo, API.

**O porquê:** o hexágono expressa visualmente que o núcleo é *agnóstico* quanto ao que está conectado nas portas. A mesma porta de entrada pode ter um adaptador de CLI *e* um de API — o núcleo não sabe qual. A mesma porta de saída pode ter um adaptador de Postgres *e* um de memória (para testes) — o núcleo não sabe qual. **Isto é o que torna o sistema testável (conecte adaptadores falsos) e flexível (troque adaptadores sem tocar no núcleo).** É a Regra da Dependência com um vocabulário operacional.

**A conexão direta com tudo que fizemos:** a nossa estratégia inteira de adaptação do RefCap foi arquitetura hexagonal aplicada, mesmo sem nomeá-la. O `MixPipe` tinha uma *porta* implícita (o contrato do dataset); nós escrevemos um *adaptador* (`QueryDataset`) que a preencheu com queries de usuário em vez de dados de benchmark. O `make_annos.py` é um adaptador que preenche a porta de entrada da construção. **Não reescrevemos o RefCap — encontramos suas portas e escrevemos adaptadores.** É a essência do hexágono, e é *por isso* que conseguimos adaptar um sistema alheio sem cirurgia: exploramos as fronteiras que já existiam.

**O limite:** portas e adaptadores explícitos para *cada* interação externa multiplicam interfaces e arquivos. A abordagem plena vale quando a *substituibilidade* ou a *testabilidade* daquela fronteira é real e importa. Para uma dependência externa única, estável e não-crítica, uma porta formal é indireção sem retorno.

---

# CAPÍTULO 10 — Testabilidade: a consequência (não o objetivo)

**O quê:** um sistema bem-arquitetado é *testável por construção* — você consegue testar a lógica de negócio isoladamente, sem subir banco, servidor, ou framework, injetando implementações falsas nas portas.

**O porquê (a inversão de causa que importa entender):** testabilidade não é algo que você *adiciona* a um sistema — é um *sintoma* de que a arquitetura está certa. Se a sua lógica de negócio é difícil de testar (exige subir meio mundo, mockar dez coisas, configurar infraestrutura), isso é um *diagnóstico*: a lógica está acoplada à infraestrutura, violando a Regra da Dependência. Se ela é fácil de testar (instancie o caso de uso, injete falsos, verifique o resultado), a arquitetura está isolando o núcleo corretamente. **A dificuldade de testar é o alarme de incêndio da arquitetura** — ela te avisa do acoplamento antes que ele te custe caro em manutenção. Por isso Martin trata os testes como a camada mais externa: eles são apenas *outro cliente* do núcleo, e se o núcleo foi projetado para ser usado por qualquer cliente (via portas), os testes o usam trivialmente.

**A consequência prática:** projete para testabilidade não porque testes são um fim, mas porque *a mesma propriedade que torna o código testável (dependências injetadas, núcleo isolado, portas explícitas) é a que o torna maleável.* Testabilidade e maleabilidade são a mesma coisa vista de dois ângulos. Um sistema testável é um sistema onde você pode trocar peças — e trocar peças é o que a manutenção exige.

**No RefCap:** a *ausência* de testabilidade fácil é o sintoma que confirma o diagnóstico arquitetural. Para testar a recuperação, *nós* tivemos que escrever scratchpads que stubavam o torchtext, mockavam modelos, e reconstruíam contexto — precisamente porque a lógica está entrelaçada com a infraestrutura (o import que força CUDA, os modelos carregados incondicionalmente, o acoplamento corpus↔queries). Um sistema com portas explícitas nos deixaria injetar falsos limpos. O esforço que gastamos para testá-lo *é a medida* da sua dívida arquitetural.

---

# CAPÍTULO 11 — O RefCap sob a lente da arquitetura (estudo de caso)

Aplicando tudo ao código que você dissecou. **Contexto, de novo, importa:** o RefCap é *código de pesquisa* — otimizado para produzir um paper, não para durar e mudar. Julgá-lo por padrões de arquitetura de produção é injusto; mas mapear onde ele diverge é o que te ensina a construir *o seu* sistema diferente. E, relevante para você, isto é literalmente o exercício do capítulo "Legacy to Clean" de Keen: olhar código não-arquitetado e ver as fronteiras que faltam.

## O que o RefCap acerta (arquiteturalmente)
1. **O registry (OCP + plugin architecture).** Pontos de extensão bem identificados (`caption_generator`, `proposal_generator`, `denoiser`). Você estende por adição. É o acerto arquitetural mais claro do projeto.
2. **A separação por disco entre construção e recuperação.** Os dois estágios se comunicam por um artefato (`tree.json`), não por acoplamento direto — uma fronteira real, cada estágio evoluindo independentemente. É quase um *pipeline architecture*.
3. **Interfaces estreitas em pontos-chave (ISP/DIP acidental).** O contrato mínimo do dataset no `MixPipe` — que exploramos — é uma porta bem-dimensionada, consciente ou não.

## Onde o RefCap peca (arquiteturalmente)
1. **Sem separação de camadas (a Regra da Dependência não é observada).** A lógica de domínio (o algoritmo VCMR) está entrelaçada com a infraestrutura (torch, ffmpeg, I/O de arquivo) no mesmo nível. Não há `domain/` isolado — o núcleo depende diretamente dos detalhes de borda.
2. **Framework vazando no import (a violação-símbolo).** `os.environ["CUDA_VISIBLE_DEVICES"]='0'` no topo do módulo. Infraestrutura ativada como efeito colateral de carregar código. O caso de estudo perfeito do Cap. 8.
3. **Obsessão por primitivos (falta de value objects).** A tupla de 7 elementos do dataset, os dicts crus como `frame_captions`, os floats de tempo soltos. Conceitos de domínio (query, intervalo, momento) representados como primitivos anônimos, sem validação nem nome. O Cap. 5.2 em negativo.
4. **Casos de uso não destilados.** A lógica de "recuperar" vive num script de avaliação, misturada com config, I/O e métricas. Não há uma fronteira "buscar momentos" reutilizável — nós tivemos que destilá-la (o `search()`).
5. **Acoplamento que vaza como armadilha.** O `compute_tree_feature` podar o corpus pelos vídeos das queries é um detalhe de implementação (otimização de benchmark) que vaza para virar uma armadilha em qualquer uso fora do benchmark. Uma abstração bem-feita não deixaria "o corpus pesquisável" depender silenciosamente do arquivo de queries.
6. **Testabilidade baixa (o sintoma que confirma).** O esforço que gastamos para testar qualquer coisa (stubs, mocks, reconstrução de contexto) é a medida direta da dívida arquitetural.

## O veredito equilibrado
O RefCap é **bom código de pesquisa e arquitetura fraca** — e isso é uma escolha *racional* para o contexto dele (papers premiam resultados, não maleabilidade). Os pecados são o *delta* entre "funciona para o paper" e "sustentável e mutável". E aqui está o ponto que conecta com o seu trabalho: **você não precisa consertar essa arquitetura — você precisa construir os adaptadores certos nas fronteiras certas.** Foi o que fizemos. Não reescrevemos o RefCap em quatro camadas (seria over-engineering sobre código que você não controla); encontramos suas poucas portas boas (o contrato do dataset) e construímos uma camada anti-corrupção ao redor. **A lição arquitetural mais madura deste caso não é "o RefCap deveria ser limpo" — é "aplique arquitetura na sua fronteira com ele, não dentro dele".**

---

# CAPÍTULO 12 — A síntese: o checklist da arquitetura limpa

A versão executável. Cada item remete ao capítulo com o porquê.

**A lei (Cap. 1)**
- [ ] As dependências do código-fonte apontam para dentro (o volátil depende do estável, nunca o contrário)?

**Camadas (Cap. 2)**
- [ ] Há uma separação clara entre domínio, aplicação, adaptadores e infraestrutura?
- [ ] A estrutura de pastas torna a Regra da Dependência visível e fiscalizável?

**SOLID (Cap. 3)**
- [ ] SRP: cada módulo tem um único eixo de mudança?
- [ ] OCP: estende-se por adição, nos eixos onde a variação é provável?
- [ ] LSP: implementações honram o contrato da abstração?
- [ ] ISP: interfaces enxutas, por papel do cliente?
- [ ] DIP: o núcleo depende de abstrações, e a infraestrutura as implementa?

**Mecanismo (Cap. 4)**
- [ ] Dependências são injetadas (recebidas), não criadas internamente?
- [ ] As abstrações de fronteira são `Protocol`s explícitos (contrato visível e checável), não só duck typing implícito?

**As camadas em detalhe (Cap. 5-8)**
- [ ] O domínio isola as regras de negócio, com value objects em vez de primitivos soltos?
- [ ] Os casos de uso são explícitos, independentes da interface e da infraestrutura?
- [ ] Os adaptadores absorvem a tradução, mantendo o núcleo falando só a língua do domínio?
- [ ] Os frameworks ficam na borda, atrás de interfaces, chamados pelo núcleo — e nunca ativados no import?

**Fronteiras e testes (Cap. 9-10)**
- [ ] As fronteiras têm portas explícitas, com adaptadores intercambiáveis?
- [ ] A lógica de negócio é testável isoladamente (o alarme de incêndio da arquitetura)?

**O princípio-mãe (Cap. 0)**
- [ ] **Esta estrutura protege o núcleo (o valor) das decisões que vão mudar (a borda) — e a maleabilidade que ela compra vale a indireção que ela custa?**

---

# CAPÍTULO 13 — Aplicando a legado: a arquitetura como destino, não big-bang

Uma nota que Keen dedica um capítulo inteiro e que é *diretamente* o seu caso: como levar código não-arquitetado (o RefCap, ou qualquer legado) em direção à arquitetura limpa **sem reescrever tudo.**

**O princípio:** você nunca refatora para arquitetura limpa de uma vez (um *big-bang rewrite* é a forma mais confiável de matar um sistema em produção). Você o faz *incrementalmente*, uma fronteira de cada vez, sempre mantendo o sistema funcionando. A técnica central é **encontrar a costura** (*seam*): um ponto onde você consegue inserir uma fronteira (uma interface, um adaptador) sem tocar no resto, e a partir dela ir isolando.

**A sequência típica:**
1. **Caracterize o comportamento atual com testes** (os testes de caracterização — nossos scratchpads). Sem eles, você não pode mudar com segurança.
2. **Encontre uma costura** — um ponto de acoplamento onde inserir uma abstração. (O contrato do dataset no RefCap foi a nossa.)
3. **Insira um adaptador** na costura, isolando um lado do outro. (O `QueryDataset`, o `retrieve_service`.)
4. **Destile os casos de uso** escondidos nos scripts, dando-lhes fronteiras. (O `search()`.)
5. **Repita**, expandindo a área isolada, sempre com o sistema funcionando.

**Por que isto valida tudo que fizemos:** a nossa jornada inteira com o RefCap foi *exatamente* esse processo. Não reescrevemos — caracterizamos (scratchpads), achamos costuras (o contrato do dataset), inserimos adaptadores (`make_annos`, `retrieve_service`), destilamos um caso de uso (`search()`), tudo mantendo o núcleo intocado e funcionando. **Você já esteve praticando refatoração-para-arquitetura-limpa em legado, no sentido técnico preciso do termo.** O que este tratado te dá é o *vocabulário* para nomear o que a sua intuição já vinha fazendo.

---

# CAPÍTULO 14 — Contra o dogmatismo: quando NÃO usar arquitetura limpa

Este é o capítulo mais importante, porque arquitetura limpa é a ideia mais *super-aplicada* da engenharia — e o dogmatismo aqui é mais destrutivo que a ausência de arquitetura. Você menospreza dogmatismo; então internalize isto acima de tudo.

## 14.1 A arquitetura tem um custo real (nomeie-o)

Toda fronteira, interface, camada e inversão que você adiciona tem um preço concreto, e ignorá-lo é o erro do dogmático:
- **Indireção.** Para entender "o que realmente acontece" você abre mais arquivos, salta por mais interfaces. Uma chamada direta vira três saltos através de abstrações.
- **Mais código.** Interfaces, adaptadores, value objects, request/response models — tudo isso é código que existe, que se lê, que se mantém.
- **Cerimônia.** Montar as dependências, definir os contratos, traduzir entre camadas — trabalho que não existiria numa função direta.
- **Curva cognitiva.** Um recém-chegado precisa entender a *arquitetura* antes de entender o *código*.

**A arquitetura compra maleabilidade pagando em indireção.** Isso é um *trade*, não um bem gratuito. O dogmático vê só o lado do benefício ("mais camadas = mais limpo") e ignora o custo. O engenheiro pesa os dois.

## 14.2 O ponto de equilíbrio (a pergunta que decide)

A pergunta é sempre: **a maleabilidade que esta estrutura compra excede a indireção que ela custa, *neste* sistema?** E isso depende inteiramente de *quanto e como o sistema vai mudar*.

**Você provavelmente NÃO precisa de arquitetura limpa plena quando:**
- **O escopo é pequeno e vai continuar pequeno.** Um script, uma automação, uma ferramenta de 200 linhas. A indireção custa mais que a mudança que ela facilitaria.
- **Os requisitos são estáveis.** Se o que o sistema faz não vai mudar muito, você está pagando por uma flexibilidade que nunca vai exercer.
- **É um protótipo ou exploração.** Você está descobrindo *se* algo funciona, não construindo para durar. Arquitetura aqui congela decisões que você ainda quer manter fluidas.
- **É código de pesquisa/análise** (como o RefCap). O objetivo é um resultado, não um sistema mantido por anos. Estrutura elaborada é esforço desviado do resultado.
- **A vida do código é curta.** Código que roda algumas vezes e morre não tem "próxima mudança" para proteger.

**Você provavelmente PRECISA quando:**
- **O sistema é longevo e vai mudar continuamente** — o cenário para o qual a arquitetura foi feita.
- **Há múltiplas integrações/interfaces** (várias fontes de dados, várias UIs, vários formatos) — a variação independente que as camadas permitem recombinar.
- **Uma equipe trabalha nele** — as fronteiras permitem que pessoas trabalhem em partes diferentes sem colidir.
- **A testabilidade é crítica** — e testabilidade exige as portas.
- **Os requisitos são voláteis ou desconhecidos** — quando você *sabe* que vai mudar mas não sabe como, manter opções abertas (o cerne da arquitetura) é o que salva.

## 14.3 O gradiente (a saída da falsa dicotomia)

O erro dogmático supõe que é tudo-ou-nada: ou você faz arquitetura limpa completa, ou você não faz arquitetura. **Falso.** Arquitetura é um *gradiente*, e a maturidade é aplicar a *dose certa* — frequentemente pequena.

Você pode aplicar **peças isoladas** onde elas pagam, sem a catedral inteira:
- Inverter *uma* dependência crítica (a que você sabe que vai trocar) sem inverter todas.
- Extrair *um* caso de uso do meio de um script, deixando o resto como está.
- Criar *um* value object para o conceito que mais se repete, mantendo primitivos no resto.
- Inserir *um* adaptador na fronteira com uma dependência volátil, sem hexágono completo.

**Foi exatamente o que fizemos com o RefCap:** não impusemos quatro camadas; aplicamos *a dose mínima* — adaptadores nas costuras que importavam, deixando o núcleo de pesquisa como estava. Isso é a aplicação *madura* da arquitetura: não "quanta arquitetura o livro descreve?", mas "quanta arquitetura *este problema* pede?".

## 14.4 As três perguntas que dissolvem o dogma arquitetural

Diante da tentação de adicionar uma camada, interface ou fronteira, pergunte:

1. **"Que mudança específica esta fronteira facilita?"** Se você não consegue nomear uma mudança provável que ela torna barata, você está adicionando indireção especulativa. Fronteira sem mudança prevista é peso morto.
2. **"Essa mudança é provável neste sistema?"** Uma fronteira que protege contra uma mudança que nunca virá é custo puro. Arquitete para as mudanças *prováveis*, não para todas as *concebíveis*.
3. **"O custo da indireção agora é menor que o custo da mudança sem ela depois?"** A pergunta-mãe. Se adicionar a fronteira custa mais (em indireção, cerimônia, cognição) do que economizaria na mudança que ela facilita, não adicione — ainda. Você pode sempre adicionar depois, *quando* a mudança se tornar real (refatorar para a fronteira na hora é barato se você tem testes).

**O sinal de que você entendeu (e não decorou):** você consegue olhar um sistema e dizer *"aqui, arquitetura plena seria over-engineering; ali, aquela costura vale uma inversão"*. Um dogmático aplica o mesmo nível de arquitetura em tudo. Um engenheiro *modula a dose* conforme a volatilidade e a longevidade de cada parte.

## 14.5 A regra sobre a regra

Arquitetura limpa é um conjunto de técnicas para comprar maleabilidade. Maleabilidade tem valor *proporcional à mudança que o sistema vai sofrer*. Logo: **a quantidade certa de arquitetura é proporcional à quantidade esperada de mudança.** Muita mudança → mais arquitetura se paga. Pouca mudança → arquitetura é desperdício. Aplicar arquitetura pesada a um sistema que não muda é tão errado quanto não aplicar nenhuma a um que muda muito — os dois são falhas de *calibração*, e o dogmatismo é a incapacidade de calibrar.

**Conhecer os padrões te torna capaz de arquitetar; saber a dose certa para cada problema te torna arquiteto.**

---

*Este tratado é uma síntese dos princípios de arquitetura limpa da tradição da engenharia de software (Robert C. Martin) e da sua aplicação idiomática em Python (Sam Keen: o mapeamento concreto de camadas, o Type-Enhanced Python com Protocols, o Domain-Driven Design com value objects, a refatoração de legado), reescrita em palavras próprias, justificada pela razão de cada princípio, e ancorada no caso concreto do RefCap e no trabalho de adaptação que você realizou sobre ele. Como o tratado de código limpo, é deliberadamente anti-dogmático: cada princípio vem com o seu porquê e — crucialmente, para arquitetura — com o seu limite e o custo de aplicá-lo onde não cabe. A dose certa de arquitetura é a que o seu problema pede, nunca a que o livro descreve. Expanda-o com os seus próprios casos; o melhor tratado é o que você reescreve com os sistemas que construiu, e cujas fronteiras você já sabe quando não traçar.*
