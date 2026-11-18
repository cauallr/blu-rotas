"""Gráficos vetoriais derivados exclusivamente das execuções SUMO salvas."""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.engine import Simulator  # noqa: E402
from backend.storage import Storage  # noqa: E402

OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT.parent / "estudo-rotas-coletivas"
SUMMARY = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
RUNS = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((OUT / "runs").glob("*.json"))
       if path.name.count("__") == 2]
COLORS = {"principal": "#2166ac", "um_desvio": "#7b61a8", "todos_desvio": "#d1495b",
          "dividido": "#d18b20", "gps_dinamico": "#238f71",
          "um_quarto": "#8d67bd", "tres_quartos": "#c35f88"}
LEVELS = ["baixo", "medio", "alto"]
STRATEGIES = [strategy for strategy in SUMMARY["design"]["strategies"]
              if any(row["strategy"] == strategy for row in SUMMARY["aggregates"])]
CORRIDOR_NAME = SUMMARY["route"]["primary_streets"][0]


def svg_start(width: int, height: int, title: str) -> list[str]:
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<style>text{font-family:Arial,sans-serif;fill:#203239}.title{font-size:23px;font-weight:700}.subtitle{font-size:13px;fill:#586d72}.axis{font-size:12px;fill:#53666b}.legend{font-size:13px}</style>',
            f'<rect width="{width}" height="{height}" fill="#fff"/>',
            f'<text x="58" y="39" class="title">{escape(title)}</text>']


def line_chart(metric: str, filename: str, title: str, unit: str, low_zero: bool = True) -> None:
    rows = SUMMARY["aggregates"]
    width, height = 1160, 610
    parts = svg_start(width, height, title)
    parts.append(f'<text x="58" y="63" class="subtitle">Média de sementes pareadas; demanda sintética no corredor {escape(CORRIDOR_NAME)}</text>')
    left, right, top, bottom = 88, 875, 105, 500
    values = [row[metric] for row in rows if row[metric] is not None]
    lo = 0 if low_zero else math.floor(min(values) / 20) * 20
    hi = math.ceil(max(values) * 1.10 / 20) * 20
    if hi <= lo: hi = lo + 20
    fy = lambda value: bottom - (value - lo) / (hi - lo) * (bottom - top)
    fx = lambda count: left + (count - 30) / 150 * (right - left)
    for i in range(6):
        value = lo + (hi - lo) * i / 5
        y = fy(value)
        parts.append(f'<line x1="{left}" x2="{right}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e5ebec"/>')
        parts.append(f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" class="axis">{value:.0f}</text>')
    for count in (30,90,180):
        x = fx(count)
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{bottom}" stroke="#edf1f1"/>')
        parts.append(f'<text x="{x:.1f}" y="{bottom+24}" text-anchor="middle" class="axis">{count}</text>')
    parts.append(f'<text x="{(left+right)/2:.1f}" y="{bottom+54}" text-anchor="middle" class="axis">Veículos no mesmo intervalo de 240 s</text>')
    parts.append(f'<text transform="translate(25 {(top+bottom)/2}) rotate(-90)" text-anchor="middle" class="axis">{escape(unit)}</text>')
    for index, strategy in enumerate(STRATEGIES):
        points = [(fx(row["vehicles"]), fy(row[metric])) for row in rows
                  if row["strategy"] == strategy and row[metric] is not None]
        if not points: continue
        color = COLORS[strategy]
        parts.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="3"/>')
        for x,y in points:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}" stroke="white" stroke-width="1.5"/>')
        yy = 145 + index * 54
        parts.append(f'<line x1="{908}" x2="{939}" y1="{yy}" y2="{yy}" stroke="{color}" stroke-width="4"/>')
        parts.append(f'<text x="948" y="{yy+4}" class="legend">{escape(SUMMARY["design"]["strategies"][strategy])}</text>')
    parts.append('<text x="58" y="585" class="subtitle">Tempos calculados apenas para viagens concluídas; veja também a taxa de conclusão no relatório.</text>')
    parts.append('</svg>')
    (OUT / filename).write_text("\n".join(parts), encoding="utf-8")


