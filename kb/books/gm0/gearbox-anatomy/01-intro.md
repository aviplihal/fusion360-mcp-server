---
id: gearbox-anatomy/01
title: Gearbox Internals
page: Gearbox Internals
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/power-and-electronics/motor-guide/gearbox-anatomy.html
---

Fundamentally, a gearbox is just a collection of gears and an enclosure that connects them. Gearboxes have an **output ratio**, the final Gear Reduction between the motor input and the final output shaft.

**Gear Reduction**: Also known as a gear ratio. In any rotational power transmission system (typically involving motors and servos in FTC®), a gear ratio defines both the number of rotations of the system's input and the number of rotations of the output.

For instance, a NeveRest 20 gearmotor consists of an unmodified NeveRest Motor and a planetary gearbox that has a gear ratio of 20:1 (or, when spoken, "20 to 1"). This means that in order for the output shaft of the gearbox to rotate 1 time, the input shaft of the motor must rotate 20 times. Gear ratios are one of the most important design considerations about a power transmission component.

Any motor or servo has two properties: speed and torque (or rotational force). These two properties are inversely proportional, meaning that increasing speed decreases torque, and vice versa. For instance, if one wishes to make a mechanism faster at the expense of torque by doubling the speed of that 20:1 gearbox, they would decrease the gear ratio by a factor of 2. Since 20 divided by 2 is 10, the new desired ratio would be 10:1 (this is referred to as gearing up). However, if one wishes to double torque instead, making the system more powerful and robust at the expense of speed, they would increase the gear ratio by a factor of 2, leaving them with a 40:1 ratio (this is referred to as gearing down).

The most common ways of gearing up or down are using gearboxes, gears, sprockets and belt-driven pulleys, all of which exist in various sizes.

In FTC, gearboxes may be more common than you think. Nearly every motor and servo has a gearbox attached or built-in to it. These gearboxes are either spur or planetary.
