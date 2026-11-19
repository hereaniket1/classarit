export function mountGames() {
  mountTicTacToe();
  const pauseSnake = mountSnake();
  document.addEventListener("student-entertainment-change", event => {
    if (event.detail?.panel !== "games") pauseSnake();
  });
  const tabs = [...document.querySelectorAll("[data-game]")];
  function selectGame(tab) {
    if (tab.dataset.game !== "snake") pauseSnake();
    for (const item of tabs) {
      const selected = item === tab;
      item.setAttribute("aria-selected", String(selected));
      item.tabIndex = selected ? 0 : -1;
      document.getElementById(item.getAttribute("aria-controls")).hidden = !selected;
    }
  }
  tabs.forEach((tab,index) => {
    tab.onclick = () => selectGame(tab);
    tab.onkeydown = event => {
      let next;
      if (event.key === "ArrowRight") next = tabs[(index+1)%tabs.length];
      if (event.key === "ArrowLeft") next = tabs[(index+tabs.length-1)%tabs.length];
      if (event.key === "Home") next = tabs[0];
      if (event.key === "End") next = tabs.at(-1);
      if (next) { event.preventDefault(); selectGame(next); next.focus(); }
    };
  });
}

function mountTicTacToe() {
  const cells = [...document.querySelectorAll("[data-ttt-cell]")];
  const mode = document.querySelector("#ttt-mode");
  const status = document.querySelector("#ttt-status");
  const lines = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];
  const scores = { X: 0, O: 0, draw: 0 };
  let board, turn, finished, computerTimer;
  function winningLine() { return lines.find(line => board[line[0]] && line.every(index => board[index] === board[line[0]])); }
  function render() {
    cells.forEach((cell, index) => {
      cell.textContent = board[index] || "";
      cell.dataset.mark = board[index] || "";
      cell.disabled = finished || Boolean(board[index]) || (mode.value === "computer" && turn === "O");
      cell.setAttribute("aria-label", `Row ${Math.floor(index / 3) + 1}, column ${index % 3 + 1}, ${board[index] || "empty"}`);
    });
  }
  function move(index) {
    if (finished || board[index]) return;
    board[index] = turn;
    const win = winningLine();
    if (win || board.every(Boolean)) {
      finished = true;
      const result = win ? turn : "draw";
      scores[result]++;
      document.querySelector("#ttt-x-score").textContent = scores.X;
      document.querySelector("#ttt-o-score").textContent = scores.O;
      document.querySelector("#ttt-draw-score").textContent = scores.draw;
      status.textContent = win ? `${turn} wins! Ready for another round?` : "A draw! Try a new opening.";
      win?.forEach(index => cells[index].classList.add("is-winning"));
    } else {
      turn = turn === "X" ? "O" : "X";
      status.textContent = mode.value === "computer" && turn === "O" ? "Computer is thinking…" : `${turn}'s turn`;
    }
    render();
  }
  function computerMove() {
    const available = board.map((mark, index) => mark ? -1 : index).filter(index => index >= 0);
    let selected;
    // Look one move ahead for a win or a block, then prefer the centre and corners.
    for (const mark of ["O", "X"]) {
      selected = available.find(index => {
        board[index] = mark;
        const win = winningLine();
        board[index] = null;
        return Boolean(win);
      });
      if (selected !== undefined) break;
    }
    if (selected === undefined && !board[4]) selected = 4;
    if (selected === undefined) {
      const corners = available.filter(index => [0,2,6,8].includes(index));
      const choices = corners.length ? corners : available;
      selected = choices[Math.floor(Math.random() * choices.length)];
    }
    if (selected !== undefined) move(selected);
  }
  function reset() {
    clearTimeout(computerTimer);
    board = Array(9).fill(null); turn = "X"; finished = false;
    cells.forEach(cell => cell.classList.remove("is-winning"));
    status.textContent = mode.value === "computer" ? "Your turn — X" : "X's turn";
    render();
  }
  cells.forEach((cell, index) => cell.onclick = () => {
    if (mode.value === "computer" && turn !== "X") return;
    move(index);
    if (!finished && mode.value === "computer" && turn === "O") computerTimer = setTimeout(computerMove, 280);
  });
  document.querySelector("#ttt-new").onclick = reset;
  mode.onchange = reset;
  window.addEventListener("pagehide", () => clearTimeout(computerTimer), { once: true });
  reset();
}

