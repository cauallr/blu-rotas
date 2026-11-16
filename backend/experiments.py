"""Experimentos controlados em processos SUMO isolados."""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4

from .engine import Simulator, WEATHER
from .storage import Storage


PRESETS = {
    "gps": ("GPS estático versus dinâmico", "Atualizar rotas reduz o tempo médio?", "O GPS dinâmico pode reduzir atrasos.", "estratégia de GPS"),
    "signals": ("Configuração semafórica", "Como a duração do verde altera filas?", "Verde maior pode reduzir filas na via principal e aumentar espera transversal.", "duração de fase"),
    "saturation": ("Saturação da rede", "Como a demanda afeta a circulação?", "Atrasos podem crescer de modo não linear.", "número de veículos"),
    "roadworks": ("Obras e interdições", "Qual o impacto de uma via bloqueada?", "O tráfego pode migrar para rotas alternativas.", "intervenção viária"),
    "new_road": ("Nova estrada", "Uma nova conexão sempre reduz o tempo total?", "A conexão pode alterar a distribuição de rotas sem melhorar todas as viagens.", "versão da rede"),
    "weather": ("Clima simulado", "Como a condução muda com o clima?", "Chuva intensa pode aumentar o tempo de viagem no modelo.", "condição climática"),
    "custom": ("Experimento personalizado", "Qual o efeito da variável escolhida?", "Os resultados testarão a hipótese informada.", "parâmetros do cenário"),
}


