---
id: choosing-servo/07
title: Choosing a Servo: Servo Range
page: Choosing a Servo
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/power-and-electronics/servo-guide/choosing-servo.html
---

The angle over which a non-continuous servo can rotate while retaining position feedback is called the range. When choosing a servo, it is important to make sure you have enough range for the movement you need.

By default, the FTC control system outputs 600-2400 microsecond signals. However, this range can be expanded to 500-2500 microseconds. When choosing a servo, it is important to make sure that its range will be usable for your application inside of 500-2500 microseconds.

**Note:** The default 600-2400 range of the FTC control system when selecting the "Servo" configuration limits the range of many servos to less than the advertised range. Make sure you select the "Full Range Servo" configuration instead to get the full 500-2500 range.
