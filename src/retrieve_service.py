#!/usr/bin/env python3
"""
retrieve_service.py — Serviço de busca RefCap (warm-start REPL)  [v2 — AUDITADO]
================================================================================
O QUE É
    Um serviço de busca residente: carrega os modelos e o índice UMA VEZ, e então
    fica em loop no terminal recebendo queries e devolvendo momentos de vídeo —
    até você digitar 'exit'.

    Substitui o retrieve.py (que é um AVALIADOR de benchmark) por um MOTOR DE
    BUSCA (que serve consultas de usuário). O núcleo do RefCap NÃO é modificado:
    CapTree e MixPipe são usados exatamente como estão.

PADRÃO: "warm-start REPL" (não orquestração — seria over-engineering)
    BOOTSTRAP (1x, minutos)  →  carregar modelos + CODIFICAR o índice
    LOOP (por query, ms)     →  encode(query) + matmul + topk + NMS

────────────────────────────────────────────────────────────────────────────────
CORREÇÕES DA v2 (achadas numa auditoria que EXECUTOU o caminho real)
  [C1] NÃO importa nada de `retrieve.py`.
       MOTIVO: retrieve.py:3 executa os.environ["CUDA_VISIBLE_DEVICES"]='0' NO
       TOPO DO MÓDULO. Importar dele FORÇA a GPU 0 e sobrescreve silenciosamente
       o --device. Usamos utils.temporal_nms (a fonte real do NMS) diretamente.
  [C2] Chama seed_it(seed) — o retrieve.py original faz isso (l.240); a v1 não.
  [C3] Reusa o GloVe já carregado, dentro do MixPipe.
       MOTIVO: MixPipe.__init__ (l.31) faz Vectors(cfg.glove_model) DE NOVO,
       duplicando ~1GB em RAM. Injetamos a instância já carregada.
  [C4] Valida o modelo do spaCy no bootstrap, com mensagem clara.
       MOTIVO: MixPipe.__init__ (l.30) faz spacy.load("en_core_web_sm"); sem ele,
       o serviço quebraria com um erro obscuro no meio do bootstrap.
  [C5] Removida a flag --cache_index (era código morto: salvava e nunca restaurava).
────────────────────────────────────────────────────────────────────────────────

AS 4 DECISÕES DE DESIGN (cada uma resolve um achado da análise do código)
  1. `vid_name_to_id` vem da ÁRVORE, não das queries.
     → DESARMA a armadilha: compute_tree_feature (capTree.py:108) PODA a árvore,
       mantendo só os vídeos presentes nesse mapa. Com as queries, o corpus zeraria.
  2. `QueryDataset` ad-hoc (duck typing).
     → O MixPipe só exige `vid_name_to_id` + __getitem__/__len__ (7 campos).
       Satisfazemos o contrato SEM tocar no núcleo e SEM ler o annos/.
  3. `ts`/`vid_name` dummy.
     → Inertes ao scoring: em MixPipe.py o `ts` é desempacotado (l.61) e apenas
       ECOADO na saída (l.160); o topk (l.139) nunca o vê.
  4. BLIP = None.
     → É ATRIBUÍDO (capTree.py:24) mas NUNCA INVOCADO na recuperação. Passamos
       None e economizamos GBs. (load_pretrained_models o carrega
       incondicionalmente — por isso montamos nosso próprio dict de modelos.)

LIMITAÇÃO CONHECIDA (leia antes de interpretar os resultados)
    Os scores são normalizados POR QUERY (MixPipe.py:128-129, min-max): o melhor
    resultado SEMPRE vira ~1.0, mesmo que seja péssimo. O sistema NUNCA diz "não
    encontrei nada". Julgue a relevância LENDO A LEGENDA, não pelo score.

USO
    python retrieve_service.py --collection meu_corpus --construct_name blip_window_it
================================================================================
"""

import argparse
import os
import sys
import time
from collections import defaultdict
from typing import Dict, List, Tuple

# Silencia avisos ruidosos ANTES dos imports pesados.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import warnings
warnings.filterwarnings("ignore")

