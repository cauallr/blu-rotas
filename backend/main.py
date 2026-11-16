"""API local e WebSocket do BLU-ROTAS."""
from __future__ import annotations

import asyncio
import csv
import io
import json
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import STEP_SECONDS, Simulator, WEATHER
from .experiments import ExperimentManager
from .experiment_analysis import compare as compare_experiment_runs
from .experiment_report import csv_export, pdf_export
from .graphs import Graph, benchmark
from .graph_view import graph_overlay
from .municipalities import MunicipalityLab, scale_experiments
from .scenario_network import ScenarioNetwork, way_id_from_edge
from .map_manager import MapManager
from .storage import Storage
from .urban import AccessPoints

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("BLU_DATA_DIR", ROOT / "data"))
STORE = Storage(os.environ.get("BLU_DB_PATH", str(DATA_DIR / "results.sqlite3")))
SIM = Simulator(str(DATA_DIR), STORE)
MUNICIPALITIES = MunicipalityLab(str(DATA_DIR / "municipalities.sqlite3"))
ACCESS_POINTS = AccessPoints(DATA_DIR / "scenarios" / "access-points.json")
SIM.access_point_store = ACCESS_POINTS
if SIM.net:
    SIM.set_access_points(ACCESS_POINTS.for_sim(SIM))
URBAN = ScenarioNetwork(DATA_DIR)
MAPS = MapManager(DATA_DIR)
EXPERIMENTS = ExperimentManager(ROOT, DATA_DIR)
BASE_WAYS = {str(feature["properties"]["id"]) for feature in
             json.loads((DATA_DIR / "roads.geojson").read_text(encoding="utf-8"))["features"]} if (DATA_DIR / "roads.geojson").exists() else set()
LOCK = asyncio.Lock()
app = FastAPI(title="BLU-ROTAS", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[os.environ.get("BLU_CORS_ORIGIN", "http://localhost:5173")],
                   allow_methods=["*"], allow_headers=["*"])
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/")
def home():
    if not DIST.exists():
        raise HTTPException(status_code=404, detail="Compile o frontend com npm run build")
    return FileResponse(DIST / "index.html")


class StartBody(BaseModel):
    seed: int = 42
    start_hour: float = Field(6, ge=0, lt=24)


class ClockBody(BaseModel):
    hour: float = Field(6, ge=0, lt=24)


class SpawnBody(BaseModel):
    count: int = Field(10, ge=1, le=500)


class SpeedBody(BaseModel):
    speed: float = Field(1, ge=0.25, le=5)


class WeatherBody(BaseModel):
    weather: str


class RoadBody(BaseModel):
    edge_id: str
    action: str
    speed_kmh: float | None = None


class LightBody(BaseModel):
    tls_id: str
    phase: int = 0
    duration: float | None = None
    restore: bool = False


class GPSBody(BaseModel):
    interval: float = Field(30, ge=5, le=300)
    benefit: float = Field(0.12, ge=0, le=0.8)
    dynamic_percent: float = Field(0.5, ge=0, le=1)


class ContinuousBody(BaseModel):
    vehicles_per_sim_second: float = Field(0, ge=0, le=5)


class MapPoint(BaseModel):
    coordinates: tuple[float, float]


class CustomCarBody(BaseModel):
    origin: MapPoint
    destination: MapPoint
    waypoints: list[MapPoint] = Field(default_factory=list, max_length=8)
    color: str = Field("#4de1cc", pattern=r"^#[0-9a-fA-F]{6}$")
    strategy: Literal["dynamic", "static"] = "dynamic"
    gps_interval: float = Field(30, ge=5, le=300)
    gps_benefit: float = Field(0.12, ge=0, le=0.8)
    speed_factor: float = Field(1.0, ge=0.6, le=1.4)
    route_choice: Literal["best", "secondary", "longer"] = "best"


class RouteGroupBody(BaseModel):
    choice: Literal["best", "secondary", "longer"]
    count: int = Field(ge=1, le=100)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class CustomGroupsBody(CustomCarBody):
    groups: list[RouteGroupBody] = Field(min_length=1, max_length=3)


class RouteChoiceBody(BaseModel):
    choice: Literal["best", "secondary", "longer"]


class VehicleGPSBody(BaseModel):
    strategy: Literal["dynamic", "static"]
    interval: float = Field(30, ge=5, le=300)
    benefit: float = Field(0.12, ge=0, le=0.8)


class VehicleStyleBody(BaseModel):
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    speed_factor: float = Field(1.0, ge=0.6, le=1.4)


class LoopBody(BaseModel):
    enabled: bool
    start_hour: float = Field(6, ge=0, lt=24)
    base_per_minute: float = Field(6, ge=0.1, le=60)
    peak_multiplier: float = Field(3, ge=1, le=8)


class ScenarioBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class GraphRequest(BaseModel):
    start: str
    end: str
    method: str = "heap"


class CityBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class AccessPointBody(BaseModel):
    coordinates: tuple[float, float]
    name: str = Field(default="Ponto de acesso", max_length=100)


class NewRoadBody(BaseModel):
    origin: tuple[float, float]
    destination: tuple[float, float]
    name: str = Field(min_length=1, max_length=100)
    oneway: bool = False
    speed_kmh: float = Field(40, ge=10, le=80)
    lanes: int = Field(1, ge=1, le=4)
    capacity_estimate: float = Field(900, ge=100, le=8000)
    hypothetical_cost: float = Field(0, ge=0)
    scenario_name: str = Field(default="Cidade modificada", min_length=1, max_length=100)
    replace_road_id: str | None = None
    via: list[tuple[float, float]] = Field(default_factory=list, max_length=12)
    direction: Literal["both", "forward", "reverse"] | None = None


class RoadEditBody(BaseModel):
    edge_id: str
    direction: Literal["both", "selected", "opposite"]
    lanes_selected: int = Field(1, ge=1, le=4)
    lanes_opposite: int = Field(1, ge=1, le=4)
    speed_kmh: float = Field(40, ge=5, le=80)
    scenario_name: str = Field(default="Vias editadas", min_length=1, max_length=100)


class NewSignalBody(BaseModel):
    coordinates: tuple[float, float]
    scenario_name: str = Field(default="Semáforos editados", min_length=1, max_length=100)


class ExperimentBody(BaseModel):
    kind: Literal["gps", "signals", "saturation", "roadworks", "new_road", "weather", "custom"]
    name: str = Field(default="", max_length=100)
    question: str = Field(default="", max_length=400)
    hypothesis: str = Field(default="", max_length=400)
    independent_variable: str = Field(default="", max_length=100)
    vehicles: int = Field(25, ge=2, le=500)
    repetitions: int = Field(1, ge=1, le=20)
    seed: int = 42
    duration_s: float = Field(180, ge=30, le=3600)
    departure_window_s: float = Field(45, ge=1, le=600)
    start_hour: float = Field(6, ge=0, lt=24)
    gps_interval: float = Field(30, ge=5, le=300)
    mode: Literal["fast", "visual"] = "fast"
    visual_speed: float = Field(1, ge=.25, le=5)
    snapshot_interval_s: float = Field(5, ge=1, le=30)
    road_id: str | None = None
    tls_id: str | None = None
    phase: int = Field(0, ge=0)
    modified_scenario_id: str | None = None
    variants: list[dict] | None = None


class LinkBody(BaseModel):
    a: int
    b: int
    distance: float = Field(gt=0)


def error(exc: Exception):
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.on_event("startup")
async def startup():
    app.state.latest_snapshot = None
    app.state.worker = asyncio.create_task(ticker())


@app.on_event("shutdown")
async def shutdown():
    app.state.worker.cancel()
    SIM.stop()


async def ticker():
    # Deadline fixo: o custo do passo não se soma ao intervalo real.
    clock = asyncio.get_running_loop()
    next_tick = clock.time()
    step_credit = 0.0
    while True:
        next_tick += STEP_SECONDS
        await asyncio.sleep(max(0, next_tick - clock.time()))
        async with LOCK:
            if SIM.connected and SIM.running:
                try:
                    step_credit += SIM.speed
                    for _ in range(int(step_credit)):
                        SIM.step()
                    step_credit -= int(step_credit)
                    app.state.latest_snapshot = SIM.snapshot()
                except Exception:
                    SIM.running = False
                    raise
            else:
                step_credit = 0.0
        if clock.time() - next_tick > STEP_SECONDS * 4:
            next_tick = clock.time()


@app.get("/api/status")
async def status():
    async with LOCK:
        return SIM.snapshot()


@app.get("/api/network")
def network():
    if SIM.net:
        return SIM.network_geojson()
    path = SIM.data_dir / "roads.geojson"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"type": "FeatureCollection", "features": []}


@app.get("/api/places")
def places():
    path = SIM.data_dir / "places.geojson"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"type": "FeatureCollection", "features": []}


@app.get("/api/roads/base")
def base_roads():
    path = SIM.data_dir / "roads.geojson"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"type": "FeatureCollection", "features": []}


@app.get("/api/nearest-road")
async def nearest_road(lon: float, lat: float):
    async with LOCK:
        try:
            return SIM.nearest_road(lon, lat)
        except Exception as exc:
            error(exc)


@app.post("/api/route/preview")
async def preview_route(body: CustomCarBody):
    async with LOCK:
        try:
            points = [SIM.nearest_road(*point.coordinates) for point in
                      [body.origin, *body.waypoints, body.destination]]
            options = SIM.route_choices([point["edge_id"] for point in points])
            if not options:
                raise ValueError("Não existe rota válida entre todos os pontos")
            route = options[0]["route"]
            current_costs = SIM._edge_costs() if SIM.connected else {}
            return {"route": route, "options": options, "points": points,
                    "free_flow_seconds": round(sum(SIM.edges[edge].getLength() / max(SIM.edges[edge].getSpeed(), 1)
                                                   for edge in route), 1),
                    "current_seconds": round(sum(current_costs.get(edge, SIM.edges[edge].getLength() / max(SIM.edges[edge].getSpeed(), 1))
                                                 for edge in route), 1)}
        except Exception as exc:
            error(exc)


