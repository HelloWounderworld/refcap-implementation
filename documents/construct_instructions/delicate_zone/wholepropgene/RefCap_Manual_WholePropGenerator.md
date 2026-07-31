# Manual de Uso — `WholePropGener.py` e a Suíte `test/`
## Instalação, Execução, Leitura da Saída, e o Mapa de Alinhamento com as Decisões

---

> **O que é este documento.** O manual prático dos dois scripts entregues: como instalar, como rodar, como ler o que sai, e — sobretudo — **onde cada decisão de projeto que alinhamos aparece no código**. A Parte 7 é o mapa de rastreabilidade: cada linha do componente ligada ao achado que a motivou.
>
> **Os dois arquivos:**
> - `WholePropGener.py` — o componente. Vai para `pipeline/propgenerator/` no repositório.
> - `test/conftest.py` + `test/test_whole_propgen.py` — a suíte pytest, **48 testes**. Vai para `<raiz-do-repo>/test/`. Roda **sem** torch, spacy, BLIP ou vídeos.
>
> **Documentos de base:** `RefCap_Projeto_WholePropGenerator.md` (a especificação), `RefCap_Similaridade_Segmentacao_e_Selecao.md` (o diagnóstico), `Fundamentos_Embeddings_Gram_e_Argmax.md` (a matemática), `ERRATA_Relatorios_RefCap.md` (o que foi refutado).

---

## Protocolo de verificação

| Marca | Significa |
|---|---|
| **[L]** | Lido no código — arquivo e linha |
| **[V]** | Verificado por execução nesta sessão |
| **[J]** | Julgamento meu |

**Escopo.** Repositório `BUAAPY/RefCap`, branch padrão. Os exemplos numéricos deste manual vêm de **embeddings sintéticos** (stubs), não de BLIP real — estão rotulados onde aparecem.

---

# PARTE 1 — Instalação

São **três edições**: uma cópia de arquivo e duas linhas. Nenhum arquivo existente tem lógica alterada.

## 1.0 Onde cada arquivo vai

```
<raiz-do-repo-RefCap>/
├── config/
│   └── cfg.py                          ← EDITAR a linha 76 (§1.3)
├── pipeline/
│   └── propgenerator/
│       ├── __init__.py                 ← EDITAR: +1 linha (§1.2)
│       ├── base.py                      (não tocar)
│       ├── QMPropGener.py               (não tocar)
│       └── WholePropGener.py           ← COPIAR para cá (§1.1)
└── test/                               ← CRIAR (nome e nível livres — ver abaixo)
    ├── conftest.py                     ← COPIAR
    └── test_whole_propgen.py           ← COPIAR
```

### Em que nível a pasta de testes pode ficar

**Em qualquer nível, desde que esteja DENTRO do repositório clonado.**

O `conftest.py` localiza a raiz **subindo** a partir de onde está até achar o marcador `pipeline/propgenerator/base.py`. Não há suposição de profundidade.

**[V] Verificado — os quatro casos rodados de fora do repositório** (para o diretório atual não mascarar o resultado):

| onde a pasta ficou | resultado |
|---|---|
| `<repo>/test/` | 48 passed |
| `<repo>/test/whole_test/` | 48 passed |
| `<repo>/tests/` | 48 passed |
| `<repo>/a/b/c/meus_testes/` | 48 passed |

**[J] Se quiser a estrutura que você mencionou** — `whole_test` dentro de `test` — basta criar `test/whole_test/` e pôr os dois arquivos lá. Funciona sem nenhum ajuste.

**⚠️ Um cuidado se você tiver várias pastas de teste:** o pytest recusa dois arquivos com o **mesmo nome-base** dentro da mesma árvore de coleta (erro `import file mismatch`). Se for ter mais de uma suíte, ou dê nomes distintos aos arquivos, ou acrescente um `__init__.py` em cada pasta.

**Fora do repositório não funciona** — e a falha é explícita, não silenciosa:
```
RuntimeError: Não encontrei a raiz do RefCap subindo a partir de /caminho/errado.
Esperava achar 'pipeline/propgenerator/base.py' em algum diretório ancestral.
Coloque a pasta de testes DENTRO do repositório clonado.
```

## 1.1 Copiar o componente

```bash
cp WholePropGener.py  <repo>/pipeline/propgenerator/
```

**[L] Estado atual da pasta:** `QMPropGener.py`, `__init__.py`, `base.py`. O arquivo novo convive com eles sem conflito.

