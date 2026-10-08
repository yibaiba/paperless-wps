import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const ASSET_DIR = new URL("../dist/assets/", import.meta.url);
const SHEET_SOURCE_DIR = new URL("../src/features/configuration/quotation/sheet/", import.meta.url);
const MAX_SHEET_JS_BYTES = 7_000_000;
const MAX_SHEET_CSS_BYTES = 130_000;

const assets = readdirSync(ASSET_DIR);
const sheetJavaScript = oneAsset(assets, /^QuotationSheet-.*\.js$/);
const sheetStyles = oneAsset(assets, /^QuotationSheet-.*\.css$/);
const jsBytes = statSync(new URL(sheetJavaScript, ASSET_DIR)).size;
const cssBytes = statSync(new URL(sheetStyles, ASSET_DIR)).size;

assert.ok(jsBytes <= MAX_SHEET_JS_BYTES, `报价工作表 JS ${jsBytes} 超过预算 ${MAX_SHEET_JS_BYTES}`);
assert.ok(cssBytes <= MAX_SHEET_CSS_BYTES, `报价工作表 CSS ${cssBytes} 超过预算 ${MAX_SHEET_CSS_BYTES}`);

const source = sourceFiles(SHEET_SOURCE_DIR).map((file) => readFileSync(file, "utf8")).join("\n");
assert.doesNotMatch(source, /@univerjs\/pro/, "报价工作表不得引入 Univer Pro 插件");
const localeImports = [...source.matchAll(/@univerjs\/[^'\"]+\/locales\/([^'\"]+)/g)].map((match) => match[1]);
assert.deepEqual([...new Set(localeImports)], ["zh-CN"], "报价工作表只能显式引入中文语言包");

console.log(JSON.stringify({ sheetJavaScript, jsBytes, sheetStyles, cssBytes, localeImports: ["zh-CN"] }));

function oneAsset(files, pattern) {
  const matches = files.filter((file) => pattern.test(file));
  assert.equal(matches.length, 1, `预期一个 ${pattern} 构建产物，实际为 ${matches.join(", ") || "无"}`);
  return matches[0];
}

function sourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory.pathname, entry.name);
    return entry.isDirectory() ? sourceFiles(new URL(`${entry.name}/`, directory)) : /\.tsx?$/.test(entry.name) ? [path] : [];
  });
}