@app.post("/api/start")
async def start(body: StartBody):
    async with LOCK:
        try:
            result = SIM.start(body.seed, body.start_hour)
            SIM.running = True
            return result | {"running": True}
        except Exception as exc:
            error(exc)


@app.post("/api/pause")
async def pause():
    async with LOCK:
        SIM.running = False
        return SIM.snapshot()


@app.post("/api/resume")
async def resume():
    async with LOCK:
        if not SIM.connected:
            raise HTTPException(status_code=400, detail="SUMO não iniciado")
        SIM.running = True
        return SIM.snapshot()


@app.post("/api/reset")
async def reset(body: StartBody):
    async with LOCK:
        try:
            return SIM.start(body.seed, body.start_hour)
        except Exception as exc:
            error(exc)


@app.post("/api/step")
async def step():
    async with LOCK:
        try:
            for _ in range(round(1 / STEP_SECONDS)):
                SIM.step()
            return SIM.snapshot()
        except Exception as exc:
            error(exc)


@app.post("/api/spawn")
async def spawn(body: SpawnBody):
    async with LOCK:
        try:
            return SIM.spawn(body.count)
        except Exception as exc:
            error(exc)


@app.post("/api/spawn/custom")
async def spawn_custom(body: CustomCarBody):
    async with LOCK:
        try:
            return SIM.spawn_custom(body.origin.model_dump(), body.destination.model_dump(),
                                    [point.model_dump() for point in body.waypoints], body.color,
                                    body.strategy, body.gps_interval, body.gps_benefit,
                                    body.speed_factor, body.route_choice)
        except Exception as exc:
            error(exc)


@app.post("/api/spawn/groups")
async def spawn_groups(body: CustomGroupsBody):
    async with LOCK:
        try:
            return SIM.spawn_custom_groups(body.origin.model_dump(), body.destination.model_dump(),
                [point.model_dump() for point in body.waypoints],
                [group.model_dump() for group in body.groups], body.strategy,
                body.gps_interval, body.gps_benefit, body.speed_factor)
        except Exception as exc:
            error(exc)


@app.get("/api/vehicles/{vehicle_id}/route-options")
async def vehicle_route_options(vehicle_id: str):
    async with LOCK:
        try:
            return {"options": SIM.vehicle_route_choices(vehicle_id)}
        except Exception as exc:
            error(exc)


@app.post("/api/vehicles/{vehicle_id}/route")
async def choose_vehicle_route(vehicle_id: str, body: RouteChoiceBody):
    async with LOCK:
        try:
            return SIM.choose_vehicle_route(vehicle_id, body.choice)
        except Exception as exc:
            error(exc)


@app.post("/api/vehicles/{vehicle_id}/gps")
async def vehicle_gps(vehicle_id: str, body: VehicleGPSBody):
    async with LOCK:
        try:
            return SIM.update_vehicle_gps(vehicle_id, body.strategy, body.interval, body.benefit)
        except Exception as exc:
            error(exc)


@app.post("/api/vehicles/{vehicle_id}/style")
async def vehicle_style(vehicle_id: str, body: VehicleStyleBody):
    async with LOCK:
        try:
            return SIM.update_vehicle_style(vehicle_id, body.color, body.speed_factor)
        except Exception as exc:
            error(exc)


@app.post("/api/speed")
async def speed(body: SpeedBody):
    async with LOCK:
        SIM.speed = body.speed
        return {"speed": SIM.speed}


@app.post("/api/clock")
async def set_clock(body: ClockBody):
    async with LOCK:
        SIM.set_city_clock(body.hour)
        return SIM.snapshot()


@app.post("/api/weather")
async def weather(body: WeatherBody):
    async with LOCK:
        try:
            SIM.set_weather(body.weather)
            return {"weather": body.weather, "modifiers": WEATHER[body.weather]}
        except Exception as exc:
            error(exc)


@app.post("/api/road")
async def road(body: RoadBody):
    async with LOCK:
        try:
            return SIM.road_action(body.edge_id, body.action, body.speed_kmh)
        except Exception as exc:
            error(exc)


@app.post("/api/light")
async def light(body: LightBody):
    async with LOCK:
        try:
            SIM.traffic_light(body.tls_id, body.phase, body.duration, body.restore)
            return SIM.snapshot()
        except Exception as exc:
            error(exc)


