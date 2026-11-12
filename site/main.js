const CUTS = [20.11, 31.12, 42.59, 52.62, 64.04, 76.95, 88.01, 100];
const LEAN = 1.58;

function showTime(value) {
  const minutes = Math.floor(value / 60);
  const rest = value - minutes * 60;
  return minutes ? `${minutes}:${rest.toFixed(2).padStart(5, "0")}` : rest.toFixed(2);
}

function typeIn() {
  const title = document.querySelector(".reveal");
  const word = title.querySelector("img");
  const caret = title.querySelector(".caret");
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return;
  }

  const show = (count) => {
    const cut = CUTS[count];
    word.style.clipPath = `polygon(0 0, ${cut + LEAN}% 0, ${cut - LEAN}% 100%, 0 100%)`;
    caret.style.left = `${Math.min(cut + 1.5, 100)}%`;
  };

  title.classList.add("typing");
  show(0);
  let count = 0;
  const next = () => {
    count += 1;
    show(count);
    if (count < CUTS.length - 1) {
      setTimeout(next, 120);
    } else {
      setTimeout(() => {
        title.classList.remove("typing");
        word.style.clipPath = "";
      }, 500);
    }
  };
  setTimeout(next, 650);
}

function tile(level) {
  const item = document.createElement("div");
  item.className = `lap ${level.status}`;
  item.setAttribute("role", "listitem");
  let time = "No finish yet";
  let detail = `author ${showTime(level.author)}`;
  if (level.best !== null) {
    time = showTime(level.best);
    const gap = level.best - level.author;
    detail = gap <= 0 ? `${Math.abs(gap).toFixed(2)} under author` : `+${gap.toFixed(2)} to author`;
  } else if (level.status === "waiting") {
    time = "Not reached";
  }
  item.innerHTML = `<b>${level.id}</b><span>${time}</span><small>${detail}</small>`;
  item.title = `${level.id} ${level.name}`;
  return item;
}

async function fillBoard() {
  const board = document.getElementById("board");
  const levels = await fetch("assets/levels.json").then((r) => r.json());
  for (const series of ["A", "B", "C", "D", "E"]) {
    const column = document.createElement("div");
    column.className = "series";
    column.innerHTML = `<h3>${series}</h3>`;
    levels.filter((l) => l.id[0] === series).forEach((l) => column.appendChild(tile(l)));
    board.appendChild(column);
  }
  document.getElementById("count-finished").textContent = levels.filter((l) => l.best !== null).length;
  document.getElementById("count-author").textContent = levels.filter((l) => l.status === "author").length;
}

typeIn();
fillBoard();