## 1.2 Registrar o módulo

**[L] Estado atual** de `pipeline/propgenerator/__init__.py` — 2 linhas:
```python
from .base import * 
from .QMPropGener import *
```

**Adicionar uma terceira:**
```python
from .base import * 
from .QMPropGener import *
from . import WholePropGener      # registra sem despejar nomes no namespace
```

**[J] Por que `from . import` e não `import *`:** o que essa linha precisa entregar é o **efeito colateral de import** — executar o módulo para que o decorador `@REGISTER_PROPGEN(["whole"])` rode e popule o registry. As duas formas produzem esse efeito de modo idêntico. A forma com `*` adicionalmente copia todos os nomes do módulo (inclusive os que ele importou: `os`, `np`, `torch`, `spacy`…) para o namespace do pacote, já que o repositório não define `__all__` em lugar nenhum. É divergência deliberada do padrão local — vale o comentário de uma linha.

## 1.3 Liberar o nome no parser

**[L] Estado atual** de `config/cfg.py`, linhas 74–77:
```python
proposal_generator: str = field(
    default="qm",
    metadata={"choices": ["qm"]}        # ← linha 76
)
```

**Alterar a linha 76 para:**
```python
    metadata={"choices": ["qm", "whole"]}
```

**[V] Esta edição é obrigatória.** Testei com o parser real: `--proposal_generator whole` é **rejeitado** enquanto `"whole"` não estiver na lista; `qm` é aceito. **[L]** A causa é `config/hf_argparser.py:150` (`kwargs = field.metadata.copy()`), que repassa o `choices` ao `argparse`.

## 1.4 (Opcional) Controlar `whole_rank_by` pela linha de comando

O componente lê suas opções com `getattr(cfg, ..., default)`, então **funciona sem nenhuma declaração** — usando `scene_score` e dedup ligada.

**[V] Mas para passar `--whole_rank_by` no shell, o campo precisa existir em `BuildArguments`.** Testei: sem declarar, o parser levanta `ValueError: Some specified arguments are not used by the HfArgumentParser: ['--whole_rank_by', ...]`.

Se quiser controle por CLI, acrescente ao `cfg.py`:
```python
whole_rank_by: str = field(
    default="scene_score",
    metadata={"choices": ["scene_score", "self_score", "consensus", "pipeline_score"]}
)
whole_dedup: bool = True
```

**Sem isso**, para mudar o critério você edita `_DEFAULT_RANK_BY` no topo do componente (**[L]** linha 46).

---

# PARTE 2 — Execução

No `scripts/construct.sh`, troque uma linha:

```bash
proposal_generator=whole        # era: qm
```

O resto do pipeline é idêntico. As etapas 1–5 (fatiamento → BLIP → features → scores → denoising) rodam exatamente como antes; só a etapa 6 muda de executor.

**[J] Reaproveitamento total:** o componente **não** refaz nada do que já foi computado. Ele recebe `captions` (do BLIP), `all_frame_features` (visuais, a parte cara) e usa os modelos **já carregados** em memória. O único cálculo novo é um *forward* do *text encoder* sobre as legendas de cada vídeo.

---

# PARTE 3 — A saída

## 3.1 Onde os arquivos são gravados

| arquivo | conteúdo | quando |
|---|---|---|
| `{exp_dir}/{proposals_file}` (padrão `proposals.json`) | propostas + **ranking completo** | sempre |
| `{exp_dir}/{prop_sim_path}` (padrão `prop_sims.pt`) | matrizes cruzadas `[N,N]` | só se **algum** vídeo passou pelo ramo de ranqueamento |
| `{exp_dir}/{tree_file}` | a árvore final | gravado pelo `build_tree_meta`, a jusante |

**⚠️ [L] Cuidado com o `prop_sims.pt`.** Os dois geradores escrevem no **mesmo nome de arquivo** com conteúdos **semanticamente diferentes**:
- `QMPropGener.py:56` salva a matriz de **auto-similaridade** (legenda×legenda, ou frame×frame no modo `vis`);
- `WholePropGener.py` salva a matriz **cruzada** (legenda×frame).

Ambas são `[N,N]`, então nada estoura — mas se você rodar os dois no mesmo `exp_dir`, o segundo sobrescreve o primeiro e o arquivo passa a significar outra coisa. **[J] Use `construct_name` diferente para cada gerador**, o que já separa os `exp_dir`.