@app.post("/api/gps")
async def gps(body: GPSBody):
    async with LOCK:
        SIM.gps_interval = body.interval
        SIM.gps_benefit = body.benefit
        SIM.dynamic_percent = body.dynamic_percent
        if SIM.connected:
            for info in SIM.vehicles.values():
                if not info["gps_customized"] and info["state"] != "arrived":
                    info["gps_interval"] = body.interval
                    info["gps_benefit"] = body.benefit
                    info["gps_next_check"] = min(info["gps_next_check"],
                                                  info["departed"] + body.interval)
        return body.model_dump()


@app.post("/api/loop")
async def loop(body: LoopBody):
    async with LOCK:
        if not SIM.connected:
            raise HTTPException(status_code=400, detail="Inicie a simulação antes de ativar o loop")
        return SIM.set_loop(body.enabled, body.start_hour, body.base_per_minute, body.peak_multiplier)


@app.post("/api/continuous")
async def continuous(body: ContinuousBody):
    async with LOCK:
        SIM.continuous_rate = body.vehicles_per_sim_second
        return body.model_dump()


@app.get("/api/metrics")
def metrics():
    return STORE.metrics(SIM.run_id) if SIM.run_id else {"samples": [], "trips": [], "interventions": []}


@app.get("/api/export/{table}.csv")
def export(table: str):
    if table not in {"samples", "trips", "interventions"}:
        raise HTTPException(status_code=404, detail="Tabela desconhecida")
    rows = STORE.metrics(SIM.run_id or -1)[table]
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return Response(output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{table}.csv"'})


@app.post("/api/scenarios")
def save_scenario(body: ScenarioBody):
    config = {"network": SIM.net_path.name, "seed": SIM.seed,
              "city_id": SIM.city_id, "network_scenario_id": SIM.network_scenario_id,
              "network_version": SIM.network_version,
              "city_start_hour": SIM.city_start_hour,
              "weather": SIM.weather, "blocked": list(SIM.blocked),
              "reduced": SIM.reduced, "gps_interval": SIM.gps_interval,
              "gps_benefit": SIM.gps_benefit, "dynamic_percent": SIM.dynamic_percent,
              "loop": SIM.loop_state(),
              "vehicle_count": len(SIM.vehicles),
              "lights": {light["id"]: {str(phase["index"]): phase["duration"] for phase in light["phases"]
                          if light["id"] in SIM.tls_original
                          and phase["index"] < len(SIM.tls_original[light["id"]][0].phases)
                          and phase["duration"] != SIM.tls_original[light["id"]][0].phases[phase["index"]].duration}
                         for light in SIM.snapshot().get("lights", [])},
              "trips": [{"origin": info["origin"], "destination": info["destination"],
                         "departed": info["departed"], "strategy": info["strategy"],
                         "waypoints": info.get("waypoints", []), "origin_pos": info.get("origin_pos"),
                         "destination_pos": info.get("destination_pos"), "color": info.get("color", "#4de1cc"),
                         "gps_interval": info.get("gps_interval"), "gps_benefit": info.get("gps_benefit"),
                         "speed_factor": info.get("speed_factor", 1.0)}
                        for info in SIM.vehicles.values()]}
    return {"id": STORE.save_scenario(body.name, config), "config": config}


@app.get("/api/scenarios")
def scenarios():
    return STORE.scenarios()


@app.post("/api/scenarios/{scenario_id}/run")
async def run_scenario(scenario_id: int):
    scenario = next((item for item in STORE.scenarios() if item["id"] == scenario_id), None)
    if not scenario:
        raise HTTPException(status_code=404, detail="Cenário não encontrado")
    config = scenario["config"]
    async with LOCK:
        try:
            if config.get("city_id") != SIM.city_id:
                activate_city(config.get("city_id"))
            if config.get("network_scenario_id") != SIM.network_scenario_id:
                activate_urban_network(config.get("network_scenario_id"))
            SIM.start(config["seed"], config.get("city_start_hour", 6))
            SIM.gps_interval = config["gps_interval"]
            SIM.gps_benefit = config["gps_benefit"]
            SIM.dynamic_percent = config["dynamic_percent"]
            loop_config = config.get("loop", {})
            if loop_config.get("enabled"):
                SIM.set_loop(True, loop_config.get("start_hour", 6),
                             loop_config.get("base_per_minute", 6), loop_config.get("peak_multiplier", 3))
            SIM.set_weather(config["weather"])
            for edge_id in config["blocked"]:
                SIM.road_action(edge_id, "close")
            for edge_id, speed in config["reduced"].items():
                SIM.road_action(edge_id, "slow", speed * 3.6)
            for tls_id, durations in config.get("lights", {}).items():
                if tls_id in SIM.tls_original:
                    if isinstance(durations, list):
                        durations = {str(index): duration for index, duration in enumerate(durations)}
                    for index_text, duration in durations.items():
                        index = int(index_text)
                        original = SIM.tls_original[tls_id][0].phases
                        if index < len(original) and duration != original[index].duration and duration >= 3:
                            SIM.traffic_light(tls_id, index, duration)
            SIM.pending_trips = sorted(config["trips"], key=lambda trip: trip["departed"])
            SIM.running = True
            return SIM.snapshot()
        except Exception as exc:
            SIM.running = False
            error(exc)


@app.get("/api/graph/stats")
def graph_stats():
    return SIM.graph.stats() if SIM.net else {"vertices": 0, "edges": 0, "density": 0, "components": 0}


@app.get("/api/graph/overlay")
def graph_geojson():
    return graph_overlay(SIM)


@app.get("/api/access-points")
def access_points():
    return {"points": ACCESS_POINTS.for_sim(SIM)}


@app.post("/api/access-points")
async def add_access_point(body: AccessPointBody):
    async with LOCK:
        try:
            point = ACCESS_POINTS.add(SIM, body.coordinates, body.name)
            SIM.set_access_points(ACCESS_POINTS.for_sim(SIM))
            return point
        except Exception as exc:
            error(exc)


@app.delete("/api/access-points/{point_id}")
async def delete_access_point(point_id: str):
    async with LOCK:
        if not ACCESS_POINTS.remove(point_id):
            raise HTTPException(status_code=404, detail="Ponto não encontrado")
        SIM.set_access_points(ACCESS_POINTS.for_sim(SIM))
        return {"deleted": point_id}


def activate_urban_network(scenario_id: str | None):
    manifest = URBAN.get(scenario_id) if scenario_id else None
    target_dir = URBAN.root / scenario_id if scenario_id else URBAN.base_dir
    net_path = target_dir / ("network.net.xml" if scenario_id or SIM.city_id else "blumenau.net.xml")
    if not net_path.exists():
        raise ValueError("Rede SUMO do cenário ausente")
    old_dir, old_path = SIM.data_dir, SIM.net_path
    old_version, old_id = SIM.network_version, SIM.network_scenario_id
    seed, start_hour = SIM.seed, SIM.city_start_hour
    SIM.stop()
    SIM.data_dir, SIM.net_path = target_dir, net_path
    try:
        SIM.network_version = (manifest["network_version"] if manifest else
            (MAPS.get(SIM.city_id)["network_version"] if SIM.city_id else "blumenau-original"))
        SIM.network_scenario_id = scenario_id
        SIM.start(seed, start_hour)
        return {"scenario": manifest, "snapshot": SIM.snapshot()}
    except Exception:
        SIM.data_dir, SIM.net_path = old_dir, old_path
        SIM.network_version, SIM.network_scenario_id = old_version, old_id
        SIM.start(seed, start_hour)
        raise


@app.get("/api/urban/networks")
def urban_networks():
    return {"active": SIM.network_scenario_id, "scenarios": URBAN.list(),
            "base": {"id": None, "name": "Blumenau original", "source": "OpenStreetMap"}}


@app.post("/api/urban/roads")
async def build_road(body: NewRoadBody):
    async with LOCK:
        try:
            a = SIM.nearest_road(*body.origin, allowed_way_ids=BASE_WAYS)
            b = SIM.nearest_road(*body.destination, allowed_way_ids=BASE_WAYS)
            spec = {"origin_way": way_id_from_edge(a["edge_id"]),
                    "destination_way": way_id_from_edge(b["edge_id"]),
                    "origin_coordinates": a["coordinates"], "destination_coordinates": b["coordinates"],
                    "name": body.name, "oneway": body.oneway, "speed_kmh": body.speed_kmh,
                    "lanes": body.lanes, "via": body.via, "direction": body.direction or ("forward" if body.oneway else "both"),
                    "capacity_estimate": body.capacity_estimate,
                    "hypothetical_cost": body.hypothetical_cost}
            current = URBAN.get(SIM.network_scenario_id) if SIM.network_scenario_id else {}
            previous = current.get("roads", [])
            if body.replace_road_id:
                if not any(road["id"] == body.replace_road_id for road in previous):
                    raise ValueError("Rua para edição não encontrada no cenário ativo")
                spec["id"] = body.replace_road_id
                previous = [road for road in previous if road["id"] != body.replace_road_id]
            manifest = await asyncio.to_thread(URBAN.build, [*previous, spec], body.scenario_name,
                                               current.get("road_edits", []), current.get("signals", []))
            return activate_urban_network(manifest["id"])
        except Exception as exc:
            error(exc)


@app.delete("/api/urban/roads/{road_id}")
async def remove_urban_road(road_id: str):
    async with LOCK:
        try:
            if not SIM.network_scenario_id:
                raise ValueError("Nenhum cenário de ruas fictícias ativo")
            current = URBAN.get(SIM.network_scenario_id)
            roads = current["roads"]
            kept = [road for road in roads if road["id"] != road_id]
            if len(kept) == len(roads):
                raise ValueError("Rua fictícia não encontrada")
            if not kept and not current.get("road_edits") and not current.get("signals"):
                return activate_urban_network(None)
            manifest = await asyncio.to_thread(URBAN.build, kept, "Cidade modificada",
                                               current.get("road_edits", []), current.get("signals", []))
            return activate_urban_network(manifest["id"])
        except Exception as exc:
            error(exc)


@app.post("/api/urban/road-edit")
async def edit_urban_road(body: RoadEditBody):
    async with LOCK:
        try:
            if body.edge_id not in SIM.edges:
                raise ValueError("Selecione um trecho trafegável da rede atual")
            way_id = way_id_from_edge(body.edge_id)
            if way_id not in BASE_WAYS:
                raise ValueError("Use Construir estrada para editar uma via fictícia")
            selected_forward = not body.edge_id.startswith("-")
            direction = ("both" if body.direction == "both" else
                         "forward" if (body.direction == "selected") == selected_forward else "reverse")
            selected_count = body.lanes_selected if body.direction != "opposite" else 0
            opposite_count = body.lanes_opposite if body.direction != "selected" else 0
            forward = selected_count if selected_forward else opposite_count
            backward = opposite_count if selected_forward else selected_count
            edit = {"way_id": way_id, "direction": direction, "lanes_forward": forward,
                    "lanes_backward": backward, "speed_kmh": body.speed_kmh}
            current = URBAN.get(SIM.network_scenario_id) if SIM.network_scenario_id else {}
            previous = [item for item in current.get("road_edits", []) if item["way_id"] != way_id]
            manifest = await asyncio.to_thread(URBAN.build, current.get("roads", []), body.scenario_name,
                                               [*previous, edit], current.get("signals", []))
            return activate_urban_network(manifest["id"])
        except Exception as exc:
            error(exc)


@app.delete("/api/urban/road-edit/{way_id}")
async def remove_urban_road_edit(way_id: str):
    async with LOCK:
        try:
            current = URBAN.get(SIM.network_scenario_id) if SIM.network_scenario_id else {}
            previous = current.get("road_edits", [])
            kept = [item for item in previous if item["way_id"] != way_id]
            if len(kept) == len(previous):
                raise ValueError("Edição da via não encontrada")
            if not kept and not current.get("roads") and not current.get("signals"):
                return activate_urban_network(None)
            manifest = await asyncio.to_thread(URBAN.build, current.get("roads", []), "Cidade modificada",
                                               kept, current.get("signals", []))
            return activate_urban_network(manifest["id"])
        except Exception as exc:
            error(exc)


@app.get("/api/urban/junction")
async def nearest_junction(lon: float, lat: float):
    async with LOCK:
        try:
            if not SIM.net:
                raise ValueError("Rede SUMO indisponível")
            x, y = SIM.net.convertLonLat2XY(lon, lat)
            candidates = [(node, ((node.getCoord()[0] - x) ** 2 + (node.getCoord()[1] - y) ** 2) ** .5)
                          for node in SIM.net.getNodes()
                          if len(node.getIncoming()) + len(node.getOutgoing()) >= 3]
            node, distance = min(candidates, key=lambda item: item[1])
            if distance > 35:
                raise ValueError("Clique a até 35 m de um cruzamento")
            return {"id": node.getID(), "coordinates": list(SIM.net.convertXY2LonLat(*node.getCoord())),
                    "type": node.getType(), "distance_m": round(distance, 1)}
        except Exception as exc:
            error(exc)


@app.post("/api/urban/signals")
async def add_urban_signal(body: NewSignalBody):
    async with LOCK:
        try:
            current = URBAN.get(SIM.network_scenario_id) if SIM.network_scenario_id else {}
            signals = current.get("signals", [])
            manifest = await asyncio.to_thread(URBAN.build, current.get("roads", []), body.scenario_name,
                                               current.get("road_edits", []),
                                               [*signals, {"coordinates": list(body.coordinates)}])
            return activate_urban_network(manifest["id"])
        except Exception as exc:
            error(exc)


@app.delete("/api/urban/signals/{node_id}")
async def remove_urban_signal(node_id: str):
    async with LOCK:
        try:
            current = URBAN.get(SIM.network_scenario_id) if SIM.network_scenario_id else {}
            signals = current.get("signals", [])
            kept = [item for item in signals if item["node_id"] != node_id]
            if len(kept) == len(signals):
                raise ValueError("Semáforo fictício não encontrado")
            if not kept and not current.get("roads") and not current.get("road_edits"):
                return activate_urban_network(None)
            manifest = await asyncio.to_thread(URBAN.build, current.get("roads", []), "Cidade modificada",
                                               current.get("road_edits", []), kept)
            return activate_urban_network(manifest["id"])
        except Exception as exc:
            error(exc)


@app.post("/api/urban/networks/{scenario_id}/activate")
async def activate_network(scenario_id: str):
    async with LOCK:
        try:
            return activate_urban_network(scenario_id)
        except Exception as exc:
            error(exc)


@app.post("/api/urban/base/activate")
async def activate_base():
    async with LOCK:
        try:
            return activate_urban_network(None)
        except Exception as exc:
            error(exc)


def activate_city(city_id: str | None):
    global URBAN, BASE_WAYS
    manifest = MAPS.get(city_id) if city_id else None
    target = MAPS.root / city_id if city_id else DATA_DIR
    net_path = target / ("network.net.xml" if city_id else "blumenau.net.xml")
    if not net_path.exists():
        raise ValueError("Rede SUMO da cidade indisponível")
    old = (SIM.data_dir, SIM.net_path, SIM.city_id, SIM.city_name, SIM.network_version,
           SIM.network_scenario_id, URBAN, BASE_WAYS)
    seed, hour = SIM.seed, SIM.city_start_hour
    SIM.stop()
    SIM.data_dir, SIM.net_path = target, net_path
    SIM.city_id, SIM.city_name = city_id, manifest["name"] if manifest else "Blumenau central"
    SIM.network_version = manifest["network_version"] if manifest else "blumenau-original"
    SIM.network_scenario_id = None
    URBAN = ScenarioNetwork(target)
    BASE_WAYS = {str(feature["properties"]["id"]) for feature in
                 json.loads((target / "roads.geojson").read_text(encoding="utf-8"))["features"]}
    try:
        SIM.start(seed, hour)
        return {"city": manifest, "snapshot": SIM.snapshot()}
    except Exception:
        (SIM.data_dir, SIM.net_path, SIM.city_id, SIM.city_name, SIM.network_version,
         SIM.network_scenario_id, URBAN, BASE_WAYS) = old
        SIM.start(seed, hour)
        raise


@app.get("/api/maps")
def maps():
    return {"active": SIM.city_id, "cities": MAPS.list()}


@app.post("/api/maps/import")
async def import_map(request: Request, name: str, region: str = "", west: float | None = None,
                     south: float | None = None, east: float | None = None, north: float | None = None):
    values = [west, south, east, north]
    if any(value is not None for value in values) and (any(value is None for value in values) or west >= east or south >= north):
        raise HTTPException(status_code=400, detail="Informe limites oeste/sul/leste/norte válidos")
    try:
        contents = await request.body()
        return await asyncio.to_thread(MAPS.import_xml, contents, name, region,
                                       tuple(values) if all(value is not None for value in values) else None)
    except Exception as exc:
        error(exc)


@app.post("/api/maps/base/activate")
async def activate_base_map():
    async with LOCK:
        try:
            return activate_city(None)
        except Exception as exc:
            error(exc)


@app.post("/api/maps/{city_id}/activate")
async def activate_imported_map(city_id: str):
    async with LOCK:
        try:
            return activate_city(city_id)
        except Exception as exc:
            error(exc)


@app.post("/api/experiments")
async def create_experiment(body: ExperimentBody):
    async with LOCK:
        try:
            return await asyncio.to_thread(EXPERIMENTS.create, body.model_dump(), SIM)
        except Exception as exc:
            error(exc)


@app.get("/api/experiments")
def list_experiments():
    return {"experiments": EXPERIMENTS.list()}


@app.get("/api/experiments/compare")
def compare_experiments(experiment_a: str, run_a: str, experiment_b: str, run_b: str):
    try:
        first = EXPERIMENTS.read(experiment_a)["results"]
        second = EXPERIMENTS.read(experiment_b)["results"]
        if not first or not second:
            raise ValueError("As duas execuções precisam estar concluídas")
        a = next(item for item in first["runs"] if item["id"] == run_a)
        b = next(item for item in second["runs"] if item["id"] == run_b)
        return {"a": {"experiment": experiment_a, "run": a},
                "b": {"experiment": experiment_b, "run": b},
                "comparison": compare_experiment_runs(a, b)}
    except (ValueError, StopIteration) as exc:
        error(exc)


@app.get("/api/experiments/{experiment_id}")
def get_experiment(experiment_id: str):
    try:
        return EXPERIMENTS.read(experiment_id)
    except ValueError as exc:
        error(exc)


@app.post("/api/experiments/{experiment_id}/repeat")
async def repeat_experiment(experiment_id: str):
    async with LOCK:
        try:
            return await asyncio.to_thread(EXPERIMENTS.repeat, experiment_id, SIM)
        except Exception as exc:
            error(exc)


@app.get("/api/experiments/{experiment_id}/frames")
def experiment_frames(experiment_id: str, run_id: str, limit: int = 1000):
    try:
        result = EXPERIMENTS.read(experiment_id)["results"]
        if not result:
            raise ValueError("Experimento ainda em execução")
        run = next(item for item in result["runs"] if item["id"] == run_id)
        path = EXPERIMENTS.path(experiment_id) / run["frames_file"]
        frames = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()[:max(1, min(limit, 2000))]]
        return {"frames": frames, "run": run_id, "source": "snapshots reais do SUMO"}
    except (ValueError, StopIteration, OSError) as exc:
        error(exc)


