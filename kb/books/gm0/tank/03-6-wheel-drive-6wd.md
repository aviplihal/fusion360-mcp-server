---
id: tank/03
title: Tank (Skid-Steer) Drivetrains: 6 Wheel Drive (6WD)
page: Tank (Skid-Steer) Drivetrains
type: drivetrain
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/common-mechanisms/drivetrains/tank.html
---

A 6 wheel drivetrain is a common competitive drivetrain in FTC for multiple reasons: it has fantastic traction, great turning, and by having 6 wheels, the drivetrain has more contact with the ground, helping with stability and traction. There are two main types of 6 wheel drivetrains: ones with **corner omnis** and ones with a **drop center**.

**Drop Center**: A drop center 6WD is a 6 wheel drive with the center wheel mounted slightly below the other two wheels. The drop should be anywhere from more than 1/16" up to 1/4". However, the recommended drop is around 1/8". Typically, lighter robots (<25 lbs.) can have less drop, while heavier robots (>25 lbs.) perform slightly better with more than 1/8" drop.

The purpose of dropping the middle wheel is to ensure that only 4 wheels are in contact with the ground at all times. This is because turning with 6 wheels on the ground introduces lots of friction, making it very difficult to turn quickly. Note that the **required drop may vary depending on both field condition and weight of the overall robot**.

Turning can drastically degrade due to a difference in material underneath the field, leading to the robot sinking down further than usual.

**Most drop center 6 wheel drives are made using custom drivetrains** because it is difficult to get the center wheel drop using a kit based build system (a notable exception being REV-based kit drivetrains). It is possible to execute a drop center using goBILDA and Actobotics using pillow blocks, but it is a little bit more awkward. However, with the new goBILDA drop-center bearing plate, it is straightforward to make a drop center drivetrain on goBILDA channel.

6 wheel drives with corner omni wheels do not need to have a center drop. It attempts to solve the issue of turning by replacing the corner traction wheels with omni wheels, allowing the drivetrain to achieve better turning, albeit with slightly less traction than a center-drop. This is very easily buildable in kits, and is a great all-around drivetrain. Drop center and corner omnis can be combined for maximum turning reliability, although this comes with side effects like rocking and reduced traction.

### Advantages

- Great traction and maneuverability
- Good acceleration, can have a high top speed
- Great stability under all robot weights
- Able to play defense

### Disadvantages

- Drop-center 6WD is tricky to build with channel based systems, though this has been partially mitigated with the goBILDA drop-center bearing plate
- Drop-center 6WD is slightly worse at turning, but has more traction
- Drop-center 6WD is dependent on field conditions
- Corner omni 6WD has less traction
- Slow gear ratios will make a 6WD feel sluggish

**goBILDA COTS:** Click here to explore this model in OnShape online CAD

**REV COTS:** Click here to explore this model in OnShape online CAD

**goBILDA Custom:** Click here to explore this model in OnShape online CAD

**REV Custom:** Click here to explore this model in OnShape online CAD
