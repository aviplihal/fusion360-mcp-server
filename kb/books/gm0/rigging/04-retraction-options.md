---
id: rigging/04
title: Rigging: Retraction Options
page: Rigging
type: slide
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/common-mechanisms/linear-motion-guide/rigging.html
---

### Continuous Retraction

As the name suggests, continuous retraction utilizes inverted continuous rigging to retract the slides. There are two main methods of doing this, **free floating retraction** where a string is run from the last stage directly back to the spool, and **with slide retraction** where the string is run in an inverse continuous pattern. Generally, **with slide retraction** should be used with extensions going outside the robot frame to prevent entanglement, and **free floating retraction** should only be used with purely vertical slides.

**Note:** If continuous retraction is being used with cascade extension, the two spools cannot be the same diameter. If the variable N is the number of stages in the system, the diameter of the cascade extension spool must be N **times smaller** than the continuous retraction spool.

**Warning:** If free floating retraction is used, **make sure your retract string is always parallel to the slides**. If the string is misaligned, it can pull on your slide and cause excess bending forces on the stages.

Advantages:

- Simplest retraction rigging

Disadvantages:

- Can become tangled if free floating
- Requires different sized spools if used with cascade retraction

### Elastic Retraction

Instead of retracting using a retraction spool, one common way to retract is to attach a piece of elastic (commonly surgical tubing) to the last stage. The elastic applies a force on the last stage that is counteracted by the motor when extending. However, when retracting, the motor reels the last slide back in. While this is the retraction method recommended by many kit slide manuals, this method is not recommended.

Advantages:

- There is only one string to tension, instead of multiple, so tensioning is simpler.
- The elastic automatically tensions the extension string.

Disadvantages:

- Since the elastic applies a force to the slide at all times, this force opposes the force applied by the motor when extending the slides. **Thus, elastic retraction decreases extension speed considerably**.
- The elastic does not apply a constant force at all times. It applies force proportional to the amount that the slide is extended, so retraction may not be smooth and controlled, like other rigging methods.
- It is very easy to unwind your extension spool when using elastic retraction.