## 3.2 O formato exato

Saída **real** do componente (gerada nesta sessão), para uma cena de 4 s com 4 legendas, das quais 3 distintas:

```json
{
  "cena_001": {
    "proposals": [
      {
        "st": 0.0,
        "ed": 4.0,
        "cap": "a woman standing in a kitchen",
        "keys": ["woman", "knife", "kitchen", "cooking", "close", "standing"],
        "ranking": [
          { "cap": "a woman standing in a kitchen",
            "scene_score": -0.3727, "self_score": -0.1407,
            "consensus": 0.9260, "pipeline_score": 0.905,
            "n_words": 6, "n_occurrences": 2, "frames": [0, 1] },
          { "cap": "a woman cooking food",
            "scene_score": -0.4131, "self_score": -0.7774,
            "consensus": 0.8939, "pipeline_score": 0.880,
            "n_words": 4, "n_occurrences": 1, "frames": [2] },
          { "cap": "a close up of a knife",
            "scene_score": -0.4317, "self_score": -0.5193,
            "consensus": 0.8772, "pipeline_score": 0.930,
            "n_words": 6, "n_occurrences": 1, "frames": [3] }
        ],
        "rank_by": "scene_score",
        "n_raw": 4,
        "n_distinct": 3
      }
    ],
    "duration": 4.0,
    "n_raw": 4,
    "n_distinct": 3,
    "warning": null
  }
}
```

**⚠️ Os valores acima vêm de embeddings SINTÉTICOS** (os stubs do teste), por isso são negativos. **[J]** Com BLIP real, cossenos entre legenda e frame tendem a ficar altos e próximos entre si — o efeito de anisotropia descrito em `Fundamentos_Embeddings_Gram_e_Argmax.md` §I.7(e). **O que importa neste exemplo é o formato, não os números.**

## 3.3 Campo a campo

**Contrato obrigatório** — o que o `build_tree_meta` lê (**[L]** `constructpipe/base.py:177`):

| campo | valor | observação |
|---|---|---|
| `st` | sempre `0.0` | início do segmento |
| `ed` | `duration` | a cena inteira |
| `cap` | topo do ranking | **[V]** verificado igual a `ranking[0]["cap"]` |
| `keys` | substantivos+verbos, deduplicados | opcional (**[L]** L178-179), alimenta o ramo GloVe |

**Diagnóstico** — sobrevive no `proposals.json` e **[L] é ignorado pelo `build_tree_meta`**, que só acessa as quatro chaves acima:

| campo | significado |
|---|---|
| `ranking` | todas as legendas distintas, com todos os sinais |
| `rank_by` | qual sinal ordenou (registro para você saber depois) |
| `n_raw` | legendas geradas pelo BLIP (= nº de frames = `int(duration)`) |
| `n_distinct` | legendas distintas após a deduplicação |
| `warning` | `null`, ou aviso (ex.: cena longa demais) |

## 3.4 Os cinco sinais e seus limites

**[J] Nenhum é "o certo".** O componente emite todos como colunas justamente porque, sem legendas de referência, eleger um a priori seria afirmar o que não sabemos.

| sinal | o que mede | limite conhecido |
|---|---|---|
| **`scene_score`** | média da similaridade com **todos** os frames — o medoide cross-modal | favorece legenda **genérica**: *"a woman in a kitchen"* casa razoavelmente com tudo |
| **`self_score`** | similaridade com o(s) frame(s) que **geraram** aquela legenda | **viés estrutural**: a legenda saiu daquele frame, e o objetivo contrastivo do BLIP treina para maximizar exatamente isso |
| **`consensus`** | centralidade textual entre as legendas distintas | com poucas legendas é estatística fraca; e **frequência ≠ qualidade** |
| **`pipeline_score`** | o que o critério **original** do RefCap diria | é a diagonal **após** min-max; pode vir `null` se contiver NaN |
| **`n_words`** | contagem de palavras | proxy grosseiro de especificidade — **não** é medida de qualidade |

**[L] Só quatro podem ordenar** (`_RANK_CRITERIA`, linha 45): `scene_score`, `self_score`, `consensus`, `pipeline_score`. `n_words` e `n_occurrences` são emitidos como colunas mas **não** são critérios de ordenação.

