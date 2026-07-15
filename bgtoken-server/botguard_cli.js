// BotGuard VM solver dung HEADLESS CHROME THAT (puppeteer) - chi phuc vu
// tinh nang "lich goc YouTube".
//
// jsdom KHONG giai duoc program BotGuard cua Studio (d=62) vi thieu browser
// signals that (canvas/webgl/events) -> tra output tho "FNL...". Chrome that
// cung cap day du moi truong -> snapshot token "$..." hop le.
//
// Doc stdin 1 dong JSON: { program, globalName, interpreterUrl, contentBinding }
//   contentBinding = { c: <challenge>, e: <engagementType>, ... }
// In stdout 1 dong JSON: { ok, webResponse } hoac { ok:false, error }

const _err = (...a) => process.stderr.write(a.map(String).join(' ') + '\n');
console.log = _err; console.info = _err; console.warn = _err; console.error = _err;

import puppeteer from 'puppeteer';

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (c) => (data += c));
    process.stdin.on('end', () => resolve(data));
    process.stdin.on('error', reject);
  });
}

async function main() {
  const { program, globalName, interpreterUrl, contentBinding } =
    JSON.parse(await readStdin());

  if (!program || !globalName) throw new Error('Thieu program / globalName');
  if (!contentBinding || !contentBinding.c) throw new Error('Thieu contentBinding.c');

  const interp = interpreterUrl
    ? (interpreterUrl.startsWith('http') ? interpreterUrl : `https:${interpreterUrl}`)
    : null;
  if (!interp) throw new Error('Thieu interpreterUrl');

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled'],
  });
  try {
    const page = await browser.newPage();
    // Origin youtube.com de BotGuard chap nhan (dung trang nhe robots.txt)
    await page.goto('https://www.youtube.com/robots.txt', { waitUntil: 'domcontentloaded', timeout: 30000 });

    // Nap interpreter script (dinh nghia globalName, vd trayride)
    await page.addScriptTag({ url: interp });

    // Chay BotGuardClient logic trong page context (Chrome that).
    // Replicate bgutils: vm.a(program, callback, true, undefined, ()=>{}, [[],[]])
    // -> callback nhan asyncSnapshotFunction -> goi voi contentBinding.
    const webResponse = await page.evaluate(async (globalName, program, contentBinding) => {
      const vm = window[globalName];
      if (!vm || !vm.a) throw new Error('VM (' + globalName + ') khong load');

      const vmFunctions = await new Promise((resolve, reject) => {
        const to = setTimeout(() => reject(new Error('VM init timeout')), 30000);
        try {
          vm.a(program, (asyncSnapshotFunction, shutdownFunction, passEventFunction, checkCameraFunction) => {
            clearTimeout(to);
            resolve({ asyncSnapshotFunction, shutdownFunction, passEventFunction, checkCameraFunction });
          }, true, undefined, () => {}, [[], []]);
        } catch (e) { clearTimeout(to); reject(e); }
      });

      if (!vmFunctions.asyncSnapshotFunction) throw new Error('asyncSnapshotFunction khong co');

      return await new Promise((resolve, reject) => {
        const to = setTimeout(() => reject(new Error('snapshot timeout')), 30000);
        vmFunctions.asyncSnapshotFunction((response) => {
          clearTimeout(to);
          resolve(response);
        }, [contentBinding, undefined, [], undefined]);
      });
    }, globalName, program, contentBinding);

    if (!webResponse) throw new Error('snapshot rong');
    process.stdout.write(JSON.stringify({ ok: true, webResponse }));
  } finally {
    await browser.close();
  }
  process.exit(0);
}

main().catch((err) => {
  process.stdout.write(JSON.stringify({ ok: false, error: String(err && err.message || err) }));
  process.exit(1);
});
