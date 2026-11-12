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
  const data = await fetch("assets/levels.json").then((r) => r.json());
  const levels = data.levels || data;
  for (const series of ["A", "B", "C", "D", "E"]) {
    const column = document.createElement("div");
    column.className = "series";
    column.innerHTML = `<h3>${series}</h3>`;
    levels.filter((l) => l.id[0] === series).forEach((l) => column.appendChild(tile(l)));
    board.appendChild(column);
  }
  document.getElementById("count-finished").textContent = levels.filter((l) => l.best !== null).length;
  document.getElementById("count-author").textContent = levels.filter((l) => l.status === "author").length;
  if (data.updated) {
    const when = new Date(`${data.updated}T12:00:00`);
    document.getElementById("updated").textContent = `Times last updated ${when.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}.`;
  }
}

function filterBoard() {
  const buttons = document.querySelectorAll(".filter button");
  const board = document.getElementById("board");
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      buttons.forEach((other) => other.setAttribute("aria-pressed", String(other === button)));
      const show = button.dataset.show;
      board.dataset.show = show;
      board.querySelectorAll(".lap").forEach((lap) => {
        lap.hidden = show !== "all" && !lap.classList.contains(show);
      });
    });
  });
}

function trackSections() {
  const links = new Map([...document.querySelectorAll(".bar nav a[href^='#']")].map((a) => [a.getAttribute("href").slice(1), a]));
  const watcher = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      const link = links.get(entry.target.id);
      if (link && entry.isIntersecting) {
        links.forEach((other) => other.removeAttribute("aria-current"));
        link.setAttribute("aria-current", "true");
      }
    });
  }, { rootMargin: "-45% 0px -50% 0px" });
  links.forEach((_, id) => {
    const section = document.getElementById(id);
    if (section) {
      watcher.observe(section);
    }
  });
}

function showLive(holder, view, wait) {
  let started = false;
  const start = () => {
    if (started) {
      return;
    }
    started = true;
    import("./car.js?v=15").then((module) => module.mountCar(holder, view)).catch(() => holder.classList.add("failed"));
  };
  if (wait) {
    new IntersectionObserver((entries, watcher) => {
      if (entries[0].isIntersecting) {
        watcher.disconnect();
        start();
      }
    }, { rootMargin: "400px" }).observe(holder);
    addEventListener("load", () => setTimeout(start, 2500));
  } else {
    start();
  }
}

function loadCars() {
  showLive(document.getElementById("hero-car"), { position: [1.95, 1.0, 3.9], height: 0.5, fov: 28, interactive: false, spin: 0 }, false);
  showLive(document.getElementById("stage"), {}, true);
  showLive(document.getElementById("rear-car"), { position: [-4.8, 1.6, 4.2], height: 0.55, interactive: false, spin: 0 }, true);
}

function guard() {
  document.addEventListener("contextmenu", (e) => e.preventDefault());
  document.addEventListener("dragstart", (e) => {
    if (e.target.tagName === "IMG") e.preventDefault();
  });
  document.addEventListener("keydown", (e) => {
    const k = e.key.toLowerCase();
    if (e.key === "F12") { e.preventDefault(); return; }
    if (e.ctrlKey && ["u", "s", "c", "a"].includes(k)) { e.preventDefault(); return; }
    if (e.ctrlKey && e.shiftKey && ["i", "j", "c", "k"].includes(k)) { e.preventDefault(); }
  });
}

guard();
typeIn();
fillBoard();
filterBoard();
trackSections();
loadCars();
