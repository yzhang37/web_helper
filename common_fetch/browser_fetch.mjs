#!/usr/bin/env node
// WebHelper — browser leg (step 5).
//
// This is the browser fallback the Python main controller (web_helper.py)
// calls when curl is not enough. It does exactly one thing: take a single
// request, render/fetch it in Chromium, and return the result as JSON.
//
// It does NOT own the six-function main logic, does NOT do curl, does NOT
// cache, and does NOT run a whole-site crawl. It uses Crawlee's BrowserPool
// (a "part", not the crawler.run() main loop) with the project-private
// Playwright/Chromium runtime. Run it through scripts/internal/run-with-runtime.sh so
// PATH / PLAYWRIGHT_BROWSERS_PATH / private state all point at web_helper/.runtime/.
//
// I/O contract
// ------------
// Input: one JSON object from argv[2], or stdin when argv[2] is "-" / absent.
// {
//   "url":          "https://...",            // required
//   "method":       "GET",                    // optional, default GET
//   "body":         "...",                    // optional, for non-GET requests
//   "headers":      {"k":"v"} | [["k","v"]],  // optional caller headers
//   "storageState": { cookies, origins },     // optional Playwright session
//   "timeoutMs":    40000                     // optional per-request timeout
// }
//
// Output: exactly one JSON object on stdout.
// {
//   "StatusCode":      200 | 404 | 500 | null,
//   "StatusCodeText":  "OK" | "Not Found" | "",
//   "FinalURL":        "https://...",
//   "ResponseHeaders": [["name","value"], ...],
//   "ContentType":     "text/html; charset=utf-8",
//   "Content":         "...",
//   "storageState":    { cookies, origins } | null,
//   "error":           null | "message"
// }
//
// StatusCode != null means Chromium/Playwright got an HTTP response. HTTP 4xx/5xx
// are still successful fetch results here; they are not helper errors.
// StatusCode == null means no HTTP response was obtained, and error explains why
// (navigation timeout, bad input, browser/helper failure, unreachable target, etc.).
//
// Content routing:
//   HTML           -> rendered DOM after JS runs (page.content()).
//   JSON/XML/other -> raw response body (response.text()), never Chromium's viewer.

import process from 'node:process';
import { BrowserPool, PlaywrightPlugin } from 'crawlee';
import { chromium } from 'playwright';

// Chrome fingerprint 的单一来源是 Python 的 config.py。.mjs 进不了 Python,
// 所以 browser_fetch.py 在 spawn 时把同一份指纹序列化成 JSON 塞进
// WEB_HELPER_FINGERPRINT 环境变量,这里解析回来(Option A)。
const FP = JSON.parse(process.env.WEB_HELPER_FINGERPRINT || '{}');
// FP.ua, FP.accept_language, FP.referer, FP.ua_metadata
// sec-ch-ua 头由 client-hints brands 拼出,和 UA 保持一致(否则默认露 HeadlessChrome)。
const SEC_CH_UA = (FP.ua_metadata?.brands || [])
    .map((b) => `"${b.brand}";v="${b.version}"`)
    .join(', ');

const VIEWPORT = { width: 1280, height: 900 };
const LOCALE = 'en-US';
const LAUNCH_ARGS = ['--disable-blink-features=AutomationControlled'];
const WEBDRIVER_PATCH = () =>
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

async function readInput() {
    const arg = process.argv[2];
    if (arg && arg !== '-') return JSON.parse(arg);
    const chunks = [];
    for await (const chunk of process.stdin) chunks.push(chunk);
    const text = Buffer.concat(chunks).toString('utf8').trim();
    if (!text) throw new Error('no input JSON on argv[2] or stdin');
    return JSON.parse(text);
}

// Accept a header object or an array of [name, value] pairs; return a plain object.
function normalizeHeaders(h) {
    if (!h) return {};
    const entries = Array.isArray(h) ? h : Object.entries(h);
    const out = {};
    for (const [k, v] of entries) {
        if (k == null) continue;
        out[String(k)] = String(v);
    }
    return out;
}