import torch

# --- Núcleo do RefCap (importado, NUNCA modificado) ---------------------------
# [C1] NÃO importamos de `retrieve.py` — ele força CUDA_VISIBLE_DEVICES no import.
from pipeline.treebuilder.capTree import CapTree
from pipeline.retrievepipe import *              # registra as pipelines no registry
from pipeline.retrievepipe import get_retrievepipe_class
from utils.temporal_nms import temporal_non_maximum_suppression   # a FONTE do NMS
from utils.basic_utils import seed_it                              # [C2]


# =============================================================================
# NMS TEMPORAL
# =============================================================================
def apply_temporal_nms(
    predictions: List[List],
    nms_threshold: float = 0.5,
    max_before_nms: int = 1000,
    max_after_nms: int = 100,
    score_col_idx: int = 3,
) -> List[List]:
    """
    [C1] Equivalente ao post_processing_vcmr_nms do retrieve.py, mas construído
    sobre utils.temporal_nms — evitando importar o retrieve.py (que tem efeito
    colateral de ambiente no topo do módulo).

    O QUE FAZ: remove momentos SOBREPOSTOS do mesmo vídeo. Sem isto, o top-K se
    encheria de variações quase idênticas do mesmo trecho (ex.: [10-20s] e
    [11-21s]), desperdiçando as posições do ranking.

    COMO: agrupa por vídeo → NMS dentro de cada grupo (descarta os que se
    sobrepõem ao melhor com IoU > threshold) → reordena tudo entre os vídeos.

    Cada predição é [vid_id, st, ed, score, vid_name, caption].
    (Verificado em execução: o NMS PRESERVA os campos extras 4 e 5.)
    """
    by_video = defaultdict(list)
    for pred in predictions[:max_before_nms]:
        by_video[pred[0]].append(pred[1:])       # tudo menos o vid_id

    after_nms = []
    for vid_id, grouped in by_video.items():
        kept = temporal_non_maximum_suppression(grouped, nms_threshold=nms_threshold)
        for p in kept:
            after_nms.append([vid_id] + p)

    # Ranking final entre todos os vídeos, do melhor para o pior.
    after_nms.sort(key=lambda x: x[score_col_idx], reverse=True)
    return after_nms[:max_after_nms]


# =============================================================================
# CONFIGURAÇÃO
# =============================================================================
class ServiceConfig:
    """
    Config mínima com os campos que CapTree/MixPipe leem do `cfg`.

    Por que não reusar TestArguments: ele exige campos de AVALIAÇÃO
    (retrieve_name, anno_file, ...) que não fazem sentido num serviço de busca.
    Princípio: menor superfície possível.
    """

    def __init__(self, args: argparse.Namespace):
        # --- Índice ---
        self.collection = args.collection
        self.construct_name = args.construct_name
        self.res_dir = args.res_dir
        self.construct_dir = args.construct_dir
        self.tree_file = args.tree_file

        # --- Modelos (só os de TEXTO — o BLIP é dispensado) ---
        self.sentence_transformer = args.sentence_transformer
        self.glove_model = args.glove_model
        self.meta_dir = args.meta_dir

        # --- Parâmetros de busca (lidos dentro do MixPipe) ---
        self.retrieve_pipeline = args.retrieve_pipeline
        self.key_policy = args.key_policy
        self.retrieve_sent_ratio = args.retrieve_sent_ratio
        self.max_vcmr_props = args.max_vcmr_props
        self.max_key_cnt_per_proposal = args.max_key_cnt_per_proposal

        # --- Runtime ---
        self.device = args.device
        self.eval_query_bsz = 1     # 1 query por vez no REPL
        self.num_workers = 0        # evita overhead de subprocessos p/ 1 item

    @property
    def tree_path(self) -> str:
        """results/construct/{collection}/{construct_name}/tree.json"""
        return os.path.join(
            self.res_dir, self.construct_dir, self.collection,
            self.construct_name, self.tree_file,
        )


