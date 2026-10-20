---
id: rigging/02
title: Continuous Rigging
page: Rigging
type: slide
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/common-mechanisms/linear-motion-guide/rigging.html
---

**Generally recommended**

Continuous rigging entails rigging one long **extension string**, originating from a motor-powered spool, to the top of the base stage, then to the bottom of the first stage, then to the top of the first stage, then to the bottom of the second stage, etc. A **retraction string**, originating from a second spool on the same axis as the extension spool, is then anchored to the top stage. When the motor rotates one direction, the extension spool reels in the extension string, so it becomes shorter. In doing so, the distance between the top of one stage and the bottom of the next stage decreases, causing the system to extend.

**Note:** The last stage always extends and retracts before the other stages (this can be either an advantage or a disadvantage, depending on the application).

Once the last stage hits its limit, the next to last stage extends outwards, and so on; the pattern repeats until every stage is fully extended. When the motor spins **in the opposite direction**, the retraction string is reeled in, pulling the top stage closer to its starting position until the system is back where it started. For the retraction string, it is often necessary to add an extra pulley near the back of the extension. This is because the retraction will only retract to the farthest point, which generally is the spool. However, the spool may not be mounted at the very back of the robot - thus an extra pulley is needed. Note that for this to work, the extension string should be wrapped around the spool in the opposite direction of the retraction string. Thus, if the extension is wrapped clockwise, the retraction must be wrapped counterclockwise.

Here are some additional considerations when rigging a continuous system.

- As a general rule, continuous spools can be powered by a system with a relatively low gear ratio.
- The extension string and retraction string **do not need to be separate strings, but it is much easier to tension the system if they are separate**.
- The extension spool and retraction spool should be the same diameter.
- You need to make sure, as with any time you work with strings and pulleys, that you are pulling the string straight. Any amount of misalignment can lead to the string coming off of your pulley.
- The width and diameter of your spool should be enough such that once fully wound, your string never overlaps. The reason for this is because when the string starts to overlap, this can change the diameter of your spool, causing the tension in the string to change.
