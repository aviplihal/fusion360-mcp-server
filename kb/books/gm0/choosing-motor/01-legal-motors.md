---
id: choosing-motor/01
title: Choosing a Motor: Legal Motors
page: Choosing a Motor
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/power-and-electronics/motor-guide/choosing-motor.html
---

12 volt motors are strictly controlled by FTC® rules. As of 2025-2026 season, the only FTC legal 12V motors are the following ones:

- AndyMark NeveRest 12V DC (am-3104, am-3104b)
- AndyMark NeveRest Hex 12V DC (am-3104c)
- goBILDA Yellow Jacket 520x Series 12V DC (5201, 5202, 5203, and 5204 series, e.g. 5201-0002-0026)
- goBILDA 5000 Series 12V DC (e.g. 5000-0002-4008)
- Modern Robotics / MATRIX 12V DC (5000-0002-0001)
- NFR Products Yuksel 12V DC
- REV Robotics HD Hex 12V DC (REV-41-1291)
- REV Robotics Core Hex 12V DC (REV-41-1300)
- Studica Robotics Maverick 12V DC (75001)
- SWYFT Robotics SWYFT Spike Motor (SR-MOTOR-DC-01)
- TETRIX MAX 12V DC (739530, 39530; now discontinued)
- TETRIX MAX TorqueNADO 12V DC (W44260)

**Note:** Many legal gearmotors are sold with labeling based on the entire assembly. These motors may be used with or without the provided gearbox, and/or with any other compatible gearbox.  Here are some examples:

- REV Robotics UltraPlanetary Gearbox Kit & HD Hex Motor (REV-41-1600)
- REV Robotics HD Hex Motor 20:1 Spur Gearbox (REV-41-1298)
- REV Robotics HD Hex Motor 40:1 Spur Gearbox (REV-41-1301)
- AndyMark NeveRest Gearmotors

**Tip:** Continuous Rotation servos can also be a great option in place of a 12V motor in various mechanisms.  See Choosing a Servo for details.

With the exception of the REV Core Hex Motor, all other motors above have very similar structures. They consist of the following components:

- **Bare motor**. In all cases above, this is a 12V motor of RS-555 type, with free speed around 6,000 RPM and stall current around 10A. The motor specs posted by different vendors might be slightly different, but the difference is mainly due to different testing methods. In real life, the bare motors used by AndyMark NeveRest motors, REV Robotics HD Hex motors, and goBILDA motors are virtually identical. The most reliable specs can be found in the motor data section.
- **Gearbox**. The gearbox is attached to the front of the motor and reduces the speed while increasing the torque. For example, a 20:1 gearbox reduces the speed by a factor of 20, resulting in a no-load speed of around 300RPM. See Gear Reduction. A gearbox also contains the output shaft (typically a 8mm REX shaft, 5mm hex shaft, or 6mm D shaft) and mounting holes. The gearbox can also be replaced; this is FTC legal but requires some skill.
- **Encoder**. Attached to the back of the motor and protected by a plastic cap, the encoder contains a sensor registering motor shaft rotation. It can be connected to REV hubs and used for precise control of motor speed or rotating to a specific position.

Since the bare motor is similar for all motors discussed above, the choice of the right motor is dictated by the gearbox: the gear ratio, output shaft type, and ease of mounting.