# =============================================================================
# O DATASET DE QUERIES (duck typing — a peça que substitui o annos/)
# =============================================================================
class QueryDataset:
    """
    Entrega as queries do USUÁRIO ao MixPipe, no lugar do DataSet4Test (que lê
    `desc` do annos/ e exige o gabarito `ts`).

    CONTRATO EXIGIDO PELO MixPipe (verificado no código):
      - atributo `vid_name_to_id`   → MixPipe.py:71, 149, 171 (os ÚNICOS usos)
      - __len__ / __getitem__       → exigidos pelo DataLoader (MixPipe.py:56)
      - __getitem__ devolve 7 campos NESTA ordem (desempacotados em MixPipe.py:61):
            (desc_name, desc_id, vid_name, vid_id, desc, ts_start, ts_end)
    """

    def __init__(self, queries: List[str], tree_meta: Dict):
        self.queries = queries
        # ⚠️ A CORREÇÃO CENTRAL: o corpus pesquisável = TODOS os vídeos da árvore.
        self.vid_name_to_id = {vid: i for i, vid in enumerate(tree_meta.keys())}

    def __len__(self) -> int:
        return len(self.queries)

    def __getitem__(self, index: int) -> Tuple:
        # vid_name/ts são DUMMY: numa busca real não sabemos onde está a resposta
        # — e ambos são inertes ao scoring (só ecoados na saída).
        return (
            f"query_{index}",      # desc_name
            index,                 # desc_id
            "__QUERY__",           # vid_name  (dummy — inerte)
            0,                     # vid_id    (dummy — inerte)
            self.queries[index],   # desc      ← A QUERY DO USUÁRIO
            0.0,                   # ts_start  (dummy — inerte)
            0.0,                   # ts_end    (dummy — inerte)
        )


# =============================================================================
# BOOTSTRAP: validação e modelos
# =============================================================================
def check_spacy_model() -> None:
    """
    [C4] O MixPipe.__init__ (l.30) faz spacy.load("en_core_web_sm").
    Validamos ANTES do bootstrap pesado, para falhar cedo e com mensagem útil.
    """
    try:
        import spacy
        spacy.load("en_core_web_sm")
    except Exception:
        raise RuntimeError(
            "Modelo do spaCy ausente (exigido pelo MixPipe). Instale com:\n"
            "    python -m spacy download en_core_web_sm"
        )


def load_text_models(cfg: ServiceConfig) -> Dict:
    """
    Carrega APENAS os modelos usados na recuperação.

    Por que não usar `load_pretrained_models` do repo: ele carrega o BLIP
    INCONDICIONALMENTE (model_utils.py:30), mesmo no stage 'retrieve' — e o BLIP
    nunca é invocado aqui (só atribuído em capTree.py:24-25). Carregá-lo
    desperdiçaria GBs de VRAM.

    As chaves 'blip_itrtv_*' PRECISAM existir (CapTree.__init__ as acessa por
    índice), mas podem ser None — nunca são chamadas.
    """
    from sentence_transformers import SentenceTransformer
    from torchtext.vocab import Vectors

    print("  → sentence-transformer (codifica legendas E queries)...", flush=True)
    sentence_transformer = SentenceTransformer(cfg.sentence_transformer).to(cfg.device)

    print("  → GloVe (lookup de vetores de palavras)...", flush=True)
    glove_model = Vectors(name=cfg.glove_model, cache=cfg.meta_dir)

    return {
        "sentence_transformer": sentence_transformer,
        "glove_model": glove_model,
        # Exigidos pelo CapTree.__init__, mas NUNCA invocados:
        "blip_itrtv_model": None,
        "blip_itrtv_processor": None,
        "cap_gen_model": None,
        "cap_gen_processor": None,
    }


