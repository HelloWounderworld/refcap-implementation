"""
WholePropGener.py — gerador de propostas para vídeos que JÁ SÃO a cena desejada.

Registrado como "whole". Emite UM segmento por vídeo cobrindo [0, duration],
sem detecção de fronteiras, e RANQUEIA as legendas geradas pelo BLIP.

Por que existe (resumo; detalhes em RefCap_Projeto_WholePropGenerator.md):
  - O QMPropGenerator detecta fronteiras. Para N<=5 legendas isso é inerte
    (sempre 1 segmento), mas de N>=6 em diante ele PARTE a cena — destrutivo
    quando cada vídeo já é o corte desejado.
  - O critério de seleção dele é argmax(capframe_scores), que é a DIAGONAL da
    matriz cruzada. A legenda i foi gerada A PARTIR do frame i, então essa
    quantidade tem viés estrutural.
  - O pipeline calcula a matriz cruzada COMPLETA e a descarta
    (constructpipe/base.py:110, `sims, _ = ...`). Este componente a recalcula.

Decisões de projeto relevantes ao ler o código:
  - Assinatura de 4 parâmetros (a REAL do QMPropGenerator), não os 3 da ABC.
  - Não usa `scores` (capframe_scores) para ranquear: ele vem min-max
    normalizado, o que produz NaN quando N==1 e zera exatamente uma legenda
    por vídeo. Usamos a matriz BRUTA. `scores` entra só como diagnóstico.
  - `get_caption_frame_sims` tem `assert frame_features.shape == cap_features.shape`,
    logo precisa ser chamada com TODAS as N legendas. A deduplicação acontece
    DEPOIS, sobre a matriz.
  - Não elege um critério vencedor: emite todos os sinais como colunas.
"""
import os
import numpy as np
import torch

from sentence_transformers import util as sim_util

from .base import BasePropGen, REGISTER_PROPGEN

import utils.sim_utils as sim_utils
import utils.basic_utils as basic_utils
import utils.tree_utils as tree_utils
import spacy


# ──────────────────────────────────────────────────────────────────────────
# Constantes locais (documentadas em vez de mágicas)
# ──────────────────────────────────────────────────────────────────────────
_RANK_CRITERIA = ("scene_score", "self_score", "consensus", "pipeline_score")
_DEFAULT_RANK_BY = "scene_score"
_LONG_SCENE_WARN_SECONDS = 30.0   # acima disso, avisa: a premissa "1 vídeo = 1 cena"
                                  # pode não valer para aquele arquivo


def _normalizar_texto(cap: str) -> str:
    """Forma canônica para comparar legendas na deduplicação.

    Minúsculas, espaços colapsados, pontuação final removida. Não altera o
    texto emitido — serve apenas como chave de agrupamento.
    """
    return " ".join(cap.lower().split()).rstrip(".!?,;: ")


def _extrair_legendas_ordenadas(frame_captions: dict) -> list:
    """Devolve as legendas em ordem temporal, agnóstico ao tipo da chave.

    As chaves de `frame_captions` são `int` na primeira execução
    (BlipCapGener.py:34 usa o `id` do enumerate) e `str` nas seguintes
    (capgenerator/base.py:33-34 recarrega do .jsonl, e JSON converte chaves
    em string). Normalizamos para int antes de ordenar.
    """
    pares = []
    for chave, meta in frame_captions.items():
        try:
            idx = int(chave)
        except (TypeError, ValueError):
            # chave inesperada: preserva a ordem de inserção como fallback
            idx = len(pares)
        pares.append((idx, meta["cap"]))
    pares.sort(key=lambda p: p[0])
    return [cap for _, cap in pares]


