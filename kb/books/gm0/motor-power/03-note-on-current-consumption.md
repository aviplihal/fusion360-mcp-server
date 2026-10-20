---
id: motor-power/03
title: Motor Power: Note on Current Consumption
page: Motor Power
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/power-and-electronics/motor-guide/motor-power.html
---

You may see while looking at motor curves that the stall current of FTC motors can be as high as 11 amps per motor. FTC batteries can only provide 20 amps of current output before blowing the fuse is likely. However, even if the 20 amp limit isn't reached, drawing too much current can cause other motors to feel sluggish or unresponsive. Care should be taken to ensure that more than two motors are never stalled at the same time.

**Note:** You may be able to ignore this when dealing with mecanum drivetrains, as they will generally slip before the motors actually reach their stall current. However, placing very low gear ratios or more than 4 motors on traction drivetrains can exceed the current limit of an FTC battery.

Motors can pull "transient current" where they pull a large amount of current for extremely brief amounts of time. This often happens when the motor starts moving or when a momentary load is placed on it. While transients generally cannot cause a fuse to pop, they can cause other issues, such as sluggish control if pulled by a motor, or low voltage if the transient is pulled by a servo (goBILDA Super Speed servos have been observed to do this occasionally).
