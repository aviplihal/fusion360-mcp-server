---
id: arms/01
title: Arms
page: Arms
type: arm
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/common-mechanisms/arms.html
---

Arms encompass a large variety of mechanisms. In FTC, they are used to add extension and flexibility to end effectors. Arms are especially powerful when paired with other mechanisms such as linear extension and mini-turrets.

## Arms for Extension

Arms can be a useful tool for extension. Long arms need large reduction ratios to drive. The example in the Single Arm section uses a 254.5:1 reduction. It is recommended to transfer torque to the arm through a gear, chain, or belt rather than directly mounting to a motor shaft due to axial forces and the ability to get a larger reduction. Due to the large amount of momentum these arms can carry, if suddenly stopped they may be able to break a motor's gearbox or even tip your robot over. Software control can help to reduce the load on motor gearboxes (see control loops).

Depending on the application and implementation, arms can be either faster or slower than other extension options.

### Single Arm

The most simple type of arm, a single arm refers to an arm on one axis of rotation. These arms are relatively easy and quick to build, however they have little high-level competitive viability as a main extension system since the extension it provides is limited due to the length restrictions of the starting cube, only being able to provide around 16" of extension whereas over 24" of extension is desired for most games.

### Pivot Extension

A pivot extension mechanism is an arm with a linear extension (typically linear slides) attached. This allows the linear extension to provide the desired extension length for both horizontal and vertical extension along with removing the need for a transfer stage.

### Multi-Axis Arms

A multi-axis arm consists of multiple rotational joints. A multi-axis arm provides the extension single arms lack in addition to providing much more flexibility in positioning the end effector. While multi-axis arms seem like the obvious solution to the problems single axis arms face, they are much more difficult to design, manufacture, and control, having issues with accuracy, backlash, and packaging, while providing little benefit over linear slides and other extension methods.

**Warning:** This is highly discouraged for inexperienced FTC teams.
