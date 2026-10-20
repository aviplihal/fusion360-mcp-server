---
id: gears/02
title: Meshing Gears
page: Gears
type: power_transmission
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/common-mechanisms/power-transmission/gears.html
---

**Mesh**: Meshing refers to the overlapping contact between a gear tooth and another gear tooth, chain and sprocket, or belt and pulley.

A proper mesh is essential to ensure maximum torque transmission. Too little mesh can result in no power transfer, derailment or gears grinding/wearing down faster. Too much mesh can produce unwanted friction and introduce inefficiencies within the drive system.

When meshing gears, it is important that the gears are not too loose nor too tight. If the gears are too loose, the teeth will easily wear out, decreasing its longevity. If the gears are too tight, however, they will have too much friction and possibly grind or bind up. The ideal way to mesh gears are to make sure the teeth interlock and just touch the base of the gear.

**Attention:** If possible, it's best to avoid meshing gears with a clamping motor mount -- due to the sensitivity of the mesh, even the slightest movement of the motor inside the clamping mount can cause the gears to slip or damage each other.

Calculating center-to-center distances using gears is quite simple. In order to calculate the desired center distance between two given gears, you must know the number of teeth for each gear and the **diametral pitch** of your gears (the number of teeth per inch of the gear's diameter). With these two pieces of information, you can use the equation D=frac{T_{1}+T_{2}}{P}. In this equation, D is the distance between the center of both gears, T_1 and T_2 are the number of teeth of each gear in question, and P is the diametral pitch of the gears.

The **module** (abbreviated **MOD**) of a gear is used similarly to diametral pitch. It is the number of millimeters of the gear's diameter per tooth of the gear. The equation to find center distance D is D = frac{(T_{1} + T_{2}) * M}{2}, where T_{1} and T_2 are the number of teeth of each gear in question, and M is the module of the gear.

**Note:** Be sure to never mesh gears that are not of the same diametral pitch. (A notable exception is 32 diametral pitch and 0.8 MOD gears. These are close enough to be perfectly fine.)

Additionally, it is possible to average the pitch diameters of the two gears to find the correct center-to-center distance.

As with sprockets, it is important to line up the gears so that they do not accidentally slip. Especially when using extrusion, it is possible that the gear may not be parallel to the extrusion, as the two supporting ends may not be perfectly in line with one another. It is imperative that the gear be lined up as straight as possible to prevent damage or gear binding.

It is highly recommended to use white lithium grease or a similar lubricant between the gears to reduce friction and possible binding.
