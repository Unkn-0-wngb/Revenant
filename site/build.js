const { minify } = require('html-minifier-terser');
const { minify: minifyJs } = require('terser');
const CleanCSS = require('clean-css');
const fs = require('fs');
const path = require('path');

const OUT = 'dist';
const COPY = ['assets', '_headers', 'robots.txt', 'favicon.ico', 'site.webmanifest'];
const PAGES = ['index.html', '404.html'];
const SCRIPTS = ['main.js', 'car.js'];

const htmlOpts = {
  collapseWhitespace: true,
  removeComments: true,
  removeRedundantAttributes: true,
  minifyCSS: { level: 2 },
  minifyJS: { compress: true, mangle: false, format: { comments: false } },
};

function lastModified() {
  return new Date().toISOString().slice(0, 10);
}

async function build() {
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });

  for (const item of COPY) {
    if (fs.existsSync(item)) fs.cpSync(item, path.join(OUT, item), { recursive: true });
  }

  const css = fs.readFileSync('style.css', 'utf8');
  const cssOut = new CleanCSS({ level: 2 }).minify(css).styles;
  fs.writeFileSync(path.join(OUT, 'style.css'), cssOut);
  console.log(`style.css: ${css.length} → ${cssOut.length} bytes`);

  for (const file of SCRIPTS) {
    if (!fs.existsSync(file)) continue;
    const src = fs.readFileSync(file, 'utf8');
    const out = await minifyJs(src, { module: file === 'car.js', compress: true, mangle: true, format: { comments: false } });
    fs.writeFileSync(path.join(OUT, file), out.code);
    console.log(`${file}: ${src.length} → ${out.code.length} bytes`);
  }

  for (const file of PAGES) {
    const src = fs.readFileSync(file, 'utf8');
    const out = await minify(src, htmlOpts);
    fs.writeFileSync(path.join(OUT, file), out);
    console.log(`${file}: ${src.length} → ${out.length} bytes`);
  }

  const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://revenant.laveryjonez.uk/</loc><lastmod>${lastModified()}</lastmod><priority>1.0</priority></url>
</urlset>
`;
  fs.writeFileSync(path.join(OUT, 'sitemap.xml'), sitemap);
  console.log('sitemap.xml: generated');
}

build().catch((e) => { console.error(e); process.exit(1); });
