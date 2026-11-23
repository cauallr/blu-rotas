import fs from 'node:fs';
import path from 'node:path';

// Cada recorte mantém a consulta abaixo do limite de 50 mil nós da API do OSM.
const longitudes = [-49.101, -49.083333, -49.065667, -49.048];
const latitudes = [-26.936, -26.9135, -26.891];
const elements = { node: new Map(), way: new Map(), relation: new Map() };
let root;

for (let row = 1; row < latitudes.length; row++) {
  for (let column = 1; column < longitudes.length; column++) {
    const bbox = [longitudes[column - 1], latitudes[row - 1], longitudes[column], latitudes[row]];
    const url = `https://api.openstreetmap.org/api/0.6/map?bbox=${bbox}`;
    const response = await fetch(url, {
      headers: { 'User-Agent': 'BLU-ROTAS local academic simulator' },
      signal: AbortSignal.timeout(60_000),
    });
    const xml = await response.text();
    if (!response.ok) throw new Error(`OSM respondeu ${response.status} para ${bbox}: ${xml.slice(0, 200)}`);
    const opening = xml.match(/<osm\b[^>]*>/)?.[0];
    if (!opening || !xml.trimEnd().endsWith('</osm>')) throw new Error(`Resposta OSM inválida para ${bbox}`);
    root ??= opening;

    for (const match of xml.matchAll(/<(node|way|relation)\s+([^>]*?)(?:\/>|>[\s\S]*?<\/\1>)/g)) {
      const [, type, attributes] = match;
      const id = attributes.match(/\bid="(\d+)"/)?.[1];
      if (!id) continue;
      const version = Number(attributes.match(/\bversion="(\d+)"/)?.[1] ?? 0);
      const previous = elements[type].get(id);
      if (!previous || previous.version < version) elements[type].set(id, { xml: match[0], version });
    }
    console.log(`Recorte OSM recebido: ${bbox}`);
  }
}

const bounds = `<bounds minlon="${longitudes[0]}" minlat="${latitudes[0]}" maxlon="${longitudes.at(-1)}" maxlat="${latitudes.at(-1)}"/>`;
const features = Object.values(elements).flatMap(group => [...group.values()].map(element => element.xml));
const target = path.resolve(process.argv[2] || path.join(import.meta.dirname, '../data/blumenau-centro.osm.xml'));
fs.writeFileSync(target, ['<?xml version="1.0" encoding="UTF-8"?>', root, bounds, ...features, '</osm>', ''].join('\n'));
console.log(`Salvo ${target} (${features.length} elementos únicos)`);
