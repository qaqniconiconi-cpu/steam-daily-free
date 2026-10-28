const test = require('node:test');
const assert = require('node:assert/strict');
require('../admin/publish-core.js');
const core = globalThis.EtAdminPublish;
const now = Date.parse('2026-10-28T08:00:00Z');
const manager = (add = [], disable = [], sort = []) => ({ add, disable, sort });
const live = () => ({
  'games.json': [
    { steam_id: '123', zh_title: 'Original', short_description: 'Description', thumbnail: 'image', end_date: '2030-01-01T00:00:00Z', original_price: '$10', custom_metadata: { keep: true } },
    { steam_id: '1234', zh_title: 'Unrelated', end_date: '2030-01-01T00:00:00Z' },
  ],
  'intel.json': { to_paid: [], freeplay: [], other_info: { preserve: true } },
  'deals.json': [{ id: '99', name: 'Deal', screenshots: ['one', 'two'], reviewPercent: 90 }],
});

test('editing a title preserves untouched fields and other games', () => {
  const input = live();
  const result = core.applyManager(input, manager([{ link: 'https://store.steampowered.com/app/123/Name', name: 'New name' }]), manager(), now);
  const game = result['games.json'].find(item => item.steam_id === '123');
  assert.equal(game.zh_title, 'New name');
  assert.equal(game.thumbnail, 'image');
  assert.deepEqual(game.custom_metadata, { keep: true });
  assert.deepEqual(result['deals.json'], input['deals.json']);
  assert.deepEqual(result['intel.json'].other_info, { preserve: true });
  assert.equal(input['games.json'][0].zh_title, 'Original');
});

test('blacklist normalizes official URLs without partial App ID matches', () => {
  const result = core.applyManager(live(), manager([], ['https://store.steampowered.com/app/123/Name']), manager(), now);
  assert.deepEqual(result['games.json'].map(item => item.steam_id), ['1234']);
  assert.equal(core.identity('https://store.epicgames.com/zh-CN/p/mafia-hotel-eaea4c?lang=zh-CN'), 'p/mafia-hotel-eaea4c');
});

test('banning a deal preserves the remaining deal records', () => {
  const input = live();
  input['deals.json'].push({ id: '999', name: 'Keep deal', screenshots: ['keep'] });
  const result = core.applyManager(input, manager([], ['app/99']), manager(), now);
  assert.deepEqual(result['deals.json'], [input['deals.json'][1]]);
});

test('new game and type changes route into the correct file without duplication', () => {
  const result = core.applyManager(live(), manager([
    { link: 'app/123', type: 'freeplay', name: 'Trial' },
    { link: 'p/sorry-were-closed-724c86', name: '即将免费', type: 'upcoming', end_date: '2030-01-01T00:00:00Z' },
  ]), manager(), now);
  assert.equal(result['games.json'].some(item => item.steam_id === '123'), false);
  assert.equal(result['intel.json'].freeplay[0].steam_id, '123');
  const upcoming = result['games.json'].find(item => item.epic_slug);
  assert.equal(upcoming.is_upcoming, true);
  assert.equal(upcoming.type, 'upcoming');
});

test('expired records and removed manual games are removed immediately', () => {
  const input = live();
  input['games.json'].push({ epic_slug: 'expired', end_date: '2026-10-28T04:00:00+08:00' });
  const result = core.applyManager(input, manager(), manager([{ link: 'app/123' }]), now);
  assert.deepEqual(result['games.json'].map(item => item.steam_id), ['1234']);
});

test('removed bans can restore a complete saved rule', () => {
  const input = live();
  const rule = { link: 'app/555', name: 'Restored', desc: 'Kept', thumbnail: 'cover', end_date: '2030-01-01T00:00:00Z' };
  const hidden = core.applyManager(input, manager([rule], ['app/555']), manager(), now);
  assert.equal(hidden['games.json'].some(item => item.steam_id === '555'), false);
  const restored = core.applyManager(hidden, manager([rule]), manager([rule], ['app/555']), now);
  assert.equal(restored['games.json'].find(item => item.steam_id === '555').short_description, 'Kept');
});