function mountSnake() {
  const canvas = document.querySelector("#snake-canvas");
  const context = canvas.getContext("2d");
  const toggle = document.querySelector("#snake-toggle");
  const status = document.querySelector("#snake-status");
  const speed = document.querySelector("#snake-speed");
  const count = 20, tile = canvas.width / count;
  let snake, direction, queuedDirection, food, score = 0, best = 0, timer;
  let running = false, gameOver = false, started = false, touchStart;
  document.querySelector("#snake-best").textContent = best;

  function placeFood() {
    const empty = [];
    for (let y = 0; y < count; y++) for (let x = 0; x < count; x++) {
      if (!snake.some(part => part.x === x && part.y === y)) empty.push({ x, y });
    }
    return empty[Math.floor(Math.random() * empty.length)];
  }
  function draw() {
    context.fillStyle = "#122f39"; context.fillRect(0, 0, canvas.width, canvas.height);
    context.strokeStyle = "#ffffff06";
    for (let n = 0; n <= count; n++) {
      context.beginPath(); context.moveTo(n * tile, 0); context.lineTo(n * tile, canvas.height); context.stroke();
      context.beginPath(); context.moveTo(0, n * tile); context.lineTo(canvas.width, n * tile); context.stroke();
    }
    if (food) {
      context.fillStyle = "#ffb347"; context.beginPath();
      context.arc((food.x + 0.5) * tile, (food.y + 0.5) * tile, tile * 0.34, 0, Math.PI * 2); context.fill();
      context.fillStyle = "#64efb0"; context.fillRect(food.x * tile + tile * 0.5, food.y * tile + 1, 3, 5);
    }
    snake.forEach((part, index) => {
      context.fillStyle = index === 0 ? "#a5ffc3" : "#3bd7ab";
      context.beginPath(); context.roundRect(part.x * tile + 1, part.y * tile + 1, tile - 2, tile - 2, 5); context.fill();
    });
    const head = snake[0];
    context.fillStyle = "#153c42";
    context.fillRect(head.x * tile + 5, head.y * tile + 5, 3, 3);
    context.fillRect(head.x * tile + 12, head.y * tile + 5, 3, 3);
  }
  function pause(message = "Paused. Press Resume when you're ready.") {
    running = false; clearTimeout(timer);
    toggle.textContent = gameOver ? "Play again" : started ? "Resume" : "Start";
    if (started && !gameOver) status.textContent = message;
  }
  function tick() {
    if (!running) return;
    direction = queuedDirection;
    const head = { x: snake[0].x + direction.x, y: snake[0].y + direction.y };
    const eating = food && head.x === food.x && head.y === food.y;
    const body = eating ? snake : snake.slice(0, -1);
    if (head.x < 0 || head.x >= count || head.y < 0 || head.y >= count ||
        body.some(part => part.x === head.x && part.y === head.y)) {
      gameOver = true; pause();
      status.textContent = `Nice run! You scored ${score}. Try again.`;
      return;
    }
    snake.unshift(head);
    if (eating) {
      score += 10; document.querySelector("#snake-score").textContent = score;
      if (score > best) {
        best = score; document.querySelector("#snake-best").textContent = best;
      }
      food = placeFood();
      if (!food) {
        gameOver = true; pause(); status.textContent = "Amazing! You filled the board."; draw(); return;
      }
    } else snake.pop();
    draw();
    timer = setTimeout(tick, Number(speed.value));
  }
  function reset() {
    pause();
    snake = [{ x: 7, y: 10 }, { x: 6, y: 10 }, { x: 5, y: 10 }];
    direction = queuedDirection = { x: 1, y: 0 };
    food = placeFood(); score = 0; gameOver = started = false;
    document.querySelector("#snake-score").textContent = 0;
    toggle.textContent = "Start"; status.textContent = "Press Start. Use arrows, WASD, or swipe."; draw();
  }
  function start() {
    if (gameOver) reset();
    started = running = true;
    toggle.textContent = "Pause"; status.textContent = "Keep going! Space pauses.";
    canvas.focus(); clearTimeout(timer); timer = setTimeout(tick, Number(speed.value));
  }
  function changeDirection(name) {
    const vectors = { up: { x: 0, y: -1 }, down: { x: 0, y: 1 }, left: { x: -1, y: 0 }, right: { x: 1, y: 0 } };
    const next = vectors[name];
    if (next && running && (next.x !== -direction.x || next.y !== -direction.y)) queuedDirection = next;
  }
  toggle.onclick = () => running ? pause() : start();
  document.querySelector("#snake-restart").onclick = () => { reset(); start(); };
  document.querySelectorAll("[data-snake-direction]").forEach(button => button.onclick = () => changeDirection(button.dataset.snakeDirection));
  canvas.addEventListener("keydown", event => {
    const keys = { ArrowUp: "up", w: "up", ArrowDown: "down", s: "down", ArrowLeft: "left", a: "left", ArrowRight: "right", d: "right" };
    const name = keys[event.key] || keys[event.key.toLowerCase()];
    if (name) { event.preventDefault(); changeDirection(name); }
    if (event.code === "Space") { event.preventDefault(); running ? pause() : start(); }
  });
  canvas.addEventListener("pointerdown", event => { touchStart = { x: event.clientX, y: event.clientY }; });
  canvas.addEventListener("pointerup", event => {
    if (!touchStart) return;
    const dx = event.clientX - touchStart.x, dy = event.clientY - touchStart.y;
    if (Math.max(Math.abs(dx), Math.abs(dy)) > 10) changeDirection(Math.abs(dx) > Math.abs(dy) ? dx > 0 ? "right" : "left" : dy > 0 ? "down" : "up");
    touchStart = null;
  });
  canvas.addEventListener("blur", () => { if (running && !document.activeElement?.closest(".snake-card")) pause(); });
  document.addEventListener("visibilitychange", () => { if (document.hidden && running) pause(); });
  window.addEventListener("blur", () => { if (running) pause(); });
  window.addEventListener("pagehide", () => clearTimeout(timer), { once: true });
  reset();
  return () => { if (running) pause(); };
}
