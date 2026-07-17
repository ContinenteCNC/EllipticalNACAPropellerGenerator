# Attribution and third-party material

## Original OpenSCAD library

**Title:** Elliptical-blade NACA airfoil propeller library  
**Author:** Alex Matulich / Amatulic  
**Thingiverse:** https://www.thingiverse.com/thing:5300828  
**Printables:** https://www.printables.com/model/159163-elliptical-blade-naca-airfoil-propeller-library  
**Technical article:** https://www.nablu.com/2022/03/elliptical-blade-naca-airfoil-propeller.html

The downloaded Thingiverse archive contains this exact licensing statement:

> This thing was created by Thingiverse user Amatulic, and is licensed under
> Creative Commons - Attribution

The bundled notice does not identify the Creative Commons version. The exact
archived text is preserved in `UPSTREAM_LICENSE.txt`.

## Changes made by this project

**Project:** Elliptical NACA Propeller Generator  
**Maintainer:** Bruno Martins

The upstream blade and spinner equations were reimplemented in Python and the
Autodesk Fusion API. Substantial changes and additions include:

- smooth B-Rep lofting instead of a faceted OpenSCAD polyhedron;
- exact analytical root and tip trimming;
- surface stitching and solid verification;
- a complete graphical and multilingual interface;
- persistent JSON presets;
- automatic section distribution;
- circular blade pattern;
- final hub and shaft hole;
- optional peripheral hoop;
- automatic assembly of parabolic and ogive spinners;
- extensive maintenance and LLM-oriented documentation.

This project is not affiliated with or endorsed by Alex Matulich,
Thingiverse, Printables or Autodesk.