**[J] O `pipeline_score` é a coluna mais útil para a sua decisão.** Ele coloca lado a lado o critério novo e o antigo, tornando o **Passo 1 do plano de validação** (concordância entre critérios) uma consulta ao JSON em vez de um experimento. No exemplo sintético acima, os dois discordam — `pipeline_score` elege o close-up da faca (0.930), `scene_score` elege a legenda da mulher na cozinha. **Isso ilustra o tipo de divergência prevista; com dados sintéticos não é evidência de que um seja melhor.**

---

# PARTE 4 — Os três caminhos de execução

**[J]** O componente ramifica pelo **dado**, não pela duração — porque o algoritmo de ranqueamento é idêntico para 2 ou 300 legendas distintas.

| condição | o que acontece | por quê |
|---|---|---|
| vídeo **ausente** em `captions` | aviso no stdout, vídeo **omitido** da saída | **[L]** `BlipCapGener.py:23` faz `return` sem registrar vídeos que falharam na decodificação; o `QMPropGenerator` estoura com `KeyError` nesse caso |
| `n_raw == 0` | proposta **vazia** + `warning` | cena com menos de 1 s: `int(duration)` = 0 |
| `n_distinct == 1` | **retorno direto** — sem matriz, sem sinais | cobre "uma legenda só" e "todas iguais"; **[V]** verificado que não chama a matriz e não propaga NaN |
| `n_distinct >= 2` | ranqueamento completo | idêntico para qualquer tamanho |

**[V] O ramo `n_distinct == 1` importa mais do que parece.** Ele elimina a classe de erro do `NaN`: com uma legenda só, `max == min` e o min-max faria `0/0`. Verificado que os sinais saem como `null` (JSON válido), não como `NaN` cru.

---

# PARTE 5 — A suíte de testes (pytest)

## 5.1 Como rodar

Da **raiz do repositório**:

```bash
pytest test/ -v
```

**[V] Quatro formas verificadas**, todas funcionam:

| comando | de onde | resultado |
|---|---|---|
| `pytest test/ -v` | raiz do repo | 48 passed |
| `pytest` | raiz do repo (descoberta automática) | 48 passed |
| `pytest -q` | de dentro de `test/` | 48 passed |
| `pytest test/test_whole_propgen.py::TestRamosDeExecucao` | raiz | 8 passed |

**Requisitos: apenas `numpy` e `pytest`.** Nem torch, nem spacy, nem sentence-transformers, nem modelos BLIP, nem vídeos. A suíte roda em ~0,15 s.

## 5.2 ★ A suíte detecta instalação incompleta

Esta é a razão principal de rodá-la logo após instalar. **[V] Verifiquei quebrando de propósito:**

| o que foi removido | resultado do pytest |
|---|---|
| a linha `from . import WholePropGener` do `__init__.py` (§1.2) | **5 failed, 42 errors** |
| o arquivo `WholePropGener.py` da pasta | **48 errors** |
| nada (instalação correta) | **48 passed** |

**[J]** Ou seja: se você esquecer qualquer uma das duas primeiras edições da instalação, a suíte grita. Ela não testa só o componente — testa que ele **está corretamente plugado no registry do repositório**.

## 5.3 Como o isolamento funciona

O `conftest.py` injeta *stubs* em `sys.modules` **antes** de qualquer import de `pipeline`. O que é stub e o que é real:

| módulo | stub ou real | por quê |
|---|---|---|
| `torch`, `spacy`, `tqdm`, `sentence_transformers` | **stub** | evita dependências pesadas e carga de modelos |
| `utils.sim_utils` | **stub** | reproduz `get_caption_frame_sims` **com o `assert` de shape** de `sim_utils.py:87` |
| `utils.tree_utils`, `utils.basic_utils` | **stub** | determinismo; `save_json` captura em memória |
| `pipeline/propgenerator/base.py` | **REAL** | define registry, decorador e ABC |
| `pipeline/propgenerator/__init__.py` | **REAL** | é a linha de integração sendo testada |
| `WholePropGener.py` | **REAL** | é o componente sob teste |

**[J] Manter `base.py` e `__init__.py` reais é deliberado.** Testar contra stubs deles não provaria que o componente se registra no repositório de verdade — e é justamente esse o modo de falha mais provável na instalação.

**⚠️ [J] Escopo dos stubs.** O `conftest.py` afeta **toda a pasta onde está**. Se você acrescentar testes que precisem do torch de verdade, ponha-os em outra pasta com o próprio `conftest.py` — senão receberão o stub.

## 5.4 O que cada classe verifica