function pairsFromHeadersArray(headersArray) {
    return headersArray.map(({ name, value }) => [name, value]);
}

function contentTypeOf(headersArray) {
    for (const { name, value } of headersArray) {
        if (name.toLowerCase() === 'content-type') return value || '';
    }
    return '';
}

function isHtmlContentType(ct) {
    const c = (ct || '').toLowerCase();
    return c.includes('text/html') || c.includes('application/xhtml');
}

function errorResult(url, message) {
    return {
        StatusCode: null,
        StatusCodeText: '',
        FinalURL: url || '',
        ResponseHeaders: [],
        ContentType: '',
        Content: '',
        storageState: null,
        error: message,
    };
}

async function fetchViaNavigation(page, url, timeout) {
    // CDP Emulation.setUserAgentOverride 是唯一能同时修好 HTTP 头 (sec-ch-ua) 和
    // JS 侧 (navigator.userAgentData) 的办法 —— 只设 extraHTTPHeaders 会让 JS 侧
    // 继续露 HeadlessChrome。
    // 不在这里给 acceptLanguage:实测 CDP 的 acceptLanguage 会把 'en-US,en;q=0.9'
    // 重新序列化成 'en-US,en;q=0.9;q=0.9'(把 'en;q=0.9' 当语言再补一个 q)。
    // Accept-Language 改由 extraHTTPHeaders 逐字下发(见 run() 的 pageOptions)。
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Emulation.setUserAgentOverride', {
        userAgent: FP.ua,
        userAgentMetadata: FP.ua_metadata,
    });

    let response = null;
    let navError = null;
    try {
        // domcontentloaded gives us the main response quickly (incl. status/headers);
        // for HTML we then wait for the network to settle so JS can render.
        response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout });
    } catch (err) {
        navError = err;
    }

    if (!response) {
        return errorResult(page.url() || url, navError ? navError.message : 'navigation returned no response');
    }

    const headersArray = await response.headersArray();
    const ct = contentTypeOf(headersArray);
    const status = response.status();
    const statusText = response.statusText();

    let content;
    if (isHtmlContentType(ct)) {
        // Let JS-driven content render, bounded so a chatty page can't hang us.
        await page.waitForLoadState('networkidle', { timeout: Math.min(timeout, 15000) }).catch(() => {});
        await page.waitForTimeout(500);
        content = await page.content(); // rendered DOM
    } else {
        // JSON / XML / anything else -> raw body, NOT the Chromium <pre> viewer.
        content = await response.text().catch(() => '');
    }

    return {
        StatusCode: status,
        StatusCodeText: statusText,
        FinalURL: page.url(),
        ResponseHeaders: pairsFromHeadersArray(headersArray),
        ContentType: ct,
        Content: content,
        storageState: null, // run 中会统一填写
        error: null,
    };
}

async function fetchViaApiRequest(ctx, url, method, body, callerHeaders, timeout) {
    // ctx.request.fetch 是 raw API request,不是页面导航,CDP override 不生效 ——
    // 所以 UA / Accept-Language / Referer / client-hints 全部在 header 里显式给。
    const headers = {
        'Accept-Language': FP.accept_language,
        Referer: FP.referer,
        'sec-ch-ua': SEC_CH_UA,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': `"${FP.ua_metadata?.platform || 'macOS'}"`,
        ...callerHeaders,
        'user-agent': FP.ua,
    };
    const options = { method, headers, timeout, maxRedirects: 20 };
    if (body != null) {
        options.data = typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body);
    }

    let response = null;
    let reqError = null;
    try {
        // context.request shares this browser context's cookies/session.
        response = await ctx.request.fetch(url, options);
    } catch (err) {
        reqError = err;
    }

    if (!response) {
        return errorResult(url, reqError ? reqError.message : 'request returned no response');
    }

    const headersArray = await response.headersArray();
    const ct = contentTypeOf(headersArray);
    const status = response.status();
    const statusText = response.statusText();
    // APIRequestContext never wraps bodies, so text() is always the raw body.
    const content = await response.text().catch(() => '');

    return {
        StatusCode: status,
        StatusCodeText: statusText,
        FinalURL: response.url(),
        ResponseHeaders: pairsFromHeadersArray(headersArray),
        ContentType: ct,
        Content: content,
        storageState: null, // run 中会统一填写
        error: null,
    };
}

