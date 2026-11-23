#!/usr/bin/env node
// assets/app を1ファイルのHTMLにまとめる（ダブルクリックで開ける配布用）。
// 実行: node scripts/build_single_html.js [出力パス]   既定: dist/nencho-app.html
const fs = require('fs');
const path = require('path');
const app = path.join(__dirname, '../assets/app');
const outPath = process.argv[2] || path.join(__dirname, '../dist/nencho-app.html');

let html = fs.readFileSync(path.join(app, 'index.html'), 'utf8');
html = html.replace(/<link rel="stylesheet" href="([^"]+)">/g, (_, href) =>
  `<style>\n${fs.readFileSync(path.join(app, href), 'utf8')}</style>`);
html = html.replace(/<script src="(js\/[^"]+)"><\/script>/g, (_, src) =>
  `<script>\n${fs.readFileSync(path.join(app, src), 'utf8').replace(/<\/script/gi, '<\\/script')}</script>`);
fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, html);
console.log(`built ${outPath} (${(html.length / 1024).toFixed(1)} KB)`);
