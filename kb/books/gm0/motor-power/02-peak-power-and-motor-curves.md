---
id: motor-power/02
title: Peak Power and Motor Curves
page: Motor Power
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/power-and-electronics/motor-guide/motor-power.html
---

In order to figure out how much power your motor will be consuming or outputting, it's helpful to reference a motor curve. These are data sheets that plot the motor's output speed, output torque, output power, and efficiency all on one graph. Every FTC legal motor except the Core Hex has been dyno tested, and their data are below. It is safe to assume other non-current limited motors (such as servos) follow similarly-shaped curves, although with different speed, torque, and power outputs.

 | Free Speed (RPM) | Free Current (A) | Maximum Power (W) | Stall Torque  (N*m) | Stall Current (A)
goBILDA (MATRIX) | 5900 | 0.3 | 29 | 0.19 | 11
NeveRest | 5500 | 0.4 | 26 | 0.17 | 9.8
REV Core Hex| 125 | 0.2 | 10 | 3.2 | 4.4
REV HD Hex | 6000 | 0.3 | 28 | 0.18 | 11
TorqueNado | 5900 | 0.2 | 26 | 0.17 | 9.8

A motor curve represents a motor at 12 V (equivalent to setting the motor power to 1 in software) with various amounts of load applied to the axle. As you can see, the power output from the motor is not constant, instead rising until about 50% load, before falling again. This point at 50% load is called the **peak power output** of the motor, and is at a similar point (50% load) across all FTC legal motors.

The varying power of a motor means that speed and torque output do not change linearly when more load is applied onto the axle. Counterintuitively, placing 50% stall load on a motor doesn't halve its speed, but will rather reduce it to slightly above 50% speed. Similarly, placing more than 50% load on a motor will cause the speed to fall faster than linearly.

In addition, you can see that efficiency rises as speed goes up. This means, if current draw is a concern, one should always be running their motors with loads below 50% of their stall torque. These two properties of a motor, the peak power output being 50% of the stall torque and the efficiency of a motor being higher the lower the load is, guide the selection of the gear ratio of a motor. **Ideally, gear ratios should be chosen such that the stall torque is twice the average torque load on the motor, and should skew towards providing more torque than needed rather than less**.