test('sorting is applied and clearing a previous rule removes the stored order', () => {
  let result = core.applyManager(live(), manager([], [], [{ link: 'app/1234', sort_order: 0 }]), manager(), now);
  assert.equal(result['games.json'][0].steam_id, '1234');
  result = core.applyManager(result, manager(), manager([], [], [{ link: 'app/1234', sort_order: 0 }]), now);
  assert.equal(Object.hasOwn(result['games.json'].find(item => item.steam_id === '1234'), 'sort_order'), false);
});

test('explicitly clearing manual date and sort takes effect immediately', () => {
  const input = live();
  input['games.json'][0].sort_order = 1;
  const result = core.applyManager(input, manager([{ link: 'app/123', end_date: '', sort_order: '' }]), manager(), now);
  const game = result['games.json'].find(item => item.steam_id === '123');
  assert.equal(game.end_date, '限免进行中');
  assert.equal(Object.hasOwn(game, 'sort_order'), false);
});

test('incomplete live data and invalid manual games fail before publication', () => {
  assert.throws(() => core.applyManager({ 'games.json': [], 'intel.json': {} }, manager()), /不完整/);
  assert.throws(() => core.applyManager(live(), manager([{ link: 'p/new-game' }]), manager(), now), /展示标题/);
  assert.throws(() => core.applyManager(live(), manager([{ link: 'app/123', end_date: 'not a date' }]), manager(), now), /截止时间/);
});

function options(overrides = {}) {
  let data = live();
  const calls = [];
  return Object.assign({
    calls,
    expectedSha: 'original-sha',
    manager: manager([{ link: 'app/123', name: 'Updated' }]),
    previousManager: manager(),
    readManager: async () => ({ sha: 'original-sha' }),
    readLive: async () => structuredClone(data),
    checkpoint: () => calls.push('checkpoint'),
    syncManager: async () => calls.push('github'),
    readFile: async file => structuredClone(data[file]),
    writeFile: async (file, body) => { calls.push(file); data[file] = structuredClone(body); },
  }, overrides);
}

test('GitHub conflict prevents all writes', async () => {
  const opts = options({ readManager: async () => ({ sha: 'new-sha' }) });
  await assert.rejects(core.publish(opts), /GitHub 配置已被/);
  assert.deepEqual(opts.calls, []);
});

test('only changed live files are published after GitHub succeeds', async () => {
  const opts = options();
  const result = await core.publish(opts);
  assert.deepEqual(result.files, ['games.json']);
  assert.deepEqual(opts.calls, ['checkpoint', 'github', 'games.json']);
});

test('GitHub save failure prevents live writes', async () => {
  const opts = options({ syncManager: async () => { throw new Error('GitHub denied'); } });
  await assert.rejects(core.publish(opts), error => !error.githubSaved && error.message === 'GitHub denied');
  assert.deepEqual(opts.calls, ['checkpoint']);
});

test('partial publication reports progress and preserves retry state', async () => {
  const opts = options({
    manager: manager([{ link: 'app/123', name: 'Trial', type: 'freeplay' }]),
    writeFile: async file => {
      opts.calls.push(file);
      if (file === 'intel.json') throw new Error('Network failed');
    },
  });
  await assert.rejects(core.publish(opts), error => error.githubSaved && error.publishedFiles.join() === 'games.json');
  assert.deepEqual(opts.calls, ['checkpoint', 'github', 'games.json', 'intel.json']);
});

test('concurrent live update is detected before overwriting it', async () => {
  const opts = options({ readFile: async () => [] });
  await assert.rejects(core.publish(opts), /刚刚发生变化/);
  assert.deepEqual(opts.calls, ['checkpoint', 'github']);
});
