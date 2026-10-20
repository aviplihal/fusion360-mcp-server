---
id: full-turret/01
title: Full Turrets
page: Full Turrets
type: turret
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/common-mechanisms/turrets/full-turret.html
---

Listed below are different techniques to implement a full turret. These mechanisms are commonly located at the base of a robot and rotate slide, arm, or shooter assemblies mounted to them.

## Lazy Susan Turrets

Lazy susan turrets are based around a type of turntable called a lazy susan, which are available off the shelf.

### Advantages

- Lazy susans come prebuilt, meaning you don't need to design or manufacture your own platform for your turret.
- Decent lazy susans are relatively cheap.

### Disadvantages

- Lazy susans are prebuilt, meaning they're generally harder to customize than other options.
- Lazy susans aren't designed to handle lateral forces, which means that e.g. the reaction force from a shooter could damage it.

### Bearing Stack Turret

Bearing stacks are stacks of bearings, usually consisting of a small bearing sandwiched between two large bearings on a screw shaft or standoff. A bearing stack turret has a disc that rotates smoothly because it is tangent to the small bearing on many bearing stacks, while the bigger bearings constrain the disc vertically. Usually, the small bearing is a radial bearing, while the big bearings may be thrust or radial bearings, depending on which loads the turret experiences.

### Advantages

- Highly customizable, as the assembly can be designed specifically for your robot and mechanisms.

### Disadvantages

- Requires a lot of design work and precision manufacturing capabilities to build.
- Many potential points of failure, though some bearing stacks can fail without the entire turret failing with redundancy.
