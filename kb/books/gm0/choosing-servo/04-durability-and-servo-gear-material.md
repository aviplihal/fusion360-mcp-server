---
id: choosing-servo/04
title: Durability and Servo Gear Material
page: Choosing a Servo
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/power-and-electronics/servo-guide/choosing-servo.html
---

The two things that threaten a servo's longevity are the internal motor burning out and, more commonly, the gears stripping inside the servo. A motor burning out is pretty uncommon, but it can happen under large loads for a prolonged amount of time.

**Caution:** You should **never** stall a servo against an immovable object.

Gear stripping is a problem which can occur when the torque needed to actuate a component exceeds that of the servo's maximum torque. There are two main cases when this can occur.

- Shock load from external force can strip the gears. An example could be the component slamming into the field wall or another robot.
- Shock load from reversing directions on an object that is too heavy can strip the gears. Torque increases with mass and also distance from the center of rotation. If the component being actuated is far from the servo, the long lever arm means larger torque. Furthermore, if the component is moving, reversing direction also will require more torque. Thus, the principle is that components should be light and not reverse direction suddenly to prolong servo life.

Shock load resistance is impacted directly by the material the gears are made from. This ranges from plastic to titanium, so let's go down the list, starting from the weakest.

- **Plastic** (usually Nylon): With low power servos, these can be okay if you ensure they are not subjected to shock loads. Generally used for applications in model airplanes such as ailerons. FTC applications include light load mechanisms which will not have direct contact with any game elements or the field. An example could be a servo that opens a trapdoor or moves game elements within the robot.
  - **Karbonite**: Hitec's gear plastic is more durable than Nylon and wears less over time, but it can still strip easily under the shock loads found in FTC.
- **Brass**: Brass gears are stronger than plastic, but also suffer greatly when faced with shock loads in FTC such as intake wrists and deposit buckets. Brass gears are found on slightly higher end servos such as the original REV Smart Robot Servo.
- **Steel**: This is where we start getting big. Steel gears are very durable and you'll have a tough time stripping these. The goBILDA Proton servos, goBILDA Dual Mode servos, REV V2 Smart Robot Servos, and Axon servos are all examples of steel gear servo.
- **Titanium**: Titanium is where you get into really high end servos. Starting from $75, they can reach over $150. A common misconception is that titanium is stronger than steel, however its advantage is in strength to weight ratio (as in, titanium gearboxes will often be lighter than steel gearboxes).

Servos with weaker materials (e.g. plastic and brass) used for their gears will often strip quite easily.  Servos with steel gears are significantly harder to strip; some teams have even reported stripping the aluminum hubs attached to their servos while the servos themselves survived with no damage.
