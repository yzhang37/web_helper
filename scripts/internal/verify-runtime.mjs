import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { chromium } from 'playwright';

const root = resolve(import.meta.dirname, '../..');
const lockText = readFileSync(resolve(root, 'toolchain.lock.env'), 'utf8');
const lock = Object.fromEntries(
  lockText
    .split('\n')
    .filter((line) => line && !line.startsWith('#'))
    .map((line) => line.split('=', 2)),
);

function requireValue(condition, message) {
  if (!condition) throw new Error(message);
}

requireValue(process.version === `v${lock.WEB_HELPER_NODE_VERSION}`, `expected Node v${lock.WEB_HELPER_NODE_VERSION}; received ${process.version}`);
requireValue(process.env.PLAYWRIGHT_BROWSERS_PATH, 'PLAYWRIGHT_BROWSERS_PATH is not set');
requireValue(process.env.PLAYWRIGHT_BROWSERS_PATH.startsWith(resolve(root, '.runtime')), 'browser path is not private to web_helper/.runtime');
requireValue(process.env.npm_config_cache?.startsWith(resolve(root, '.runtime')), 'npm cache is not private to web_helper/.runtime');

const systemCurl = process.env.WEB_HELPER_SYSTEM_CURL;
requireValue(systemCurl === '/usr/bin/curl', `expected host curl path /usr/bin/curl; received ${systemCurl ?? 'none'}`);
requireValue(existsSync(systemCurl), `system curl is missing: ${systemCurl}`);
const curl = spawnSync(systemCurl, ['--version'], { encoding: 'utf8' });
requireValue(curl.status === 0, 'system curl did not run');
const curlVersion = curl.stdout.match(/^curl\s+(\S+)/m)?.[1];
requireValue(curlVersion, 'system curl did not report a version');

const crawleeVersion = JSON.parse(readFileSync(resolve(root, 'node_modules/crawlee/package.json'), 'utf8')).version;
const playwrightVersion = JSON.parse(readFileSync(resolve(root, 'node_modules/playwright/package.json'), 'utf8')).version;
requireValue(crawleeVersion === lock.WEB_HELPER_CRAWLEE_VERSION, `expected crawlee ${lock.WEB_HELPER_CRAWLEE_VERSION}; received ${crawleeVersion}`);
requireValue(playwrightVersion === lock.WEB_HELPER_PLAYWRIGHT_VERSION, `expected playwright ${lock.WEB_HELPER_PLAYWRIGHT_VERSION}; received ${playwrightVersion}`);

const executablePath = chromium.executablePath();
requireValue(executablePath.startsWith(process.env.PLAYWRIGHT_BROWSERS_PATH), `Chromium is not in the private browser path: ${executablePath}`);
requireValue(existsSync(executablePath), `Chromium binary is missing: ${executablePath}`);
const browser = await chromium.launch({ headless: true });
await browser.close();

console.log(JSON.stringify({
  node: process.version,
  npm: spawnSync('npm', ['--version'], { encoding: 'utf8' }).stdout.trim(),
  curl: curlVersion,
  curlPath: systemCurl,
  crawlee: crawleeVersion,
  playwright: playwrightVersion,
  chromiumExecutable: executablePath,
  browserPath: process.env.PLAYWRIGHT_BROWSERS_PATH,
  targetWebsiteRequests: 0,
}, null, 2));