def heat_color(ratio: float | None) -> str:
    if ratio is None: return "#aab9bd"
    ratio = max(0, min(1, ratio))
    stops = ((0.0,(209,57,73)), (.45,(238,163,61)), (1.0,(47,158,100)))
    for (a,ca),(b,cb) in zip(stops, stops[1:]):
        if ratio <= b:
            p = (ratio-a)/(b-a)
            return '#'+''.join(f'{round(x+(y-x)*p):02x}' for x,y in zip(ca,cb))
    return "#2f9e64"


def heatmaps() -> None:
    sim = Simulator(str(ROOT / "data"), Storage(":memory:"))
    try:
        route = SUMMARY["route"]
        edges = set(route["primary"]["route"]) | set(route["alternative"]["route"])
        geometries = {edge: [sim.net.convertXY2LonLat(x,y) for x,y in sim.edges[edge].getShape()]
                      for edge in edges}
        all_points = [point for shape in geometries.values() for point in shape]
        xmin, xmax = min(p[0] for p in all_points), max(p[0] for p in all_points)
        ymin, ymax = min(p[1] for p in all_points), max(p[1] for p in all_points)
        xpad, ypad = (xmax-xmin)*.14, (ymax-ymin)*.14
        xmin -= xpad; xmax += xpad; ymin -= ypad; ymax += ypad
        width, height = 1550, 1050
        parts = svg_start(width, height, "Velocidade observada nas vias · fluxo alto (180 veículos)")
        parts.append('<text x="58" y="62" class="subtitle">Razão entre velocidade média observada e limite da via; média ponderada por observações de veículos nas sementes executadas</text>')
        cols = [(30,110),(535,110),(1040,110),(280,565),(785,565)]
        roads_geo = json.loads((ROOT / "data" / "roads.geojson").read_text(encoding="utf-8"))
        for (strategy, (left,top)) in zip(STRATEGIES, cols):
            panel_w, panel_h = 480, 420
            parts.append(f'<rect x="{left}" y="{top}" width="{panel_w}" height="{panel_h}" rx="12" fill="#f5f8f8" stroke="#d9e3e5"/>')
            parts.append(f'<text x="{left+18}" y="{top+30}" style="font-size:16px;font-weight:700">{escape(SUMMARY["design"]["strategies"][strategy])}</text>')
            x0,y0,x1,y1 = left+24,top+54,left+panel_w-24,top+panel_h-25
            scale = min((x1-x0)/(xmax-xmin), (y1-y0)/(ymax-ymin))
            centerx, centery = (xmin+xmax)/2,(ymin+ymax)/2
            px = lambda point: (x0+x1)/2 + (point[0]-centerx)*scale
            py = lambda point: (y0+y1)/2 - (point[1]-centery)*scale
            def poly(shape):
                return ' '.join(f'{px(p):.1f},{py(p):.1f}' for p in shape)
            for feature in roads_geo["features"]:
                shape = feature["geometry"]["coordinates"]
                if feature["geometry"]["type"] != "LineString" or not any(xmin <= p[0] <= xmax and ymin <= p[1] <= ymax for p in shape):
                    continue
                parts.append(f'<polyline points="{poly(shape)}" fill="none" stroke="#dbe3e5" stroke-width="1.2" stroke-linecap="round"/>')
            selected = [run for run in RUNS if run["level"] == "alto" and run["strategy"] == strategy]
            for edge, shape in geometries.items():
                observations = [(run["roads"][edge]["mean_speed_kmh"], run["roads"][edge]["vehicle_observations"])
                                for run in selected if edge in run["roads"] and run["roads"][edge]["mean_speed_kmh"] is not None]
                weight = sum(n for _,n in observations)
                speed = sum(v*n for v,n in observations)/weight if weight else None
                ratio = speed/(sim.edges[edge].getSpeed()*3.6) if speed is not None else None
                parts.append(f'<polyline points="{poly(shape)}" fill="none" stroke="{heat_color(ratio)}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>')
            parts.append(f'<text x="{left+18}" y="{top+panel_h-10}" class="subtitle">Vermelho = lento; verde = próximo ao limite; cinza = sem carros</text>')
        for i,(ratio,label) in enumerate(((0,"0%"),(.25,"25%"),(.5,"50%"),(.75,"75%"),(1,"100%"))):
            x = 490+i*95
            parts.append(f'<rect x="{x}" y="{1007}" width="70" height="15" fill="{heat_color(ratio)}"/>')
            parts.append(f'<text x="{x+35}" y="{1041}" text-anchor="middle" class="axis">{label}</text>')
        parts.append('</svg>')
        (OUT / "mapas-calor-fluxo-alto.svg").write_text("\n".join(parts), encoding="utf-8")
    finally:
        sim.storage.db.close()


