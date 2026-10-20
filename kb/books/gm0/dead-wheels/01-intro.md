---
id: dead-wheels/01
title: Dead Wheels
page: Dead Wheels
type: drivetrain
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/common-mechanisms/dead-wheels.html
---

**Warning:** This is a very niche aspect of design in FTC®. Generally it is something done by more experienced teams who have had time to repeatedly test their designs and mechanisms with software during the off-season.

The term dead wheels, tracking wheels, odometry pods, and odometry are often conflated in the FTC community. However, there are a few key differences one must keep in mind. Odometry is an umbrella term and refers to the general use of motion sensors for localization purposes. Meanwhile, dead wheels, tracking wheels, and odometry pods are all synonymous terms.

**Dead Wheel**: A small unpowered wheel (usually an omni wheel) that tracks the distance the robot has traveled through the encoder attached to the wheel's axle.

Usually, there will be two or three wheels - one or two on the x and y axis each to track the front-back and left-right position relative to the starting point. Generally, odometry wheels are sprung so that the wheel is in contact with the floor tiles at all times to ensure accuracy.

Odometry refers to the use of motion sensors for localization. Localization is a means for being able to locate the position of the bot at some point in time. Localization is crucial in path following and advanced autonomous modes as one needs to know where they are to generate the necessary movements needed to reach a desired destination. Localization software plays a major role in odometry; however, in order to produce accurate results, reliable and accurate hardware design is a necessity.

The simplest form of odometry is drive encoder localization. This is the use of encoders measuring the rotation of motors that power the drive train. One is able to read the encoder data and feed it through the kinematic equation for that specific drive train to derive the body's velocity. Drive encoder localization is generally quite simple and easy to set up as almost all of the FTC legal motors have built-in encoders. Getting drive encoder localization set up is simply a matter of plugging in wires, no additional hardware needed.

Many teams in the community have converged on a unique solution that isn't seen very much outside of FTC: the use of "dead wheels," "tracking wheels," or "odometry pods" (these terms are all synonymous). These refer to small "dead" or non-driven (not powered by a motor) wheels attached to an encoder sensor. Two or three dead wheel pods are often sprung to the ground to ensure accurate tracking. The two-wheel design utilizes one parallel and one perpendicular pod (parallel and perpendicular with respect to the drive wheel axis), measuring x and y movement respectively. Change in heading is measured via a gyroscope. The three-wheel design utilizes two parallel and one perpendicular pod, measuring x and y movement respectively. However, this design forgoes the gyroscope and instead measures heading via the difference with the two parallel wheels. This is often more accurate in the context of the FTC control system because the BNO055 IMU (used for the gyroscope in the two-wheel design) utilizes I2C which is slower than the rest of the I/O on the REV Hub and cannot be bulk read. These two issues lead to minute drift issues which can compound over time, thus leading to a more inaccurate localization system when using the two-wheel design.

However, designing consistently accurate dead wheels proves to be a difficult design challenge. It is often quite pricey. A set of three dead wheels will cost a minimum of $100 for the encoders alone, prior to any hardware.

Let's go through the advantages and disadvantages of each system.
