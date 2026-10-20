# Design rules for custom parts

Loaded every session. Model custom parts to these numbers. All numbers are starting defaults, **unverified — confirm with the team**; replace each with the measured value and delete its tag. Fusion works in cm; the tables are in mm.

## Questions for the team
1. FDM: which printers and materials (PLA, PETG, other)? Print a test card with 3, 4, 5, 8 and 14 mm holes: what do they measure?
2. FDM: bearing pockets: press fit or glued slip fit? Which pocket size held a goBILDA 14 mm OD flanged bearing best?
3. FDM: do we use heat-set inserts? Which brand and sizes (M3, M4)?
4. FDM: default walls, infill and layer height for structural parts?
5. Laser wood: which laser, bed size, and measured kerf on our plywood? Which thicknesses do we stock?
6. Laser aluminum: which service, which alloys and thicknesses, minimum hole size and hole-to-edge distance, can they bend, lead time and cost?
7. Aluminum: do we tap holes or always use nuts? Any countersinking?
8. Fasteners: which M4 screw lengths and nuts do we stock (nylock, keps)? Threadlocker?
9. Should custom plates always match the goBILDA 8 mm grid so COTS parts bolt on?
10. Is the robot's Fusion document set to Z up?

## Choosing a process
| Need | Use |
|---|---|
| Flat structural plate, final robot | Laser aluminum (service; plan for lead time) |
| Flat plate, prototype or low load | Laser wood |
| 3D shape, spacer, bracket, guide, hood, low/medium load | FDM |
| Shafts, bearings, motors, channels, hubs | goBILDA COTS (`kb_find_part`) |

## FDM (0.4 mm nozzle)
| Feature | Model at | Note |
|---|---|---|
| M3 clearance hole | 3.4 mm | **unverified — confirm with the team** |
| M4 clearance hole | 4.4 mm | **unverified — confirm with the team** |
| Holes in general | nominal + 0.3 mm | prints shrink holes; **unverified — confirm with the team** |
| 8 mm REX shaft, free spin | REX profile + 0.3 mm | **unverified — confirm with the team** |
| Bearing pocket, 14 mm OD flanged (press) | 14.05 mm | **unverified — confirm with the team** |
| Bearing pocket, 14 mm OD flanged (slip + glue) | 14.2 mm | **unverified — confirm with the team** |
| Heat-set insert M3 | 4.0 mm hole, depth insert + 1 mm | **unverified — confirm with the team** |
| Heat-set insert M4 | 5.6 mm hole, depth insert + 1 mm | **unverified — confirm with the team** |
| Wall around an insert or screw | ≥ 2 mm | **unverified — confirm with the team** |
| Minimum wall | 1.2 mm (3 perimeters) | **unverified — confirm with the team** |
| Structural part | 4 walls, 40 % gyroid, 0.2 mm layers | **unverified — confirm with the team** |
| Non-structural part | 3 walls, 15 % infill | **unverified — confirm with the team** |
| Overhang without support | ≤ 45° | **unverified — confirm with the team** |

Orient prints so the load runs along the layers, not across them. Fillet inside corners (≥ 1 mm) on loaded brackets.

## Laser-cut wood (prototypes)
| Feature | Value | Note |
|---|---|---|
| Plywood thicknesses | 3 mm, 6 mm | **unverified — confirm with the team** |
| Kerf (beam width) | 0.2 mm | **unverified — confirm with the team** |
| Press-fit tab/slot | slot = thickness − 0.1 mm | **unverified — confirm with the team** |
| Hole and slot sizes | model nominal; the laser makes them ~kerf larger | **unverified — confirm with the team** |
| Minimum hole | ≥ thickness | **unverified — confirm with the team** |
| Hole to edge | ≥ 1.5 × hole diameter | **unverified — confirm with the team** |
| Bed size | ? | **unverified — confirm with the team** |

## Laser-cut aluminum (outside service)
| Feature | Value | Note |
|---|---|---|
| Alloy | 5052-H32 (bendable) or 6061-T6 (stiffer) | **unverified — confirm with the team** |
| Thicknesses | 1.6 mm (1/16 in), 2.3 mm (0.090 in), 3.2 mm (1/8 in) | **unverified — confirm with the team** |
| Minimum hole | ≥ thickness | **unverified — confirm with the team** |
| Hole to edge | ≥ thickness and ≥ 1 × hole diameter | **unverified — confirm with the team** |
| Minimum slot or web width | ≥ thickness | **unverified — confirm with the team** |
| Kerf | the service compensates; model nominal | **unverified — confirm with the team** |
| Bends (if offered) | inside radius ≈ thickness, flange ≥ 4 × thickness | **unverified — confirm with the team** |

Pocket plates to save weight but keep ≥ 4 mm webs around bolt holes.

## Fasteners and goBILDA standard
| Item | Value | Note |
|---|---|---|
| Standard screw | M4 × 0.7 socket head, goBILDA lengths | **unverified — confirm with the team** |
| Nut | M4 nylock | **unverified — confirm with the team** |
| goBILDA hole pattern | M4 holes on an 8 mm grid | **unverified — confirm with the team** |
| goBILDA shaft | 8 mm REX; bearings 14 mm OD flanged | **unverified — confirm with the team** |
| Clearance hole in custom parts | FDM 4.4 mm, laser 4.2 mm | **unverified — confirm with the team** |

Put holes in custom plates on the goBILDA 8 mm grid where possible, so channels, motor mounts and pillow blocks bolt straight on (`join_on_holes`).
