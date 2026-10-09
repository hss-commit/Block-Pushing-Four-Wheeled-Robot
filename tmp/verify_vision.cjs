const { chromium } = require('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const { pathToFileURL } = require('url');
const path = require('path');

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true,
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(path.resolve(__dirname, '..', '视觉照片识别.html')).href);
    const png = await page.evaluate(() => {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 600;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#4a83bb'; ctx.fillRect(0, 0, 600, 600);
      ctx.fillStyle = '#ed3c2a';
      ctx.fillRect(140, 240, 20, 20);
      ctx.fillRect(390, 340, 20, 20);
      return canvas.toDataURL('image/png').split(',')[1];
    });
    await page.locator('#photo').setInputFiles({ name: 'field.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
    await page.waitForFunction(() => document.querySelector('#source').width === 600);
    async function clickCanvas(selector, x, y) {
      const box = await page.locator(selector).boundingBox();
      await page.mouse.click(box.x + x * box.width / 600, box.y + y * box.height / 600);
    }
    for (const [x, y] of [[1, 1], [598, 1], [598, 598], [1, 598]]) await clickCanvas('#source', x, y);
    await clickCanvas('#field', 150, 250);
    const rows = await page.locator('#results tr').evaluateAll(elements =>
      elements.map(row => [...row.cells].map(cell => Number(cell.textContent))));
    if (rows.length !== 2 || errors.length ||
        Math.abs(rows[0][1] - 300) > 10 || Math.abs(rows[0][2] - 700) > 10 ||
        Math.abs(rows[1][1] - 800) > 10 || Math.abs(rows[1][2] - 500) > 10)
      throw Error(JSON.stringify({ rows, errors }));
    console.log(JSON.stringify({ result: 'passed', regions: rows.length, rows, errors }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
