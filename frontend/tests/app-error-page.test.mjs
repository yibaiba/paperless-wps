import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = readFileSync(new URL('../src/AppErrorPage.tsx', import.meta.url), 'utf8');
const js = ts.transpileModule(source, {
  compilerOptions: {
    jsx: ts.JsxEmit.ReactJSX,
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const exports = {};
vm.runInNewContext(js, {
  exports,
  Error,
  require(name) {
    if (name === 'react/jsx-runtime') return { jsx() {}, jsxs() {} };
    if (name === 'antd') return {};
    if (name === 'react-router-dom') return {
      isRouteErrorResponse: (error) => Boolean(error?.routeResponse),
      useRouteError() {},
    };
    throw new Error(`unexpected module: ${name}`);
  },
});

test('application error page keeps route and runtime failures visible', () => {
  assert.equal(exports.errorMessage(new Error('真实运行错误')), '真实运行错误');
  assert.equal(
    exports.errorMessage({ routeResponse: true, status: 404, statusText: 'Not Found' }),
    '404 Not Found',
  );
  assert.equal(exports.errorMessage(undefined), '未知页面错误');
});
