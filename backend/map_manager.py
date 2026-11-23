"""Importação local de mapas OSM XML em camadas independentes da cidade original."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4

import sumolib

from .engine import BLUMENAU_NETWORK_VERSION


DRIVING = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
           "residential", "living_street", "service", "motorway_link", "trunk_link",
           "primary_link", "secondary_link", "tertiary_link"}


def _tags(element: ET.Element) -> dict[str, str]:
    return {tag.attrib.get("k", ""): tag.attrib.get("v", "") for tag in element.findall("tag")}


def _inside(point: tuple[float, float], bounds: tuple[float, float, float, float]) -> bool:
    west, south, east, north = bounds
    return west <= point[0] <= east and south <= point[1] <= north


def prepare_osm(root: ET.Element, bounds: tuple[float, float, float, float] | None):
    if root.tag != "osm":
        raise ValueError("Envie um arquivo OpenStreetMap XML (.osm.xml)")
    nodes = {node.attrib["id"]: (float(node.attrib["lon"]), float(node.attrib["lat"]))
             for node in root.findall("node") if all(key in node.attrib for key in ("id", "lon", "lat"))}
    ways = [way for way in root.findall("way") if _tags(way).get("highway") in DRIVING and _tags(way).get("area") != "yes"]
    if bounds:
        ways = [way for way in ways if any(ref.attrib.get("ref") in nodes and _inside(nodes[ref.attrib["ref"]], bounds)
                                       for ref in way.findall("nd"))]
        needed = {ref.attrib["ref"] for way in ways for ref in way.findall("nd") if ref.attrib.get("ref") in nodes}
        keep_nodes = [node for node in root.findall("node") if node.attrib.get("id") in needed or
                      (node.attrib.get("id") in nodes and _inside(nodes[node.attrib["id"]], bounds) and
                       _tags(node).get("place") in {"suburb", "neighbourhood"})]
        root[:] = keep_nodes + ways
    if len(ways) < 5:
        raise ValueError("A área escolhida contém menos de cinco vias dirigíveis")
    roads = []
    all_coords = []
    for way in ways:
        tags = _tags(way)
        coordinates = [nodes[ref.attrib["ref"]] for ref in way.findall("nd") if ref.attrib.get("ref") in nodes]
        if len(coordinates) < 2:
            continue
        roads.append({"type": "Feature", "id": way.attrib["id"],
                      "geometry": {"type": "LineString", "coordinates": coordinates},
                      "properties": {"id": way.attrib["id"], "name": tags.get("name", "Via sem nome"),
                                     "highway": tags["highway"], "oneway": tags.get("oneway", "no"),
                                     "bridge": tags.get("bridge", "no")}})
        all_coords.extend(coordinates)
    if not roads:
        raise ValueError("Nenhuma via válida no arquivo")
    places = []
    for node in root.findall("node"):
        tags = _tags(node)
        if node.attrib.get("id") in nodes and tags.get("place") in {"suburb", "neighbourhood"} and tags.get("name"):
            places.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": nodes[node.attrib["id"]]},
                           "properties": {"name": tags["name"], "place": tags["place"], "osm_id": node.attrib["id"]}})
    west, east = min(point[0] for point in all_coords), max(point[0] for point in all_coords)
    south, north = min(point[1] for point in all_coords), max(point[1] for point in all_coords)
    return {"type": "FeatureCollection", "features": roads}, {"type": "FeatureCollection", "features": places}, [west, south, east, north]


class MapManager:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.root = self.data_dir / "cities"
        self.root.mkdir(parents=True, exist_ok=True)
        binary = os.environ.get("NETCONVERT_BINARY")
        if not binary and os.environ.get("SUMO_BINARY"):
            binary = str(Path(os.environ["SUMO_BINARY"]).with_name("netconvert.exe"))
        self.netconvert = binary or "netconvert"

    def get(self, city_id: str) -> dict:
        if len(city_id) != 12 or any(char not in "0123456789abcdef" for char in city_id):
            raise ValueError("ID de cidade inválido")
        path = self.root / city_id / "manifest.json"
        if not path.exists():
            raise ValueError("Cidade não encontrada")
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self) -> list[dict]:
        base = {"id": None, "name": "Blumenau central", "region": "Centro e bairros vizinhos",
                "source": "OpenStreetMap", "bounds": [-49.101, -26.936, -49.048, -26.891],
                "network_version": BLUMENAU_NETWORK_VERSION}
        imported = []
        for file in self.root.glob("*/manifest.json"):
            try:
                item = json.loads(file.read_text(encoding="utf-8"))
                item["scenarios"] = [path.parent.name for path in (file.parent / "scenarios").glob("*/manifest.json")]
                imported.append(item)
            except (OSError, ValueError):
                pass
        return [base, *sorted(imported, key=lambda item: item["id"], reverse=True)]

    def import_xml(self, contents: bytes, name: str, region: str = "",
                   bounds: tuple[float, float, float, float] | None = None) -> dict:
        if len(contents) > 250_000_000:
            raise ValueError("Arquivo maior que 250 MB")
        city_id = uuid4().hex[:12]
        target = self.root / city_id
        target.mkdir(parents=True)
        try:
            tree = ET.ElementTree(ET.fromstring(contents))
            roads, places, actual_bounds = prepare_osm(tree.getroot(), bounds)
            source = target / "source.osm.xml"
            net_path = target / "network.net.xml"
            tree.write(source, encoding="utf-8", xml_declaration=True)
            result = subprocess.run([self.netconvert, "--osm-files", str(source), "--output-file", str(net_path),
                "--geometry.remove", "--ramps.guess", "true", "--junctions.join", "true",
                "--tls.guess", "true", "--tls.guess-signals", "true", "--tls.default-type", "static",
                "--remove-edges.isolated", "true", "--no-turnarounds", "true"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=300)
            if result.returncode or not net_path.exists():
                raise ValueError("netconvert falhou: " + (result.stderr or result.stdout)[-700:])
            net = sumolib.net.readNet(str(net_path), withInternal=True)
            drivable = [edge for edge in net.getEdges() if edge.allows("passenger") and not edge.getID().startswith(":")]
            if len(drivable) < 5:
                raise ValueError("A rede SUMO importada não contém vias trafegáveis suficientes")
            (target / "roads.geojson").write_text(json.dumps(roads, ensure_ascii=False), encoding="utf-8")
            (target / "places.geojson").write_text(json.dumps(places, ensure_ascii=False), encoding="utf-8")
            manifest = {"id": city_id, "name": name.strip(), "region": region.strip(),
                        "source": "Arquivo OSM XML local", "bounds": actual_bounds,
                        "center": [(actual_bounds[0] + actual_bounds[2]) / 2, (actual_bounds[1] + actual_bounds[3]) / 2],
                        "road_features": len(roads["features"]), "drivable_edges": len(drivable),
                        "network_version": hashlib.sha256(net_path.read_bytes()).hexdigest()[:16],
                        "scenarios": []}
            (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            return manifest
        except Exception:
            if target.resolve().is_relative_to(self.root.resolve()) and target.resolve() != self.root.resolve():
                shutil.rmtree(target)
            raise
