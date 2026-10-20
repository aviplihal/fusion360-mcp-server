---
id: choosing-servo/02
title: Servo Type: Regular or Continuous
page: Choosing a Servo
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/power-and-electronics/servo-guide/choosing-servo.html
---

Servos that can rotate to a given position based on PWM input signal are called **regular servos**. In addition, there are also **continuous rotation servos**, which are effectively just small motors in a servo form factor. They have no position control; instead, PWM signal is used to control their rotation speed.

**Tip:** Continuous rotation servos aren't even always in a traditional servo form factor.  The Melonbotics Super Servo Plus, while considered a continuous rotation servo from a rules and control system perspective, is essentially a small motor + spur gearbox.  The 1000rpm rated output speed makes it an excellent alternative to large, heavy standard motors for small, high-speed mechanisms such as active intakes.

Many servos from FTC® vendors are Dual Mode, meaning they can switch between continuous and regular modes (often requiring the use of a sold-separately servo programmer). These servos can be used as either continuous or regular servos.
