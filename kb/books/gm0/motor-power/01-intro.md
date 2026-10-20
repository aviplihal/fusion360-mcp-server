---
id: motor-power/01
title: Motor Power
page: Motor Power
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/power-and-electronics/motor-guide/motor-power.html
---

Just like any electrical device, motors draw current and consume a certain amount of power to function. Motors convert some portion of the input power into spinning the shaft; this portion is the output power. Thinking of motors in terms of energy instead of speed and torque can make it easier to calculate how it should be used and provide tools for choosing the optimal gear ratio for an application.

## What is Power?

Fundamentally, power is defined as the amount of energy transferred in a given time period. Practically, this means power is how much "energy" you can get out of the motor. **The output power of a motor varies depending on how much load is on it, but does not change as the gear ratio of the motor changes**. What this means is that a free-spinning 1:1 motor will output the same amount of power as a free spinning 100:1 motor (ignoring friction differences), but the actual speed and torque will be different. Output power is proportional to speed times torque, so as speed and torque are changed with a gearbox, the output power must remain the same.

Another piece of information, although not always as useful, is the *input* power of the motor. The input power of the motor is how many watts of power the motor consumes, which is equal to the voltage sent to the motor times the current consumed by the motor. **Motors are not 100% efficient, so to get a certain output power you often need double or even triple the input power**. For example, a standard FTC® motor can consume up to 65 watts just to produce 29 watts of output power.
