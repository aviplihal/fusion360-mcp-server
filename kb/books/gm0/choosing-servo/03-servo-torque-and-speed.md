---
id: choosing-servo/03
title: Choosing a Servo: Servo Torque And Speed
page: Choosing a Servo
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/power-and-electronics/servo-guide/choosing-servo.html
---

Servo output power is measured in both **speed** and **torque**. Speed (normally in seconds per 60°) refers to how fast the servo turns 60 degrees in Standard Rotation mode.

**Why seconds per 60 degrees?:** Historically, the servos commonly used in FTC were created for RC (Radio Controlled) car setups. These cars often had steering linkages with a maximum side to side travel of 60 degrees so manufacturers would often advertise their servos using seconds for 60 degrees.

Torque (usually measured in oz-in or in kg-cm) refers to the amount of force the servo can apply to a lever. For reference, if you put a 1" bar on a servo, then put a force gauge on the end, the torque rating of the servo (in oz-in) will be measured.

As you may know, speed and torque will generally have an inverse relationship. You can find some insanely powerful servos that are pretty slow (slower than 0.20 s/60°) or some less powerful ones with faster ratios (anything faster than 0.12 s/60° is considered fast).

Finding the right servo for your application can be tough, but a good way is trying to decide if you need more speed or torque, and if your servo will experience shock loads or not.
