# Night City — Master Plan (2026 Restructuring)

_Created by: Arena.ai Agent Mode (AI) — the plan that `source/nc/plan.py` builds._

## 1. Geography

The city sits on a coastal plain in the GTA:SA world frame (origin = city centre, x east, y north,
z = street level). Nothing about its outline is rectangular:

- **East coast**: a wiggly shoreline (`coast_x`) with headlands and bays; the river mouth is carved
  into it as a bay. Beaches slope under the water (`land_s` / `land_h` in `nc/terrain.py`).
- **South bay + sea**: the land rolls away into farmland and open water; the sea floor sits at −9.5 m.
- **North-west mountains**: three overlapping massifs with noisy ridgelines, up to ~395 m.
- **North-east hills**: the hillside district — villas on the slopes, a crest road to a lookout.
- **The river**: a canalised waterway with quay walls and promenades crosses the city east-west
  (grid row `RIVER_J`) and meets the bay at its mouth.
- **The road tunnel** cuts a real trench through the land at its two open mouths (the terrain mesh
  dips into it) and dives under the city blocks.

## 2. The urban grid (2 km × 1.8 km)

A **16 × 14 district grid with variable block sizes** (72–160 m) and street classes:
avenues (36 m), streets (22 m), lanes (14 m). The grid is **clipped by the geography**: every cell
whose footprint touches the water is dropped, so the built footprint follows the coast and the bay —
an organic silhouette, never a rectangle. District letter map (see `nc/plan.py`):

| letter | district | character |
|---|---|---|
| C / F | CBD + financial | setback glass towers, skybridges |
| K | the Arcology | the 70-floor hero block |
| P | the Plaza Gate | twin-pylon landmark |
| H | high-rise residential | slabs + towers + parking garages |
| R / S | residential / suburb | megablocks, row houses, villas, green pockets |
| O / M | old town / market | pastel row houses, tenements, alleys, kiosks |
| E / W | entertainment / waterfront | midrise neon, garages, promenades |
| Q / I / T / Y / X | port + industrial | warehouses, piers, cranes, tanks, container yards |
| V | parks | lawn, meandering paths, ponds, tree clusters |
| ~ | the river | water between the quays |

Palettes are seeded (2077 / 31337) so no two districts read as copies.

## 3. Curved corridors

Four spline corridors (Catmull-Rom → quantised circular-arc segment models, graded):

1. **Bayshore Parkway** — hugs the east coast from the port to the northern bay.
2. **Crest Road** — climbs from the suburb into the north-west mountains (grades to ~100 m).
3. **Airport Parkway** — the southern airfield link.
4. **Harbour Service Road** — along the bay.

Plus two roundabouts, a ramp interchange, two expressways (elevated, with piers), river bridges
(including a cable-stayed hero bridge at the central avenue) and the road tunnel.

## 4. The Night City Metro

A **closed organic loop of ~5.7 km** (dense polyline, ~29 m samples) with six stations:

| station | kind | zone |
|---|---|---|
| DOCKS | elevated | over the harbour |
| BAY | at grade | along the bay shore |
| UNION | underground | beneath the CBD |
| MARKET | underground | beneath the market |
| HEIGHTS | elevated | the western heights |
| WORKS | elevated | the industrial south |

The consist is the **vanilla GTA:SA train** (538 streak + three 570 streakc cars) — the player rides
**inside** a carriage (press E), never on the roof; it sits **on** the running surface (bbox lift).
Guideway pieces are `rail_seg` models (viaduct / ground / tube), stations are the three station
types, portals mark every dive / surface. The loop crosses the river twice **on viaducts** and never
passes below a water polygon (GTA water rule).

## 5. Landmarks & special zones

- the **stadium** (its own city block), the **central station hall**,
- the **airfield** (runway + taxiway + hangars) on the southern flat,
- **harbour piers** reaching into the bay and a **lighthouse** on the head,
- the **arcology** and the **plaza gate** in the CBD,
- **hillside villas** on the north-east slopes, **skybridges** between CBD towers.

## 6. Terrain & LOD

Terrain tiles (470 m, ~26 m resolution) with beach sand, grass, dirt and rock by height/slope,
merged vegetation (pines, broadleaf, bushes, rock outcrops), walkable collision that matches the
visible mesh exactly; coarse no-collision **far rings** for the horizon; a dark sea floor; a
skyline-strip silhouette on the far edges. All tiles are centred on their own height range to stay
inside the COL int16 quantisation.

## 7. Atmosphere

Sky dome with analytic day/sunset/night colours and procedural cloud layers (no cloud-deck noise
texture), photo-style god rays, the 150 % saturation grade (post.fx), district-tinted night
emissives, the rain engine (wet surfaces, puddle ripples, lightning) and the redesigned water
(`water.fx`: depth-graded body colour, wind waves, rain rings, Fresnel sky reflection with a night
city-glow band, sun/moon glints).

## 8. Runtime contract (generated `layout.lua`)

- `NC_OBJECTS` {model index, x, y, z, rz, tag} — tags: ground, bld, park, infra, bridge, tunnel,
  metro, road, terrain, sky, skyline
- `NC_WATER` even-integer quads (river cells + the sea), `NC_POINTS` named tour/teleport points,
  `NC_EXTENT`, `NC_TUNNEL` (the road trench), `NC_SURFACES` (wet.fx surface classes),
  `NC_TOUR` (camera path), **`NC_METRO`** = { total, dw, vx, path = {{x,y,z}…}, stops = {{s,x,y,z,
  kind, name}…} } — `metro.lua` follows the path by arc length with station dwells.