@app.get("/api/experiments/{experiment_id}/live")
def experiment_live(experiment_id: str, limit: int = 3):
    try:
        path = EXPERIMENTS.path(experiment_id)
        status_data = json.loads((path / "status.json").read_text(encoding="utf-8"))
        run_id = status_data.get("run")
        frame_file = path / f"{run_id}.ndjson" if run_id else None
        frames = [json.loads(line) for line in frame_file.read_text(encoding="utf-8").splitlines()[-max(1, min(limit, 30)):]] if frame_file and frame_file.exists() else []
        return {"run": run_id, "frames": frames, "status": status_data}
    except (ValueError, OSError) as exc:
        error(exc)


@app.get("/api/experiments/{experiment_id}/live-network")
def experiment_live_network(experiment_id: str, run_id: str):
    try:
        config = EXPERIMENTS.read(experiment_id)["config"]
        variant = next(item for item in config["variants"] if run_id.startswith(item["key"] + "-r"))
        scenario_id = variant["parameters"].get("network_scenario_id", config["source_network_scenario_id"])
        city_id = config.get("source_city_id")
        city_dir = DATA_DIR / "cities" / city_id if city_id else DATA_DIR
        data_dir = city_dir / "scenarios" / scenario_id if scenario_id else city_dir
        return json.loads((data_dir / "roads.geojson").read_text(encoding="utf-8"))
    except (ValueError, StopIteration, OSError) as exc:
        error(exc)