def deterministic_demand(sim: Simulator, seed: int, count: int, window: float,
                         trip_budget_s: float | None = None) -> list[dict]:
    rng = random.Random(seed)
    candidates = [edge_id for edge_id, edge in sim.edges.items() if edge.getLength() >= 35]
    if len(candidates) < 2:
        raise ValueError("A rede não tem vias suficientes")
    trips = []
    fallback = []
    attempts = 0
    while len(trips) < count and attempts < count * 40:
        attempts += 1
        origin, destination = rng.sample(candidates, 2)
        path = sim.route(origin, destination)
        if not 4 <= len(path) <= 100:
            continue
        free_flow_s = sum(sim.edges[edge_id].getLength() / max(1, sim.edges[edge_id].getSpeed())
                          for edge_id in path)
        a = sim.edges[origin].getShape()[len(sim.edges[origin].getShape()) // 2]
        b = sim.edges[destination].getShape()[len(sim.edges[destination].getShape()) // 2]
        trip = {"origin_coordinates": list(sim.net.convertXY2LonLat(*a)),
                      "destination_coordinates": list(sim.net.convertXY2LonLat(*b)),
                      "origin_edge": origin, "destination_edge": destination,
                      "departed": round(rng.random() * window, 2)}
        if trip_budget_s is not None and free_flow_s > trip_budget_s:
            fallback.append((free_flow_s, attempts, trip))
        else:
            trips.append(trip)
    if len(trips) < count:
        trips.extend(item for _, _, item in sorted(fallback, key=lambda value: (value[0], value[1]))[:count - len(trips)])
    if len(trips) != count:
        raise ValueError("Não foi possível gerar a demanda solicitada")
    for index, trip in enumerate(trips, 1):
        trip["id"] = index
    return sorted(trips, key=lambda item: (item["departed"], item["id"]))


def focus_new_road_demand(source: Simulator, modified: Simulator, roads: list[dict],
                          trips: list[dict], seed: int, trip_budget_s: float) -> int:
    """Amostra ODs capazes de usar a ligação, preservando partidas e pares A/B."""
    if not roads or not trips:
        return 0
    rng = random.Random(seed)
    target = max(1, round(len(trips) * .25))
    chosen = []
    seen = set()
    for road in roads:
        way_id = str(road["id"])
        endpoints = [source.net.convertLonLat2XY(*road[key]) for key in
                     ("origin_coordinates", "destination_coordinates")]
        neighborhoods = []
        for point in endpoints:
            nearby = sorted((math.dist(point, edge.getShape()[len(edge.getShape()) // 2]), edge_id)
                            for edge_id, edge in source.edges.items() if edge.getLength() >= 35)
            candidates = []
            for _, edge_id in nearby[:50]:
                edge = source.edges[edge_id]
                xy = edge.getShape()[len(edge.getShape()) // 2]
                coordinates = list(source.net.convertXY2LonLat(*xy))
                try:
                    modified_edge = modified.nearest_road(*coordinates)["edge_id"]
                except ValueError:
                    continue
                candidates.append((edge_id, modified_edge, coordinates))
            rng.shuffle(candidates)
            neighborhoods.append(candidates)
        for left, right in ((0, 1), (1, 0)):
            for origin in neighborhoods[left]:
                for destination in neighborhoods[right]:
                    pair = (origin[0], destination[0])
                    if pair in seen or pair[0] == pair[1]:
                        continue
                    seen.add(pair)
                    changed_route = modified.route(origin[1], destination[1])
                    if not any(edge_id.lstrip("-").split("#")[0] == way_id for edge_id in changed_route):
                        continue
                    original_route = source.route(*pair)
                    if not 4 <= len(original_route) <= 100:
                        continue
                    free_flow_s = sum(source.edges[edge_id].getLength() /
                                      max(1, source.edges[edge_id].getSpeed()) for edge_id in original_route)
                    if free_flow_s > trip_budget_s:
                        continue
                    chosen.append((origin, destination))
                    if len(chosen) >= target:
                        break
                if len(chosen) >= target:
                    break
            if len(chosen) >= target:
                break
        if len(chosen) >= target:
            break
    for trip, (origin, destination) in zip(trips, chosen):
        trip.update(origin_edge=origin[0], destination_edge=destination[0],
                    origin_coordinates=origin[2], destination_coordinates=destination[2])
    return len(chosen)


class ExperimentManager:
    def __init__(self, project_root: Path, data_dir: Path):
        self.project_root, self.data_dir = Path(project_root), Path(data_dir)
        self.root = self.data_dir / "experiments"
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, experiment_id: str) -> Path:
        if len(experiment_id) != 12 or any(char not in "0123456789abcdef" for char in experiment_id):
            raise ValueError("ID de experimento inválido")
        path = self.root / experiment_id
        if not path.exists():
            raise ValueError("Experimento não encontrado")
        return path

    def _variants(self, spec: dict, sim: Simulator) -> list[dict]:
        kind = spec["kind"]
        if kind == "gps":
            pairs = [("static", "GPS estático", {"gps_strategy": "static"}),
                     ("dynamic", "GPS dinâmico", {"gps_strategy": "dynamic"})]
        elif kind == "weather":
            pairs = [(key, label, {"weather": key}) for key, label in
                     [("sun", "Sol"), ("light_rain", "Chuva fraca"), ("heavy_rain", "Chuva intensa")]]
        elif kind == "saturation":
            levels = sorted(set([value for value in (25, 50, 100, 250, 500) if value <= spec["vehicles"]] + [spec["vehicles"]]))
            if len(levels) < 3:
                levels = sorted(set([max(2, round(spec["vehicles"] * fraction)) for fraction in (.2, .5, 1)]))
            pairs = [(f"n{count}", f"{count} veículos", {"vehicle_limit": count}) for count in levels]
        elif kind == "roadworks":
            road_id = spec.get("road_id") or next((edge_id for edge_id, edge in sim.edges.items() if len(edge.getLanes()) > 1), None)
            if road_id not in sim.edges:
                raise ValueError("Selecione uma via válida")
            spec["road_id"] = road_id
            pairs = [("base", "Sem intervenção", {"road_action": "none"}),
                     ("closed", "Interdição total", {"road_action": "close"}),
                     ("slow", "Velocidade reduzida", {"road_action": "slow"})]
            if len(sim.edges[road_id].getLanes()) > 1:
                pairs.insert(2, ("partial", "Interdição parcial", {"road_action": "partial"}))
        elif kind == "signals":
            lights = ET.parse(sim.net_path).getroot().findall("tlLogic")
            if not lights:
                raise ValueError("A rede não tem semáforos")
            tls_id, phase = spec.get("tls_id") or lights[0].attrib["id"], int(spec.get("phase", 0))
            logic = next((item for item in lights if item.attrib["id"] == tls_id), None)
            if logic is None or not 0 <= phase < len(logic.findall("phase")):
                raise ValueError("Semáforo ou fase inválida")
            duration = float(logic.findall("phase")[phase].attrib["duration"])
            spec["tls_id"], spec["phase"] = tls_id, phase
            pairs = [("original", "Original", {"light_duration_s": duration}),
                     ("short", "Verde reduzido", {"light_duration_s": max(3, round(duration * .7, 2))}),
                     ("long", "Verde ampliado", {"light_duration_s": min(180, round(duration * 1.3, 2))}),
                     ("balanced", "Alternativa equilibrada", {"light_duration_s": min(180, round(duration * 1.1, 2))})]
        elif kind == "new_road":
            scenario_id = spec.get("modified_scenario_id") or sim.network_scenario_id
            if not scenario_id or not re.fullmatch(r"[0-9a-f]{12}", str(scenario_id)):
                raise ValueError("Construa uma rua fictícia antes deste experimento")
            spec["modified_scenario_id"] = scenario_id
            pairs = [("base", "Rede original", {"network_scenario_id": None}),
                     ("new", "Nova estrada", {"network_scenario_id": scenario_id})]
        elif kind == "custom":
            variants = spec.get("variants") or []
            allowed = {"gps_strategy", "weather", "road_action", "light_duration_s", "vehicle_limit", "network_scenario_id"}
            if not 2 <= len(variants) <= 8 or any(not isinstance(item, dict) for item in variants):
                raise ValueError("Defina 2 a 8 variantes com parâmetros suportados")
            keys = [item.get("key") for item in variants]
            if any(not isinstance(key, str) or not re.fullmatch(r"[a-z0-9_]{1,20}", key)
                   for key in keys) or len(set(keys)) != len(keys):
                raise ValueError("Cada variante precisa de uma chave única com letras minúsculas, números ou _")
            for item in variants:
                parameters = item.get("parameters")
                if not isinstance(item.get("label"), str) or not 1 <= len(item["label"]) <= 80 or not isinstance(parameters, dict) or not parameters or not set(parameters) <= allowed:
                    raise ValueError("Cada variante precisa de nome e parâmetros suportados")
                if (parameters.get("gps_strategy", "dynamic") not in {"dynamic", "static"} or
                    parameters.get("weather", "sun") not in WEATHER or
                    parameters.get("road_action", "none") not in {"none", "close", "partial", "slow"}):
                    raise ValueError("GPS, clima ou intervenção inválidos")
                if "vehicle_limit" in parameters and (not isinstance(parameters["vehicle_limit"], int) or
                    not 2 <= parameters["vehicle_limit"] <= spec["vehicles"]):
                    raise ValueError("Quantidade de veículos da variante inválida")
                if "light_duration_s" in parameters and (not isinstance(parameters["light_duration_s"], (int, float)) or
                    not 3 <= parameters["light_duration_s"] <= 180 or not spec.get("tls_id")):
                    raise ValueError("Escolha um semáforo e uma duração válida para a variante")
                if parameters.get("road_action", "none") != "none" and not spec.get("road_id"):
                    raise ValueError("Escolha uma via para testar a intervenção")
                if parameters.get("road_action", "none") != "none" and spec.get("road_id") not in sim.edges:
                    raise ValueError("Via da intervenção não existe nesta rede")
                if parameters.get("road_action") == "partial" and len(sim.edges[spec["road_id"]].getLanes()) < 2:
                    raise ValueError("Interdição parcial exige uma via com duas faixas")
                if "light_duration_s" in parameters and spec.get("tls_id") not in {
                    item.attrib["id"] for item in ET.parse(sim.net_path).getroot().findall("tlLogic")}:
                    raise ValueError("Semáforo da variante não existe nesta rede")
                scenario_id = parameters.get("network_scenario_id")
                if scenario_id is not None and (not isinstance(scenario_id, str) or
                    not re.fullmatch(r"[0-9a-f]{12}", scenario_id)):
                    raise ValueError("ID de cenário viário inválido")
            return variants
        else:
            raise ValueError("Tipo de experimento desconhecido")
        return [{"key": key, "label": label, "parameters": parameters} for key, label, parameters in pairs]

    def create(self, spec: dict, sim: Simulator, *, exact_demand: list[list[dict]] | None = None,
               parent_id: str | None = None) -> dict:
        kind = spec["kind"]
        if kind not in PRESETS:
            raise ValueError("Experimento desconhecido")
        experiment_id = uuid4().hex[:12]
        path = self.root / experiment_id
        path.mkdir(parents=True)
        city_id = spec.get("source_city_id", sim.city_id)
        city_dir = self.data_dir / "cities" / city_id if city_id else self.data_dir
        source_id = None if kind == "new_road" else spec.get("source_network_scenario_id", sim.network_scenario_id)
        source_dir = city_dir / "scenarios" / source_id if source_id else city_dir
        source_net = source_dir / ("network.net.xml" if source_id or city_id else "blumenau.net.xml")
        if not source_net.exists():
            raise ValueError("Malha do experimento indisponível")
        source_sim = Simulator(str(source_dir), Storage(str(path / "demand.sqlite3")))
        source_sim.net_path = source_net
        source_sim.network_scenario_id = source_id
        source_sim.load_network()
        variants = self._variants(spec, source_sim)
        for variant in variants:
            scenario_id = variant["parameters"].get("network_scenario_id")
            if scenario_id and not (city_dir / "scenarios" / scenario_id / "network.net.xml").exists():
                raise ValueError("A rede SUMO do cenário escolhido não existe")
        demand = exact_demand if exact_demand is not None else [
            deterministic_demand(source_sim, spec["seed"] + index, spec["vehicles"], spec["departure_window_s"],
                                 max(30, (spec["duration_s"] - spec["departure_window_s"]) * .7))
            for index in range(spec["repetitions"])]
        focused_counts = list(spec.get("focused_trip_counts", [])) if exact_demand is not None else []
        if kind == "new_road" and exact_demand is None:
            scenario_dir = city_dir / "scenarios" / spec["modified_scenario_id"]
            manifest = json.loads((scenario_dir / "manifest.json").read_text(encoding="utf-8"))
            modified_sim = Simulator(str(scenario_dir), Storage(str(path / "modified-demand.sqlite3")))
            modified_sim.net_path = scenario_dir / "network.net.xml"
            modified_sim.load_network()
            for index, trips in enumerate(demand):
                focused_counts.append(focus_new_road_demand(
                    source_sim, modified_sim, manifest.get("roads", []), trips, spec["seed"] + index,
                    max(30, (spec["duration_s"] - spec["departure_window_s"]) * .7)))
        hashes = [hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()[:16] for items in demand]
        title, question, hypothesis, independent = PRESETS[kind]
        digest = hashlib.sha256()
        for file in sorted((self.project_root / "backend").glob("*.py")):
            digest.update(file.name.encode())
            digest.update(file.read_bytes())
        config = {"id": experiment_id, "parent_id": parent_id, "name": spec.get("name") or title,
                  "kind": kind, "question": spec.get("question") or question,
                  "hypothesis": spec.get("hypothesis") or hypothesis,
                  "independent_variable": spec.get("independent_variable") or independent,
                  "dependent_variables": ["tempo de viagem", "tempo parado", "distância", "filas", "conclusão"],
                  "controlled_conditions": ["origens", "destinos", "partidas", "sementes", "malha, salvo quando variável"],
                  "method": "SUMO 1.28; passo físico 0,25 s; variantes em processo isolado",
                  "indicators": ["média", "mediana", "p95", "desvio-padrão", "taxa de conclusão"],
                  "limitations": ["Demanda sintética, sem calibração por contagens reais da cidade",
                                  "Arquivo OSM importado; cobertura e qualidade dependem da fonte fornecida" if city_id else
                                  "Recorte OSM central, não a cidade inteira",
                                  "Viagens não concluídas são contabilizadas separadamente"],
                  "seed": spec["seed"], "repetitions": spec["repetitions"], "vehicles": spec["vehicles"],
                  "duration_s": spec["duration_s"], "departure_window_s": spec["departure_window_s"],
                  "start_hour": spec.get("start_hour", 6), "gps_interval": spec.get("gps_interval", 30),
                  "mode": spec.get("mode", "fast"), "visual_speed": spec.get("visual_speed", 1),
                  "snapshot_interval_s": spec.get("snapshot_interval_s", 5),
                  "road_id": spec.get("road_id"), "tls_id": spec.get("tls_id"), "phase": spec.get("phase", 0),
                  "modified_scenario_id": spec.get("modified_scenario_id"),
                  "source_city_id": city_id,
                  "source_network_scenario_id": source_id,
                  "source_network_version": hashlib.sha256(source_net.read_bytes()).hexdigest()[:16],
                  "code_version": digest.hexdigest()[:16], "variants": variants,
                  "demand": demand, "demand_hashes": hashes,
                  "demand_rule": ("ODs sintéticos; até 25% amostrados próximos à nova ligação quando a rota livre pode utilizá-la, "
                                  "com as mesmas partidas e pares nos dois cenários; tempo livre até 70% do orçamento"
                                  if kind == "new_road" else
                                  "trajetos com tempo livre estimado até 70% do tempo após janela de partidas"),
                  "focused_trip_counts": focused_counts,
                  "weather_model": WEATHER}
        (path / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        (path / "status.json").write_text(json.dumps({"state": "queued", "progress": 0}), encoding="utf-8")
        log = (path / "worker.log").open("w", encoding="utf-8")
        command = [sys.executable, str(self.project_root / "scripts" / "experiment_worker.py"), str(path)]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(command, cwd=self.project_root, env=os.environ.copy(),
                                   stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        log.close()
        return {"id": experiment_id, "state": "queued", "pid": process.pid,
                "config": {key: value for key, value in config.items() if key != "demand"}}

    def read(self, experiment_id: str) -> dict:
        path = self.path(experiment_id)
        config = json.loads((path / "config.json").read_text(encoding="utf-8"))
        status = json.loads((path / "status.json").read_text(encoding="utf-8"))
        results_file = path / "results.json"
        return {"config": {key: value for key, value in config.items() if key != "demand"},
                "status": status,
                "results": json.loads(results_file.read_text(encoding="utf-8")) if results_file.exists() else None}

    def list(self) -> list[dict]:
        found = []
        for file in sorted(self.root.glob("*/config.json"), reverse=True):
            try:
                data = self.read(file.parent.name)
                found.append({"id": file.parent.name, "name": data["config"]["name"],
                              "kind": data["config"]["kind"], "status": data["status"]})
            except (OSError, ValueError):
                continue
        return found

    def repeat(self, experiment_id: str, sim: Simulator) -> dict:
        config = json.loads((self.path(experiment_id) / "config.json").read_text(encoding="utf-8"))
        source_id = config.get("source_network_scenario_id")
        city_id = config.get("source_city_id")
        city_dir = self.data_dir / "cities" / city_id if city_id else self.data_dir
        source_dir = city_dir / "scenarios" / source_id if source_id else city_dir
        source_net = source_dir / ("network.net.xml" if source_id or city_id else "blumenau.net.xml")
        if not source_net.exists() or hashlib.sha256(source_net.read_bytes()).hexdigest()[:16] != config["source_network_version"]:
            raise ValueError("A versão da malha mudou; a repetição exata não é possível")
        keys = ("name", "kind", "question", "hypothesis", "independent_variable", "seed",
                "repetitions", "vehicles", "duration_s", "departure_window_s", "start_hour",
                "gps_interval", "mode", "visual_speed", "snapshot_interval_s", "road_id",
                "tls_id", "phase", "modified_scenario_id", "source_network_scenario_id", "source_city_id",
                "focused_trip_counts")
        spec = {key: config[key] for key in keys if key in config}
        if config["kind"] == "custom":
            spec["variants"] = config["variants"]
        return self.create(spec, sim, exact_demand=config["demand"], parent_id=experiment_id)
