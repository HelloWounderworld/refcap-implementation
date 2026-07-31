"""Suíte pytest do `WholePropGenerator`.

RODAR (a partir da raiz do repositório):
    pytest test/ -v

Requisitos: numpy e pytest. Os stubs estão em `conftest.py` — nem torch, nem
spacy, nem sentence-transformers, nem modelos BLIP, nem vídeos.

ORGANIZAÇÃO
    TestRegistro          o componente se registra e herda corretamente
    TestContratoDeSaida   o que `build_tree_meta` lê existe e está correto
    TestRanking           os sinais e a ordenação
    TestDeduplicacao      agrupamento de legendas idênticas
    TestRamosDeExecucao   os três caminhos (n_raw==0, n_distinct==1, >=2)
    TestRobustez          entradas degeneradas não derrubam o processo
    TestIntegracao        contratos do RefCap (assert de shape, persistência)

Cada teste cita, quando aplicável, a linha do RefCap que motivou a verificação.
"""
import json

import numpy as np
import pytest

from conftest import (
    montar_captions,
    features_de_frame,
    ft,
    CHAMADAS_SIM_UTILS,
    JSON_SALVO,
)

# Cena de referência usada por vários testes: 3 legendas distintas, 3 s.
LEGENDAS_BASE = [
    "a woman standing in a kitchen",
    "a woman cooking food",
    "a close up of a knife",
]


@pytest.fixture
def cena_simples(gen):
    """Roda o gerador sobre uma cena de 3 s com 3 legendas distintas."""
    resultado = gen(
        ["cena.mp4"],
        [montar_captions("cena", LEGENDAS_BASE, 3.0)],
        {"cena": ft(np.array([0.91, 0.88, 0.93]))},
        {"cena": features_de_frame(3, seed=1)},
    )
    return resultado["cena"]


# =========================================================================== #
class TestRegistro:
    """O componente precisa ser alcançável pelo registry do RefCap."""

    def test_nome_whole_esta_registrado(self, registry):
        # Falha se faltar a linha `from . import WholePropGener` no __init__.py
        assert "whole" in registry["registry"]

    def test_getter_devolve_a_classe(self, registry):
        assert registry["get"]("whole").__name__ == "WholePropGenerator"

    def test_herda_de_base_propgen(self, registry):
        mro = registry["get"]("whole").__mro__
        assert any(base.__name__ == "BasePropGen" for base in mro[1:])

    def test_instancia_sem_erro(self, gen):
        # Se a ABC não estivesse satisfeita, a instanciação levantaria TypeError
        assert gen is not None

    def test_default_de_ordenacao(self, gen):
        assert gen.rank_by == "scene_score"
        assert gen.dedup is True

    def test_criterio_invalido_e_rejeitado(self, registry, cfg, models):
        cfg.whole_rank_by = "criterio_inexistente"
        with pytest.raises(ValueError):
            registry["get"]("whole")(cfg, models)


# =========================================================================== #
class TestContratoDeSaida:
    """O que `build_tree_meta` (constructpipe/base.py:177) lê de cada proposta."""

    def test_estrutura_por_video(self, cena_simples):
        assert "proposals" in cena_simples
        assert "duration" in cena_simples

    def test_exatamente_uma_proposta(self, cena_simples):
        # A premissa do componente: cada vídeo JÁ É a cena desejada
        assert len(cena_simples["proposals"]) == 1

    @pytest.mark.parametrize("campo", ["st", "ed", "cap"])
    def test_campos_obrigatorios(self, cena_simples, campo):
        assert campo in cena_simples["proposals"][0]

    def test_campo_keys_presente(self, cena_simples):
        # Opcional em build_tree_meta:178-179, mas alimenta o ramo GloVe
        assert "keys" in cena_simples["proposals"][0]

    def test_segmento_cobre_a_cena_inteira(self, cena_simples):
        proposta = cena_simples["proposals"][0]
        assert proposta["st"] == 0.0
        assert proposta["ed"] == cena_simples["duration"]

    def test_cap_e_o_topo_do_ranking(self, cena_simples):
        proposta = cena_simples["proposals"][0]
        assert proposta["cap"] == proposta["ranking"][0]["cap"]

    def test_saida_e_json_serializavel(self, cena_simples):
        # Nenhum NaN cru, nenhum tensor — o proposals.json precisa ser válido
        texto = json.dumps(cena_simples)
        assert "NaN" not in texto


