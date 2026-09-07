const fs = require('node:fs');
const ts = require('typescript');
const assert = require('node:assert/strict');
const { test } = require('node:test');
require.extensions['.ts'] = (module, filename) => {
  module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, filename);
};
const { createFieldConfiguration, createAnimationSession } = require('../src/models/index.ts');
const { advanceAnimationSession } = require('../src/features/animation-playback/animation-engine.ts');

for (const speed of [1, 1.25, 1.5]) {
  test(`batched playback at ${speed}x preserves movements and instantaneous turns`, () => {
    const field = createFieldConfiguration('5v5');
    const player = field.players[0];
    const response = { duration: 2, events: [
      { id: 'move', type: 'MOVE_WITH_BALL', playerId: player.id, startTime: 0, duration: 1, target: { x: 6000, y: 4500 } },
      { id: 'turn', type: 'TURN', playerId: player.id, startTime: 1.01, duration: 0, startOrientation: 0, targetOrientation: 90 },
    ] };
    let expected = createAnimationSession(field, response);
    const snapshots = [expected];
    for (let frame = 1; frame <= 200; frame++) {
      expected = advanceAnimationSession(expected, frame);
      snapshots.push(expected);
    }
    let actual = createAnimationSession(field, response);
    // Include delayed display callbacks; the elapsed-time target catches up.
    for (let milliseconds = 0; actual.currentTime < 200; milliseconds += 37) {
      const frame = Math.min(200, Math.floor(milliseconds * speed / 10));
      if (frame === actual.currentTime) continue;
      actual = advanceAnimationSession(actual, frame);
      assert.deepEqual(actual, snapshots[frame]);
    }
    assert.equal(actual.status, 'completed');
    const replay = advanceAnimationSession(actual, 0);
    assert.equal(replay.currentTime, 0);
    assert.deepEqual(replay.animatedConfiguration.players[0].position, player.position);
  });
}
