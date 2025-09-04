#!/usr/bin/env python3
# extract_and_patch.py
# Usage: python3 extract_and_patch.py site.har [site_root_dir]
# Example: python3 extract_and_patch.py site.har .

import json, os, sys, base64, urllib.parse, re, time

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico")

def safe_write(path, data, binary=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = 'wb' if binary else 'w'
    with open(path, mode) as f:
        f.write(data if binary else data)

def extract_har(har_path, out_dir):
    print("Reading HAR:", har_path)
    with open(har_path, 'r', encoding='utf-8') as f:
        har = json.load(f)
    entries = har.get('log', {}).get('entries', [])
    hosts = set()
    written = 0
    for e in entries:
        req = e.get('request', {})
        url = req.get('url')
        if not url:
            continue
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc
        if host == '':
            continue
        hosts.add(host)
        path = urllib.parse.unquote(parsed.path.lstrip('/'))
        if path == '':
            path = host + '/index.html'

        # 🚫 skip images entirely
        if path.lower().endswith(IMAGE_EXTS):
            continue

        out_path = os.path.join(out_dir, path)
        resp = e.get('response', {})
        content = resp.get('content', {})
        text = content.get('text')
        if text is None:
            status = resp.get('status')
            print(f"SKIP (no body): {url} (status {status})")
            continue
        encoding = content.get('encoding')
        try:
            if encoding == 'base64':
                data = base64.b64decode(text)
                safe_write(out_path, data, binary=True)
            else:
                safe_write(out_path, text, binary=False)
            written += 1
            print("WROTE:", out_path)
        except Exception as ex:
            print("ERROR writing", out_path, ex)
    print(f"\nExtraction complete: wrote {written} non-image files to {out_dir}")
    with open(os.path.join(out_dir, "extracted_hosts.txt"), 'w', encoding='utf-8') as hf:
        hf.write("\n".join(sorted(hosts)))
    return hosts

def patch_index(index_path, hosts, backup=True):
    if not os.path.exists(index_path):
        print("index.html not found at:", index_path)
        return
    with open(index_path, 'r', encoding='utf-8') as f:
        s = f.read()
    if backup:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        bak = index_path + f".bak-{stamp}"
        with open(bak, 'w', encoding='utf-8') as bf:
            bf.write(s)
        print("Backed up index to:", bak)

    def replacer(match):
        url = match.group(1)
        # 🚫 skip images
        if url.lower().endswith(IMAGE_EXTS):
            return match.group(0)
        for host in hosts:
            if host in url:
                return match.group(0).replace(url, './' + url.split(host, 1)[-1].lstrip('/'))
        return match.group(0)

    # patch <script src> and <link href>, but not <img src>
    s = re.sub(r'<script[^>]+src="([^"]+)"', lambda m: replacer(m), s)
    s = re.sub(r'<link[^>]+href="([^"]+)"', lambda m: replacer(m), s)

    # also patch CSS @import
    s = re.sub(r'@import\s+url\(["\']?(https?://[^)]+)["\']?\)', lambda m: '@import url("./' + m.group(1).split("/", 3)[-1] + '")', s)

    # Handle _next/static
    s = re.sub(r'https?://[^/]+/_next/static/', './_next/static/', s)
    s = re.sub(r'//[^/]+/_next/static/', './_next/static/', s)

    # Remove integrity and crossorigin attributes
    s = re.sub(r'\s+integrity="[^"]*"', '', s)
    s = re.sub(r'\s+crossorigin="[^"]*"', '', s)

    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(s)
    print("Patched index.html (scripts & CSS → local, images left on CDN).")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 extract_and_patch.py site.har [site_root_dir]")
        sys.exit(1)
    har_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else '.'
    out_sub = os.path.join(out_dir, 'out_extracted')
    os.makedirs(out_sub, exist_ok=True)
    hosts = extract_har(har_path, out_sub)
    if os.path.abspath(out_sub) != os.path.abspath(out_dir):
        print(f"Copying extracted files from {out_sub} -> {out_dir}")
        for root, dirs, files in os.walk(out_sub):
            for file in files:
                rel = os.path.relpath(os.path.join(root, file), out_sub)
                src = os.path.join(root, file)
                dst = os.path.join(out_dir, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(src, 'rb') as r, open(dst, 'wb') as w:
                    w.write(r.read())
        print("Copy complete.")
    else:
        print("Extraction directory equals target; nothing to copy.")
    index_path = os.path.join(out_dir, 'index.html')
    if not os.path.exists(index_path):
        index_path = 'index.html'
    patch_index(index_path, hosts)

if __name__ == '__main__':
    main()