# =========================================================================== #
class TestRanking:
    """Os cinco sinais e a ordenação."""

    SINAIS = ["scene_score", "self_score", "consensus",
              "pipeline_score", "n_words", "n_occurrences"]

    def test_uma_entrada_por_legenda_distinta(self, cena_simples):
        assert len(cena_simples["proposals"][0]["ranking"]) == 3

    @pytest.mark.parametrize("sinal", SINAIS)
    def test_sinal_presente_em_todas_as_entradas(self, cena_simples, sinal):
        assert all(sinal in item for item in cena_simples["proposals"][0]["ranking"])

    def test_ordenado_decrescente_pelo_criterio(self, cena_simples):
        proposta = cena_simples["proposals"][0]
        valores = [item[proposta["rank_by"]] for item in proposta["ranking"]]
        assert valores == sorted(valores, reverse=True)

    def test_criterio_usado_fica_registrado(self, cena_simples):
        assert cena_simples["proposals"][0]["rank_by"] == "scene_score"

    def test_scene_score_difere_de_self_score(self, cena_simples):
        # scene_score é a média da LINHA (todos os frames);
        # self_score usa só os frames de origem. Devem divergir em geral.
        ranking = cena_simples["proposals"][0]["ranking"]
        assert any(
            abs(item["scene_score"] - item["self_score"]) > 1e-9 for item in ranking
        )

    def test_ordenacao_alternativa(self, registry, cfg, models):
        cfg.whole_rank_by = "self_score"
        gerador = registry["get"]("whole")(cfg, models)
        resultado = gerador(
            ["cena.mp4"],
            [montar_captions("cena", LEGENDAS_BASE, 3.0)],
            {"cena": ft(np.array([0.91, 0.88, 0.93]))},
            {"cena": features_de_frame(3, seed=1)},
        )
        proposta = resultado["cena"]["proposals"][0]
        assert proposta["rank_by"] == "self_score"
        valores = [item["self_score"] for item in proposta["ranking"]]
        assert valores == sorted(valores, reverse=True)


# =========================================================================== #
class TestDeduplicacao:
    """Legendas idênticas devem virar uma entrada só."""

    LEGENDAS_COM_REPETICAO = [
        "a woman in a kitchen",
        "A WOMAN IN A KITCHEN.",   # difere só em caixa e pontuação
        "a woman in a kitchen",
        "a close up of a knife",
    ]

    @pytest.fixture
    def cena_com_repeticao(self, gen):
        resultado = gen(
            ["vid.mp4"],
            [montar_captions("vid", self.LEGENDAS_COM_REPETICAO, 4.0)],
            {"vid": ft(np.array([0.9, 0.8, 0.7, 0.6]))},
            {"vid": features_de_frame(4, seed=2)},
        )
        return resultado["vid"]["proposals"][0]

    def test_n_raw_conta_todas(self, cena_com_repeticao):
        assert cena_com_repeticao["n_raw"] == 4

    def test_n_distinct_agrupa_caixa_e_pontuacao(self, cena_com_repeticao):
        assert cena_com_repeticao["n_distinct"] == 2

    def test_n_occurrences_correto(self, cena_com_repeticao):
        maior = max(item["n_occurrences"] for item in cena_com_repeticao["ranking"])
        assert maior == 3

    def test_frames_batem_com_ocorrencias(self, cena_com_repeticao):
        assert all(
            len(item["frames"]) == item["n_occurrences"]
            for item in cena_com_repeticao["ranking"]
        )

    def test_dedup_desligada(self, registry, cfg, models):
        cfg.whole_dedup = False
        gerador = registry["get"]("whole")(cfg, models)
        resultado = gerador(
            ["vid.mp4"],
            [montar_captions("vid", self.LEGENDAS_COM_REPETICAO, 4.0)],
            {"vid": ft(np.array([0.9, 0.8, 0.7, 0.6]))},
            {"vid": features_de_frame(4, seed=2)},
        )
        proposta = resultado["vid"]["proposals"][0]
        assert proposta["n_distinct"] == 4