# =============================================================================
# O SERVIÇO DE BUSCA
# =============================================================================
class SearchService:
    """
    Encapsula o estado warm (modelos + índice codificado) e expõe `search()`.

      __init__  → BOOTSTRAP (caro, uma vez)
      search()  → POR QUERY (barato). É o NÚCLEO REUTILIZÁVEL: embrulhe-o numa
                  API HTTP depois, sem retrabalho.
    """

    def __init__(self, cfg: ServiceConfig):
        self.cfg = cfg
        t0 = time.time()

        # [C4] Falha cedo se o spaCy não estiver pronto.
        check_spacy_model()

        # --- 1. Modelos ------------------------------------------------------
        print("[1/4] Carregando modelos de texto...", flush=True)
        self.models = load_text_models(cfg)

        # --- 2. Índice (tree.json) -------------------------------------------
        print(f"[2/4] Carregando índice: {cfg.tree_path}", flush=True)
        if not os.path.exists(cfg.tree_path):
            raise FileNotFoundError(
                f"tree.json não encontrada: {cfg.tree_path}\n"
                f"Rode a construção antes (construct.py), e confira "
                f"--collection / --construct_name."
            )
        self.captree = CapTree(cfg, cfg.tree_path, self.models)

        # Captura a lista COMPLETA de vídeos ANTES da poda.
        # (compute_tree_feature SUBSTITUI self.captree.tree_meta pela versão
        #  podada — capTree.py:110 — então precisamos capturar isto agora.)
        self.all_video_names = list(self.captree.tree_meta.keys())
        print(f"      {len(self.all_video_names)} vídeo(s) no índice.", flush=True)

        # --- 3. Codificação do índice (o forward pass CARO) ------------------
        print("[3/4] Codificando o índice (forward pass do sentence-transformer)...", flush=True)
        # ⚠️ CRÍTICO: passamos TODOS os vídeos da árvore. É isto que impede a
        # poda do corpus (a armadilha de capTree.py:108).
        self.captree.compute_tree_feature(resume_video_names=self.all_video_names)

        # --- 4. Pipeline de busca (MixPipe — INTOCADO) -----------------------
        print(f"[4/4] Instanciando pipeline '{cfg.retrieve_pipeline}'...", flush=True)
        pipe_cls = get_retrievepipe_class(cfg.retrieve_pipeline)
        self.pipeline = pipe_cls(cfg=cfg, captree=self.captree, models=self.models)

        # [C3] MixPipe/KeyPipe recarregam o GloVe no __init__ (l.31), duplicando
        # ~1GB em RAM. Substituímos pela instância já carregada.
        if hasattr(self.pipeline, "vecs"):
            self.pipeline.vecs = self.models["glove_model"]

        print(
            f"\n✓ Serviço pronto em {time.time() - t0:.1f}s "
            f"({self.captree.cap_cnt} eventos indexados).\n",
            flush=True,
        )

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """
        ★ O NÚCLEO REUTILIZÁVEL ★
        Recebe uma query em texto, devolve os momentos mais relevantes.

        Fluxo (tudo dentro do MixPipe, que NÃO tocamos):
          query → encode_caps (forward pass, MixPipe.py:68)
                → cos_sim contra TODOS os eventos (l.69)
                → keywords (spaCy) + GloVe (l.79-82)
                → Max_Mean (l.101-104)
                → fusão α·sent + (1-α)·key (l.130)
                → topk (l.139)
          depois → NMS temporal (remove sobreposições)

        Returns: [{vid_name, start, end, score, caption}, ...]
        """
        # 1. Empacota a query no contrato que o MixPipe espera (sem annos/).
        dataset = QueryDataset([query], self.captree.tree_meta)

        # 2. A BUSCA (núcleo intocado). no_grad: é inferência, não treino.
        with torch.no_grad():
            _vr_indices, vcmr_res_dict = self.pipeline.retrieval(dataset)

        # 3. NMS temporal. Predição: [vid_id, st, ed, score, vid_name, caption]
        raw_preds = vcmr_res_dict["VCMR"][0]["predictions"]
        nmsed = apply_temporal_nms(raw_preds, nms_threshold=0.5)

        # 4. Formata a saída.
        return [
            {
                "vid_name": p[4],
                "start": float(p[1]),
                "end": float(p[2]),
                "score": float(p[3]),
                "caption": p[5],
            }
            for p in nmsed[:top_k]
        ]


