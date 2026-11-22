"""Reconstrói uma rede SUMO para ruas fictícias, sem alterar o OSM original."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4

import sumolib


def way_id_from_edge(edge_id: str) -> str:
    match = re.match(r"^-?(\d+)", edge_id)
    if not match:
        raise ValueError("A conexão deve começar e terminar em ruas da fonte OSM")
    return match.group(1)


def _project(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]):
    cos_lat = math.cos(math.radians(point[1]))
    ax, ay = a[0] * cos_lat, a[1]
    bx, by = b[0] * cos_lat, b[1]
    px, py = point[0] * cos_lat, point[1]
    dx, dy = bx - ax, by - ay
    fraction = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy))) if dx * dx + dy * dy else 0
    snapped = (a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction)
    metres = math.hypot((snapped[0] - point[0]) * 111_000 * cos_lat, (snapped[1] - point[1]) * 111_000)
    return metres, fraction, snapped


def _tag(element: ET.Element, key: str, value: str | None):
    for child in list(element.findall("tag")):
        if child.attrib.get("k") == key:
            element.remove(child)
    if value is not None:
        ET.SubElement(element, "tag", {"k": key, "v": value})


def _metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot((a[0] - b[0]) * 111_000 * math.cos(math.radians(a[1])),
                      (a[1] - b[1]) * 111_000)


class ScenarioNetwork:
    def __init__(self, base_dir: Path, netconvert: str | None = None):
        self.base_dir = Path(base_dir)
        self.root = self.base_dir / "scenarios"
        self.root.mkdir(parents=True, exist_ok=True)
        binary = netconvert or os.environ.get("NETCONVERT_BINARY")
        if not binary and os.environ.get("SUMO_BINARY"):
            binary = str(Path(os.environ["SUMO_BINARY"]).with_name("netconvert.exe"))
        self.netconvert = binary or "netconvert"

    def list(self) -> list[dict]:
        manifests = []
        for path in self.root.glob("*/manifest.json"):
            try:
                manifests.append(json.loads(path.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
        return sorted(manifests, key=lambda item: item["id"], reverse=True)

    def get(self, scenario_id: str) -> dict:
        if not re.fullmatch(r"[0-9a-f]{12}", scenario_id):
            raise ValueError("ID de cenário inválido")
        path = self.root / scenario_id / "manifest.json"
        if not path.exists():
            raise ValueError("Cenário viário não encontrado")
        return json.loads(path.read_text(encoding="utf-8"))

    def build(self, roads: list[dict], name: str = "Cidade modificada",
              road_edits: list[dict] | None = None, signals: list[dict] | None = None) -> dict:
        road_edits, signals = road_edits or [], signals or []
        if not roads and not road_edits and not signals:
            raise ValueError("O cenário precisa ter ao menos uma modificação")
        scenario_id = uuid4().hex[:12]
        output_dir = self.root / scenario_id
        output_dir.mkdir(parents=True)
        source = self.base_dir / "source.osm.xml"
        if not source.exists():
            source = self.base_dir / "blumenau-centro.osm.xml"
        if not source.exists():
            raise ValueError("Fonte OSM original indisponível")
        try:
            tree = ET.parse(source)
            root = tree.getroot()
            nodes = {node.attrib["id"]: (float(node.attrib["lon"]), float(node.attrib["lat"]))
                     for node in root.findall("node")}
            longitudes = [point[0] for point in nodes.values()]
            latitudes = [point[1] for point in nodes.values()]
            bounds = (min(longitudes) - .005, min(latitudes) - .005,
                      max(longitudes) + .005, max(latitudes) + .005)
            ways = {way.attrib["id"]: way for way in root.findall("way")}
            base_roads = json.loads((self.base_dir / "roads.geojson").read_text(encoding="utf-8"))
            for edit in road_edits:
                way = ways.get(str(edit["way_id"]))
                if way is None:
                    raise ValueError("A via editada não existe no OSM original")
                direction = edit["direction"]
                forward = int(edit["lanes_forward"])
                backward = int(edit["lanes_backward"])
                if direction not in {"both", "forward", "reverse"} or not 0 <= forward <= 4 or not 0 <= backward <= 4:
                    raise ValueError("Sentido ou número de faixas inválido")
                if ((direction == "both" and (forward < 1 or backward < 1)) or
                    (direction == "forward" and (forward < 1 or backward != 0)) or
                    (direction == "reverse" and (backward < 1 or forward != 0))):
                    raise ValueError("Configure ao menos uma faixa em cada sentido permitido")
                _tag(way, "oneway", {"both": "no", "forward": "yes", "reverse": "-1"}[direction])
                _tag(way, "lanes", str(forward + backward))
                _tag(way, "lanes:forward", str(forward) if direction == "both" else None)
                _tag(way, "lanes:backward", str(backward) if direction == "both" else None)
                _tag(way, "maxspeed", str(edit["speed_kmh"]))
                if edit.get("name"):
                    _tag(way, "name", edit["name"].strip())
                    for feature in base_roads["features"]:
                        if str(feature["properties"].get("id")) == str(edit["way_id"]):
                            feature["properties"]["name"] = edit["name"].strip()
            insertions: dict[str, list[tuple[int, float, str]]] = {}
            new_nodes: list[ET.Element] = []
            new_ways: list[ET.Element] = []
            normalized = []
            for ordinal, spec in enumerate(roads):
                if spec["origin_way"] not in ways or spec["destination_way"] not in ways:
                    raise ValueError("A rua fictícia deve ligar dois trechos presentes no OSM original")
                if spec["origin_way"] == spec["destination_way"]:
                    raise ValueError("Escolha vias diferentes para uma conexão física nova")
                endpoints = []
                for side in ("origin", "destination"):
                    way_id = spec[f"{side}_way"]
                    refs = [node.attrib["ref"] for node in ways[way_id].findall("nd")]
                    point = tuple(spec[f"{side}_coordinates"])
                    choices = [(*_project(point, nodes[refs[index]], nodes[refs[index + 1]]), index)
                               for index in range(len(refs) - 1) if refs[index] in nodes and refs[index + 1] in nodes]
                    if not choices:
                        raise ValueError("Via OSM sem geometria válida")
                    metres, fraction, snapped, segment = min(choices, key=lambda item: item[0])
                    if metres > 25:
                        raise ValueError("O ponto está muito distante da rua OSM escolhida")
                    if fraction < 0.02:
                        node_id = refs[segment]
                        snapped = nodes[node_id]
                    elif fraction > 0.98:
                        node_id = refs[segment + 1]
                        snapped = nodes[node_id]
                    else:
                        node_id = str(9_000_000_000_000_000 + ordinal * 2 + (side == "destination"))
                        new_nodes.append(ET.Element("node", {"id": node_id, "visible": "true", "lat": str(snapped[1]), "lon": str(snapped[0])}))
                        nodes[node_id] = snapped
                        insertions.setdefault(way_id, []).append((segment, fraction, node_id))
                    endpoints.append((node_id, snapped))
                road_id = str(spec.get("id") or (8_000_000_000_000_000 + int(uuid4().hex[:10], 16)))
                bends = [tuple(point) for point in spec.get("via", [])]
                if len(bends) > 12 or any(not bounds[0] <= lon <= bounds[2] or not bounds[1] <= lat <= bounds[3]
                                          for lon, lat in bends):
                    raise ValueError("Os pontos intermediários da rua estão fora da área permitida")
                geometry = [endpoints[0][1], *bends, endpoints[1][1]]
                length_m = sum(_metres(a, b) for a, b in zip(geometry, geometry[1:]))
                if length_m < 8 or length_m > 3000:
                    raise ValueError("A nova rua deve medir entre 8 m e 3 km")
                way = ET.Element("way", {"id": road_id, "visible": "true"})
                new_ways.append(way)
                ET.SubElement(way, "nd", {"ref": endpoints[0][0]})
                for bend_index, bend in enumerate(bends):
                    bend_id = str(9_100_000_000_000_000 + ordinal * 20 + bend_index)
                    new_nodes.append(ET.Element("node", {"id": bend_id, "visible": "true", "lat": str(bend[1]), "lon": str(bend[0])}))
                    nodes[bend_id] = bend
                    ET.SubElement(way, "nd", {"ref": bend_id})
                ET.SubElement(way, "nd", {"ref": endpoints[1][0]})
                direction = spec.get("direction", "forward" if spec["oneway"] else "both")
                if direction not in {"both", "forward", "reverse"}:
                    raise ValueError("Sentido da rua fictícia inválido")
                for key, value in {"highway": "residential", "name": spec["name"],
                                   "oneway": {"both": "no", "forward": "yes", "reverse": "-1"}[direction],
                                   "maxspeed": str(spec["speed_kmh"]), "lanes": str(spec["lanes"])}.items():
                    ET.SubElement(way, "tag", {"k": key, "v": value})
                normalized.append({**spec, "id": road_id, "origin_coordinates": list(endpoints[0][1]),
                                   "destination_coordinates": list(endpoints[1][1]), "via": [list(point) for point in bends],
                                   "direction": direction, "oneway": direction != "both", "length_m": round(length_m, 1)})
                base_roads["features"].append({"type": "Feature", "id": road_id,
                    "geometry": {"type": "LineString", "coordinates": [list(point) for point in geometry]},
                    "properties": {"id": road_id, "name": spec["name"], "highway": "residential",
                                   "oneway": {"both": "no", "forward": "yes", "reverse": "-1"}[direction],
                                   "bridge": "no", "fictional": True}})
            for way_id, entries in insertions.items():
                way = ways[way_id]
                refs = [node.attrib["ref"] for node in way.findall("nd")]
                for node in way.findall("nd"):
                    way.remove(node)
                ordered = sorted(entries, key=lambda item: (item[0], item[1]))
                next_insert = 0
                for index, ref in enumerate(refs):
                    way.insert(index + next_insert, ET.Element("nd", {"ref": ref}))
                    while next_insert < len(ordered) and ordered[next_insert][0] == index:
                        next_insert += 1
                        way.insert(index + next_insert, ET.Element("nd", {"ref": ordered[next_insert - 1][2]}))
            first_way = next(index for index, child in enumerate(root) if child.tag == "way")
            for offset, node in enumerate(new_nodes):
                root.insert(first_way + offset, node)
            first_relation = next((index for index, child in enumerate(root) if child.tag == "relation"), len(root))
            for offset, way in enumerate(new_ways):
                root.insert(first_relation + offset, way)
            node_elements = {node.attrib["id"]: node for node in root.findall("node")}
            node_ways: dict[str, set[str]] = {}
            for way in root.findall("way"):
                if not any(tag.attrib.get("k") == "highway" for tag in way.findall("tag")):
                    continue
                for nd in way.findall("nd"):
                    node_ways.setdefault(nd.attrib["ref"], set()).add(way.attrib["id"])
            normalized_signals = []
            for signal in signals:
                point = tuple(signal["coordinates"])
                candidates = [(_metres(point, coordinate), node_id) for node_id, coordinate in nodes.items()
                              if len(node_ways.get(node_id, ())) >= 2]
                if not candidates:
                    raise ValueError("Não há cruzamento OSM adequado para o semáforo")
                distance, node_id = min(candidates)
                if distance > 25:
                    raise ValueError("Semáforo precisa estar a até 25 m de um cruzamento real ou de uma ligação construída")
                _tag(node_elements[node_id], "highway", "traffic_signals")
                normalized_signals.append({"node_id": node_id, "coordinates": list(nodes[node_id])})
            osm_path = output_dir / "source.osm.xml"
            net_path = output_dir / "network.net.xml"
            tree.write(osm_path, encoding="utf-8", xml_declaration=True)
            command = [self.netconvert, "--osm-files", str(osm_path), "--output-file", str(net_path),
                       "--output.street-names", "true",
                       "--geometry.remove", "--ramps.guess", "true", "--junctions.join", "true",
                       "--tls.guess", "true", "--tls.default-type", "static",
                       "--remove-edges.isolated", "true", "--no-turnarounds", "true"]
            result = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", timeout=180)
            if result.returncode or not net_path.exists():
                raise ValueError("netconvert não conseguiu construir a rua: " + (result.stderr or result.stdout)[-600:])
            net = sumolib.net.readNet(str(net_path), withInternal=True)
            for signal in normalized_signals:
                x, y = net.convertLonLat2XY(*signal["coordinates"])
                if not any(node.getType() == "traffic_light" and math.dist(node.getCoord(), (x, y)) <= 25
                           for node in net.getNodes()):
                    raise ValueError("O SUMO não criou semáforo nesse cruzamento; escolha outro ponto")
            edge_ids = {edge.getID().lstrip("-").split("#")[0] for edge in net.getEdges() if edge.allows("passenger")}
            missing = [road["id"] for road in normalized if road["id"] not in edge_ids]
            if missing:
                raise ValueError("A rede SUMO descartou uma conexão fictícia; verifique os pontos: " + ", ".join(missing)
                                 + "\nID parecidos: " + repr([edge.getID() for edge in net.getEdges() if any(road in edge.getID() for road in missing)][:8])
                                 + "\n" + result.stdout[-500:] + result.stderr[-500:])
            for edit in road_edits:
                matches = [edge for edge in net.getEdges() if edge.allows("passenger")
                           and edge.getID().lstrip("-").split("#")[0] == str(edit["way_id"])]
                forward = [edge for edge in matches if not edge.getID().startswith("-")]
                backward = [edge for edge in matches if edge.getID().startswith("-")]
                if (not matches or bool(forward) != (edit["lanes_forward"] > 0)
                    or bool(backward) != (edit["lanes_backward"] > 0)):
                    raise ValueError("O SUMO não preservou o sentido solicitado para a via editada")
                if (forward and max(len(edge.getLanes()) for edge in forward) < edit["lanes_forward"]
                    or backward and max(len(edge.getLanes()) for edge in backward) < edit["lanes_backward"]):
                    raise ValueError("O SUMO não preservou o número de faixas solicitado")
            for road in normalized:
                created = [edge for edge in net.getEdges() if edge.getID().lstrip("-").split("#")[0] == road["id"]]
                created_ids = {edge.getID() for edge in created}
                incoming = any(neighbor.getID() not in created_ids and neighbor.allows("passenger")
                               for edge in created for neighbor in edge.getIncoming())
                outgoing = any(neighbor.getID() not in created_ids and neighbor.allows("passenger")
                               for edge in created for neighbor in edge.getOutgoing())
                if not incoming or not outgoing:
                    raise ValueError("A rua fictícia ficou sem conexões dirigíveis com a rede original")
            (output_dir / "roads.geojson").write_text(json.dumps(base_roads, ensure_ascii=False), encoding="utf-8")
            shutil.copy2(self.base_dir / "places.geojson", output_dir / "places.geojson")
            version = hashlib.sha256(net_path.read_bytes()).hexdigest()[:16]
            manifest = {"id": scenario_id, "name": name, "source": "OSM Blumenau + alterações fictícias",
                        "network_version": version, "roads": normalized, "road_edits": road_edits,
                        "signals": normalized_signals,
                        "network_path": "network.net.xml", "map_path": "roads.geojson"}
            (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            return manifest
        except Exception:
            if output_dir.resolve().is_relative_to(self.root.resolve()) and output_dir.resolve() != self.root.resolve():
                shutil.rmtree(output_dir)
            raise