# =========================================================================== #
class TestRamosDeExecucao:
    """Os três caminhos, que ramificam pelo DADO e não pela duração."""

    def test_uma_legenda_nao_calcula_matriz(self, gen):
        """Ramo curto: evita o NaN que o min-max produz quando N==1."""
        resultado = gen(
            ["vid.mp4"],
            [montar_captions("vid", ["a dog running"], 1.5)],
            {"vid": ft(np.array([np.nan]))},   # o NaN real do pipeline
            {"vid": features_de_frame(1, seed=3)},
        )
        proposta = resultado["vid"]["proposals"][0]
        assert proposta["n_distinct"] == 1
        assert proposta["cap"] == "a dog running"
        assert len(CHAMADAS_SIM_UTILS) == 0, "não deveria ter chamado a matriz"

    def test_uma_legenda_nao_propaga_nan(self, gen):
        resultado = gen(
            ["vid.mp4"],
            [montar_captions("vid", ["a dog running"], 1.5)],
            {"vid": ft(np.array([np.nan]))},
            {"vid": features_de_frame(1, seed=3)},
        )
        item = resultado["vid"]["proposals"][0]["ranking"][0]
        assert item["scene_score"] is None
        assert item["consensus"] is None
        assert "NaN" not in json.dumps(resultado["vid"])

    def test_legendas_todas_iguais_caem_no_ramo_curto(self, gen):
        resultado = gen(
            ["vid.mp4"],
            [montar_captions("vid", ["a cat sleeping"] * 3, 3.0)],
            {"vid": ft(np.array([0.5, 0.5, 0.5]))},
            {"vid": features_de_frame(3, seed=4)},
        )
        proposta = resultado["vid"]["proposals"][0]
        assert proposta["n_raw"] == 3
        assert proposta["n_distinct"] == 1
        assert proposta["ranking"][0]["n_occurrences"] == 3
        assert len(CHAMADAS_SIM_UTILS) == 0

    @pytest.mark.parametrize("n", [2, 3, 5, 8, 12])
    def test_ranqueamento_identico_para_qualquer_tamanho(self, gen, n):
        """Não há ramo por duração: 2 ou 12 legendas seguem o mesmo caminho."""
        legendas = [f"legenda numero {i} distinta" for i in range(n)]
        resultado = gen(
            ["vid.mp4"],
            [montar_captions("vid", legendas, float(n))],
            {"vid": ft(np.linspace(0.5, 0.9, n))},
            {"vid": features_de_frame(n, seed=n)},
        )
        proposta = resultado["vid"]["proposals"][0]
        assert proposta["n_distinct"] == n
        assert len(proposta["ranking"]) == n
        # o segmento cobre a cena inteira, independentemente do tamanho
        assert proposta["st"] == 0.0
        assert proposta["ed"] == float(n)
        # e continua sendo UMA proposta só
        assert len(resultado["vid"]["proposals"]) == 1