async function run(input) {
    const url = input && input.url;
    if (!url || typeof url !== 'string') return errorResult(url, 'missing required "url"');

    const method = String(input.method || 'GET').toUpperCase();
    const timeout = Number(input.timeoutMs) > 0 ? Number(input.timeoutMs) : 40000;
    const callerHeaders = normalizeHeaders(input.headers);
    const storageState = input.storageState || undefined;

    const pageOptions = {
        // 不设 context userAgent:GET 走 CDP override,POST 在 header 里显式给 UA。
        // 不设 locale:实测 locale('en-US') 会让 Playwright 另发一次
        // setUserAgentOverride,把 Accept-Language 搅成 'en-US,en;q=0.9;q=0.9',
        // 还会盖掉 CDP 设的 client-hints metadata。
        // Accept-Language 逐字放进 extraHTTPHeaders(CDP acceptLanguage 会重复 q 值),
        // Referer + 调用方头也在这里。
        viewport: VIEWPORT,
        extraHTTPHeaders: {
            'Accept-Language': FP.accept_language,
            Referer: FP.referer,
            ...callerHeaders,
        },
    };
    if (storageState) pageOptions.storageState = storageState;

    const pool = new BrowserPool({
        // 关键:BrowserPool 默认 useFingerprints:true,会生成一份随机指纹经
        // fingerprintInjector 注入(自带 CDP setUserAgentOverride + initScript),
        // 把我们上面 CDP 设的 UA_METADATA 冲掉 —— 结果 sec-ch-ua 和
        // navigator.userAgentData 都露出浏览器原生 Chromium 版本(和我们的 UA 串对不上)。
        // 关掉它,让 config.py 的指纹成为唯一来源。
        useFingerprints: false,
        browserPlugins: [
            new PlaywrightPlugin(chromium, {
                // incognito pages let per-request context options (UA, viewport,
                // storageState, headers) actually apply.
                useIncognitoPages: true,
                launchOptions: { headless: true, args: LAUNCH_ARGS },
            }),
        ],
    });

    let page;
    let result;
    try {
        page = await pool.newPage({ pageOptions });
        const ctx = page.context();
        // Hide the automation flag before we navigate.
        await ctx.addInitScript(WEBDRIVER_PATCH);

        if (method === 'GET') {
            result = await fetchViaNavigation(page, url, timeout);
        } else {
            result = await fetchViaApiRequest(ctx, url, method, input.body, callerHeaders, timeout);
        }

        // Hand the (possibly updated) cookies/session back for Python to persist.
        try {
            result.storageState = await ctx.storageState();
        } catch (err) {
            result.storageState = null;
        }
    } catch (err) {
        result = errorResult(url, err && err.message ? err.message : String(err));
        result.storageState = null;
    } finally {
        try {
            if (page) await page.close();
        } catch {}
        try {
            await pool.destroy();
        } catch {}
    }

    return result;
}

async function main() {
    let input;
    try {
        input = await readInput();
    } catch (err) {
        process.stdout.write(JSON.stringify({ ...errorResult('', `bad input: ${err.message}`), storageState: null }));
        process.exitCode = 0;
        return;
    }
    const result = await run(input);
    process.stdout.write(JSON.stringify(result));
    process.exitCode = 0;
}

main().catch((err) => {
    process.stdout.write(JSON.stringify({ ...errorResult('', err && err.message ? err.message : String(err)), storageState: null }));
    process.exitCode = 1;
});
