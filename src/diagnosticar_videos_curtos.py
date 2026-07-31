#!/usr/bin/env python3
"""
diagnosticar_videos_curtos.py — encontra os vídeos que derrubam a construção.

O PROBLEMA
----------
`dataset/viddataset.py:47` faz:

    for i in range(int(duration)):

Se a duração for menor que 1.0 s, `int(duration)` é 0, o laço nunca roda,
`frames` fica vazio, e a linha 60:

    video = np.stack(frames, axis=0)

levanta `ValueError: need at least one array to stack`.

⚠️ E essa linha está FORA do try/except (que protege só o ffprobe, L39-44),
então a construção inteira aborta.

⚠️ ATENÇÃO À DURAÇÃO CERTA
O RefCap lê `video_stream['duration']` — a duração do STREAM DE VÍDEO, que
frequentemente difere do que o player mostra e da duração do CONTÊINER.
Um vídeo que "parece ter 1 segundo" pode ter stream de 0,96 s.
Este script lê exatamente o mesmo campo, pelo mesmo caminho.

USO
    python diagnosticar_videos_curtos.py <pasta_de_videos>
    python diagnosticar_videos_curtos.py <pasta_de_videos> --mover-para <pasta>

SAÍDA
    Lista os vídeos problemáticos e imprime os nomes-base, prontos para você
    remover do arquivo de anotações.
"""
import argparse
import json
import os
import pathlib
import sys

try:
    import ffmpeg
except ImportError:
    sys.exit(
        "ERRO: o pacote `ffmpeg-python` não está disponível.\n"
        "Rode este script no mesmo ambiente em que o RefCap roda."
    )

# O RefCap gera 1 frame por segundo inteiro; abaixo de 1.0 s dá zero frames.
DURACAO_MINIMA = 1.0

EXTENSOES = {".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v", ".mpg", ".mpeg"}


