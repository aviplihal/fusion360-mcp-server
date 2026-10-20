<!--
ROBOT DESIGN FILE FORMAT — kb/designs/<robot>/design.md
One file per robot. It carries what subsystems built in different sessions agree on.
Claude reads it at the start of every subsystem session (robot_design action=get, or
the work_on_subsystem prompt) and updates it at the end. Humans may edit it by hand.
`robot_design action=create` copies this template and drops this comment.

Sections (headings are fixed; tools find them by name):
  ## Frame               `frame:` line, one-line JSON. Default: origin at the centre of the
                         robot footprint on the field tiles, +x right, +y front, +z up, cm.
                         Set the Fusion document to Z up so its axes match.
  ## Subsystem: <key>    one per subsystem (drivetrain, intake, transfer, shooter, turret, or
                         any other key, lowercase with dashes). First line `spec:` + one-line
                         JSON, then free notes for humans. spec fields:
     status      "not started" | "concept" | "built" | "accepted"
     component   name of the subsystem's top-level Fusion component
     envelope    stowed box in robot coordinates, cm: {"min": [x, y, z], "max": [x, y, z]},
                 or null. Must sit inside the 45.7 cm start cube: x,y in ±22.85, z 0..45.7
     extended    fully extended box (same form) for subsystems that move out, or null.
                 Its footprint must fit 45.7 × 61 and its top 73.65 cm (R105)
     motors      whole number; all subsystems together ≤ 8 (R503)
     servos      whole number; all subsystems together ≤ 8 (R503)
     interfaces  [{"name": "…", "where": "…", "provided_by": "<subsystem or COTS part>"}]
                 holes, shafts, plates this subsystem mounts to or offers
     based_on    KB entry ids it was designed from (kb_search / kb_get ids)
  ## Open questions      `- [ ] question` lines; resolved ones become `- [x] … → answer`
  ## Change log          `- YYYY-MM-DD what changed` (robot_design adds a line per update)
robot_design refuses updates that break the actuator totals or put an envelope outside the
start cube. Keep notes short: this file is read every session.
-->
# Robot design: {robot}

Created {date} · season {season} · units cm.

## Frame
frame: {"origin": "centre of the robot footprint, on the field tiles", "x": "right", "y": "front", "z": "up", "units": "cm"}
Start cube (R102): x −22.85..22.85, y −22.85..22.85, z 0..45.7.

## Subsystem: drivetrain
spec: {"status": "not started", "component": "Drivetrain", "envelope": null, "extended": null, "motors": 0, "servos": 0, "interfaces": [], "based_on": []}
Notes:

## Subsystem: intake
spec: {"status": "not started", "component": "Intake", "envelope": null, "extended": null, "motors": 0, "servos": 0, "interfaces": [], "based_on": []}
Notes:

## Subsystem: transfer
spec: {"status": "not started", "component": "Transfer", "envelope": null, "extended": null, "motors": 0, "servos": 0, "interfaces": [], "based_on": []}
Notes:

## Subsystem: shooter
spec: {"status": "not started", "component": "Shooter", "envelope": null, "extended": null, "motors": 0, "servos": 0, "interfaces": [], "based_on": []}
Notes:

## Subsystem: turret
spec: {"status": "not started", "component": "Turret", "envelope": null, "extended": null, "motors": 0, "servos": 0, "interfaces": [], "based_on": []}
Notes: optional; delete this section if the robot has no turret.

## Open questions

## Change log
- {date} created from the template
