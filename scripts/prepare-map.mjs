import fs from 'node:fs';
import path from 'node:path';

const data = path.resolve(import.meta.dirname, '../data');
const xml = fs.readFileSync(path.join(data, 'blumenau-centro.osm.xml'), 'utf8');
const nodes = new Map();
const places = [];
const decode = value => value.replaceAll('&amp;', '&').replaceAll('&quot;', '"').replaceAll('&apos;', "'").replaceAll('&lt;', '<').replaceAll('&gt;', '>');
const attrs = source => Object.fromEntries([...source.matchAll(/(\w+)="([^"]*)"/g)].map(match => [match[1], decode(match[2])]));
const tags = body => Object.fromEntries([...body.matchAll(/<tag\s+([^>]+?)\s*\/>/g)].map(match => {
  const tag = attrs(match[1]);
  return [tag.k, tag.v];
}));
for (const match of xml.matchAll(/<node\s+([^>]*?)(?:\s*\/>|>([\s\S]*?)<\/node>)/g)) {
  const a = attrs(match[1]);
  if (!a.id || !a.lat || !a.lon) continue;
  const coord = [Number(a.lon), Number(a.lat)];
  nodes.set(a.id, coord);
  if (match[2]) {
    const t = tags(match[2]);
    if (['suburb', 'neighbourhood'].includes(t.place) && t.name) {
      places.push({ type: 'Feature', geometry: { type: 'Point', coordinates: coord }, properties: { name: t.name, place: t.place, osm_id: a.id } });
    }
  }
}
const roads = [];
const driving = new Set(['motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified', 'residential', 'living_street', 'service', 'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link']);
for (const match of xml.matchAll(/<way\s+([^>]*?)>([\s\S]*?)<\/way>/g)) {
  const a = attrs(match[1]);
  const t = tags(match[2]);
  if (!driving.has(t.highway) || t.area === 'yes') continue;
  const coordinates = [...match[2].matchAll(/<nd ref="(\d+)"\s*\/>/g)].map(item => nodes.get(item[1])).filter(Boolean);
  if (coordinates.length < 2) continue;
  roads.push({ type: 'Feature', id: a.id, geometry: { type: 'LineString', coordinates },
    properties: { id: a.id, name: t.name || 'Via sem nome', highway: t.highway, oneway: t.oneway || 'no', bridge: t.bridge || 'no' } });
}
fs.writeFileSync(path.join(data, 'roads.geojson'), JSON.stringify({ type: 'FeatureCollection', features: roads }));
fs.writeFileSync(path.join(data, 'places.geojson'), JSON.stringify({ type: 'FeatureCollection', features: places }));
console.log(`${nodes.size} nós OSM, ${roads.length} vias e ${places.length} bairros extraídos.`);
