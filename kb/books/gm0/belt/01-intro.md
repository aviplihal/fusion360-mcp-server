---
id: belt/01
title: Timing Belt
page: Timing Belt
type: power_transmission
source: gm0 c81f4c44dc85, CC BY-NC 2.0
url: https://gm0.org/en/latest/docs/common-mechanisms/power-transmission/belt.html
---

When you think of a belt, you're probably thinking of a very important men's fashion accessory. However, there's another type of belt, and it's way more relevant to robotics - the timing belt. If you've ever tinkered with the insides of a car before, you probably recognize timing belts as an important component designed to keep everything under the hood in sync.

**Timing Belt**: Timing belts use a series of small, wide teeth to engage a pulley with a number of matching grooves. They earn their name because they can be very precise, transmitting power with virtually no slop and ensuring a snug connection between shafts.

While a timing belt may complete a similar objective to chain, its characteristics and strengths are very different. Timing belts are lighter and more compact than chains, but they lack the customizability of their bulkier brother - belts come in a closed loop of predetermined length, and there's no changing that length on the fly.

Like chain, belt is identified by its pitch - common pitches found on FTC® robots include HTD 5mm, HTD 3mm, and GT2 3mm.

When using timing belts, correct tension is very important. There are two main ways to get your tension right. The first is easy - goBILDA and Actobotics already have belts integrated into their hole patterns. You can buy correctly sized belt directly from each vendor, and your tension will be perfect as soon as the belt is installed. As your designs gain complexity, so will your belt runs - maybe there are more than 2 pulleys, and maybe your pulleys are all different sizes. To compensate for this, the second way to ensure tension is to use a dynamic tensioner, similar to those found in complex chain runs. To design for these tensioners, we recommend planning more complex belt runs in CAD before building them in real life.
