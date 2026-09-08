const fs = require('node:fs');
const ts = require('typescript');
const assert = require('node:assert/strict');
const { test } = require('node:test');
require.extensions['.ts'] = (module, filename) => {
  module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, filename);
};
const { runCommentaryQueue } = require('../src/features/commentary/generation-queue.ts');
const { generateCommentary } = require('../src/api/analyze-field.ts');

test('API helper sends no HTTP request when disabled or cancelled', async () => {
  const previousFetch = global.fetch;
  let calls = 0;
  global.fetch = async () => { calls++; throw new Error('Unexpected fetch'); };
  try {
    await assert.rejects(generateCommentary({}, {}, false), /Enable commentary/);
    const controller = new AbortController();
    controller.abort();
    await assert.rejects(generateCommentary({}, {}, true, undefined, controller.signal), /cancelled/);
    assert.equal(calls, 0);
  } finally {
    global.fetch = previousFetch;
  }
});

test('Off never starts generation', async () => {
  await runCommentaryQueue([1, 2], {
    enabled: () => false, signal: new AbortController().signal,
    generate: () => assert.fail('Must not generate while Off'),
    onReady: () => assert.fail(), onError: () => assert.fail(),
  });
});

for (const cancel of ['off', 'abort']) {
  test(`${cancel} during generation discards late results and stops alternatives`, async () => {
    let enabled = true;
    const controller = new AbortController();
    let finish;
    const calls = [];
    const pending = runCommentaryQueue([1, 2, 3], {
      enabled: () => enabled, signal: controller.signal,
      generate: (plan) => { calls.push(plan); return new Promise(resolve => { finish = resolve; }); },
      onReady: () => assert.fail('Late result must be ignored'), onError: () => assert.fail(),
    });
    if (cancel === 'off') enabled = false;
    else controller.abort();
    finish('late narration');
    await pending;
    assert.deepEqual(calls, [1]);
  });
}

test('enabled queue generates all plans and isolates a failed plan', async () => {
  const ready = [], failed = [];
  await runCommentaryQueue([1, 2, 3], {
    enabled: () => true, signal: new AbortController().signal,
    generate: async (plan) => { if (plan === 2) throw new Error(); return plan; },
    onReady: (plan) => ready.push(plan), onError: (plan) => failed.push(plan),
  });
  assert.deepEqual(ready, [1, 3]);
  assert.deepEqual(failed, [2]);
});
