// Monopoly Meta: a 3D board in plain WebGL (no libraries), drawn in the project's own style.
//
//   const board = MMBoard3D.create(container, { onPick(square), onHover(square|null, event) });
//   board.set({ squares, selected, mode, heights, colors, moves, labels });   // redraws on demand
//   board.roll() -> Promise<{ d1, d2, from, to }>                              // dice + pawn animation
//   board.destroy();
//
// `squares`: 40 rows {square, name, type, group, price, tax}; `heights`: 40 numbers in 0..1 (null = no tower);
// `colors`: {paper, ink, line, side, neutral, accent, pawn, groups:{brown:…}} as CSS colours;
// `moves`: 40 probabilities of landing on each square from `selected` (roll mode).
// Returns null when WebGL isn't available, so the caller can fall back to a flat board.
window.MMBoard3D = (() => {
  'use strict';

  // ------------------------------------------------------------------ board layout (x right, z towards the viewer)
  const B = 6.1, C = 1.6, W = 1.0, BAND = 0.34;
  const side = (i) => Math.floor(i / 10);
  const rect = (i) => {
    const k = i % 10, s = side(i);
    if (k === 0) return [[B - C, B, B - C, B], [-B, -B + C, B - C, B], [-B, -B + C, -B, -B + C], [B - C, B, -B, -B + C]][s];
    if (s === 0) { const x1 = B - C - (k - 1) * W; return [x1 - W, x1, B - C, B]; }
    if (s === 1) { const z1 = B - C - (k - 1) * W; return [-B, -B + C, z1 - W, z1]; }
    if (s === 2) { const x0 = -B + C + (k - 1) * W; return [x0, x0 + W, -B, -B + C]; }
    const z0 = -B + C + (k - 1) * W; return [B - C, B, z0, z0 + W];
  };
  const centre = (i) => { const [x0, x1, z0, z1] = rect(i); return [(x0 + x1) / 2, (z0 + z1) / 2]; };
  const squareAt = (x, z) => {
    for (let i = 0; i < 40; i++) { const [x0, x1, z0, z1] = rect(i); if (x >= x0 && x <= x1 && z >= z0 && z <= z1) return i; }
    return null;
  };

  // ------------------------------------------------------------------ small matrix kit (column-major 4x4)
  const M = {
    ident: () => [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
    mul(a, b) {
      const o = new Array(16);
      for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
        o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
      }
      return o;
    },
    persp(fovy, aspect, near, far) {
      const f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far);
      return [f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0];
    },
    look(eye, at, up) {
      const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
      const norm = (v) => { const l = Math.hypot(...v) || 1; return v.map((x) => x / l); };
      const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
      const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
      const zz = norm(sub(eye, at)), xx = norm(cross(up, zz)), yy = cross(zz, xx);
      return [xx[0], yy[0], zz[0], 0, xx[1], yy[1], zz[1], 0, xx[2], yy[2], zz[2], 0, -dot(xx, eye), -dot(yy, eye), -dot(zz, eye), 1];
    },
    trs(t, r, s) { // translate * rotate(3x3, row-major array or null) * scale
      const [sx, sy, sz] = s, R = r || [1, 0, 0, 0, 1, 0, 0, 0, 1];
      return [R[0] * sx, R[3] * sx, R[6] * sx, 0, R[1] * sy, R[4] * sy, R[7] * sy, 0, R[2] * sz, R[5] * sz, R[8] * sz, 0, t[0], t[1], t[2], 1];
    },
    invert(m) {
      const inv = new Array(16);
      inv[0] = m[5] * m[10] * m[15] - m[5] * m[11] * m[14] - m[9] * m[6] * m[15] + m[9] * m[7] * m[14] + m[13] * m[6] * m[11] - m[13] * m[7] * m[10];
      inv[4] = -m[4] * m[10] * m[15] + m[4] * m[11] * m[14] + m[8] * m[6] * m[15] - m[8] * m[7] * m[14] - m[12] * m[6] * m[11] + m[12] * m[7] * m[10];
      inv[8] = m[4] * m[9] * m[15] - m[4] * m[11] * m[13] - m[8] * m[5] * m[15] + m[8] * m[7] * m[13] + m[12] * m[5] * m[11] - m[12] * m[7] * m[9];
      inv[12] = -m[4] * m[9] * m[14] + m[4] * m[10] * m[13] + m[8] * m[5] * m[14] - m[8] * m[6] * m[13] - m[12] * m[5] * m[10] + m[12] * m[6] * m[9];
      inv[1] = -m[1] * m[10] * m[15] + m[1] * m[11] * m[14] + m[9] * m[2] * m[15] - m[9] * m[3] * m[14] - m[13] * m[2] * m[11] + m[13] * m[3] * m[10];
      inv[5] = m[0] * m[10] * m[15] - m[0] * m[11] * m[14] - m[8] * m[2] * m[15] + m[8] * m[3] * m[14] + m[12] * m[2] * m[11] - m[12] * m[3] * m[10];
      inv[9] = -m[0] * m[9] * m[15] + m[0] * m[11] * m[13] + m[8] * m[1] * m[15] - m[8] * m[3] * m[13] - m[12] * m[1] * m[11] + m[12] * m[3] * m[9];
      inv[13] = m[0] * m[9] * m[14] - m[0] * m[10] * m[13] - m[8] * m[1] * m[14] + m[8] * m[2] * m[13] + m[12] * m[1] * m[10] - m[12] * m[2] * m[9];
      inv[2] = m[1] * m[6] * m[15] - m[1] * m[7] * m[14] - m[5] * m[2] * m[15] + m[5] * m[3] * m[14] + m[13] * m[2] * m[7] - m[13] * m[3] * m[6];
      inv[6] = -m[0] * m[6] * m[15] + m[0] * m[7] * m[14] + m[4] * m[2] * m[15] - m[4] * m[3] * m[14] - m[12] * m[2] * m[7] + m[12] * m[3] * m[6];
      inv[10] = m[0] * m[5] * m[15] - m[0] * m[7] * m[13] - m[4] * m[1] * m[15] + m[4] * m[3] * m[13] + m[12] * m[1] * m[7] - m[12] * m[3] * m[5];
      inv[14] = -m[0] * m[5] * m[14] + m[0] * m[6] * m[13] + m[4] * m[1] * m[14] - m[4] * m[2] * m[13] - m[12] * m[1] * m[6] + m[12] * m[2] * m[5];
      inv[3] = -m[1] * m[6] * m[11] + m[1] * m[7] * m[10] + m[5] * m[2] * m[11] - m[5] * m[3] * m[10] - m[9] * m[2] * m[7] + m[9] * m[3] * m[6];
      inv[7] = m[0] * m[6] * m[11] - m[0] * m[7] * m[10] - m[4] * m[2] * m[11] + m[4] * m[3] * m[10] + m[8] * m[2] * m[7] - m[8] * m[3] * m[6];
      inv[11] = -m[0] * m[5] * m[11] + m[0] * m[7] * m[9] + m[4] * m[1] * m[11] - m[4] * m[3] * m[9] - m[8] * m[1] * m[7] + m[8] * m[3] * m[5];
      inv[15] = m[0] * m[5] * m[10] - m[0] * m[6] * m[9] - m[4] * m[1] * m[10] + m[4] * m[2] * m[9] + m[8] * m[1] * m[6] - m[8] * m[2] * m[5];
      let det = m[0] * inv[0] + m[1] * inv[4] + m[2] * inv[8] + m[3] * inv[12];
      det = det ? 1 / det : 0;
      return inv.map((v) => v * det);
    },
    xform(m, v) { // point
      const x = v[0], y = v[1], z = v[2];
      const w = m[3] * x + m[7] * y + m[11] * z + m[15];
      return [(m[0] * x + m[4] * y + m[8] * z + m[12]) / w, (m[1] * x + m[5] * y + m[9] * z + m[13]) / w, (m[2] * x + m[6] * y + m[10] * z + m[14]) / w];
    },
  };
  const rotX = (a) => [1, 0, 0, 0, Math.cos(a), -Math.sin(a), 0, Math.sin(a), Math.cos(a)];
  const rotY = (a) => [Math.cos(a), 0, Math.sin(a), 0, 1, 0, -Math.sin(a), 0, Math.cos(a)];
  const rotZ = (a) => [Math.cos(a), -Math.sin(a), 0, Math.sin(a), Math.cos(a), 0, 0, 0, 1];
  const mul3 = (a, b) => {
    const o = new Array(9);
    for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) o[r * 3 + c] = a[r * 3] * b[c] + a[r * 3 + 1] * b[3 + c] + a[r * 3 + 2] * b[6 + c];
    return o;
  };

  // ------------------------------------------------------------------ meshes: [x,y,z, nx,ny,nz, u,v] per vertex
  const box = () => { // unit cube centred on the origin, with each face's own uv square
    const f = (n, u, v) => {
      const out = [];
      const c = [[-1, -1], [1, -1], [1, 1], [-1, -1], [1, 1], [-1, 1]];
      for (const [a, b] of c) {
        const p = n.map((x, i) => x * 0.5 + u[i] * a * 0.5 + v[i] * b * 0.5);
        out.push(...p, ...n, (a + 1) / 2, (1 - b) / 2);
      }
      return out;
    };
    return new Float32Array([
      ...f([0, 1, 0], [1, 0, 0], [0, 0, -1]), ...f([0, -1, 0], [1, 0, 0], [0, 0, 1]),
      ...f([1, 0, 0], [0, 0, -1], [0, 1, 0]), ...f([-1, 0, 0], [0, 0, 1], [0, 1, 0]),
      ...f([0, 0, 1], [1, 0, 0], [0, 1, 0]), ...f([0, 0, -1], [-1, 0, 0], [0, 1, 0]),
    ]);
  };
  const roof = () => { // a pyramid on a unit square: base y=0, apex y=1
    const out = [];
    const base = [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]];
    for (let i = 0; i < 4; i++) {
      const a = base[i], b = base[(i + 1) % 4];
      const p = [[a[0], 0, a[1]], [b[0], 0, b[1]], [0, 1, 0]];
      const e1 = p[1].map((x, k) => x - p[0][k]), e2 = p[2].map((x, k) => x - p[0][k]);
      let n = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]];
      const l = Math.hypot(...n); n = n.map((x) => x / l);
      if (n[1] < 0) { n = n.map((x) => -x); p.reverse(); }
      for (const q of p) out.push(...q, ...n, 0, 0);
    }
    return new Float32Array(out);
  };
  const quad = () => new Float32Array([ // unit square in the xz plane, facing up, uv over it
    -0.5, 0, -0.5, 0, 1, 0, 0, 0, 0.5, 0, 0.5, 0, 1, 0, 1, 1, 0.5, 0, -0.5, 0, 1, 0, 1, 0,
    -0.5, 0, -0.5, 0, 1, 0, 0, 0, -0.5, 0, 0.5, 0, 1, 0, 0, 1, 0.5, 0, 0.5, 0, 1, 0, 1, 1,
  ]);
  const lathe = (profile, n = 28) => { // a pawn: profile [[r, y], ...] spun around y
    const out = [];
    for (let i = 0; i < profile.length - 1; i++) {
      const [r0, y0] = profile[i], [r1, y1] = profile[i + 1];
      const dr = r1 - r0, dy = y1 - y0, len = Math.hypot(dr, dy) || 1;
      const nr = dy / len, ny = -dr / len;
      for (let k = 0; k < n; k++) {
        const a0 = (k / n) * Math.PI * 2, a1 = ((k + 1) / n) * Math.PI * 2;
        const v = (r, y, a) => [r * Math.cos(a), y, r * Math.sin(a), nr * Math.cos(a), ny, nr * Math.sin(a), 0, 0];
        out.push(...v(r0, y0, a0), ...v(r1, y1, a1), ...v(r1, y1, a0), ...v(r0, y0, a0), ...v(r0, y0, a1), ...v(r1, y1, a1));
      }
    }
    return new Float32Array(out);
  };
  const PAWN = [[0, 0], [0.3, 0], [0.31, 0.07], [0.22, 0.12], [0.13, 0.2], [0.09, 0.42], [0.16, 0.47], [0.16, 0.5],
    [0.1, 0.53], [0.15, 0.6], [0.16, 0.66], [0.14, 0.73], [0.08, 0.78], [0, 0.8]];

  // ------------------------------------------------------------------ shaders
  const VS = `attribute vec3 aPos; attribute vec3 aNor; attribute vec2 aUV;
    uniform mat4 uMVP; uniform mat4 uModel; uniform mat4 uNorm;
    varying vec3 vNor; varying vec2 vUV;
    void main() { vNor = normalize((uNorm * vec4(aNor, 0.0)).xyz); vUV = aUV; gl_Position = uMVP * vec4(aPos, 1.0); }`;
  const FS = `precision mediump float;
    varying vec3 vNor; varying vec2 vUV;
    uniform vec4 uColor; uniform sampler2D uTex; uniform float uUseTex; uniform float uLit; uniform vec3 uLight;
    void main() {
      vec4 base = uUseTex > 0.5 ? texture2D(uTex, vUV) * vec4(uColor.rgb, 1.0) : uColor;
      float d = max(dot(normalize(vNor), uLight), 0.0);
      float shade = mix(1.0, 0.58 + 0.5 * d, uLit);
      gl_FragColor = vec4(base.rgb * shade, base.a * uColor.a);
    }`;

  // ------------------------------------------------------------------ colours
  const rgba = (() => {
    const cv = document.createElement('canvas'); cv.width = cv.height = 1;
    const ctx = cv.getContext('2d', { willReadFrequently: true });
    return (c, a = 1) => {
      ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = '#888'; ctx.fillStyle = c; ctx.fillRect(0, 0, 1, 1);
      const d = ctx.getImageData(0, 0, 1, 1).data;
      return [d[0] / 255, d[1] / 255, d[2] / 255, a];
    };
  })();
  const mix = (a, b, t) => a.map((x, i) => (i < 3 ? x + (b[i] - x) * t : x));
  const css = (c) => `rgb(${Math.round(c[0] * 255)}, ${Math.round(c[1] * 255)}, ${Math.round(c[2] * 255)})`;

  // ------------------------------------------------------------------ the board's printed top, drawn on a canvas
  const ICONS = {
    chance(ctx, s) { ctx.beginPath(); ctx.arc(0, -s * 0.05, s * 0.2, 0, Math.PI * 2); ctx.stroke(); ctx.font = `700 ${s * 0.3}px var(--mm-board-font)`; ctx.fillText('?', 0, s * 0.06); },
    community_chest(ctx, s) {
      ctx.strokeRect(-s * 0.22, -s * 0.16, s * 0.44, s * 0.26);
      ctx.beginPath(); ctx.moveTo(-s * 0.22, -s * 0.06); ctx.lineTo(s * 0.22, -s * 0.06); ctx.stroke();
      ctx.beginPath(); ctx.arc(0, -s * 0.16, s * 0.22, Math.PI, 0); ctx.stroke();
    },
    station(ctx, s) {
      ctx.strokeRect(-s * 0.2, -s * 0.2, s * 0.4, s * 0.28);
      ctx.beginPath(); ctx.arc(-s * 0.1, s * 0.12, s * 0.05, 0, Math.PI * 2); ctx.arc(s * 0.1, s * 0.12, s * 0.05, 0, Math.PI * 2); ctx.fill();
      ctx.fillRect(-s * 0.14, -s * 0.15, s * 0.28, s * 0.08);
    },
    utility(ctx, s) {
      ctx.beginPath(); ctx.arc(0, -s * 0.08, s * 0.14, 0.75 * Math.PI, 2.25 * Math.PI); ctx.lineTo(s * 0.06, s * 0.12); ctx.lineTo(-s * 0.06, s * 0.12); ctx.closePath(); ctx.stroke();
      ctx.fillRect(-s * 0.06, s * 0.14, s * 0.12, s * 0.05);
    },
    tax(ctx, s) { ctx.beginPath(); ctx.moveTo(-s * 0.18, s * 0.1); ctx.lineTo(0, -s * 0.18); ctx.lineTo(s * 0.18, s * 0.1); ctx.closePath(); ctx.stroke(); },
  };
  const wrap = (ctx, text, maxW) => {
    const words = String(text).toUpperCase().split(/\s+/), lines = [];
    let line = '';
    for (const w of words) {
      const t = line ? line + ' ' + w : w;
      if (ctx.measureText(t).width > maxW && line) { lines.push(line); line = w; } else line = t;
    }
    if (line) lines.push(line);
    return lines;
  };
  const drawBoard = (cv, squares, col, font) => {
    const N = cv.width, k = N / (2 * B), ctx = cv.getContext('2d');
    const X = (x) => (x + B) * k, Z = (z) => (z + B) * k;
    ctx.save();
    ctx.fillStyle = css(col.paper); ctx.fillRect(0, 0, N, N);
    // centre: a faint grid of the project's own, and the frame of the track
    ctx.strokeStyle = css(mix(col.paper, col.ink, 0.07)); ctx.lineWidth = Math.max(1, k * 0.012);
    for (let g = -B + C + 0.5; g < B - C; g += 0.5) {
      ctx.beginPath(); ctx.moveTo(X(g), Z(-B + C)); ctx.lineTo(X(g), Z(B - C)); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(X(-B + C), Z(g)); ctx.lineTo(X(B - C), Z(g)); ctx.stroke();
    }
    ctx.strokeStyle = css(col.line); ctx.lineWidth = k * 0.025;
    ctx.strokeRect(X(-B) + ctx.lineWidth / 2, Z(-B) + ctx.lineWidth / 2, 2 * B * k - ctx.lineWidth, 2 * B * k - ctx.lineWidth);
    ctx.strokeRect(X(-B + C), Z(-B + C), 2 * (B - C) * k, 2 * (B - C) * k);
    const angle = [0, Math.PI / 2, Math.PI, -Math.PI / 2];
    const cornerAngle = [-Math.PI / 4, Math.PI / 4, 3 * Math.PI / 4, -3 * Math.PI / 4];
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (const r of squares) {
      const i = +r.square, s = side(i), [x0, x1, z0, z1] = rect(i);
      ctx.strokeStyle = css(col.line); ctx.lineWidth = k * 0.018;
      ctx.strokeRect(X(x0), Z(z0), (x1 - x0) * k, (z1 - z0) * k);
      const [cx, cz] = centre(i);
      ctx.save();
      ctx.fillStyle = css(col.ink); ctx.strokeStyle = css(col.ink); ctx.lineWidth = k * 0.022;
      if (i % 10 === 0) { // corners, text across the diagonal
        ctx.translate(X(cx), Z(cz)); ctx.rotate(cornerAngle[s]);
        const u = C * k;
        const big = (t, y, size) => { ctx.font = `700 ${size}px ${font}`; ctx.fillText(t, 0, y); };
        if (r.type === 'go') {
          big('GO', u * 0.05, u * 0.34);
          ctx.beginPath(); ctx.moveTo(u * 0.28, -u * 0.26); ctx.lineTo(-u * 0.24, -u * 0.26); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(-u * 0.24, -u * 0.26); ctx.lineTo(-u * 0.14, -u * 0.32); ctx.lineTo(-u * 0.14, -u * 0.2); ctx.closePath(); ctx.fill();
        } else if (r.type === 'jail') {
          const b = u * 0.36;
          ctx.strokeRect(-b / 2, -b / 2 - u * 0.08, b, b);
          for (let q = 1; q < 4; q++) { ctx.beginPath(); ctx.moveTo(-b / 2 + (q * b) / 4, -b / 2 - u * 0.08); ctx.lineTo(-b / 2 + (q * b) / 4, b / 2 - u * 0.08); ctx.stroke(); }
          big('JAIL', u * 0.25, u * 0.13);
          ctx.font = `500 ${u * 0.08}px ${font}`; ctx.fillText('JUST VISITING', 0, u * 0.37);
        } else if (r.type === 'free_parking') {
          ctx.strokeRect(-u * 0.13, -u * 0.32, u * 0.26, u * 0.3);
          big('P', -u * 0.165, u * 0.22);
          big('FREE', u * 0.11, u * 0.12); big('PARKING', u * 0.26, u * 0.12);
        } else {
          ctx.beginPath(); ctx.moveTo(u * 0.22, -u * 0.12); ctx.lineTo(-u * 0.2, -u * 0.12); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(-u * 0.26, -u * 0.12); ctx.lineTo(-u * 0.14, -u * 0.2); ctx.lineTo(-u * 0.14, -u * 0.04); ctx.closePath(); ctx.fill();
          big('GO TO', u * 0.1, u * 0.13); big('JAIL', u * 0.27, u * 0.16);
        }
        ctx.restore();
        continue;
      }
      // a regular square: local frame with its outer edge at y = 0 and the board centre towards -y
      const ox = s === 0 ? cx : s === 1 ? -B : s === 2 ? cx : B, oz = s === 0 ? B : s === 1 ? cz : s === 2 ? -B : cz;
      ctx.translate(X(ox), Z(oz)); ctx.rotate(angle[s]);
      const w = W * k, h = C * k;
      if (r.type === 'street' && col.groups[r.group]) {
        ctx.fillStyle = css(col.groups[r.group]); ctx.fillRect(-w / 2, -h, w, BAND * k);
        ctx.strokeStyle = css(col.line); ctx.lineWidth = k * 0.018;
        ctx.beginPath(); ctx.moveTo(-w / 2, -h + BAND * k); ctx.lineTo(w / 2, -h + BAND * k); ctx.stroke();
        ctx.fillStyle = css(col.ink);
      }
      const top = r.type === 'street' ? -h + BAND * k + w * 0.12 : -h + w * 0.14;
      ctx.font = `600 ${w * 0.15}px ${font}`;
      const lines = wrap(ctx, r.name, w * 0.86).slice(0, 3);
      lines.forEach((t, j) => ctx.fillText(t, 0, top + j * w * 0.17));
      const icon = ICONS[r.type];
      if (icon) { ctx.save(); ctx.translate(0, -h * 0.36); ctx.lineWidth = k * 0.03; icon(ctx, w); ctx.restore(); }
      const money = r.price ? r.price : r.tax ? r.tax : null;
      if (money) {
        ctx.font = `500 ${w * 0.15}px ${font}`;
        ctx.fillText((r.tax ? 'PAY £' : '£') + Number(money).toLocaleString('en-GB'), 0, -w * 0.18);
      }
      ctx.restore();
    }
    ctx.restore();
  };
  const drawDice = (cv, col) => { // 6 faces in a row; pips in ink on paper
    const n = cv.height, ctx = cv.getContext('2d');
    const pips = { 1: [[0.5, 0.5]], 2: [[0.28, 0.28], [0.72, 0.72]], 3: [[0.28, 0.28], [0.5, 0.5], [0.72, 0.72]],
      4: [[0.28, 0.28], [0.72, 0.28], [0.28, 0.72], [0.72, 0.72]], 5: [[0.28, 0.28], [0.72, 0.28], [0.5, 0.5], [0.28, 0.72], [0.72, 0.72]],
      6: [[0.28, 0.25], [0.72, 0.25], [0.28, 0.5], [0.72, 0.5], [0.28, 0.75], [0.72, 0.75]] };
    for (let f = 1; f <= 6; f++) {
      const x0 = (f - 1) * n;
      ctx.fillStyle = css(mix(col.paper, [1, 1, 1, 1], 0.6)); ctx.fillRect(x0, 0, n, n);
      ctx.fillStyle = css(col.ink);
      for (const [u, v] of pips[f]) { ctx.beginPath(); ctx.arc(x0 + u * n, v * n, n * 0.085, 0, Math.PI * 2); ctx.fill(); }
    }
  };

  // ------------------------------------------------------------------ create
  const create = (container, opts = {}) => {
    const canvas = document.createElement('canvas');
    canvas.className = 'mm-b3-canvas';
    const gl = canvas.getContext('webgl', { antialias: true, alpha: true, premultipliedAlpha: false, preserveDrawingBuffer: true });
    if (!gl) return null;
    container.appendChild(canvas);
    const overlay = document.createElement('div');
    overlay.className = 'mm-b3-overlay';
    container.appendChild(overlay);

    const compile = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; };
    const prog = gl.createProgram();
    gl.attachShader(prog, compile(gl.VERTEX_SHADER, VS)); gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(prog); gl.useProgram(prog);
    const A = { pos: gl.getAttribLocation(prog, 'aPos'), nor: gl.getAttribLocation(prog, 'aNor'), uv: gl.getAttribLocation(prog, 'aUV') };
    const U = Object.fromEntries(['uMVP', 'uModel', 'uNorm', 'uColor', 'uTex', 'uUseTex', 'uLit', 'uLight'].map((n) => [n, gl.getUniformLocation(prog, n)]));
    const mesh = (data) => { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW); return { b, n: data.length / 8 }; };
    const meshes = { box: mesh(box()), roof: mesh(roof()), quad: mesh(quad()), pawn: mesh(lathe(PAWN)) };
    const texture = (cv) => {
      const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, cv);
      gl.generateMipmap(gl.TEXTURE_2D);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      const an = gl.getExtension('EXT_texture_filter_anisotropic');
      if (an) gl.texParameterf(gl.TEXTURE_2D, an.TEXTURE_MAX_ANISOTROPY_EXT, Math.min(8, gl.getParameter(an.MAX_TEXTURE_MAX_ANISOTROPY_EXT)));
      return t;
    };
    const maxTex = gl.getParameter(gl.MAX_TEXTURE_SIZE);
    const boardCanvas = document.createElement('canvas');
    boardCanvas.width = boardCanvas.height = Math.min(2048, maxTex);
    const diceCanvas = document.createElement('canvas'); diceCanvas.width = 6 * 128; diceCanvas.height = 128;
    const shadowCanvas = document.createElement('canvas'); shadowCanvas.width = shadowCanvas.height = 128;
    {
      const ctx = shadowCanvas.getContext('2d'), g = ctx.createRadialGradient(64, 64, 20, 64, 64, 64);
      g.addColorStop(0, 'rgba(0,0,0,0.55)'); g.addColorStop(0.62, 'rgba(0,0,0,0.25)'); g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g; ctx.fillRect(0, 0, 128, 128);
    }
    let boardTex = null, diceTex = null;
    const shadowTex = texture(shadowCanvas);

    // ------------------------------------------------ state
    const S = { squares: [], heights: Array(40).fill(null), colors: null, selected: 0, mode: 'towers', moves: null, labels: null };
    const cam = { yaw: -0.62, pitch: 0.92, zoom: 1 };
    const anim = { dice: null, pawn: null, drop: 0 };
    let raf = 0, view = null, viewProj = null, size = [1, 1], destroyed = false, lastSig = '';
    const reduced = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
    const fontFamily = () => {
      const f = getComputedStyle(container).getPropertyValue('--mm-display').trim();
      return f || 'Impact, "Arial Narrow", sans-serif';
    };

    const resize = () => {
      const w = Math.max(240, container.clientWidth), h = Math.round(Math.min(Math.max(w * 0.72, 280), 600));
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      container.style.height = h + 'px';
      size = [w, h];
      request();
    };
    const camera = () => {
      const [w, h] = size, aspect = w / h, fovy = 0.62;
      const hf = 2 * Math.atan(Math.tan(fovy / 2) * aspect);
      const need = Math.max(8.7 / Math.tan(Math.min(hf, fovy * 1.15) / 2), 7.4 / Math.tan(fovy / 2));
      const dist = need * cam.zoom;
      const eye = [dist * Math.cos(cam.pitch) * Math.sin(cam.yaw), dist * Math.sin(cam.pitch), dist * Math.cos(cam.pitch) * Math.cos(cam.yaw)];
      view = M.look(eye, [0, -0.6, 0], [0, 1, 0]);
      viewProj = M.mul(M.persp(fovy, aspect, 0.5, 80), view);
      return eye;
    };
    const draw = (model, meshName, color, { tex = null, lit = 1, normal = null } = {}) => {
      const m = meshes[meshName];
      gl.bindBuffer(gl.ARRAY_BUFFER, m.b);
      gl.vertexAttribPointer(A.pos, 3, gl.FLOAT, false, 32, 0); gl.enableVertexAttribArray(A.pos);
      gl.vertexAttribPointer(A.nor, 3, gl.FLOAT, false, 32, 12); gl.enableVertexAttribArray(A.nor);
      gl.vertexAttribPointer(A.uv, 2, gl.FLOAT, false, 32, 24); gl.enableVertexAttribArray(A.uv);
      gl.uniformMatrix4fv(U.uMVP, false, new Float32Array(M.mul(viewProj, model)));
      gl.uniformMatrix4fv(U.uModel, false, new Float32Array(model));
      const inv = M.invert(model);
      const nm = normal || [inv[0], inv[4], inv[8], 0, inv[1], inv[5], inv[9], 0, inv[2], inv[6], inv[10], 0, 0, 0, 0, 1];
      gl.uniformMatrix4fv(U.uNorm, false, new Float32Array(nm));
      gl.uniform4fv(U.uColor, color);
      gl.uniform1f(U.uUseTex, tex ? 1 : 0); gl.uniform1f(U.uLit, lit);
      if (tex) { gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, tex); gl.uniform1i(U.uTex, 0); }
      gl.drawArrays(gl.TRIANGLES, 0, m.n);
    };
    const towerBox = (i) => {
      const [cx, cz] = centre(i), corner = i % 10 === 0, f = corner ? 0.56 : 0.42;
      const h = S.heights[i] == null ? 0 : 0.1 + S.heights[i] * 2.3;
      return { cx, cz, f, h };
    };
    const pawnPos = () => {
      if (anim.pawn) return anim.pawn.pos;
      const [x, z] = centre(S.selected);
      return [x, 0, z];
    };

    const render = () => {
      raf = 0;
      if (destroyed || !S.colors) return;
      const col = S.colors;
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.DEPTH_TEST); gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      camera();
      const L = [-0.42, 0.85, 0.55], l = Math.hypot(...L); gl.uniform3fv(U.uLight, L.map((x) => x / l));
      // soft contact shadow, the slab, and its printed top
      gl.depthMask(false);
      draw(M.trs([0.25, -0.42, 0.35], null, [2 * B + 3.2, 1, 2 * B + 3.2]), 'quad', [1, 1, 1, 0.9], { tex: shadowTex, lit: 0 });
      gl.depthMask(true);
      draw(M.trs([0, -0.18, 0], null, [2 * B, 0.36, 2 * B]), 'box', col.side);
      if (boardTex) draw(M.trs([0, 0.002, 0], null, [2 * B, 1, 2 * B]), 'quad', [1, 1, 1, 1], { tex: boardTex, lit: 0.55 });
      // the selected square's frame
      const sel = S.selected, [sx0, sx1, sz0, sz1] = rect(sel), lw = 0.07;
      const frame = [[(sx0 + sx1) / 2, sz0, sx1 - sx0 + lw, lw], [(sx0 + sx1) / 2, sz1, sx1 - sx0 + lw, lw], [sx0, (sz0 + sz1) / 2, lw, sz1 - sz0], [sx1, (sz0 + sz1) / 2, lw, sz1 - sz0]];
      for (const [x, z, w, d] of frame) draw(M.trs([x, 0.012, z], null, [w, 1, d]), 'quad', col.accent, { lit: 0 });
      if (S.mode === 'roll' && S.moves) {
        const pmax = Math.max(...S.moves.filter((p) => p != null)) || 1;
        gl.depthMask(false);
        for (let i = 0; i < 40; i++) {
          const p = S.moves[i];
          if (!p) continue;
          const [x0, x1, z0, z1] = rect(i);
          draw(M.trs([(x0 + x1) / 2, 0.008, (z0 + z1) / 2], null, [x1 - x0 - 0.04, 1, z1 - z0 - 0.04]), 'quad',
            [col.glow[0], col.glow[1], col.glow[2], 0.12 + 0.68 * (p / pmax)], { lit: 0 });
        }
        gl.depthMask(true);
      } else {
        for (let i = 0; i < 40; i++) {
          const { cx, cz, f, h } = towerBox(i);
          if (!h) continue;
          const r = S.squares[i], base = r && r.type === 'street' || r && (r.type === 'station' || r.type === 'utility')
            ? (col.groups[r.group] || col.neutral) : col.neutral;
          const c = i === sel ? mix(base, [1, 1, 1, 1], 0.18) : base;
          const drop = i === sel ? anim.drop : 0;
          draw(M.trs([cx, h / 2 + drop, cz], null, [f, h, f]), 'box', c);
          draw(M.trs([cx, h + drop, cz], null, [f * 1.12, 0.32 * f / 0.5, f * 1.12]), 'roof', mix(c, [1, 1, 1, 1], 0.22));
        }
      }
      // the pawn on the selected square (or hopping), and the dice while they roll
      const [px, py, pz] = pawnPos();
      const ph = S.mode === 'roll' || anim.pawn ? 1 : 0;
      if (ph) {
        draw(M.trs([px + 0.3, 0.012, pz + 0.3], null, [0.8, 1, 0.8]), 'quad', [1, 1, 1, 0.55], { tex: shadowTex, lit: 0 });
        draw(M.trs([px, py, pz], null, [1.1, 1.1, 1.1]), 'pawn', col.pawn);
      }
      if (anim.dice && diceTex) for (const d of anim.dice.cubes) draw(M.trs(d.pos, d.rot, [0.72, 0.72, 0.72]), 'box', [1, 1, 1, 1], { tex: d.tex });
      placeLabels();
      if (anim.dice || anim.pawn || anim.drop > 0.001) request();
    };
    const request = () => { if (!raf && !destroyed) raf = requestAnimationFrame(render); };

    // ------------------------------------------------ labels over the board (HTML), placed by projection
    const project = (p) => {
      const q = M.xform(viewProj, p);
      return [(q[0] * 0.5 + 0.5) * size[0], (1 - (q[1] * 0.5 + 0.5)) * size[1], q[2]];
    };
    const placeLabels = () => {
      const want = S.labels || [];
      while (overlay.children.length > want.length) overlay.lastChild.remove();
      while (overlay.children.length < want.length) { const d = document.createElement('div'); d.className = 'mm-b3-label'; overlay.appendChild(d); }
      want.forEach((lab, j) => {
        const el = overlay.children[j], [cx, cz] = centre(lab.square);
        const y = S.mode === 'roll' ? 0.05 : (towerBox(lab.square).h + 0.5);
        const [sx, sy] = project([cx, y, cz]);
        el.textContent = lab.text;
        el.className = 'mm-b3-label' + (lab.strong ? ' mm-b3-strong' : '');
        el.style.transform = `translate(${Math.round(sx)}px, ${Math.round(sy)}px) translate(-50%, -110%)`;
      });
    };

    // ------------------------------------------------ picking
    const ray = (event) => {
      const box = canvas.getBoundingClientRect();
      const nx = ((event.clientX - box.left) / box.width) * 2 - 1, ny = 1 - ((event.clientY - box.top) / box.height) * 2;
      const inv = M.invert(viewProj);
      const a = M.xform(inv, [nx, ny, -1]), b = M.xform(inv, [nx, ny, 1]);
      const d = b.map((v, i) => v - a[i]), l = Math.hypot(...d);
      return [a, d.map((v) => v / l)];
    };
    const pick = (event) => {
      const [o, d] = ray(event);
      let best = null, bestT = Infinity;
      if (S.mode !== 'roll') for (let i = 0; i < 40; i++) {
        const { cx, cz, f, h } = towerBox(i);
        if (!h) continue;
        const lo = [cx - f * 0.56, 0, cz - f * 0.56], hi = [cx + f * 0.56, h + 0.32, cz + f * 0.56];
        let t0 = -Infinity, t1 = Infinity;
        for (let k = 0; k < 3; k++) {
          if (Math.abs(d[k]) < 1e-9) { if (o[k] < lo[k] || o[k] > hi[k]) { t0 = Infinity; break; } continue; }
          let ta = (lo[k] - o[k]) / d[k], tb = (hi[k] - o[k]) / d[k];
          if (ta > tb) [ta, tb] = [tb, ta];
          t0 = Math.max(t0, ta); t1 = Math.min(t1, tb);
        }
        if (t0 <= t1 && t0 > 0 && t0 < bestT) { bestT = t0; best = i; }
      }
      if (best != null) return best;
      if (Math.abs(d[1]) < 1e-9) return null;
      const t = -o[1] / d[1];
      if (t <= 0) return null;
      return squareAt(o[0] + t * d[0], o[2] + t * d[2]);
    };

    // ------------------------------------------------ interaction: drag to turn, wheel or pinch to zoom, tap to pick
    const pointers = new Map();
    let drag = null, moved = 0, pinch = null;
    canvas.addEventListener('pointerdown', (e) => {
      pointers.set(e.pointerId, [e.clientX, e.clientY]);
      if (pointers.size === 2) { const [a, b] = [...pointers.values()]; pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), z: cam.zoom }; drag = null; return; }
      drag = { x: e.clientX, y: e.clientY, touch: e.pointerType === 'touch' }; moved = 0;
    });
    canvas.addEventListener('pointermove', (e) => {
      if (pointers.has(e.pointerId)) pointers.set(e.pointerId, [e.clientX, e.clientY]);
      if (pinch && pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        cam.zoom = Math.min(1.6, Math.max(0.55, pinch.z * pinch.d / Math.max(20, Math.hypot(a[0] - b[0], a[1] - b[1]))));
        request(); return;
      }
      if (drag && (e.buttons & 1 || drag.touch)) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        moved += Math.abs(dx) + Math.abs(dy);
        cam.yaw -= dx * 0.008;
        if (!drag.touch) cam.pitch = Math.min(1.38, Math.max(0.38, cam.pitch + dy * 0.006));
        drag.x = e.clientX; drag.y = e.clientY;
        if (opts.onHover) opts.onHover(null, e);
        request(); return;
      }
      if (opts.onHover) opts.onHover(pick(e), e);
    });
    const up = (e) => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = null;
      if (drag && moved < 6 && e.type === 'pointerup') { const i = pick(e); if (i != null && opts.onPick) opts.onPick(i); }
      drag = null;
    };
    canvas.addEventListener('pointerup', up); canvas.addEventListener('pointercancel', up);
    canvas.addEventListener('pointerleave', (e) => { if (opts.onHover) opts.onHover(null, e); });
    canvas.addEventListener('wheel', (e) => {
      if (!e.ctrlKey && Math.abs(e.deltaY) < 1) return;
      e.preventDefault();
      cam.zoom = Math.min(1.6, Math.max(0.55, cam.zoom * Math.exp(e.deltaY * 0.0012)));
      request();
    }, { passive: false });
    canvas.tabIndex = 0;
    canvas.addEventListener('keydown', (e) => {
      const step = { ArrowLeft: 1, ArrowRight: -1 }[e.key];
      if (step) { e.preventDefault(); cam.yaw += step * Math.PI / 12; request(); }
      if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); cam.pitch = Math.min(1.38, Math.max(0.38, cam.pitch + (e.key === 'ArrowUp' ? 0.08 : -0.08))); request(); }
    });
    const ro = new ResizeObserver(() => resize());
    ro.observe(container);

    // ------------------------------------------------ dice and pawn animation
    const FACE_UP = { // rotation that brings face n of the cube texture to the top (+y)
      1: rotX(0), 2: rotX(Math.PI / 2), 3: rotZ(Math.PI / 2), 4: rotZ(-Math.PI / 2), 5: rotX(-Math.PI / 2), 6: rotX(Math.PI),
    };
    const faceTex = [];
    const ensureDice = () => {
      if (diceTex) return;
      drawDice(diceCanvas, S.colors);
      // one small texture per face value, so the cube's six faces can show different pips
      for (let f = 1; f <= 6; f++) {
        const c = document.createElement('canvas'); c.width = c.height = 128;
        c.getContext('2d').drawImage(diceCanvas, (f - 1) * 128, 0, 128, 128, 0, 0, 128, 128);
        faceTex[f] = texture(c);
      }
      diceTex = faceTex[1];
    };
    const roll = () => new Promise((resolve) => {
      if (!S.colors) return resolve(null);
      ensureDice();
      const d1 = 1 + Math.floor(Math.random() * 6), d2 = 1 + Math.floor(Math.random() * 6);
      const from = S.selected;
      let to = (from + d1 + d2) % 40;
      const T = reduced ? 0 : 900, t0 = performance.now();
      const spin = [[Math.random() * 9 + 6, Math.random() * 9 + 6], [Math.random() * 9 + 6, Math.random() * 9 + 6]];
      anim.dice = { cubes: [{ pos: [-0.55, 1.2, 0.2], rot: FACE_UP[d1], tex: faceTex[d1] }, { pos: [0.55, 1.2, -0.2], rot: FACE_UP[d2], tex: faceTex[d2] }] };
      const hop = () => {
        const path = [];
        for (let k = 1; k <= d1 + d2; k++) path.push((from + k) % 40);
        if (to === 30) { path.push(10); to = 10; }
        const per = reduced ? 0 : 140, t1 = performance.now();
        const step = (now) => {
          const k = Math.min(path.length - 1e-6, (now - t1) / Math.max(1, per));
          const j = Math.floor(k), u = k - j;
          const a = centre(j === 0 ? from : path[j - 1]), b = centre(path[j]);
          anim.pawn = { pos: [a[0] + (b[0] - a[0]) * u, Math.sin(u * Math.PI) * 0.45, a[1] + (b[1] - a[1]) * u] };
          request();
          if (now - t1 < per * path.length && !reduced) requestAnimationFrame(step);
          else {
            anim.pawn = null; anim.dice = null; request();
            resolve({ d1, d2, from, to });
          }
        };
        requestAnimationFrame(step);
      };
      const tumble = (now) => {
        const u = T ? Math.min(1, (now - t0) / T) : 1, e = 1 - Math.pow(1 - u, 3);
        anim.dice.cubes.forEach((c, i) => {
          const [ax, az] = spin[i];
          c.rot = mul3(FACE_UP[i === 0 ? d1 : d2], mul3(rotX((1 - e) * ax), rotZ((1 - e) * az)));
          c.pos = [i === 0 ? -0.55 : 0.55, 0.36 + Math.abs(Math.sin(u * Math.PI * 3)) * (1 - u) * 1.2, i === 0 ? 0.2 : -0.2];
        });
        request();
        if (u < 1) requestAnimationFrame(tumble); else setTimeout(hop, reduced ? 0 : 250);
      };
      requestAnimationFrame(tumble);
    });

    // ------------------------------------------------ public api
    const set = (next) => {
      Object.assign(S, next);
      const sig = JSON.stringify([S.colors && S.colors.paper, S.colors && S.colors.ink, S.squares.map((r) => [r.name, r.price, r.tax]), fontFamily()]);
      if (S.colors && S.squares.length === 40 && sig !== lastSig) {
        lastSig = sig;
        drawBoard(boardCanvas, S.squares, S.colors, fontFamily());
        if (boardTex) gl.deleteTexture(boardTex);
        boardTex = texture(boardCanvas);
        faceTex.forEach((t) => t && gl.deleteTexture(t)); faceTex.length = 0; diceTex = null;
      }
      if ('selected' in next && next.selected !== set.prev) {
        if (set.prev != null && !reduced) {
          const t0 = performance.now();
          const fall = (now) => { const u = Math.min(1, (now - t0) / 350); anim.drop = (1 - u) * (1 - u) * 0.9; request(); if (u < 1) requestAnimationFrame(fall); };
          requestAnimationFrame(fall);
        }
        set.prev = next.selected;
      }
      request();
    };
    const turn = (step) => { cam.yaw += step; request(); };
    const destroy = () => {
      destroyed = true; ro.disconnect(); cancelAnimationFrame(raf);
      const lose = gl.getExtension('WEBGL_lose_context'); if (lose) lose.loseContext();
      canvas.remove(); overlay.remove();
    };
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { lastSig = ''; if (S.colors) set({}); });
    resize();
    return { set, roll, turn, destroy, canvas, colorOf: rgba };
  };

  return { create, rgba, layout: { rect, centre } };
})();
