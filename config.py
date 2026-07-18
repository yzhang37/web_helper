# WebHelper 抓取指纹的单一来源。curl 腿与浏览器腿都从这里取,别再各写一份。
CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)
ACCEPT_LANGUAGE = "en-US,en;q=0.9"
REFERER = "https://www.google.com/"

# 浏览器腿专用:client-hints 元数据。用 CDP override 才能让 sec-ch-ua 和
# navigator.userAgentData 都跟 UA 一致(否则默认露 HeadlessChrome)。curl 用不到。
UA_METADATA = {
    "brands": [
        {"brand": "Google Chrome", "version": "149"},
        {"brand": "Chromium", "version": "149"},
        {"brand": "Not)A;Brand", "version": "24"},
    ],
    "fullVersion": "149.0.0.0",
    "platform": "macOS",
    "platformVersion": "10_15_7",
    "architecture": "x86",
    "model": "",
    "mobile": False,
}