def duracao_do_stream(caminho):
    """Lê a duração EXATAMENTE como `viddataset._get_video_dim` faz.

    Devolve (duracao, problema). `problema` é None quando deu tudo certo.
    """
    try:
        probe = ffmpeg.probe(str(caminho))
    except Exception as exc:
        return None, f"ffprobe falhou: {exc}"

    stream = next(
        (s for s in probe.get("streams", []) if s.get("codec_type") == "video"), None
    )
    if stream is None:
        return None, "nenhum stream de vídeo no arquivo"

    if "duration" not in stream:
        # Alguns contêineres (ex.: certos .mkv) só trazem duração no formato.
        # O RefCap levantaria KeyError aqui -> cairia no except -> torch.zeros(1)
        # -> o vídeo seria PULADO no captioning, e depois daria KeyError em
        # compute_frame_features (constructpipe/base.py:143).
        dur_formato = probe.get("format", {}).get("duration")
        extra = f" (formato diz {float(dur_formato):.3f}s)" if dur_formato else ""
        return None, f"stream sem campo 'duration'{extra}"

    try:
        return float(stream["duration"]), None
    except (TypeError, ValueError):
        return None, f"duração ilegível: {stream['duration']!r}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta", help="pasta com os vídeos (o video_root do construct.sh)")
    ap.add_argument("--mover-para", metavar="DESTINO",
                    help="move os vídeos problemáticos para esta pasta")
    ap.add_argument("--limpar-annos", metavar="ARQUIVO_JSONL",
                    help="reescreve o .jsonl de anotações sem os vídeos problemáticos "
                         "(faz backup .bak antes)")
    ap.add_argument("--json", metavar="ARQUIVO",
                    help="grava o relatório completo em JSON")
    args = ap.parse_args()

    pasta = pathlib.Path(args.pasta)
    if not pasta.is_dir():
        sys.exit(f"ERRO: {pasta} não é uma pasta.")

    arquivos = sorted(
        p for p in pasta.iterdir()
        if p.is_file() and p.suffix.lower() in EXTENSOES
    )
    if not arquivos:
        sys.exit(f"Nenhum vídeo encontrado em {pasta}.")

    ok, curtos, ilegiveis = [], [], []

    print(f"Analisando {len(arquivos)} arquivo(s) em {pasta} ...\n")
    for caminho in arquivos:
        dur, problema = duracao_do_stream(caminho)
        registro = {"arquivo": caminho.name, "nome_base": caminho.stem}

        if problema is not None:
            registro["problema"] = problema
            ilegiveis.append(registro)
            continue

        registro["duracao_stream"] = round(dur, 3)
        registro["frames_gerados"] = int(dur)

        if int(dur) < 1:
            curtos.append(registro)
        else:
            ok.append(registro)

    # ---------------- relatório ----------------
    largura = 74
    print("=" * largura)
    print(f" RESUMO — limite: duração do stream >= {DURACAO_MINIMA} s")
    print("=" * largura)
    print(f"  OK (>= 1 frame)        : {len(ok)}")
    print(f"  CURTOS (0 frames)      : {len(curtos)}   <- estes DERRUBAM a construção")
    print(f"  ILEGÍVEIS              : {len(ilegiveis)}")

    if curtos:
        print("\n" + "=" * largura)
        print(" VÍDEOS CURTOS (duração do stream < 1.0 s)")
        print("=" * largura)
        for r in curtos:
            print(f"  {r['duracao_stream']:>7.3f}s  ->  {r['arquivo']}")
        print("\n  Nomes-base para remover do arquivo de anotações:")
        for r in curtos:
            print(f"    {r['nome_base']}")

    if ilegiveis:
        print("\n" + "=" * largura)
        print(" VÍDEOS ILEGÍVEIS (o ffprobe não deu a duração do stream)")
        print("=" * largura)
        for r in ilegiveis:
            print(f"  {r['arquivo']}")
            print(f"      {r['problema']}")
        print("\n  ⚠️ Estes NÃO derrubam no np.stack, mas caem no except do")
        print("     viddataset (torch.zeros(1)), são pulados no captioning, e")
        print("     depois causam KeyError em constructpipe/base.py:143.")
        print("     Trate-os junto com os curtos.")

    # ---------------- ações ----------------
    problematicos = curtos + ilegiveis

    if args.mover_para and problematicos:
        destino = pathlib.Path(args.mover_para)
        destino.mkdir(parents=True, exist_ok=True)
        print("\n" + "=" * largura)
        print(f" MOVENDO {len(problematicos)} arquivo(s) para {destino}")
        print("=" * largura)
        for r in problematicos:
            origem = pasta / r["arquivo"]
            origem.rename(destino / r["arquivo"])
            print(f"  movido: {r['arquivo']}")

    if args.limpar_annos and problematicos:
        anno_path = pathlib.Path(args.limpar_annos)
        if not anno_path.is_file():
            print(f"\n  AVISO: {anno_path} não existe — nada a limpar.")
        else:
            remover = {r["nome_base"] for r in problematicos}
            linhas = anno_path.read_text(encoding="utf-8").splitlines()
            mantidas, descartadas = [], 0
            for linha in linhas:
                if not linha.strip():
                    continue
                try:
                    dado = json.loads(linha)
                except json.JSONDecodeError:
                    mantidas.append(linha)      # não mexe no que não entende
                    continue
                if dado.get("vid_name") in remover:
                    descartadas += 1
                else:
                    mantidas.append(linha)

            backup = anno_path.with_suffix(anno_path.suffix + ".bak")
            backup.write_text("\n".join(linhas) + "\n", encoding="utf-8")
            anno_path.write_text("\n".join(mantidas) + "\n", encoding="utf-8")

            print("\n" + "=" * largura)
            print(" ANOTAÇÕES LIMPAS")
            print("=" * largura)
            print(f"  arquivo   : {anno_path}")
            print(f"  backup    : {backup}")
            print(f"  removidas : {descartadas} linha(s)")
            print(f"  mantidas  : {len(mantidas)} linha(s)")

    if args.json:
        relatorio = {
            "pasta": str(pasta),
            "duracao_minima": DURACAO_MINIMA,
            "ok": ok,
            "curtos": curtos,
            "ilegiveis": ilegiveis,
        }
        pathlib.Path(args.json).write_text(
            json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nRelatório gravado em {args.json}")

    if not problematicos:
        print("\n  ✓ Nenhum vídeo problemático. O erro deve ter outra causa.")

    return 1 if problematicos else 0


if __name__ == "__main__":
    sys.exit(main())