@REGISTER_PROPGEN(["whole"])
class WholePropGenerator(BasePropGen):
    def __init__(self, cfg, models) -> None:
        # Segue o padrão do QMPropGenerator (QMPropGener.py:20-25): atribuição
        # direta, sem super(). A ABC só define self.cfg, então super() não
        # acrescentaria nada.
        self.cfg = cfg
        self.txt_sim_model = models["sentence_transformer"]
        self.it_sim_model = models["blip_itrtv_model"]
        self.it_sim_processor = models["blip_itrtv_processor"]
        self.nlp = spacy.load("en_core_web_sm")

        # Opções sem exigir campos novos no cfg: se você adicionar
        # `whole_rank_by` / `whole_dedup` ao BuildArguments, eles passam a
        # valer; sem isso, os defaults abaixo são usados.
        self.rank_by = getattr(cfg, "whole_rank_by", _DEFAULT_RANK_BY)
        if self.rank_by not in _RANK_CRITERIA:
            raise ValueError(
                f"whole_rank_by={self.rank_by!r} inválido; use um de {_RANK_CRITERIA}"
            )
        self.dedup = bool(getattr(cfg, "whole_dedup", True))

    # ──────────────────────────────────────────────────────────────────
    # Passo 1 — deduplicação
    # ──────────────────────────────────────────────────────────────────
    def _deduplicar(self, legendas: list) -> list:
        """Agrupa legendas idênticas preservando a ordem de primeira aparição.

        Devolve uma lista de dicts:
            {'texto': str, 'frames': [int], 'linha': int}
        onde `linha` é o índice de uma ocorrência qualquer — usado para indexar
        a matriz cruzada. Legendas idênticas produzem embeddings idênticos,
        logo linhas idênticas na matriz; qualquer ocorrência serve.
        """
        if not self.dedup:
            return [{"texto": c, "frames": [i], "linha": i}
                    for i, c in enumerate(legendas)]

        vistos = {}
        ordem = []
        for i, cap in enumerate(legendas):
            chave = _normalizar_texto(cap)
            if chave not in vistos:
                vistos[chave] = {"texto": cap, "frames": [i], "linha": i}
                ordem.append(chave)
            else:
                vistos[chave]["frames"].append(i)
        return [vistos[k] for k in ordem]

    # ──────────────────────────────────────────────────────────────────
    # Passo 2 — sinais de ranqueamento
    # ──────────────────────────────────────────────────────────────────
    def _calcular_sinais(self, distintas, all_sims, txt_sims, pipeline_scores):
        """Calcula os quatro sinais para cada legenda distinta.

        all_sims  : [N, N] BRUTA (legenda i x frame j), sem min-max
        txt_sims  : [n_distinct, n_distinct] similaridade textual entre distintas
        pipeline_scores : [N] o capframe_scores do pipeline (pode conter NaN)
        """
        n_dist = len(distintas)
        registros = []

        for d, item in enumerate(distintas):
            linha = item["linha"]
            frames = item["frames"]

            # scene_score: aderência à cena INTEIRA (média sobre todos os frames)
            scene = float(all_sims[linha].mean().item())

            # self_score: aderência aos frames que GERARAM esta legenda.
            # Para n_occurrences == 1 coincide com a diagonal original.
            self_sc = float(all_sims[linha, frames].mean().item())

            # consensus: centralidade textual entre as legendas distintas.
            # Com n_distinct == 1 não há "outras": fica indefinido (None).
            if n_dist > 1:
                linha_txt = txt_sims[d]
                soma = float(linha_txt.sum().item()) - float(linha_txt[d].item())
                consenso = soma / (n_dist - 1)
            else:
                consenso = None

            # pipeline_score: o que o critério ORIGINAL diria (diagnóstico).
            # Pode ser NaN quando N==1 (min-max faz 0/0) — reportamos None nesse caso.
            ps = pipeline_scores[frames] if pipeline_scores is not None else None
            if ps is None or len(ps) == 0 or bool(np.isnan(ps).any()):
                pipeline_sc = None
            else:
                pipeline_sc = float(np.mean(ps))

            registros.append({
                "cap": item["texto"],
                "scene_score": scene,
                "self_score": self_sc,
                "consensus": consenso,
                "pipeline_score": pipeline_sc,
                "n_words": len(item["texto"].split()),
                "n_occurrences": len(frames),
                "frames": frames,
            })
        return registros

    def _ordenar(self, registros: list) -> list:
        """Ordena por `self.rank_by`, decrescente. `None` vai para o fim."""
        def chave(r):
            v = r[self.rank_by]
            return (v is None, -(v if v is not None else 0.0))
        return sorted(registros, key=chave)

    # ──────────────────────────────────────────────────────────────────
    # Passo 3 — keywords (insumo do ramo GloVe da busca)
    # ──────────────────────────────────────────────────────────────────
    def _coletar_keywords(self, legendas: list) -> list:
        """Substantivos e verbos de TODAS as legendas de TODOS os frames.

        Espelha QMPropGener.py:134-139. Coletar de todas (não só da vencedora)
        preserva a riqueza que o ramo de keywords da busca consome.
        """
        keys = []
        for cap in legendas:
            nouns, verbs = tree_utils.get_nouns_verbs(self.nlp, cap)
            keys += nouns
            keys += verbs
        return list(set(keys))

    # ──────────────────────────────────────────────────────────────────
    # O orquestrador
    # ──────────────────────────────────────────────────────────────────
    def __call__(self, vid_list, captions, scores, all_frame_features):
        # Assinatura de 4 parâmetros: a ABC declara 3 (propgenerator/base.py:28)
        # mas a implementação real e o chamador usam 4
        # (QMPropGener.py:44 e constructpipe/base.py:86).
        proposals = {}
        prop_sims = {}
        vid_2_cap = {x["vid_name"]: x for x in captions}

        for vid in vid_list:
            video_name = vid.split(".")[0]

            if video_name not in vid_2_cap:
                # Ocorre quando o captioning pulou o vídeo (ex.: decodificação
                # falhou, BlipCapGener.py:23). Avisamos em vez de estourar.
                print(f"[whole] AVISO: {video_name} sem legendas; ignorado.")
                continue

            cap_meta = vid_2_cap[video_name]
            duration = cap_meta["duration"]
            legendas = _extrair_legendas_ordenadas(cap_meta["frame_captions"])
            n_raw = len(legendas)

            # ── Ramo A: nenhuma legenda ────────────────────────────────
            # Só ocorre se o vídeo tiver menos de 1s (int(duration) == 0) e o
            # pipeline tiver chegado até aqui. Defensivo — o ideal é filtrar
            # esses vídeos na fronteira (make_annos.py).
            if n_raw == 0:
                print(f"[whole] AVISO: {video_name} sem nenhuma legenda "
                      f"(duration={duration}); proposta vazia.")
                proposals[video_name] = {
                    "proposals": [],
                    "duration": duration,
                    "n_raw": 0,
                    "n_distinct": 0,
                    "warning": "sem legendas (duracao < 1s?)",
                }
                continue

            distintas = self._deduplicar(legendas)
            n_distinct = len(distintas)
            keys = self._coletar_keywords(legendas)

            aviso = None
            if duration > _LONG_SCENE_WARN_SECONDS:
                aviso = (f"duracao {duration:.1f}s acima de "
                         f"{_LONG_SCENE_WARN_SECONDS:.0f}s: verifique se este "
                         f"video e' mesmo uma cena unica")

            # ── Ramo B: uma legenda distinta → retorno direto ──────────
            # Cobre N==1 e "todas as legendas iguais". Sem matriz, sem sinais,
            # sem argmax — e sem risco de NaN (não há normalização a fazer).
            if n_distinct == 1:
                unica = distintas[0]
                ranking = [{
                    "cap": unica["texto"],
                    "scene_score": None,
                    "self_score": None,
                    "consensus": None,
                    "pipeline_score": None,
                    "n_words": len(unica["texto"].split()),
                    "n_occurrences": len(unica["frames"]),
                    "frames": unica["frames"],
                }]
                proposals[video_name] = {
                    "proposals": [{
                        "st": 0.0,
                        "ed": duration,
                        "cap": unica["texto"],
                        "keys": keys,
                        "ranking": ranking,
                        "rank_by": self.rank_by,
                        "n_raw": n_raw,
                        "n_distinct": 1,
                    }],
                    "duration": duration,
                    "n_raw": n_raw,
                    "n_distinct": 1,
                    "warning": aviso,
                }
                continue

            # ── Ramo C: ranqueamento (idêntico para n_distinct 2 ou 300) ──
            frame_features = all_frame_features[video_name].to(self.cfg.device)

            # A matriz cruzada BRUTA. Chamada com TODAS as N legendas porque
            # get_caption_frame_sims (sim_utils.py:87) exige
            # frame_features.shape == cap_features.shape. O segundo retorno é
            # a matriz completa [N, N] que o pipeline descarta.
            with torch.no_grad():
                _, all_sims = sim_utils.get_caption_frame_sims(
                    self.it_sim_model, self.it_sim_processor,
                    frame_features, legendas, self.cfg
                )

                # Similaridade textual entre as legendas DISTINTAS, para o consenso.
                textos_distintos = [d["texto"] for d in distintas]
                emb = self.txt_sim_model.encode(textos_distintos)
                txt_sims = sim_util.cos_sim(emb, emb)

            prop_sims[video_name] = all_sims.cpu()

            ps = scores.get(video_name) if isinstance(scores, dict) else None
            pipeline_scores = ps.cpu().numpy() if ps is not None else None

            registros = self._calcular_sinais(
                distintas, all_sims, txt_sims, pipeline_scores)
            ranking = self._ordenar(registros)

            proposals[video_name] = {
                "proposals": [{
                    "st": 0.0,
                    "ed": duration,
                    "cap": ranking[0]["cap"],   # contrato de build_tree_meta:177
                    "keys": keys,               # contrato opcional, L178-179
                    # abaixo: diagnóstico. build_tree_meta ignora chaves extras,
                    # então isto sobrevive no proposals.json sem poluir tree.json.
                    "ranking": ranking,
                    "rank_by": self.rank_by,
                    "n_raw": n_raw,
                    "n_distinct": n_distinct,
                }],
                "duration": duration,
                "n_raw": n_raw,
                "n_distinct": n_distinct,
                "warning": aviso,
            }

        # Persistência, espelhando QMPropGener.py:63-64.
        if prop_sims:
            torch.save(prop_sims,
                       os.path.join(self.cfg.exp_dir, self.cfg.prop_sim_path))
        basic_utils.save_json(
            proposals,
            os.path.join(self.cfg.exp_dir, self.cfg.proposals_file),
            save_pretty=True,
        )
        return proposals
