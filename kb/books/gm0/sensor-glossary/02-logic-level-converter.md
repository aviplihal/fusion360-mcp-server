---
id: sensor-glossary/02
title: Sensor Glossary: Logic Level Converter
page: Sensor Glossary
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/power-and-electronics/sensor-glossary.html
---

The old Modern Robotics system run on 5v sensor logic. The new REV Robotics system uses 3.3v. For most off the shelf sensors, this doesn't cause any problems, but for some existing FTC sensors it does. To solve this REV sells boards, called logic level converters, that convert the sensor data to be readable by the REV hubs. The REV Expansion Hub guide has a chart detailing what adapters are needed for what sensors.

**Attention:** According to REV testing, goBILDA, REV and TorqueNado motors don't need logic level converters, but only some NeveRest motors worked with no discernible reason why.

It is ideal to not use logic level converters to simplify your wiring. If you need to, there is a best practice. Electrical tape the connectors on either end, this helps with static, and it keeps it from being physically disconnected. This does produce a very noticeable effect with encoders on fields with lots of static.

The second tip is to never tape over the middle or LED. The board generates a very small amount of heat, and it's very easy to overheat if it can't ventilate, also don't fully enclose it in any cases without holes.
