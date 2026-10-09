import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const workbench = readFileSync(new URL('../src/Workbench.tsx', import.meta.url), 'utf8');
const projects = readFileSync(
  new URL('../src/features/projects/ProjectsPage.tsx', import.meta.url),
  'utf8',
);

test('primary navigation groups the supported presales workflow', () => {
  for (const label of ['产品与价格', '系统与搭配知识', '售前项目', '资料维护']) {
    assert.match(workbench, new RegExp(label));
  }
  assert.match(workbench, /高级与历史/);
  assert.match(workbench, /children:[\s\S]*旧配套规则[\s\S]*独立拓扑/);
});

test('project creation and list entry open the unified configuration', () => {
  assert.match(projects, /navigate\(`\/configuration\/\$\{result\.id\}`\)/);
  assert.match(projects, /navigate\(`\/configuration\/\$\{project\.id\}`\)/);
  assert.match(projects, /进入售前配置/);
});
