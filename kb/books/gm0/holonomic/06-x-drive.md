---
id: holonomic/06
title: Holonomic Drivetrains: X-Drive
page: Holonomic Drivetrains
type: drivetrain
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/common-mechanisms/drivetrains/holonomic.html
---

X-Drive is a holonomic omni-wheel based drivetrain. This type of drive involves mounting 4 omni wheels at the corner of the robot at a 45 degree angle.

One notable difference between X-Drive and mecanum is strafe speed. While, as mentioned in the mecanum section, the ratio of strafe speed to forward speed is noticeably less than 1, the ratio on an X-Drive is exactly 1 due to the rotational symmetry of the wheel placement. This means that an X-Drive bot's strafe speed and forward speed are equivalent. The drivetrains are slower, however, when strafing at 45° (approximately frac{sqrt{2}}{2} of its forward speed).

Even though X-drive has good turning and acceleration, the main downside to the drive is packaging/form factor. Packaging refers to how easy/convenient the drivetrain fits into the overall design of the robot.

Ideally, the drivetrain should take up as little space as possible to make it easier to design mechanisms around. Because the omni wheels are offset, packaging a X-Drive is more difficult than other types of holonomic drive like mecanum or H-Drive. Also because of the strange packaging, it is relatively difficult to cleanly transfer power from the motors to wheels, meaning that most X-Drives end up being direct-driven, which is bad for the lifespan of the motor gearbox.

**Note:** When using X-Drive, the robot moves forwards/backwards/straight side-to-side sqrt{2} times faster than a drivetrain with wheels in the normal orientation (with the same gear ratio and wheel size).

For an explanation of why exactly this is, see this analysis.

### Advantages

- Good maneuverability and agility
- Good acceleration

### Disadvantages

- Prone to defense, pushed around easily
- Often uses direct drive due to awkward form factor
