---
id: dead-wheels/02
title: Dead Wheels: Drive Encoder Localization
page: Dead Wheels
type: drivetrain
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/common-mechanisms/dead-wheels.html
---

- **Pros**:
  - Cheap (the motors you're using most likely already have encoders built in)
  - Accessible
  - Very little configuration necessary
- **Cons**:
  - Drive encoder localization on mecanum drive can be quite inaccurate due to lack of traction on mecanum wheels.
  - Will drift on high acceleration on mecanum drive. Accuracy will be good enough for basic autonomous modes if acceleration is limited

## Two-Wheel Odometry Pods

- **Pros**:
  - Cheaper than 3-wheel design
  - Pretty good accuracy
  - No tuning of the heading necessary
- **Cons**:
  - Subject to more drift than the 3-wheel design

## Three-Wheel Odometry Pods

- **Pros**:
  - Relatively accurate tracking. Great accuracy in a 30-second autonomous mode
- **Cons**:
  - Quite pricey
  - Tuning of the heading is very important
