---
id: drivetrains/02
title: Drivetrains: Drivetrain selection
page: Drivetrains
type: drivetrain
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/common-mechanisms/drivetrains/index.html
---

When building any mechanism, teams must list out some necessities or desired features. Here are some priorities that we think are important for each drivetrain:

- **Reliability**: Reliability, the key to success in *FIRST*® Tech Challenge, starts with the drivetrain, the foundation to any robot. One aspect of reliability to consider is the type of motor and gearbox that is used in the drivetrain. For example, spur gearboxes are more likely to break under load than a planetary gearboxes. (See the index for details). Thus, spur gear motors are not the optimal choice for drivetrain, especially if the robot is projected to be on the heavy side (30+ pounds).

**Note:** Generally, more complex drivetrains pose more reliability challenges for inexperienced teams. Our advice is to stick to the simpler drivetrains such as 4 or 6 wheel drive and mecanum drive.

- **Agility**: There are many factors to agility: top speed, acceleration, turning radius, turn speed, and ability to strafe. Note that turning radius is an often overlooked feature that is critical to the overall agility of the drivetrain. Generally, a solid drivetrain should have a free speed (speed under no load) in the range of 4.5-6 feet/second.
- **Number of motors and gear ratio**: Generally, new teams may try to use only two motors on the drivetrain. While this is possible, it is not recommended, as all competitive teams use 4+ motors on the drivetrain. Another issue stemming from experience is that most teams' drivetrains are too slow. More advanced teams may focus on the ability to play defense, but in general, maneuverability and speed are the main factors to a successful drivetrain.

60:1 and 40:1 motors are **almost always too slow for FTC drivetrain use cases**. Any gear ratio between 16:1 and 20:1 is perfectly reasonable on 4 inch wheels. 19.2:1 on 4 inch wheels is a popular choice because it enables one to go 1 to 1 off of a 19.2:1 planetary motor. This ratio gives a great balance, having near instant acceleration and a high top speed.

On 3 inch wheels, the equivalent ratios are 12:1 to 15:1, which makes 13.7:1 on 3 inch wheels convenient, as it can be taken 1 to 1 off of goBILDA's 13.7:1 planetary gearbox motor. Teams can slow the drivetrain down in code by providing less power to the motors if needed.

**Warning:** It is not recommended for teams to use spur gearboxes on their drivetrain. Instead, use planetary gearboxes, as they are less prone to shock loads and breakage.

- **Traction/Pushing Power**: While this feature is often overemphasized, it is still very important. Pushing power describes a drivetrain's ability to endure defense/engage in defense. In addition, traction will be important if the drivetrain must traverse obstacles or some sort of terrain. Many factors affect the pushing power of a drivetrain, including wheel type, motor gearing, and overall weight of the robot.

**Note:** If you already have a very agile drivetrain with experienced drivers, a team can avoid defense instead of having to fend it off or engage in it.

- **Powering the drivetrain**: Generally, there are four options for power transmission: direct drive, chain, gear, and belt. More detail about each option can be found in the power transmission section.

Teams should stay away from direct drive, as gearboxes are prone to breaking, especially under shock loads (for example, if the wheel is hit by another robot, or the wheel slams into the wall).