| classe | testes | verifica |
|---|---|---|
| `TestRegistro` | 6 | registro no registry, herança da ABC, defaults, rejeição de critério inválido |
| `TestContratoDeSaida` | 9 | `st`/`ed`/`cap`/`keys`; `cap` == topo do ranking; JSON serializável |
| `TestRanking` | 11 | os 6 sinais presentes; ordenação decrescente; ordenação alternativa |
| `TestDeduplicacao` | 5 | caixa e pontuação normalizadas; `n_occurrences`; dedup desligável |
| `TestRamosDeExecucao` | 8 | ★ ramo curto não chama a matriz nem propaga NaN; mesmo caminho para N=2..12 |
| `TestRobustez` | 5 | ★ vídeo ausente não estoura; zero frames; chaves `str`; ordem temporal; cena longa |
| `TestIntegracao` | 4 | ★ `assert` de shape; persistência; keywords de todas; diagnóstico não polui |

**[J] Os três marcados com ★ verificam defeitos reais** que mapeamos no `QMPropGenerator` e que este componente evita — em especial o `KeyError` de vídeo ausente e o `NaN` de `N=1`.

## 5.5 Como estender

Os auxiliares vêm do `conftest.py`:

```python
from conftest import montar_captions, features_de_frame, ft, CHAMADAS_SIM_UTILS

def test_meu_caso(gen):
    resultado = gen(
        ["vidX.mp4"],
        [montar_captions("vidX", ["legenda A", "legenda B"], 2.0)],
        {"vidX": ft(np.array([0.9, 0.8]))},   # capframe_scores (pode ter NaN)
        {"vidX": features_de_frame(2, seed=42)},
    )
    assert resultado["vidX"]["proposals"][0]["n_distinct"] == 2
```

*Fixtures* disponíveis: `gen` (gerador pronto), `cfg` (config com `exp_dir` temporário do pytest), `models` (modelos falsos), `registry` (o registry real).

**[J] Limite honesto da suíte:** ela testa a **lógica** contra o **contrato**. Não valida a qualidade das legendas escolhidas, nem o comportamento com BLIP real, nem o impacto nas métricas de recuperação — para isso é preciso rodar o pipeline de verdade.


# PARTE 6 — Configuração

| opção | default | onde muda | efeito |
|---|---|---|---|
| `whole_rank_by` | `"scene_score"` | `cfg.py` (§1.4) ou `_DEFAULT_RANK_BY` (linha 46) | qual sinal ordena o ranking |
| `whole_dedup` | `True` | idem | se `False`, cada frame vira uma entrada, sem agrupar iguais |
| `_LONG_SCENE_WARN_SECONDS` | `30.0` | linha 47 do componente | acima disso, emite `warning` de cena suspeita |

**[J] Sobre `whole_rank_by="pipeline_score"`:** ele pode sair `null` para vídeos onde o `capframe_scores` contém NaN. Nesses casos o `_ordenar` (**[L]** linha 181) manda os `None` para o fim — comportamento definido, mas o topo do ranking passa a ser decidido pelos que têm valor. **[J]** Use essa opção para diagnóstico comparativo, não como critério de produção.

---

# PARTE 7 — ★ Mapa de alinhamento

Onde cada decisão que alinhamos aparece no código, e qual achado a motivou.

