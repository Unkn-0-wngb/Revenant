import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const TEAL = "#00c4ac";
const LENGTH = 4.3;

const SKINNED = /Body|PilHead/;
const WHEELS = /Wheel/;

async function readParts() {
  const [list, buffer] = await Promise.all([
    fetch("assets/stadium.json").then((r) => r.json()),
    fetch("assets/stadium.bin").then((r) => r.arrayBuffer()),
  ]);
  let offset = 0;
  return list.map((entry) => {
    const verts = entry.verts;
    const take = (Type, count) => {
      const out = new Type(buffer, offset, count);
      offset += count * Type.BYTES_PER_ELEMENT;
      return out;
    };
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(take(Float32Array, verts * 3), 3));
    geometry.setAttribute("normal", new THREE.BufferAttribute(take(Float32Array, verts * 3), 3));
    geometry.setAttribute("uv", new THREE.BufferAttribute(take(Float32Array, verts * 2), 2));
    geometry.setIndex(new THREE.BufferAttribute(take(Uint32Array, entry.indices), 1));
    return { name: entry.name, geometry };
  });
}

async function buildCar() {
  const parts = await readParts();
  const texture = await new THREE.TextureLoader().loadAsync("assets/skin.png");
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;

  const paint = new THREE.MeshPhysicalMaterial({ map: texture, roughness: 0.35, metalness: 0.1, clearcoat: 1, clearcoatRoughness: 0.12 });
  const gloss = new THREE.MeshPhysicalMaterial({ color: "#0b0c0d", roughness: 0.4, metalness: 0.2, clearcoat: 0.6 });
  const rubber = new THREE.MeshStandardMaterial({ color: "#151515", roughness: 0.85, metalness: 0.1 });

  const car = new THREE.Group();
  for (const part of parts) {
    let material = gloss;
    if (WHEELS.test(part.name)) {
      material = rubber;
    } else if (SKINNED.test(part.name)) {
      material = paint;
    }
    const mesh = new THREE.Mesh(part.geometry, material);
    car.add(mesh);
  }
  const box = new THREE.Box3().setFromObject(car);
  const size = box.getSize(new THREE.Vector3());
  const fit = LENGTH / Math.max(size.x, size.z);
  car.scale.setScalar(fit);
  car.position.set(-(box.min.x + size.x / 2) * fit, -box.min.y * fit, -(box.min.z + size.z / 2) * fit);
  const holder = new THREE.Group();
  holder.add(car);
  return holder;
}

function blobTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 128;
  const g = canvas.getContext("2d");
  const fade = g.createRadialGradient(128, 64, 0, 128, 64, 128);
  fade.addColorStop(0, "rgba(0,0,0,0.85)");
  fade.addColorStop(0.45, "rgba(0,0,0,0.5)");
  fade.addColorStop(1, "rgba(0,0,0,0)");
  g.save();
  g.scale(1, 0.5);
  g.translate(0, 64);
  g.fillStyle = fade;
  g.fillRect(0, -64, 256, 256);
  g.restore();
  return new THREE.CanvasTexture(canvas);
}

let shared;

async function freshCar() {
  shared ??= buildCar();
  return (await shared).clone();
}

export async function mountCar(holder, view = {}) {
  const interactive = view.interactive ?? true;
  const spin = view.spin ?? 1.1;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  holder.appendChild(renderer.domElement);
  if (!interactive) {
    renderer.domElement.style.pointerEvents = "none";
  }

  const scene = new THREE.Scene();
  const environment = new THREE.PMREMGenerator(renderer);
  scene.environment = environment.fromScene(new RoomEnvironment(), 0.04).texture;

  const camera = new THREE.PerspectiveCamera(view.fov ?? 32, 16 / 9, 0.1, 100);
  camera.position.set(...(view.position ?? [5.4, 2.3, 5.2]));

  const key = new THREE.DirectionalLight("#ffffff", 2.4);
  key.position.set(2.5, 9, 2);
  scene.add(key);
  const rim = new THREE.DirectionalLight(TEAL, 0.45);
  rim.position.set(-5, 3, -4);
  scene.add(rim);
  scene.add(new THREE.HemisphereLight("#d9e6ff", "#0c0d0e", 0.55));

  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(6.2, 3.1), new THREE.MeshBasicMaterial({ map: blobTexture(), transparent: true, depthWrite: false }));
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = 0.01;
  scene.add(shadow);

  const car = await freshCar();
  scene.add(car);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, view.height ?? 0.62, 0);
  controls.enabled = interactive;
  controls.minDistance = interactive ? 4.2 : 1;
  controls.maxDistance = 11;
  controls.enableDamping = true;
  controls.enablePan = false;
  controls.minPolarAngle = 0.25;
  controls.maxPolarAngle = 1.5;
  controls.autoRotate = spin > 0 && !matchMedia("(prefers-reduced-motion: reduce)").matches;
  controls.autoRotateSpeed = spin;
  controls.addEventListener("start", () => {
    controls.autoRotate = false;
  });

  const bounds = new THREE.Box3().setFromObject(car).getBoundingSphere(new THREE.Sphere());
  const look = camera.position.clone().sub(controls.target).normalize();

  const resize = () => {
    const width = holder.clientWidth;
    const height = holder.clientHeight;
    if (!width || !height) {
      return;
    }
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    if (view.fit) {
      const tall = THREE.MathUtils.degToRad(camera.fov);
      const wide = 2 * Math.atan(Math.tan(tall / 2) * camera.aspect);
      const distance = (bounds.radius * view.fit) / Math.sin(Math.min(tall, wide) / 2);
      camera.position.copy(controls.target).addScaledVector(look, distance);
    }
  };
  new ResizeObserver(resize).observe(holder);
  resize();

  let visible = true;
  new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
  }).observe(holder);

  renderer.setAnimationLoop(() => {
    if (!visible) {
      return;
    }
    controls.update();
    renderer.render(scene, camera);
  });
  holder.classList.add("ready");
  return { camera, controls, renderer, scene };
}