def occupancy() -> None:
    width,height = 1250,920
    parts = svg_start(width,height,"Veículos nas duas rotas ao longo do tempo · fluxo alto")
    parts.append('<text x="58" y="63" class="subtitle">Média das sementes executadas; a área compartilhada e a fila de inserção são mostradas separadamente nos dados CSV</text>')
    keys = ["principal","todos_desvio","dividido"]
    for panel,strategy in enumerate(keys):
        left,right = 85,1170
        top,bottom = 110+panel*265,310+panel*265
        selected = [run for run in RUNS if run["level"] == "alto" and run["strategy"] == strategy]
        series = defaultdict(lambda: defaultdict(list))
        for run in selected:
            for sample in run["route_occupancy"]:
                for key in ("on_primary_only","on_alternative_only","on_shared"):
                    series[sample["time_s"]][key].append(sample[key])
        times=sorted(series)
        max_t=max(times,default=1)
        max_y=max((statistics.mean(v) for t in times for v in series[t].values()),default=1)*1.15
        fx=lambda t:left+t/max_t*(right-left)
        fy=lambda v:bottom-v/max_y*(bottom-top)
        parts.append(f'<text x="{left}" y="{top-17}" style="font-size:16px;font-weight:700">{escape(SUMMARY["design"]["strategies"][strategy])}</text>')
        for i in range(4):
            y=top+i*(bottom-top)/3
            parts.append(f'<line x1="{left}" x2="{right}" y1="{y}" y2="{y}" stroke="#e5ebec"/>')
        for metric,color,label in (("on_primary_only","#2166ac",CORRIDOR_NAME),
                                   ("on_alternative_only","#d1495b","Alternativa"),
                                   ("on_shared","#777f86","Trechos compartilhados")):
            points=' '.join(f'{fx(t):.1f},{fy(statistics.mean(series[t][metric])):.1f}' for t in times if series[t][metric])
            parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        parts.append(f'<text x="{left}" y="{bottom+23}" class="axis">0 s</text>')
        parts.append(f'<text x="{right}" y="{bottom+23}" text-anchor="end" class="axis">{max_t:.0f} s</text>')
    for i,(color,label) in enumerate((("#2166ac",CORRIDOR_NAME),("#d1495b","Alternativa"),("#777f86","Trechos compartilhados"))):
        x=160+i*350
        parts.append(f'<line x1="{x}" x2="{x+28}" y1="{898}" y2="{898}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text x="{x+36}" y="{903}" class="legend">{label}</text>')
    parts.append('</svg>')
    (OUT / "ocupacao-rotas-fluxo-alto.svg").write_text("\n".join(parts),encoding="utf-8")


line_chart("mean_travel_s", "tempo-medio-demanda.svg", "Tempo médio de viagem × demanda", "Segundos após entrar na via")
line_chart("mean_door_to_door_s", "tempo-total-demanda.svg", "Tempo total desde a partida planejada × demanda", "Segundos, incluindo espera para entrar")
line_chart("mean_time_loss_s", "tempo-perdido-demanda.svg", "Tempo perdido no SUMO × demanda", "Segundos abaixo da velocidade ideal")
heatmaps()
occupancy()