| # | decisão | achado que a motivou | onde está no componente |
|---|---|---|---|
| 1 | **Segmento declarado `[0, duration]`**, sem detecção de fronteiras | **[L]** `QMPropGener.py:96` adiciona a 1ª fronteira **incondicionalmente**, antes da checagem de `prop_max_cnt` (L98) → configuração não resolve. **[V]** E de N≥6 o `QMPropGenerator` **parte a cena** em 26%→100% dos casos | `"st": 0.0, "ed": duration` — nenhum kernel, nenhuma convolução |
| 2 | **Usar a matriz bruta**, ignorando `scores` para ranquear | **[L]** `constructpipe/base.py:111-112` aplica min-max, que **[V]** produz NaN em N=1, é degenerado em N=2, e zera **exatamente uma** legenda por vídeo | ramo C recalcula via `get_caption_frame_sims`; `scores` entra só como `pipeline_score` |
| 3 | **Chamar com TODAS as N legendas** (dedup depois) | **[L]** `sim_utils.py:87` tem `assert frame_features.shape == cap_features.shape` — chamar com as distintas **estouraria** | comentário explícito na chamada; **[V]** T12 verifica |
| 4 | **Ramificar por `n_distinct`**, não por duração | **[V]** o algoritmo é idêntico para N=2 e N=300; o que muda é a *confiabilidade*, não a *lógica* | três ramos: ausente / `n_raw==0` / `n_distinct==1` / `>=2` |
| 5 | **Agnóstico a chave `int`/`str`** | **[L]** `BlipCapGener.py:34` grava `int`; a recarga do `.jsonl` devolve `str`; `QMPropGener.py:133` indexa sempre com `str()` | `_extrair_legendas_ordenadas`; **[V]** T8 verifica |
| 6 | **Uma legenda indexada** | **[L]** `build_tree_meta:177` grava `'caps': [prop['cap']]` — **hardcoded** a um elemento. Indexar várias exigiria **modificar** esse arquivo | `"cap": ranking[0]["cap"]`; o resto vive em `ranking` |
| 7 | **Colunas, não veredito** | sem legendas de referência, eleger um critério a priori seria afirmar o que não sabemos | cinco sinais emitidos; `rank_by` configurável e **registrado** na saída |
| 8 | **Keywords de todas as legendas** | alimentam o ramo GloVe da busca; **[L]** espelha `QMPropGener.py:134-139` | `_coletar_keywords`; **[V]** T14 verifica |
| 9 | **Vídeo ausente não estoura** | **[L]** o `QMPropGenerator` faz `vid_2_cap[video_name]` direto → `KeyError` quando o captioning pulou o vídeo | `if video_name not in vid_2_cap: continue` com aviso; **[V]** T10 |
| 10 | **`pipeline_score` como coluna** | permite o Passo 1 do plano de validação (concordância entre critérios) sem experimento extra | calculado em `_calcular_sinais`, com `None` quando há NaN |

---

# PARTE 8 — Limites conhecidos

**[J]** Registro explícito, para o manual não convidar à leitura excessiva:

- **Nada foi medido com dados reais.** Os 56 testes verificam lógica contra contrato, com embeddings sintéticos.
- **Não está estabelecido que `scene_score` escolhe melhor** que `self_score`. Os critérios *diferem*; qual acerta mais exigiria referências que não existem.
- **A anisotropia não foi medida.** Com BLIP real, espere cossenos altos e próximos — o que torna as margens pequenas. A coluna de valores existe justamente para você **ver** a margem em vez de confiar num argmax cego.
- **O `prop_sims.pt` colide em nome** com o do `QMPropGenerator`, com conteúdo semanticamente diferente (§3.1).
- **Não avaliei o impacto nas métricas** de recuperação. Exigiria rodar `retrieve.py` e comparar.
- **`np.stack([])` em `viddataset.py:60`** continua sendo um risco a montante: cenas < 1 s derrubam a construção **antes** de o componente rodar. O tratamento correto é filtrar no `make_annos.py`.

---

# PARTE 9 — A ordem recomendada

**[J] Antes de rodar o pipeline inteiro, meça a distribuição.** Um script curto sobre `meta/captions/{collection}_{gen}.jsonl` responde: quantas cenas têm uma legenda distinta só? Qual a mediana?

**Se a maioria tiver 1–2 distintas, boa parte do ranqueamento é inócua** — e descobrir isso antes economiza uma rodada completa. Foi essa a razão de especificar antes de codificar.

Depois:

1. **Instalar** (§1) e rodar a suíte (§5.1) — confirma que o registro funciona no seu clone.
2. **Rodar a construção** com `proposal_generator=whole`.
3. **Abrir o `proposals.json`** e olhar ~30 cenas com as colunas lado a lado.
4. **Comparar `scene_score` × `pipeline_score`** — em quantas cenas o topo diverge? Se convergirem quase sempre, a escolha do critério é irrelevante para os seus dados.
5. **Checar o viés genérico:** se o topo por `scene_score` for sistematicamente a legenda com menor `n_words`, o efeito previsto está presente e vale considerar desempate.

---

*Manual de uso dos dois scripts. Toda afirmação carrega marca: **[L]** lida no código com arquivo e linha, **[V]** verificada por execução nesta sessão, **[J]** julgamento de engenharia. A Parte 7 é o mapa de rastreabilidade — cada decisão do componente ligada ao achado verificado que a motivou. A Parte 8 delimita o que os scripts não estabelecem: eles verificam lógica contra contrato, não qualidade de legenda com dados reais.*
