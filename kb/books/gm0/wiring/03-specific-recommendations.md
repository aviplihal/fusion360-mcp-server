---
id: wiring/03
title: Wiring Guide: Specific Recommendations
page: Wiring Guide
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/power-and-electronics/wiring.html
---

### Module Power

Be aware, XT30 connectors can wear out significantly faster than PowerPole connectors. Additionally, because XT30 connectors are soldered, they can break much easier than PowerPole connections.

Cabling for module power should be at least 14awg, if not 12awg. Keep in mind that it must be stranded, not solid, wire.

### Motor Power

Cabling for motor power should be between 16awg and 12awg. Again, stranded, not solid, wire.

Some motors (like the REV HD Hex and Core Hex) will have removable power connectors on the back, while other motors (like the Andymark NeveRests) will have a cable permanently soldered on the back. It is much more convenient to have a connector on the back, or failing that, have a very short plug on the back of the motor. Once your wires are run and secured, taking them out won't be fun.

### Servo Wires

Using heavy-duty extension wires are recommended.

Tape the connections between extension wires and servo wires with electrical tape. This is as the connections can become loose over time and are easy to pull out.

The VEX Motor Controller 29 has the wrong gender connector on the 3-pin end. You are required to either use an adapter cable, or add the right connector to the wires (recommended). **Be sure to protect the MC29, as it is fragile and prone to failure if it takes impact from another object**.

### USB

USB is generally a strong connector, but is prone to wearing out over time. Refrain from plugging/unplugging these cables more than necessary, especially on the RC/DS phones.

USB loves strain relief. To keep disconnects low, tie down cables to leave as little loose cabling on the robot as possible.

### Sensor Wires/Encoder Wires

Sensor wires and their connectors can be incredibly fragile. Use caution when routing, and keep slack on the connector end when adding strain relief to the cable.

The JST data connectors on the REV Expansion Hub and Control Hub have +5v, GND, and two data pins. If you are using a digital or analog sensor that does not use I2C, you can use a Y cable that gives two sensors off of one port.
