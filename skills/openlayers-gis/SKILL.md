---
name: openlayers-gis
description: >
  OpenLayers (ol) map development — layers, views, projections, features, interactions.
  Use when editing maps, GIS, coordinates, WMS/WFS, GeoJSON, or ol/Leaflet code.
---

# OpenLayers / GIS

## Setup

- Import only needed `ol/*` modules (tree-shaking)
- Default view: `EPSG:3857` for web tiles; transform user coords from `EPSG:4326` via `fromLonLat` / `toLonLat`

## Layers

- `TileLayer` + `OSM` / `XYZ` for basemaps
- `VectorLayer` + `VectorSource` for GeoJSON/features
- Set `zIndex` when stacking; one basemap, vectors on top

## Map lifecycle (Angular)

- Create map in `ngAfterViewInit` or `afterNextRender` on a container with explicit height
- `map.setTarget(null)` + dispose listeners on destroy
- Resize: `map.updateSize()` when container size changes

## Projections

- Never mix lon/lat and Web Mercator without `transform`
- Document which CRS each API returns

## Leaflet coexistence

- If project has both `ol` and `leaflet`, match existing component's library — don't mix in one map instance

## Performance

- Cluster or simplify large feature sets
- `useGeographic()` (ol 9+) when working in lon/lat end-to-end
