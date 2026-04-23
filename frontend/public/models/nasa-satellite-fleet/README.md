# NASA Satellite Fleet Models

This folder contains GLB models downloaded from NASA 3D Resources for the
space forecast orbital visualization.

NASA states that the 3D Resources hub stores models related to NASA missions
and that the assets are free to download and use. Follow the NASA Images and
Media Usage Guidelines when publishing the app.

Sources:

- Landsat 8: https://science.nasa.gov/3d-resources/landsat-8/
- CubeSat ICECube: https://science.nasa.gov/3d-resources/cubesat-icecube/
- CloudSat (B): https://science.nasa.gov/3d-resources/cloudsat-b/
- AcrimSAT (B): https://science.nasa.gov/3d-resources/active-cavity-irradiance-monitor-satellite-acrimsat-b/
- Mars Global Surveyor: https://science.nasa.gov/3d-resources/mars-global-surveyor/
- NASA 3D Resources hub: https://science.nasa.gov/3d-resources/
- NASA media usage guidelines: https://www.nasa.gov/nasa-brand-center/images-and-media/

Runtime note:

- These GLB files use Draco-compressed geometry, so the viewer serves the
  Three.js Draco decoder from `/vendor/draco/`.
