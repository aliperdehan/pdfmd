---
title: "Rates of an acid-catalysed hydrolysis"
author: "A. Student"
date: 2026-11-04
bibliography: refs.bib
---

# Introduction

Ester hydrolysis in dilute acid follows pseudo-first-order kinetics when water is in large excess [@laidler1987]. The rate law is

$$ -\frac{d[\mathrm{E}]}{dt} = k_\mathrm{obs}\,[\mathrm{E}], \qquad k_\mathrm{obs} = k\,[\mathrm{H^+}] $$

and the integrated form $\ln [\mathrm{E}]_t = \ln [\mathrm{E}]_0 - k_\mathrm{obs} t$ gives a straight line.

# Method

Samples were titrated at fixed intervals with 0.100 M NaOH. Each run was repeated three times.

## Reagents

- ethyl acetate, 0.50 M
- hydrochloric acid, 1.0 M
- sodium hydroxide, 0.100 M (standardised)

## Procedure

1. Mix the ester and the acid in a thermostatted flask.
2. Withdraw 5.00 mL every five minutes.
3. Quench in ice and titrate.

# Results

| t / min | V(NaOH) / mL | ln(V∞ − Vt) |
|--------:|-------------:|------------:|
| 0       | 12.1         | 2.75        |
| 10      | 14.3         | 2.51        |
| 20      | 16.0         | 2.27        |
| 30      | 17.4         | 2.01        |

The slope of the fitted line is $-0.0247\ \mathrm{min^{-1}}$, so $k_\mathrm{obs} = 4.1\times10^{-4}\ \mathrm{s^{-1}}$.

# Discussion

The value agrees with the literature within 8 % [@laidler1987]. The largest error is the quench time; see `notes.md`.

# References
