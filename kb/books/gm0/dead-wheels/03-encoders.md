---
id: dead-wheels/03
title: Dead Wheels: Encoders
page: Dead Wheels
type: drivetrain
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/common-mechanisms/dead-wheels.html
---

A lot of the localization done in software relies on readings from encoders. encoders are sensors that track "counts" or "ticks," which are values that represent a certain amount of a rotation. Different encoders might have a different number of counts per revolution (CPR), which is also sometimes called ticks per revolution. The greater the number of counts, the more precise the data.

Encoders are plugged into the JST-PH ports in the REV hubs. These encoders can either be built-in to the motors or external. External encoders will still need to be plugged into an encoder port but are not related to the motor in that port. Through software, we can use the motor object to determine the position of the encoder. This should be done with motors that do not use encoders. If you're using dead wheels, you will not need the drive motor encoder ports, so those are potential ports you might want to use.

If one chooses to design dead wheels, there are only two recommended encoders that one should use for FTC: REV Through-Bore Encoders and U.S. Digital S4T Encoders.

### REV Through-Bore

Often short-handed to "REVcoders" or "revcoders," the REV Through-Bore encoders has quickly become the de facto option the FTC community. The REV encoders have gained such a reputation due to its relative affordability, much improved reliability, and ease of use. The through-bore design proves to be a *significant* improvement over previous optical disc encoder designs. Optical disc encoders are very fragile, prone to scratching, and are much less tolerant to design flaws.

- Through-bore design is very robust and easy to design with
- Relatively cheap
- High CPR
- Easy wiring
- Quite large relative to other encoders. May be challenging to create a compact design
- Many Through-Bores seem to experience slight, uneven resistance when rotating. REV says this is normal and will subside as the encoder wears in
  - To forcefully wear in a REV Through-Bore encoder a 1/2" hex shaft can be spun on a drill through the encoder for a couple of minutes
- Odd mounting points

**Note:** The Through-Bore encoders have a very high CPR (8k). The REV Hub transmits velocity in a 16-bit signed integer. This means it can only communicate a maximum value of 2^15 (which is 32768). Thus, it only takes 4 rotations a second (32k / 8k = 4) for the velocity value on the REV Hub to experience an integer overflow. This is primarily a concern when dealing with motion profiling. The popular, existing tools (Road Runner and FTCLib) have mechanisms for dealing with this issue so this is not a concern and should not sway your design decision. Just keep this detail in mind once you start programming.
