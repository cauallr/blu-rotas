"""Exportações científicas sem dependências adicionais no servidor local."""
from __future__ import annotations

import csv
import io
import json


def csv_export(report: dict, dataset: str) -> str:
    result = report["results"]
    if not result:
        raise ValueError("Experimento ainda não concluído")
    if dataset == "summary":
        rows = [{"run": run["id"], "variant": run["variant_label"], "seed": run["seed"],
                 "network_version": run["network_version"], "demand_hash": run["demand_hash"],
                 **{key: value for key, value in run["summary"].items() if not isinstance(value, dict)}}
                for run in result["runs"]]
    elif dataset == "vehicles":
        rows = [{"run": run["id"], "variant": run["variant_label"], **vehicle}
                for run in result["runs"] for vehicle in run["vehicles"]]
    elif dataset == "roads":
        rows = [{"run": run["id"], "variant": run["variant_label"], "time": sample["time"], **road}
                for run in result["runs"] for sample in run["road_samples"] for road in sample["roads"]]
    else:
        raise ValueError("Conjunto CSV desconhecido")
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                             for key, value in row.items()})
    return output.getvalue()


def _escaped(value: object) -> bytes:
    value = str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return value.encode("cp1252", errors="replace")


def pdf_export(report: dict) -> bytes:
    config, result = report["config"], report["results"]
    if not result:
        raise ValueError("Experimento ainda não concluído")
    pages: list[list[bytes]] = [[]]
    y = 795

    def page():
        nonlocal y
        pages.append([])
        y = 795

    def text(value: object, *, x=48, size=10, bold=False, mono=False, gap=18):
        nonlocal y
        if y < 65:
            page()
        font = b"F3" if mono else b"F2" if bold else b"F1"
        pages[-1].append(b"0.11 0.20 0.25 rg BT /" + font + b" " + str(size).encode() + b" Tf " +
                         f"{x} {y} Td ".encode() + b"(" + _escaped(value) + b") Tj ET\n")
        y -= gap

    def wrap(value: object, width=92):
        words = str(value).split()
        line = ""
        for word in words:
            if len(line) + len(word) + 1 > width:
                text(line)
                line = word
            else:
                line = (line + " " + word).strip()
        if line:
            text(line)

    def rule():
        nonlocal y
        pages[-1].append(f"0.73 0.82 0.82 RG 48 {y} m 547 {y} l S\n".encode())
        y -= 17

    text("BLU-ROTAS 2.0 | Relatório científico", size=18, bold=True, gap=28)
    text(config["name"], size=14, bold=True, gap=24)
    rule()
    text("Pergunta científica", bold=True)
    wrap(config["question"])
    text("Hipótese", bold=True)
    wrap(config["hypothesis"])
    text("Variável independente: " + config["independent_variable"])
    text(f"Demanda: {config['vehicles']} veículos | Repetições: {config['repetitions']} | Semente: {config['seed']}")
    text(f"Duração máxima: {config['duration_s']} s | Janela de partida: {config['departure_window_s']} s")
    text(f"Versão do código: {config['code_version']} | Malha: {config['source_network_version']}")
    text(f"GPS: {config['gps_interval']} s | Modo: {config['mode']} | Clima/modelo: {config['kind']}")
    if config.get("demand_rule"):
        text("Regra de amostragem", bold=True)
        wrap(config["demand_rule"])
    if config.get("focused_trip_counts"):
        text("Viagens próximas da nova ligação por repetição: " +
             ", ".join(map(str, config["focused_trip_counts"])))
    text("Condições por variante", bold=True)
    for variant in config["variants"]:
        wrap(variant["label"] + ": " + json.dumps(variant["parameters"], ensure_ascii=False), width=85)
    rule()
    text("Resultados por variante", size=13, bold=True, gap=24)
    text("Variante                         Média (s)   Conclusão    Espera (s)", mono=True, size=9)
    for key, aggregate in result["aggregates"].items():
        text(f"{aggregate['label'][:31]:31} {str(aggregate['mean_travel_s'] or '-'):>8}    "
             f"{100 * (aggregate['mean_completion_rate'] or 0):5.1f}%       {str(aggregate['mean_waiting_s'] or '-'):>8}", size=9, mono=True)
        interval = aggregate.get("confidence_interval_95")
        if interval:
            text(f"   IC 95% da média: [{interval['lower']}, {interval['upper']}] s (n={interval['n']})", size=8, gap=14)
    y -= 6
    text("Tempo médio das viagens concluídas", bold=True)
    numeric = [item["mean_travel_s"] for item in result["aggregates"].values() if item["mean_travel_s"] is not None]
    maximum = max(numeric, default=1)
    for aggregate in result["aggregates"].values():
        if y < 100:
            page()
        width = 0 if aggregate["mean_travel_s"] is None else 290 * aggregate["mean_travel_s"] / max(maximum, 1)
        pages[-1].append(f"0.28 0.70 0.64 rg 230 {y - 2} {width:.1f} 11 re f\n".encode())
        text(f"{aggregate['label'][:27]:27}  {aggregate['mean_travel_s'] if aggregate['mean_travel_s'] is not None else 'sem conclusão'}", size=9, gap=22)
    y -= 4
    rule()
    text("Interpretação descritiva", bold=True)
    wrap(result["interpretation"])
    text("Limitações", bold=True)
    for limitation in config["limitations"]:
        wrap("- " + limitation)
    text("Espaço para análise dos estudantes:", bold=True, gap=25)
    for _ in range(3):
        rule()
    if y < 100 + 16 * len(result["runs"]):
        page()
    text("Execuções e indicadores", size=14, bold=True, gap=24)
    text("Execução             Concluídos  Pendentes  Média(s)  P95(s)  Espera(s)", mono=True, size=9)
    for run in result["runs"]:
        summary = run["summary"]
        text(f"{run['id'][:20]:20} {summary['completed']:>7}       {summary['unfinished']:>7}   "
             f"{str(summary['mean_travel_s'] or '-'):>7}  {str(summary['p95_travel_s'] or '-'):>7}   "
             f"{str(summary['mean_waiting_s'] or '-'):>7}", size=8, mono=True, gap=16)
    for number, commands in enumerate(pages, start=1):
        commands.append(b"BT /F1 8 Tf 48 28 Td (BLU-ROTAS | dados simulados, nao medicoes reais) Tj ET\n")
        commands.append(b"BT /F1 8 Tf 520 28 Td (" + str(number).encode() + b") Tj ET\n")

    objects: list[bytes] = [b"", b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
                            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
                            b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"]
    page_ids = []
    for commands in pages:
        page_id = len(objects)
        content_id = page_id + 1
        page_ids.append(page_id)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> /Contents {content_id} 0 R >>".encode())
        stream = b"".join(commands)
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream")
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = b"<< /Type /Pages /Kids [" + b" ".join(f"{item} 0 R".encode() for item in page_ids) + f"] /Count {len(page_ids)} >>".encode()
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, value in enumerate(objects[1:], start=1):
        offsets.append(len(content))
        content += f"{index} 0 obj\n".encode() + value + b"\nendobj\n"
    start = len(content)
    content += f"xref\n0 {len(objects)}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]:
        content += f"{offset:010} 00000 n \n".encode()
    content += f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF".encode()
    return bytes(content)
