---
id: rigging/06
title: Using PTFE Tubing and John Guest Adapters to Route the String
page: Rigging
type: slide
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/common-mechanisms/linear-motion-guide/rigging.html
---

If you're looking for the ability to mount your linear slides in a different location than your motor/pulley, consider using PTFE tubing and John Guest Adapters to route the string.

1/8 in. PTFE tubing and John-guest push-to-connect adapters with M5 thread on one side work really well for this purpose. These tubing are identical to the ones used in 3D printers to route filament.

The tubing can be routed over long distances without adding significant friction

## Belt-driven slides

One increasingly popular alternative to traditional string-based rigging is belt-driven slides. This can be done continuously or using cascade rigging.

### Advantages over string

Unlike string, belts used on slides never need to be tensioned. As discussed in the linear motion section, in order for string-driven slides to remain efficient, string tension must be maintained. Naturally, string loosens over time, so you either need a mechanism that can provide extra tension (a spring) or manually tighten string, which can get a bit tedious (especially for cascade rigging).

However, belts do not have this issue. They tend not to stretch over time, meaning complex external tensioners are rarely needed. Belts are also on an automatic one to one loop, meaning that for every inch you pull in on the extension side, you always feed back out that inch on the retraction side, and vice versa. While this might not seem like a big deal, if a string winds itself up on a spool and overlaps at any point, the diameter of the spool changes, making the two spools out of sync.

### Disadvantages over string

The main disadvantage of belt-driven slides is the amount of space they take up. Simply put, belt pulleys take up much more room than the 4mm thick, 12mm diameter pulley bearings REV sells. When using belt-driven slides, pulleys are at least double that thickness and have a considerably larger diameter, meaning each stage must be thicker.
