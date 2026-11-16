import fs from 'node:fs';
import path from 'node:path';

// Recorte limitado pelo limite de 50 mil nós da API principal do OSM.
const bbox = '-49.077,-26.928,-49.055,-26.906';
const url = `https://www.openstreetmap.org/api/0.6/map?bbox=${bbox}`;
const response = await fetch(url, { headers: { 'User-Agent': 'BLU-ROTAS local academic simulator' } });
if (!response.ok) throw new Error(`OSM respondeu ${response.status}: ${(await response.text()).slice(0, 200)}`);
const xml = await response.text();
if (!xml.includes('<osm')) throw new Error('Resposta OSM inválida');
const target = path.resolve(import.meta.dirname, '../data/blumenau-centro.osm.xml');
fs.writeFileSync(target, xml);
console.log(`Salvo ${target} (${xml.length} caracteres)`);
