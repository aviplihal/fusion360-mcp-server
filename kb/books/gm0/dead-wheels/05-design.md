---
id: dead-wheels/05
title: Dead Wheels: Design
page: Dead Wheels
type: drivetrain
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/common-mechanisms/dead-wheels.html
---

There are few open source dead wheel designs. Dead wheels are often designed around a team's own drive train and FTC teams seldom publicly release their own robot CADs.

Here are a few publicly available dead wheel designs:

- **Open Odometry by 18219**
  - https://openodometry.weebly.com
  - Utilizes the REV Through-Bore Encoder
  - Most popular and robust publicly available design
  - Compact enough to fit into a goBILDA channel
  - **Things to consider**:
  - Utilizes Rotacaster 35mm wheels from Australia. Shipping may take a while
- **goREVdometry**
  - https://discord.com/invite/Cvz3MbM9dX
  - Utilizes the REV Through-Bore Encoder
  - Compact enough to fit into a goBILDA channel
  - **Things to consider**:
  - Information only available through their Discord channel
  - Hasn't been iterated on in a while
- **9794 Wizards.exe Design**
  - https://www.youtube.com/watch?list=PLICNg-rquurYgWAQGhu6iC0At75vgqFJp&v=OjNvAD350M4&feature=emb_title
  - Compact enough to fit into a goBILDA channel
  - **No longer recommended as it utilizes the E8T**

### Spring Tensioning

It is *highly* recommended that your dead wheel design includes some form of spring tensioning that pushes the wheel into the ground. This ensures that the wheel is always in contact with ground and has adequate traction. Sufficient force is required to ensure constant traction to prevent the wheels from slipping. Keep in mind that too much force may lift a light drive train off the ground and disrupt driving.

The most popular method of spring tensioning is to pivot your pod around a point and provide a rotational force via a spring or rubber band.

A much more niche option is to vertically spring odometry pods. The idea is that springing around a pivot will cause the dead wheels to move in the axis parallel to the ground if the height of the dead wheels relative to the ground changes. Vertically sprung odometry pods will not experience such an issue. However, this is not really an issue that most teams will experience. Vertically springing is much harder to design well and is not recommended for the relatively minor improvement in accuracy it yields.
