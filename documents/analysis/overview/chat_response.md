Perfeito — esse é o passo certo: um mapa da arquitetura antes do mergulho técnico. Como você quer que isto sirva de guia para consultar enquanto navega o código, vou entregar como um documento em markdown (um artefato que você pode guardar junto do repositório), com ponteiros de arquivo/função/linha comprovando cada afirmação.

Deixa eu verificar rapidamente as convenções de formatação de documento no ambiente e confirmar alguns números de linha antes de escrever.Confirmado. Vou escrever o guia de arquitetura como um documento markdown navegável, em nível de *overview* (o esqueleto e os sinalizadores), deixando o mergulho técnico de cada função para as próximas etapas — como você pediu.Pronto. O guia está organizado em 10 seções, indo do conceitual (a ideia central, a vista de voo dos dois estágios) ao operacional (superfície de controle, artefatos em disco) e fechando com um **roteiro de leitura** (§9) e um **mapa de importância** (§10) para você priorizar o que atacar primeiro. Cada afirmação estrutural tem o ponteiro de arquivo/função/linha ao lado.

Três ideias que valem carregar como modelo mental antes do mergulho técnico:

- **Os dois estágios só se falam por um arquivo** (`tree.json`). Construção é offline e cara; recuperação é online e barata. Entender essa fronteira já resolve 80% da confusão sobre "onde as coisas acontecem".
- **O captioning é agnóstico à consulta.** O índice é construído sem saber o que será perguntado — é isso que o torna reutilizável e é o que sustenta a alegação zero-shot.
- **Um único sinal (o score ITM legenda-frame) é reaproveitado** no denoising e na segmentação. É modesto no código mas é onde o visual entra na parte textual do método — e é o maior ponto de acoplamento ao BLIP.

O roteiro em §9 sugere começar por `config/cfg.py` e pelos dois `.sh` (os botões), e o §10 aponta que os componentes §D (denoiser) e §E (segmentação) são onde provavelmente mora a contribuição do artigo — bons candidatos para o primeiro mergulho técnico. Quando você anexar o PDF, cruzo cada "candidata a novidade" marcada aqui com o texto e as ablações.