# =============================================================================
# APRESENTAÇÃO (CLI)
# =============================================================================
def format_results(results: List[Dict], elapsed: float) -> str:
    """Formata os resultados para o terminal."""
    if not results:
        return "  (nenhum resultado)"

    lines = [f"\n  {len(results)} momento(s) em {elapsed * 1000:.0f}ms:\n"]
    for i, r in enumerate(results, 1):
        lines.append(
            f"  {i:2d}. [{r['start']:6.1f}s → {r['end']:6.1f}s]  "
            f"score={r['score']:.3f}  {r['vid_name']}"
        )
        # A LEGENDA é o instrumento de julgamento: explica POR QUE este momento
        # foi retornado (a explicabilidade do RefCap). O SCORE é enganoso.
        lines.append(f'      └─ "{r["caption"]}"')
    return "\n".join(lines)


def run_repl(service: SearchService, top_k: int) -> None:
    """
    O LOOP: lê queries do terminal até 'exit'.
    Cada iteração é BARATA — todo o custo (modelos + índice) já foi pago no
    bootstrap e permanece residente em memória.
    """
    print("=" * 70)
    print("  RefCap — Serviço de Busca")
    print("  Digite sua query (ex.: 'a person opens a door')")
    print("  Comandos: 'exit' / 'quit' para sair | Ctrl-D também funciona")
    print("=" * 70)
    print("\n  ⚠️  Os scores são normalizados por query: o melhor resultado sempre")
    print("      fica perto de 1.0, MESMO que seja irrelevante. Julgue pela LEGENDA.\n")

    while True:
        try:
            query = input("🔎 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nEncerrando.")
            break

        if not query:
            continue
        if query.lower() in {"exit", "quit", "sair"}:
            print("Encerrando.")
            break

        try:
            t0 = time.time()
            results = service.search(query, top_k=top_k)
            print(format_results(results, time.time() - t0))
            print()
        except Exception as e:
            # Um erro numa query NÃO derruba o serviço (o estado warm é caro).
            print(f"  ✗ Erro ao buscar: {e}\n", file=sys.stderr)


# =============================================================================
# ENTRY POINT
# =============================================================================
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Serviço de busca RefCap (warm-start REPL).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # --- Índice ---
    p.add_argument("--collection", required=True,
                   help="Nome da collection (o mesmo usado na construção).")
    p.add_argument("--construct_name", required=True,
                   help="Nome do experimento de construção (ex.: blip_window_it).")
    p.add_argument("--res_dir", default="results")
    p.add_argument("--construct_dir", default="construct")
    p.add_argument("--tree_file", default="tree.json")

    # --- Modelos (só os de texto) ---
    p.add_argument("--sentence_transformer", default="paraphrase-distilroberta-v2")
    p.add_argument("--glove_model", default="meta/glove.6B/glove.6B.300d.txt")
    p.add_argument("--meta_dir", default="meta")

    # --- Busca ---
    p.add_argument("--retrieve_pipeline", default="mix", choices=["mix", "sent", "key"])
    p.add_argument("--key_policy", default="max_mean", choices=["max_mean", "max_max"])
    p.add_argument("--retrieve_sent_ratio", type=float, default=0.5,
                   help="α: peso da similaridade de sentença (1-α = palavras).")
    p.add_argument("--max_vcmr_props", type=int, default=1000)
    p.add_argument("--max_key_cnt_per_proposal", type=int, default=50)

    # --- Runtime ---
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    p.add_argument("--top_k", type=int, default=10, help="Resultados a exibir.")
    p.add_argument("--seed", type=int, default=42)      # [C2]
    return p.parse_args()


def main() -> None:
    args = parse_args()
    seed_it(args.seed)                                   # [C2] reprodutibilidade
    cfg = ServiceConfig(args)

    print(f"\nIniciando serviço (device={cfg.device})...\n")
    try:
        service = SearchService(cfg)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"\n✗ {e}\n", file=sys.stderr)
        sys.exit(1)

    run_repl(service, top_k=args.top_k)


if __name__ == "__main__":
    main()
