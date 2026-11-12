# 3D View Guide

This document explains the three.js visualization that ships with the project
(`frontend/index.html`) and how to build your own. It covers:

1. [Running the bundled frontend](#1-running-the-bundled-frontend)
2. [How it works](#2-how-it-works)
   - [Architecture](#architecture)
   - [The coordinate mapping (the important part)](#the-coordinate-mapping)
   - [Scene setup](#scene-setup)
   - [Rendering a result](#rendering-a-result)
   - [Interaction](#interaction)
3. [Building your own 3D view](#3-building-your-own-3d-view)
   - [Minimal skeleton](#minimal-skeleton)
   - [Step-by-step](#step-by-step)
   - [Common pitfalls](#common-pitfalls)
4. [Customization](#4-customization)

---

## 1. Running the bundled frontend

The frontend is a **single self-contained HTML file** — no build step, no
bundler. It loads three.js from a CDN via an import map.

### Prerequisites

- The API running (see [API.md](API.md#1-running-the-service)).
- A web browser with WebGL.

### Serve and open

```bash
cd frontend
python3 -m http.server 5500
# open http://localhost:5500
```

The page defaults to calling the API at `http://localhost:8000`. If you serve
the frontend from the API's own origin (port 8000), it uses that origin
automatically.

### Using it

1. On load, the 3D view shows a **live sample load** (the default 40 ft
   container with pallets), slowly auto-rotating, so the view is never blank.
2. Enter the **container** dimensions (L/W/H) and an optional max weight.
3. Add **products** (name, L/W/H, quantity, optional weight, orientation).
4. Press **Calculate & visualize** — the sample is replaced by your real
   result. The 3D view renders the container (transparent shell) and every
   placed unit (colored by product). The left panel shows the result (fits
   badge, units placed, remaining volume/percentage, a utilization bar, and a
   collision check).

**Controls:** drag to rotate · scroll to zoom · right-drag to pan ·
double-click to reset the view · hover a box for its name, position, and
dimensions.

**Responsive:** on narrow screens (< 760px) the panel stacks above the 3D
view and the page scrolls vertically; on desktop it is a fixed side panel.

---

## 2. How it works

### Architecture

The whole thing is one HTML file with a `<script type="module">` block:

```
index.html
├── <style>            — layout (left panel + 3D view), dark theme
├── <div id="panel">   — container inputs, product form, result panel
├── <div id="view">    — the WebGL canvas mount point
└── <script type="module">
    ├── imports three + OrbitControls (via import map)
    ├── scene setup (renderer, camera, lights, controls)
    ├── buildContainer() / buildBox() / buildGrid()
    ├── showIdleSample()   — live auto-rotating sample on load
    ├── renderResult(res)  — called after each /check
    ├── checkCollisions(res) — client-side sanity check
    ├── collectRequest()   — read the form into a /check body
    ├── runCheck()         — POST /check, then renderResult()
    └── animate loop + hover/click handlers
```

Data flow:

```
form  →  collectRequest()  →  POST /check  →  response
                                                  │
   renderResult(response)  ←──────────────────────┘
     ├─ buildContainer()      (transparent shell + edges)
     ├─ buildBox() per placement (colored box + edge outline)
     ├─ center content on the grid
     ├─ buildGrid() + fitCameraToBox()
     └─ checkCollisions() → HUD + result panel
```

### The coordinate mapping

This is the single most important thing to get right, and the source of the
"boxes float outside the container" bug.

The **solver** uses `(x, y, z)` = **(length, width, height)** of the
container, and each placement's `(dx, dy, dz)` = the placed
**(length, width, height)** of the unit.

three.js `BoxGeometry(w, h, d)` maps to `(X, Y, Z)`. To keep the container
shell and the boxes **on the same axes**, both use:

```
three.js (X, Y, Z) = (length, height, width)
```

So for a placement:

```
mesh.position = ( x + dx/2 ,  z + dz/2 ,  y + dy/2 )
                 └── X ──┘   └── Y ──┘   └── Z ──┘
                 (length)    (height)    (width)
```

and the container shell:

```
BoxGeometry( length , height , width )
position    = ( length/2 , height/2 , width/2 )   // center the corner-at-origin geometry
```

**If the shell and the boxes use different mappings, they will not align.**
That was the original bug: the shell used `(width, height, length)` while the
boxes used `(dy, dz, dx)`, so the boxes appeared to collide and float outside
the container.

### Scene setup

```javascript
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(80, 1, 0.1, 100000);
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
renderer.setClearColor("#263238");          // dark background
view.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.25;

scene.add(new THREE.AmbientLight(0xffffff, 0.7));
const dir = new THREE.DirectionalLight(0xffffff, 0.9);
dir.position.set(1, 2, 1);
scene.add(dir);
```

- **Camera auto-fit** (`fitCameraToBox`) positions the camera so the whole
  container is visible, using the FOV to compute the required distance.
- **Ground grid + axes** (`buildGrid`) is a `GridHelper` centered at the
  origin plus `ArrowHelper` axis lines.

### Rendering a result

`renderResult(res)` runs on every successful `/check`:

1. `clearContent()` — remove the previous container/boxes/grid and dispose
   geometries (avoids leaks and stale meshes).
2. Build the container shell (`buildContainer`).
3. Build one mesh per placement (`buildBox`), colored by product.
4. **Center** the whole content group on the grid:
   `contentGroup.position.set(-len/2, 0, -wid/2)`.
5. Add the grid and fit the camera.
6. Run `checkCollisions(res)` (a client-side sanity check, independent of the
   API) and update the HUD + result panel.

### Interaction

- **Hover** — a `Raycaster` finds the closest visible box; the box gets an
  emissive highlight and a tooltip shows its name, position, and dimensions.
- **Double-click** — re-fits the camera to the container.
- **Resize** — updates the camera aspect and renderer size.
- **Animation loop** — `requestAnimationFrame` updates the orbit controls and
  renders the scene every frame.

### Client-side collision check

`checkCollisions(res)` re-verifies, from the returned placements alone, that
(a) no two placed boxes overlap and (b) every box lies inside the container.
It is an independent sanity check on top of the solver's own guarantees, and
its result is shown in the HUD (`✓ no collisions`) and the result panel.

---

## 3. Building your own 3D view

### Minimal skeleton

A working viewer is ~150 lines. The minimum you need:

```html
<!DOCTYPE html>
<html>
<head>
  <style> body { margin:0; } #view { width:100vw; height:100vh; } </style>
</head>
<body>
  <div id="view"></div>
  <script type="importmap">
  { "imports": {
      "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
      "three/addons/": "https://unpkg.com/three@0.160.0/examples/jsm/"
  } }
  </script>
  <script type="module">
  import * as THREE from "three";
  import { OrbitControls } from "three/addons/controls/OrbitControls.js";

  const view = document.getElementById("view");
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(80, 1, 0.1, 100000);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setClearColor("#263238");
  renderer.setSize(innerWidth, innerHeight);
  view.appendChild(renderer.domElement);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const dir = new THREE.DirectionalLight(0xffffff, 0.9);
  dir.position.set(1, 2, 1); scene.add(dir);

  // --- fit the camera to a box ---
  function fitCameraToBox(box, offset = 1.5) {
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = camera.fov * Math.PI / 180;
    const camZ = Math.abs(maxDim / 2 / Math.tan(fov / 2)) * offset;
    camera.position.set(center.x - camZ * 0.2, center.y + camZ * 0.55, center.z + camZ);
    camera.lookAt(center);
    controls.target.copy(center);
    controls.update();
  }

  // --- container shell ---
  function buildContainer(len, wid, hei) {
    const geo = new THREE.BoxGeometry(len, hei, wid);
    const g = new THREE.Group();
    const shell = new THREE.Mesh(geo, new THREE.MeshPhongMaterial({
      color: 0x888888, opacity: 0.12, transparent: true, depthWrite: false }));
    shell.position.set(len / 2, hei / 2, wid / 2);
    g.add(shell);
    g.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo),
      new THREE.LineBasicMaterial({ color: 0x9aa7ad })));
    return g;
  }

  // --- one box (a placement) ---
  function buildBox(p, color) {
    const geo = new THREE.BoxGeometry(p.dx, p.dz, p.dy);
    const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
      color, opacity: 0.72, metalness: 0.15, roughness: 0.9, transparent: true }));
    m.position.set(p.x + p.dx / 2, p.z + p.dz / 2, p.y + p.dy / 2);
    m.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo),
      new THREE.LineBasicMaterial({ color: 0x10151a })));
    return m;
  }

  // --- render a /check response ---
  async function render() {
    const res = await (await fetch("http://localhost:8000/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        box: { length: 1200, width: 235, height: 235 },
        products: [{ id: "pallet", length: 120, width: 80, height: 100, quantity: 30 }],
      }),
    })).json();

    scene.clear();
    const len = res._box?.length ?? 1200, wid = 235, hei = 235;
    const content = new THREE.Group();
    content.add(buildContainer(len, wid, hei));
    for (const p of res.placements) content.add(buildBox(p, 0x42a5f5));
    content.position.set(-len / 2, 0, -wid / 2);
    scene.add(content);
    fitCameraToBox(new THREE.Box3(new THREE.Vector3(-len/2, 0, -wid/2),
                                  new THREE.Vector3(len/2, hei, wid/2)));
  }

  (function animate() { requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); })();
  render();
  </script>
</body>
</html>
```

### Step-by-step

1. **Create the scene, camera, renderer, and lights** (see the skeleton).
2. **Add `OrbitControls`** for rotate/zoom/pan.
3. **Build the container shell** — a transparent `BoxGeometry` + `EdgesGeometry`
   outline, centered on its corner-at-origin geometry.
4. **Build one mesh per placement** — a `BoxGeometry(dx, dz, dy)` positioned at
   `(x + dx/2, z + dz/2, y + dy/2)`, with an edge outline. Use one color per
   product.
5. **Center the content** on the grid: `content.position.set(-len/2, 0, -wid/2)`.
6. **Fit the camera** to the container using the FOV.
7. **Animate** with `requestAnimationFrame`, updating controls and rendering.
8. **(Optional) Add hover** with a `Raycaster` + emissive highlight + tooltip.
9. **(Optional) Add a ground grid** with `GridHelper` + `ArrowHelper` axes.

### Common pitfalls

- **Mismatched axis mapping** (the big one). The container shell and the boxes
  must use the *same* `(X, Y, Z)` mapping. If they differ, boxes float outside
  the container and appear to collide. Use `(X, Y, Z) = (length, height, width)`
  for both.
- **Forgetting to center the shell.** `BoxGeometry` is centered at its own
  origin, but the solver's coordinates start at the container corner. Offset the
  shell (and the content group) by half its size so the corner sits at the
  origin.
- **Not disposing geometries** when re-rendering. Call `geometry.dispose()` on
  removed meshes to avoid GPU memory leaks.
- **Calling `renderer.setSize` only once.** Update it on window resize.
- **Using a CDN without internet.** The bundled frontend loads three.js from
  unpkg. For an offline environment, vendor the library locally (see
  [Customization](#4-customization)).

---

## 4. Customization

- **Colors:** change the `color` argument to `buildBox` (one per product) and
  the shell/edge colors in `buildContainer`.
- **Background:** `renderer.setClearColor(...)`.
- **Offline three.js:** download `three.module.js` and the `OrbitControls`
  addon, serve them locally, and point the import map at the local paths
  instead of unpkg.
- **Multiple containers / comparison:** lay several containers out side by
  side along one axis (as the reference visualizer does) and fit the camera to
  the combined extent.
- **Packing steps animation:** store each placement's order and reveal boxes
  progressively (the reference visualizer steps through placements with a
  keypress).
- **Colour modes:** recolor boxes by support, load, or group (see the
  reference `colorModes.ts` for the idea).