@app.get("/api/experiments/{experiment_id}/network")
def experiment_network(experiment_id: str, run_id: str):
    try:
        result = EXPERIMENTS.read(experiment_id)
        run = next(item for item in result["results"]["runs"] if item["id"] == run_id)
        scenario_id = run["parameters"].get("network_scenario_id", result["config"]["source_network_scenario_id"])
        city_id = result["config"].get("source_city_id")
        city_dir = DATA_DIR / "cities" / city_id if city_id else DATA_DIR
        data_dir = city_dir / "scenarios" / scenario_id if scenario_id else city_dir
        return json.loads((data_dir / "roads.geojson").read_text(encoding="utf-8"))
    except (ValueError, StopIteration, OSError, TypeError) as exc:
        error(exc)


@app.get("/api/experiments/{experiment_id}/export/{format}")
def export_experiment(experiment_id: str, format: Literal["csv", "json", "pdf"], dataset: str = "summary"):
    try:
        report = EXPERIMENTS.read(experiment_id)
        if not report["results"]:
            raise ValueError("Experimento ainda em execução")
        if format == "csv":
            return Response(csv_export(report, dataset), media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="blu-rotas-{experiment_id}-{dataset}.csv"'})
        if format == "json":
            return Response(json.dumps(report, ensure_ascii=False), media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="blu-rotas-{experiment_id}.json"'})
        return Response(pdf_export(report), media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="blu-rotas-{experiment_id}.pdf"'})
    except ValueError as exc:
        error(exc)


@app.post("/api/graph/path")
def graph_path(body: GraphRequest):
    try:
        distances, previous = SIM.graph.dijkstra(body.start, body.end, method=body.method)
        return {"path": SIM.graph.path(previous, body.start, body.end),
                "distance": distances[body.end], "method": body.method}
    except (KeyError, ValueError) as exc:
        error(exc)


@app.get("/api/municipalities")
def municipalities():
    return MUNICIPALITIES.list()


@app.post("/api/municipalities")
def create_city(body: CityBody):
    try:
        return MUNICIPALITIES.create(body.name)
    except Exception as exc:
        error(exc)


@app.put("/api/municipalities/{city_id}")
def rename_city(city_id: int, body: CityBody):
    try:
        MUNICIPALITIES.rename(city_id, body.name)
        return MUNICIPALITIES.list()
    except Exception as exc:
        error(exc)


@app.delete("/api/municipalities/{city_id}")
def delete_city(city_id: int):
    MUNICIPALITIES.delete(city_id)
    return MUNICIPALITIES.list()


@app.post("/api/municipalities/links")
def create_link(body: LinkBody):
    try:
        MUNICIPALITIES.link(body.a, body.b, body.distance)
        return MUNICIPALITIES.list()
    except Exception as exc:
        error(exc)


@app.get("/api/municipalities/benchmarks")
def municipality_benchmarks(seed: int = 42):
    return scale_experiments(seed)


@app.websocket("/ws")
async def websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            async with LOCK:
                cached = app.state.latest_snapshot
                payload = (cached if SIM.connected and SIM.running and cached
                           and cached.get("run_id") == SIM.run_id else SIM.snapshot())
            await websocket.send_json(payload)
            await asyncio.sleep(STEP_SECONDS if SIM.running else 1)
    except WebSocketDisconnect:
        pass
