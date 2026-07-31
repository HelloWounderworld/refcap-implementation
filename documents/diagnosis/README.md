Esse é **exatamente** o defeito que mapeamos na especificação (§6.1) — e agora ele apareceu de verdade. Deixa eu confirmar o mecanismo no código:Confirmado, e com dois agravantes: o `try/except` (linhas 39–44) protege **só** o `ffprobe` — o `np.stack` da linha 60 está **fora** dele. E o `_get_video_dim` usa a duração do **stream de vídeo**, que costuma diferir do que o player mostra.

Deixa eu verificar se você perde o trabalho já feito:Boa notícia: o cache é **por vídeo** e gravado após cada um. Nada do que já foi legendado se perde — ao reiniciar, ele pula tudo que está no `.jsonl`.

Agora, o script de diagnóstico. Vou usar exatamente o mesmo caminho que o RefCap usa, para não haver discrepância:Vou verificar a lógica do script com um mock, já que não tenho vídeos aqui:O script funciona — e note o caso `cena_curta.mp4` com **0,967 s**: é exatamente o seu cenário, um vídeo que "parece ter 1 segundo". Vou acrescentar a opção de limpar o arquivo de anotações direto:É exatamente o defeito que mapeamos na especificação (§6.1) e que ficou na lista de "o que fazer antes de rodar". Ele apareceu.

**O mecanismo:** `viddataset.py:47` faz `for i in range(int(duration))`. Com duração < 1,0 s, `int()` dá **0**, o laço não roda, `frames` fica vazio, e a linha 60 (`np.stack(frames)`) estoura. E o `try/except` das linhas 39–44 protege **só** o `ffprobe` — o `np.stack` está fora dele, então a construção inteira aborta.

**Sobre o "1 segundo" que você viu:** o RefCap lê `video_stream['duration']` — a duração do **stream de vídeo**, que costuma diferir do que o player mostra. Um clipe que aparece como 1 s tem tipicamente 0,96–0,99 s de stream. No teste do script, simulei exatamente esse caso (0,967 s) e ele é classificado como problemático.

**Você não perde o trabalho já feito.** O cache é gravado no `.jsonl` **após cada vídeo** (`BlipCapGener.py:38-40`), e recarregado no início (`base.py:32-34`). Ao reiniciar, todos os vídeos já legendados são pulados.

## O caminho

**1. Achar os culpados**
```bash
python diagnosticar_videos_curtos.py <video_root>
```

**2. Removê-los.** Duas opções, conforme preferir:

```bash
# opção A — tirar os arquivos da pasta e regerar as anotações
python diagnosticar_videos_curtos.py <video_root> --mover-para ../videos_descartados
python make_annos.py     # regenera annos sem eles

# opção B — manter os arquivos, só limpar as anotações (faz backup .bak)
python diagnosticar_videos_curtos.py <video_root> --limpar-annos annos/<collection>/<anno_file>
```

**3. Rodar de novo** — `bash scripts/construct.sh` retoma do cache.

## Por que não basta "consertar" o `viddataset.py`

Vale explicar, porque é a tentação natural: fazer o `_get_video_frames` devolver `torch.zeros(1)` quando não há frames faria o `BlipCapGener.py:23` pular o vídeo — **mas isso só move o crash**. O vídeo continuaria em `vid_list` sem entrar em `captions`, e o `compute_frame_features` estouraria com `KeyError` na linha 143. É o Defeito 2 do relatório de análise, que provei em execução.

**A correção certa é remover o vídeo de `vid_list`** — ou seja, filtrar na origem (anotações ou pasta de vídeos), que é o que o script faz.

## Um alerta extra do script

Ele separa duas categorias. Além dos **curtos** (< 1 s, que derrubam no `np.stack`), ele detecta os **ilegíveis** — vídeos sem campo `duration` no stream, ou que o `ffprobe` não lê. Esses **não** derrubam ali, mas caem no `except`, são pulados no captioning, e causam o mesmo `KeyError` três etapas depois. Trate os dois grupos juntos.