# =========================================================================== #
class TestRobustez:
    """Entradas degeneradas não devem derrubar a construção."""

    def test_video_ausente_em_captions_nao_estoura(self, gen):
        """O QMPropGenerator levanta KeyError aqui (vid_2_cap[video_name])."""
        resultado = gen(
            ["ausente.mp4", "cena.mp4"],
            [montar_captions("cena", LEGENDAS_BASE, 3.0)],
            {"cena": ft(np.array([0.9, 0.8, 0.7]))},
            {"cena": features_de_frame(3, seed=1)},
        )
        assert "ausente" not in resultado
        assert "cena" in resultado

    def test_cena_sem_frames_nao_estoura(self, gen):
        """duration < 1.0 => int(duration) == 0 => nenhuma legenda."""
        resultado = gen(
            ["curto.mp4"],
            [{"vid_name": "curto", "duration": 0.8, "frame_captions": {}}],
            {},
            {},
        )
        assert resultado["curto"]["proposals"] == []
        assert resultado["curto"].get("warning") is not None

    def test_chaves_string_dao_o_mesmo_resultado(self, gen):
        """1ª execução grava chaves int; a recarga do .jsonl devolve str."""
        com_int = gen(
            ["a.mp4"],
            [montar_captions("a", LEGENDAS_BASE, 3.0, chaves_str=False)],
            {"a": ft(np.array([0.9, 0.8, 0.7]))},
            {"a": features_de_frame(3, seed=1)},
        )["a"]["proposals"][0]
        com_str = gen(
            ["b.mp4"],
            [montar_captions("b", LEGENDAS_BASE, 3.0, chaves_str=True)],
            {"b": ft(np.array([0.9, 0.8, 0.7]))},
            {"b": features_de_frame(3, seed=1)},
        )["b"]["proposals"][0]
        assert com_int["cap"] == com_str["cap"]
        assert com_int["n_raw"] == com_str["n_raw"]

    def test_ordem_temporal_reconstruida(self, gen):
        """Chaves fora de ordem devem ser reordenadas pelo índice."""
        frame_captions = {
            "2": {"cap": "terceira legenda"},
            "0": {"cap": "primeira legenda"},
            "1": {"cap": "segunda legenda"},
        }
        resultado = gen(
            ["vid.mp4"],
            [{"vid_name": "vid", "duration": 3.0, "frame_captions": frame_captions}],
            {"vid": ft(np.array([0.1, 0.2, 0.3]))},
            {"vid": features_de_frame(3, seed=5)},
        )
        por_legenda = {
            item["cap"]: item["frames"][0]
            for item in resultado["vid"]["proposals"][0]["ranking"]
        }
        assert por_legenda["primeira legenda"] == 0
        assert por_legenda["terceira legenda"] == 2

    def test_cena_longa_gera_aviso(self, gen):
        """Acima de 30 s, a premissa '1 vídeo = 1 cena' fica suspeita."""
        legendas = [f"momento {i} da cena" for i in range(40)]
        resultado = gen(
            ["longa.mp4"],
            [montar_captions("longa", legendas, 40.0)],
            {"longa": ft(np.linspace(0.5, 0.9, 40))},
            {"longa": features_de_frame(40, seed=9)},
        )
        assert resultado["longa"]["warning"] is not None


# =========================================================================== #
class TestIntegracao:
    """Contratos do RefCap que o componente precisa respeitar."""

    def test_assert_de_shape_e_respeitado(self, gen):
        """`sim_utils.py:87` exige frame_features.shape == cap_features.shape.

        Por isso a chamada usa TODAS as N legendas, e a deduplicação acontece
        depois, sobre a matriz. Chamar com as distintas levantaria AssertionError.
        """
        legendas = ["igual", "igual", "diferente", "outra"]
        gen(
            ["vid.mp4"],
            [montar_captions("vid", legendas, 4.0)],
            {"vid": ft(np.array([0.9, 0.8, 0.7, 0.6]))},
            {"vid": features_de_frame(4, seed=2)},
        )
        assert len(CHAMADAS_SIM_UTILS) == 1
        chamada = CHAMADAS_SIM_UTILS[0]
        assert chamada["n_legendas"] == 4, "deve usar todas, não as 3 distintas"
        assert chamada["n_legendas"] == chamada["shape_frames"][0]

    def test_proposals_json_e_gravado(self, gen, cfg, cena_simples):
        caminho = f"{cfg.exp_dir}/proposals.json"
        assert caminho in JSON_SALVO

    def test_keywords_vem_de_todas_as_legendas(self, cena_simples):
        """Não só da vencedora — o ramo GloVe da busca consome todas."""
        keys = cena_simples["proposals"][0]["keys"]
        assert isinstance(keys, list) and len(keys) > 0
        assert len(keys) == len(set(keys)), "não deve haver duplicatas"
        # 'knife' vem da 3ª legenda, que NÃO é a vencedora
        assert any("knife" in k for k in keys)

    def test_diagnostico_nao_polui_o_contrato(self, cena_simples):
        """Campos extras sobrevivem no proposals.json e são ignorados a jusante.

        `build_tree_meta` acessa apenas st/ed/cap/keys — qualquer outra chave
        passa despercebida, o que é o que permite anexar o ranking aqui.
        """
        proposta = cena_simples["proposals"][0]
        for extra in ["ranking", "rank_by", "n_raw", "n_distinct"]:
            assert extra in proposta
