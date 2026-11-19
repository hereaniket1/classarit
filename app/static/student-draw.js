export function mountDraw() {
  const canvas = document.querySelector("#drawing-canvas");
  const context = canvas.getContext("2d");
  const color = document.querySelector("#draw-color");
  const size = document.querySelector("#draw-size");
  const status = document.querySelector("#draw-status");
  const undo = [], redo = [];
  let scene = [], tool = "pen", selectedShape = null, current = null, moving = null, frame = 0;
  const shapeNames = new Set(["rectangle", "circle", "triangle", "star", "arrow"]);
  const workspace = document.querySelector(".draw-workspace");
  const toolsToggle = document.querySelector("#draw-tools-toggle");
  const cursorArtwork = {
    pen: '<path d="M4 27 7 18 23 2a2 2 0 0 1 3 0l3 3a2 2 0 0 1 0 3L13 24Z" fill="#635bff" stroke="white" stroke-width="2"/><path d="m4 27 3-9 6 6Z" fill="#26344f"/><path d="m20 5 6 6" stroke="white" stroke-width="2"/>',
    brush: '<path d="M12 20 25 3q3-3 5 0L18 23Z" fill="#ac7e4a" stroke="white" stroke-width="1.5"/><path d="m10 18 9 6-5 5q-6 4-11-1c5 0 2-5 7-10Z" fill="#635bff" stroke="white" stroke-width="1.5"/>',
    eraser: '<path d="m5 20 12-15q2-2 4 0l8 6q2 2 0 4L17 29H9Z" fill="#ef8cab" stroke="white" stroke-width="2"/><path d="m5 20 7-8 12 10-7 7H9Z" fill="#f1f4fc" stroke="#5b6680" stroke-width="1.5"/>',
  };
  const cursors = Object.fromEntries(Object.entries(cursorArtwork).map(([name, artwork]) => [
    name, `url("data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">'+artwork+'</svg>')}") ${name === "eraser" ? "8 25" : "4 27"}, crosshair`,
  ]));

  function closeTools() {
    workspace.classList.remove("tools-open");
    toolsToggle.setAttribute("aria-expanded","false");
  }
  toolsToggle.onclick = () => {
    const open = workspace.classList.toggle("tools-open");
    toolsToggle.setAttribute("aria-expanded",String(open));
  };

  function save() {
    status.textContent = "Draft lives only while this page is open. Download PNG to keep it.";
  }
  function snapshot() {
    undo.push(structuredClone(scene));
    if (undo.length > 20) undo.shift();
    redo.length = 0;
  }
  function setTool(value) {
    tool = value;
    document.querySelectorAll("[data-draw-tool]").forEach(button => {
      button.setAttribute("aria-pressed", String(button.dataset.drawTool === tool));
    });
    document.querySelectorAll("[data-shape]").forEach(button => {
      button.setAttribute("aria-pressed",String(tool === "shape" && selectedShape === button.dataset.shape));
    });
    canvas.style.cursor = tool === "move" ? "default" : cursors[tool] || "crosshair";
    canvas.dataset.tool = tool;
  }
  function position(event) {
    const bounds = canvas.getBoundingClientRect();
    return { x: (event.clientX - bounds.left) * canvas.width / bounds.width,
      y: (event.clientY - bounds.top) * canvas.height / bounds.height };
  }
  function shapePath(item) {
    const { x, y, width: w, height: h } = item;
    context.beginPath();
    if (item.shape === "rectangle") context.rect(x - w / 2, y - h / 2, w, h);
    if (item.shape === "circle") context.ellipse(x, y, w / 2, h / 2, 0, 0, Math.PI * 2);
    if (item.shape === "triangle") {
      context.moveTo(x, y - h / 2); context.lineTo(x + w / 2, y + h / 2);
      context.lineTo(x - w / 2, y + h / 2); context.closePath();
    }
    if (item.shape === "star") {
      for (let i = 0; i < 10; i++) {
        const angle = -Math.PI / 2 + i * Math.PI / 5, radius = i % 2 ? 0.22 : 0.5;
        const px = x + Math.cos(angle) * w * radius, py = y + Math.sin(angle) * h * radius;
        if (i === 0) context.moveTo(px, py); else context.lineTo(px, py);
      }
      context.closePath();
    }
    if (item.shape === "arrow") {
      const points = [[-0.5,-0.15],[0.1,-0.15],[0.1,-0.4],[0.5,0],[0.1,0.4],[0.1,0.15],[-0.5,0.15]];
      points.forEach(([px, py], index) => {
        if (!index) context.moveTo(x + px * w, y + py * h);
        else context.lineTo(x + px * w, y + py * h);
      });
      context.closePath();
    }
  }
  function paint() {
    frame = 0;
    context.clearRect(0, 0, canvas.width, canvas.height);
    for (const item of scene) {
      context.save();
      context.strokeStyle = context.fillStyle = item.color;
      context.lineCap = context.lineJoin = "round";
      context.lineWidth = item.size;
      if (item.kind === "shape") {
        shapePath(item);
        if (item.fill) context.fill(); else context.stroke();
      } else {
        if (item.tool === "eraser") context.globalCompositeOperation = "destination-out";
        if (item.tool === "brush") context.globalAlpha = 0.45;
        context.beginPath();
        item.points.forEach((point, index) => {
          if (!index) context.moveTo(point.x, point.y);
          else context.lineTo(point.x, point.y);
        });
        if (item.points.length === 1) {
          const point = item.points[0];
          context.arc(point.x, point.y, item.size / 2, 0, Math.PI * 2); context.fill();
        } else context.stroke();
      }
      context.restore();
    }
    document.querySelector("#draw-undo").disabled = !undo.length;
    document.querySelector("#draw-redo").disabled = !redo.length;
  }
  function repaint() { if (!frame) frame = requestAnimationFrame(paint); }
  function addShape(shape, point = { x: canvas.width / 2, y: canvas.height / 2 }) {
    if (!shapeNames.has(shape)) return;
    snapshot();
    scene.push({ kind: "shape", shape, ...point, width: 140, height: 120,
      size: Number(size.value), color: color.value, fill: document.querySelector("#draw-fill").checked });
    repaint(); save();
    status.textContent = "Shape added. Choose Move shape to reposition it.";
  }
  canvas.addEventListener("pointerdown", event => {
    if (event.button !== 0) return;
    event.preventDefault();
    canvas.focus();
    closeTools();
    const point = position(event);
    if (tool === "shape") { addShape(selectedShape,point); return; }
    if (tool === "move") {
      const item = [...scene].reverse().find(item => item.kind === "shape" &&
        Math.abs(item.x - point.x) <= item.width / 2 && Math.abs(item.y - point.y) <= item.height / 2);
      if (!item) return;
      snapshot();
      moving = { item, offsetX: point.x - item.x, offsetY: point.y - item.y };
    } else {
      snapshot();
      current = { kind: "stroke", tool, color: color.value,
        size: Number(size.value) * (tool === "brush" || tool === "eraser" ? 3 : 1), points: [point] };
      scene.push(current);
    }
    canvas.setPointerCapture(event.pointerId);
    repaint();
  });
  canvas.addEventListener("pointermove", event => {
    if (!current && !moving) return;
    const point = position(event);
    if (moving) {
      moving.item.x = Math.max(0, Math.min(canvas.width, point.x - moving.offsetX));
      moving.item.y = Math.max(0, Math.min(canvas.height, point.y - moving.offsetY));
    } else {
      const previous = current.points.at(-1);
      if (Math.hypot(point.x - previous.x, point.y - previous.y) >= 2 && current.points.length < 10000) current.points.push(point);
    }
    repaint();
  });
  function finish(event) {
    if (!current && !moving) return;
    current = moving = null;
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    save(); repaint();
  }
  canvas.addEventListener("pointerup", finish);
  canvas.addEventListener("pointercancel", finish);
  canvas.addEventListener("dragover", event => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; });
  canvas.addEventListener("drop", event => {
    event.preventDefault();
    addShape(event.dataTransfer.getData("application/x-classarit-shape"), position(event));
  });
  document.querySelectorAll("[data-shape]").forEach(button => {
    button.addEventListener("dragstart", event => {
      selectedShape = button.dataset.shape;
      setTool("shape");
      event.dataTransfer.setData("application/x-classarit-shape", button.dataset.shape);
      event.dataTransfer.effectAllowed = "copy";
    });
    button.addEventListener("click", () => {
      selectedShape = button.dataset.shape;
      setTool("shape");
      closeTools();
      status.textContent = "Click the canvas to place your shape.";
    });
  });
  document.querySelectorAll("[data-draw-tool]").forEach(button => button.onclick = () => { setTool(button.dataset.drawTool); closeTools(); });
  document.querySelectorAll("[data-draw-color]").forEach(button => button.onclick = () => { color.value = button.dataset.drawColor; });
  size.oninput = () => { document.querySelector("#draw-size-value").textContent = size.value; };
  document.querySelector("#draw-undo").onclick = () => {
    if (!undo.length) return;
    redo.push(structuredClone(scene)); scene = undo.pop(); repaint(); save();
  };
  document.querySelector("#draw-redo").onclick = () => {
    if (!redo.length) return;
    undo.push(structuredClone(scene)); scene = redo.pop(); repaint(); save();
  };
  document.querySelector("#draw-clear").onclick = () => {
    if (!scene.length || !confirm("Clear this drawing? You can undo this.")) return;
    snapshot(); scene = []; repaint(); save();
  };
  document.querySelector("#draw-download").onclick = () => {
    paint();
    const exported = document.createElement("canvas");
    exported.width = canvas.width; exported.height = canvas.height;
    const output = exported.getContext("2d");
    output.fillStyle = "#ffffff"; output.fillRect(0, 0, exported.width, exported.height); output.drawImage(canvas, 0, 0);
    exported.toBlob(blob => {
      if (!blob) return;
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob); link.download = "classarit-drawing.png"; link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    }, "image/png");
  };
  function fitCanvas() {
    const bounds = canvas.getBoundingClientRect();
    if (!bounds.width) return;
    const availableHeight = Math.max(280,window.innerHeight - bounds.top - 45);
    let contentHeight = 0;
    for (const item of scene) {
      if (item.kind === "shape") contentHeight = Math.max(contentHeight,item.y + item.height / 2 + item.size);
      else for (const point of item.points) contentHeight = Math.max(contentHeight,point.y + item.size);
    }
    const height = Math.ceil(Math.max(650,availableHeight * canvas.width / bounds.width,contentHeight + 10));
    if (canvas.height !== height) { canvas.height = height; paint(); }
  }
  const resizeObserver = new ResizeObserver(fitCanvas);
  resizeObserver.observe(workspace);
  window.addEventListener("resize",fitCanvas);
  document.addEventListener("student-entertainment-change", event => {
    if (event.detail?.panel === "draw") requestAnimationFrame(() => { fitCanvas(); paint(); });
  });
  window.addEventListener("pagehide", () => {
    if (frame) cancelAnimationFrame(frame);
    resizeObserver.disconnect();
    window.removeEventListener("resize",fitCanvas);
  }, { once: true });
  setTool("pen");
  fitCanvas();
  paint();
}
